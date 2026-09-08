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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.config import Provider, Settings


class ProviderError(Exception):
    """Base class for anything the provider does that we must survive."""


class ProviderTimeout(ProviderError):
    """The provider did not answer in time."""


class ProviderRateLimited(ProviderError):
    """Free-tier throttling. Expected, and handled with backoff.

    Carries retry_after when the provider tells us how long to wait, which it
    knows better than any backoff schedule we could guess.
    """

    retry_after: float | None = None


class ProviderUnavailable(ProviderError):
    """The provider could not be reached at all."""


class ProviderQuotaExhausted(ProviderError):
    """The account's budget for the period is spent. Not retryable in-run.

    Discovered live: the free tier carries a 200,000 tokens-per-day cap that
    appears ONLY in the body of the 429. The rate-limit headers reported the
    per-minute bucket as completely full while the day's budget was gone, so
    pacing was watching the wrong bucket and the retry loop waited three to
    five minutes per call for a reset that was hours away.

    A9 requires the run to finish. Treating this as terminal degrades the run
    to retrieval-only in seconds instead of stretching it overnight, and the
    report says plainly that the budget ran out.
    """


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
    quota_exhausted: bool = False
    paced_seconds: float = 0.0
    paced_count: int = 0


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


_DURATION = re.compile(
    r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?"
)


def _duration(raw):
    """Parse the provider reset format, e.g. 1h39m21.6s or 35.437s."""
    match = _DURATION.fullmatch(raw.strip())
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (float(g) if g else 0.0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


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

    # Reasoning models bill their thinking against the completion budget.
    # Measured 2026-09-07 on openai/gpt-oss-20b: reasoning tokens fall from
    # 113 to 7 and total tokens from 650 to 556 with effort set low, which
    # both saves allowance and removes the truncation that produced empty
    # content. Omitted when blank so providers that reject the field work.
    effort = kwargs.get("reasoning_effort")
    if effort:
        payload["reasoning_effort"] = effort

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
        body = response.text or ""
        # The daily cap is only distinguishable from the per-minute one by
        # reading the message; both are HTTP 429 and the headers look healthy.
        if "per day" in body or "TPD" in body or "RPD" in body:
            raise ProviderQuotaExhausted(body[:300])
        error = ProviderRateLimited("rate limited by provider")
        hint = response.headers.get("retry-after")
        if hint:
            try:
                error.retry_after = float(hint)
            except ValueError:
                error.retry_after = _duration(hint)
        raise error
    if response.status_code >= 500:
        raise ProviderUnavailable(f"provider returned {response.status_code}")
    if response.status_code >= 400:
        # 400/401/403/404 mean the request itself is wrong. Retrying cannot help.
        raise ProviderConfigError(
            f"provider returned {response.status_code}: {response.text[:200]}"
        )

    def header_number(name):
        raw = response.headers.get(name)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return _duration(raw)

    payload_json = response.json()
    text = payload_json["choices"][0]["message"]["content"]
    usage = payload_json.get("usage") or {}
    return text, {
        "observed_tokens": usage.get("total_tokens"),
        "remaining_tokens": header_number("x-ratelimit-remaining-tokens"),
        "reset_tokens": header_number("x-ratelimit-reset-tokens"),
        "remaining_requests": header_number("x-ratelimit-remaining-requests"),
        "limit_tokens": header_number("x-ratelimit-limit-tokens"),
    }


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
        # Last known allowance, taken from the previous response headers.
        self._remaining_tokens = None
        self._reset_seconds = None
        self._limit_tokens = None
        # What a call actually costs, learned from the provider's own usage
        # figures rather than assumed from max_tokens.
        self._observed_cost = None

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

    # -- rate limit pacing ----------------------------------------------------

    # Never wait longer than this for the allowance, whatever the headers say.
    # A9 forbids a single response from being able to stall an unattended run.
    MAX_PACING_SECONDS = 65.0

    # Only used before the first response has reported a real usage figure.
    ASSUMED_PROMPT_TOKENS = 700

    # A little headroom over the observed average, since costs vary per ticket.
    COST_SAFETY_FACTOR = 1.25

    def _record_limits(self, limits):
        if not limits:
            return
        if limits.get("remaining_tokens") is not None:
            self._remaining_tokens = float(limits["remaining_tokens"])
        if limits.get("reset_tokens") is not None:
            self._reset_seconds = float(limits["reset_tokens"])
        if limits.get("limit_tokens") is not None:
            self._limit_tokens = float(limits["limit_tokens"])
        observed = limits.get("observed_tokens")
        if observed:
            # Exponential moving average of what calls actually cost. The
            # provider reports it, so there is no need to guess.
            cost = float(observed)
            self._observed_cost = (
                cost if self._observed_cost is None else 0.7 * self._observed_cost + 0.3 * cost
            )

    def _refill_rate(self):
        """Tokens per second, derived from the headers rather than assumed.

        The provider reports `reset` as time until the bucket is FULL, so the
        refill rate is the current deficit divided by that time. Measured on Groq
        this is constant at 133 tokens/second, which is the 8000-per-minute limit
        — but deriving it means the pacing follows a changed limit without a code
        change.
        """
        if not self._limit_tokens or self._reset_seconds is None or self._reset_seconds <= 0:
            return None
        deficit = self._limit_tokens - (self._remaining_tokens or 0.0)
        if deficit <= 0:
            return None
        return deficit / self._reset_seconds

    def _pace(self, max_tokens):
        """Wait only long enough to accrue the shortfall for the next call.

        The earlier version slept the entire reset window whenever the allowance
        dipped below a fixed floor. Because `reset` grows as the bucket empties,
        that meant sleeping up to a minute to buy a few hundred tokens: an
        80-ticket run managed 25 tickets in 90 minutes, against a sustainable
        rate of roughly 6.5 tickets a minute. Waiting for the deficit rather than
        for a full bucket is the difference between clearing A9 and failing it.
        """
        if self._remaining_tokens is None:
            return

        # Reserving prompt+max_tokens over-reserved by more than two to one:
        # a classification call is budgeted 1200 tokens and costs 544. Over an
        # 80-ticket run that alone doubled the wall clock. The observed cost
        # is what the provider bills, so it is what we pace against.
        if self._observed_cost:
            needed = self._observed_cost * self.COST_SAFETY_FACTOR
        else:
            needed = self.ASSUMED_PROMPT_TOKENS + max_tokens
        shortfall = needed - self._remaining_tokens
        if shortfall <= 0:
            return

        rate = self._refill_rate()
        if rate is None or rate <= 0:
            # No usable rate signal. Fall back to the reset window, capped.
            wait = min(self._reset_seconds or 0.0, self.MAX_PACING_SECONDS)
        else:
            wait = min(shortfall / rate, self.MAX_PACING_SECONDS)

        if wait > 0:
            self.stats.paced_seconds += wait
            self.stats.paced_count += 1
            self._sleep(wait)
            # Assume the wait bought what it was meant to buy; the next response
            # replaces this with a measured figure.
            self._remaining_tokens = min(
                self._limit_tokens or needed, self._remaining_tokens + wait * (rate or 0.0)
            )

    def _backoff_for(self, exc, attempt):
        """Prefer the provider hint over our own exponential schedule."""
        hint = getattr(exc, "retry_after", None)
        if hint:
            return float(hint)
        return self.BASE_BACKOFF_SECONDS * (2**attempt)

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

        if self.stats.quota_exhausted:
            # The budget is spent for the period. Every further call would
            # cost a multi-minute wait and fail anyway.
            return CompletionResult(
                ok=False,
                error="provider quota exhausted for the period; running retrieval-only",
            )

        if not self.settings.has_model_access:
            self.stats.degraded = True
            return CompletionResult(
                ok=False,
                error="no api key configured; running retrieval-only",
            )

        self._pace(max_tokens)

        last_error: str | None = None
        last_exception: Exception | None = None
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
                    reasoning_effort=self.settings.reasoning_effort,
                )
            except ProviderQuotaExhausted as exc:
                self.stats.failed += 1
                self.stats.degraded = True
                self.stats.quota_exhausted = True
                return CompletionResult(
                    ok=False, attempts=attempts, error=f"{type(exc).__name__}: {exc}"
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
                last_exception = exc
            except Exception as exc:  # noqa: BLE001 - nothing may escape (A9)
                last_error = f"{type(exc).__name__}: {exc}"
                last_exception = exc
            else:
                if isinstance(text, tuple):
                    text, limits = text
                    self._record_limits(limits)
                if not (text or "").strip():
                    # HTTP 200 with no content. Reasoning models can spend
                    # the whole completion budget thinking and emit nothing.
                    # Caching that would make one truncation permanent.
                    last_error = "provider returned an empty completion"
                    last_exception = None
                else:
                    self.stats.succeeded += 1
                    self._cache.put(key, text)
                    return CompletionResult(text=text, ok=True, attempts=attempts)

            if attempts < max(1, self.settings.max_retries):
                self.stats.retries += 1
                # Free tiers throttle, and hammering a throttled endpoint is
                # what turns a pause into a ban.
                self._sleep(self._backoff_for(last_exception, attempt))

        self.stats.failed += 1
        self.stats.degraded = True
        return CompletionResult(ok=False, attempts=attempts, error=last_error)
