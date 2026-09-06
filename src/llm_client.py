"""Model access — A5, A11, FR-14, FR-21, FR-25, and decisions D5 and D-10.

Three requirements meet in this file, and the design follows from holding all
three at once.

**Determinism (A5).** `temperature=0` plus a content-addressed cache keyed on the
model, the system prompt, the user text and the parameters. The same ticket
therefore produces the same routing decision, and a recorded demonstration run
can be replayed exactly.

**Resilience (A11).** No provider failure escapes this module. A timeout, a 429,
a total outage, or an exception nobody predicted all resolve to a
`CompletionResult` with `ok=False`. A9 requires the unattended run to continue
through everything, so a raised exception here would be a failure of the gate,
not merely of one ticket.

**Prompt integrity (FR-14).** The system instructions and the customer's text are
passed as separate messages and never concatenated, so ticket content cannot
overwrite the instructions by construction rather than by hoping the model
ignores it.

**Failures are never cached.** Caching an outage would make a transient provider
problem permanent for the rest of the run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.config import Provider, Settings


class ProviderError(Exception):
    """Base class for anything the provider does that we must survive."""


class ProviderTimeout(ProviderError):
    """The provider did not answer in time."""


class ProviderRateLimited(ProviderError):
    """Free-tier throttling. Expected, and handled with backoff."""


class ProviderUnavailable(ProviderError):
    """The provider could not be reached at all."""


class ProviderConfigError(ProviderError):
    """The request is wrong and will never succeed: bad key, missing model.

    Deliberately NOT retried. Discovered live: a stale model name produced three
    identical 404s and two backoff sleeps before reporting a failure that was
    certain from the first attempt. Over a 120-ticket unattended run that wastes
    free-tier allowance and triples the time to discover a misconfiguration.
    """


@dataclass
class CompletionResult:
    """The outcome of one completion request. Never an exception."""

    text: str = ""
    ok: bool = False
    from_cache: bool = False
    attempts: int = 0
    error: str | None = None


@dataclass
class CallStats:
    """Per-run counters.

    `degraded` is the flag decision D-10 requires: a misconfigured run and a very
    conservative working system produce identical output, so an escalation rate
    must never be reported without saying whether the model was reachable.
    `attempted` and `succeeded` are what make the F7 throughput budget computable.
    """

    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    cache_hits: int = 0
    retries: int = 0
    degraded: bool = False


class _DiskCache:
    """Content-addressed JSON cache. One file per request signature."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def _file(self, key: str) -> Path:
        return self.path / f"{key}.json"

    def get(self, key: str) -> str | None:
        file = self._file(key)
        if not file.exists():
            return None
        try:
            return json.loads(file.read_text(encoding="utf-8"))["text"]
        except (ValueError, KeyError, OSError):  # pragma: no cover - corrupt entry
            return None

    def put(self, key: str, text: str) -> None:
        try:
            self._file(key).write_text(
                json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:  # pragma: no cover - a cache miss is survivable
            pass


def _default_transport(
    *, provider: Provider, api_key: str, base_url: str, timeout: int, **kwargs
) -> str:
    """Call the real provider. Imported lazily so tests never need the SDK."""
    import httpx

    url = (
        "https://api.groq.com/openai/v1/chat/completions"
        if provider is Provider.GROQ
        else f"{base_url.rstrip('/')}/chat/completions"
    )
    payload = {
        "model": kwargs["model"],
        "temperature": kwargs["temperature"],
        "max_tokens": kwargs["max_tokens"],
        "messages": [
            {"role": "system", "content": kwargs["system"]},
            {"role": "user", "content": kwargs["user"]},
        ],
    }

    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise ProviderTimeout(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(str(exc)) from exc

    if response.status_code == 429:
        raise ProviderRateLimited("rate limited by provider")
    if response.status_code >= 500:
        raise ProviderUnavailable(f"provider returned {response.status_code}")
    if response.status_code >= 400:
        # 400/401/403/404 mean the request itself is wrong. Retrying cannot help.
        raise ProviderConfigError(
            f"provider returned {response.status_code}: {response.text[:200]}"
        )

    return response.json()["choices"][0]["message"]["content"]


class LLMClient:
    """Provider-agnostic completion with caching, backoff and degradation."""

    BASE_BACKOFF_SECONDS = 1.0

    def __init__(
        self,
        settings: Settings,
        transport: Callable[..., str] | None = None,
        cache_path: Path | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport or _default_transport
        self._cache = _DiskCache(cache_path or settings.cache_path)
        self._sleep = sleep or __import__("time").sleep
        self.stats = CallStats()

    # -- cache key ------------------------------------------------------------

    def _cache_key(self, system: str, user: str, max_tokens: int) -> str:
        signature = json.dumps(
            {
                "model": self.settings.model_name,
                "provider": self.settings.provider.value,
                "system": system,
                "user": user,
                "temperature": 0,
                "max_tokens": max_tokens,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(signature.encode("utf-8")).hexdigest()

    # -- the one public call --------------------------------------------------

    def complete(self, system: str, user: str, max_tokens: int = 512) -> CompletionResult:
        """Return a completion, or a result explaining why there is none.

        This method does not raise. Every failure path produces a
        `CompletionResult` with `ok=False`, because A9 requires the unattended run
        to continue.
        """
        key = self._cache_key(system, user, max_tokens)

        cached = self._cache.get(key)
        if cached is not None:
            self.stats.cache_hits += 1
            return CompletionResult(text=cached, ok=True, from_cache=True, attempts=0)

        if not self.settings.has_model_access:
            self.stats.degraded = True
            return CompletionResult(
                ok=False,
                error="no api key configured; running retrieval-only",
            )

        last_error: str | None = None
        attempts = 0

        for attempt in range(max(1, self.settings.max_retries)):
            attempts = attempt + 1
            self.stats.attempted += 1
            try:
                text = self._transport(
                    provider=self.settings.provider,
                    api_key=self.settings.api_key,
                    base_url=self.settings.base_url,
                    timeout=self.settings.request_timeout_seconds,
                    model=self.settings.model_name,
                    system=system,
                    user=user,
                    temperature=0,
                    max_tokens=max_tokens,
                )
            except ProviderConfigError as exc:
                # Not transient. Fail immediately rather than burning retries.
                self.stats.failed += 1
                self.stats.degraded = True
                return CompletionResult(
                    ok=False, attempts=attempts, error=f"{type(exc).__name__}: {exc}"
                )
            except (ProviderRateLimited, ProviderTimeout, ProviderUnavailable) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            except Exception as exc:  # noqa: BLE001 - nothing may escape (A9)
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                self.stats.succeeded += 1
                self._cache.put(key, text)
                return CompletionResult(text=text, ok=True, attempts=attempts)

            if attempts < max(1, self.settings.max_retries):
                self.stats.retries += 1
                # Exponential backoff. Free tiers throttle, and hammering a
                # throttled endpoint is what turns a pause into a ban.
                self._sleep(self.BASE_BACKOFF_SECONDS * (2**attempt))

        self.stats.failed += 1
        self.stats.degraded = True
        return CompletionResult(ok=False, attempts=attempts, error=last_error)
