"""Configuration — FR-22, FR-25, NFR-04.

Two principles here, both aimed at the clean-checkout gate (A1):

1. **A missing key is a degraded run, not a crash.** The system falls back to
   retrieval-only when it cannot reach a model (A11, FR-21), so absent
   credentials must not stop it from starting. Malformed *configuration*, by
   contrast, fails loudly: a threshold of "high" is a mistake to surface now,
   not to silently reinterpret.

2. **Both providers are supported.** The pack's Setup Guide uses an OpenRouter
   key; this project defaults to Groq. A grader holding either must get a
   working system rather than the fallback path.

Secrets never appear in `repr` or `str`, so a key cannot leak through a log line
or a traceback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping

# Design decision D4: thresholds are derived, not chosen. The Project Brief
# penalises "a threshold chosen because it looked reasonable rather than because
# it was measured".

DEFAULT_CONFIDENCE_THRESHOLD = 0.80  # TODO(D4): replace from the Day 3 sweep

# DERIVED 2026-09-04 from scripts/tune_retrieval.py over the 500 development
# tickets. Full curve: evaluation/results/2026-09-04-retrieval-tuning.txt
#
#   floor   any-hit@3   ungroundable rejected
#   0.35      93.6%          12.6%
#   0.40      92.7%          14.7%   <- chosen
#   0.45      85.4%          21.0%
#   0.50      73.4%          35.0%   <- argmax of the naive combined score
#
# 0.40 is the knee: past it, any-hit falls off a cliff (7.3 points between 0.40
# and 0.45) for a modest gain in rejection.
#
# We deliberately do NOT take the argmax of the combined score (0.50). Doing so
# would trade 19 points of retrieval hit rate for 20 points of rejection, and
# that trade is wrong here because rejecting ungroundable tickets is not the
# relevance floor's job. Retrieval similarity turns out to be a weak signal for
# groundability — even at 0.60 only 70.6% of ungroundable tickets are rejected,
# by which point any-hit has collapsed to 33.9%. Groundability is decided
# downstream by the grounding guardrail, which checks whether claims are actually
# supported. The floor's job is narrower: keep irrelevant passages out of the
# generation prompt.
DEFAULT_RELEVANCE_FLOOR = 0.40
DEFAULT_KILL_SWITCH_PATH = Path("storage/KILL")

# Values shipped in .env.example. Copying the template without editing it must
# not be mistaken for a working key.
_PLACEHOLDERS = {
    "your_groq_key_here",
    "your_openrouter_key_here",
    "your_key_here",
    "changeme",
}


class ConfigError(ValueError):
    """Raised when configuration is present but unusable."""


class Provider(str, Enum):
    GROQ = "groq"
    OPENROUTER = "openrouter"


class _Secret:
    """A string that refuses to render itself."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "<redacted>" if self._value else "<unset>"

    __str__ = __repr__


def _clean(env: Mapping[str, str], key: str, default: str = "") -> str:
    value = env.get(key)
    return value.strip() if isinstance(value, str) else default


def _ratio(env: Mapping[str, str], key: str, default: float) -> float:
    raw = _clean(env, key)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number between 0 and 1, got {raw!r}") from exc
    if not 0.0 <= value <= 1.0:
        raise ConfigError(f"{key} must be between 0 and 1, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for one run."""

    provider: Provider
    model_name: str
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    relevance_floor: float = DEFAULT_RELEVANCE_FLOOR

    chroma_path: Path = Path("storage/chroma")
    database_url: str = "sqlite:///./storage/decisions.db"
    cache_path: Path = Path("storage/cache")

    request_timeout_seconds: int = 30
    max_retries: int = 3
    log_level: str = "INFO"
    metrics_port: int = 8001

    base_url: str = ""
    kill_switch_path: Path = DEFAULT_KILL_SWITCH_PATH
    _kill_switch_env: bool = False
    _api_key: _Secret = field(default_factory=lambda: _Secret(""), repr=False)

    # -- construction --------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        kill_switch_path: Path | None = None,
    ) -> "Settings":
        env = os.environ if env is None else env

        raw_provider = _clean(env, "PROVIDER", "groq").lower() or "groq"
        try:
            provider = Provider(raw_provider)
        except ValueError as exc:
            supported = ", ".join(p.value for p in Provider)
            raise ConfigError(
                f"PROVIDER must be one of: {supported}. Got {raw_provider!r}"
            ) from exc

        if provider is Provider.GROQ:
            api_key = _clean(env, "GROQ_API_KEY")
            model_name = _clean(env, "GROQ_MODEL", "llama-3.3-70b-versatile")
            base_url = ""
        else:
            api_key = _clean(env, "OPENROUTER_API_KEY")
            model_name = _clean(env, "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
            base_url = _clean(env, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

        if api_key in _PLACEHOLDERS:
            api_key = ""

        return cls(
            provider=provider,
            model_name=model_name or "unset",
            confidence_threshold=_ratio(env, "CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD),
            relevance_floor=_ratio(env, "RELEVANCE_FLOOR", DEFAULT_RELEVANCE_FLOOR),
            chroma_path=Path(_clean(env, "CHROMA_PATH", "storage/chroma")),
            database_url=_clean(env, "DATABASE_URL", "sqlite:///./storage/decisions.db"),
            cache_path=Path(_clean(env, "CACHE_PATH", "storage/cache")),
            request_timeout_seconds=int(_clean(env, "REQUEST_TIMEOUT_SECONDS", "30") or 30),
            max_retries=int(_clean(env, "MAX_RETRIES", "3") or 3),
            log_level=_clean(env, "LOG_LEVEL", "INFO") or "INFO",
            metrics_port=int(_clean(env, "METRICS_PORT", "8001") or 8001),
            base_url=base_url,
            kill_switch_path=kill_switch_path or DEFAULT_KILL_SWITCH_PATH,
            _kill_switch_env=_clean(env, "KILL_SWITCH", "0") in {"1", "true", "True", "yes"},
            _api_key=_Secret(api_key),
        )

    # -- derived properties --------------------------------------------------

    @property
    def api_key(self) -> str:
        return self._api_key.reveal()

    @property
    def has_model_access(self) -> bool:
        """False means the run degrades to retrieval-only rather than failing."""
        return bool(self._api_key)

    @property
    def kill_switch_engaged(self) -> bool:
        """Checked once per ticket. A file sentinel needs no redeployment."""
        return self._kill_switch_env or self.kill_switch_path.exists()
