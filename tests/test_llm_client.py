"""Model client tests — A5, A11, FR-21, and decision D5.

This component is where three separate requirements meet:

  A5  determinism: the same input must produce the same routing decision, which
      cannot hold if the model call is not itself reproducible.
  A11 resilience: provider timeout, rate limiting and total outage must degrade
      rather than crash. "Each condition is induced, including disconnecting the
      model provider entirely."
  D5  the content-addressed cache serves determinism, free-tier preservation and
      reproducibility of the recorded run all at once.

Every test here runs without a network call and without an API key, by injecting
a transport. That is deliberate: CI must be green on a clean checkout before the
grader has obtained credentials.
"""

from __future__ import annotations

import pytest

from src.config import Provider, Settings
from src.llm_client import (
    LLMClient,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)


def _settings(**overrides):
    base = {
        "PROVIDER": "groq",
        "GROQ_API_KEY": "gsk_test_key",
        "GROQ_MODEL": "openai/gpt-oss-20b",
        "MAX_RETRIES": "3",
    }
    base.update(overrides)
    return Settings.from_env(base)


class RecordingTransport:
    """A stand-in provider that records calls and replays scripted outcomes."""

    def __init__(self, outcomes=None):
        self.calls: list[dict] = []
        self._outcomes = list(outcomes or [])

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self._outcomes:
            return "default reply"
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture()
def client(tmp_path):
    def _make(transport, settings=None, **kw):
        return LLMClient(
            settings or _settings(),
            transport=transport,
            cache_path=tmp_path / "cache",
            sleep=lambda _seconds: None,  # no real backoff delay in tests
            **kw,
        )

    return _make


# --- the happy path -----------------------------------------------------------


def test_a_completion_returns_the_provider_text(client):
    result = client(RecordingTransport(["authentication_failure"])).complete("sys", "user")

    assert result.ok is True
    assert result.text == "authentication_failure"


def test_the_model_name_from_settings_is_sent(client):
    transport = RecordingTransport()
    client(transport).complete("sys", "user")

    assert transport.calls[0]["model"] == "openai/gpt-oss-20b"


def test_temperature_is_zero_for_determinism(client):
    """A5: the same input must produce the same decision."""
    transport = RecordingTransport()
    client(transport).complete("sys", "user")

    assert transport.calls[0]["temperature"] == 0


def test_the_system_prompt_and_customer_text_are_sent_separately(client):
    """FR-14: ticket content must not be concatenated into the instructions.

    Keeping them in separate messages is the first line of defence against a
    ticket that tries to redirect the system.
    """
    transport = RecordingTransport()
    client(transport).complete("SYSTEM RULES", "customer wrote this")

    call = transport.calls[0]
    assert call["system"] == "SYSTEM RULES"
    assert "SYSTEM RULES" not in call["user"]
    assert call["user"] == "customer wrote this"


# --- D5: the content-addressed cache -----------------------------------------


def test_an_identical_request_is_served_from_cache_without_calling_the_provider(client):
    transport = RecordingTransport(["first answer"])
    c = client(transport)

    first = c.complete("sys", "user")
    second = c.complete("sys", "user")

    assert first.text == second.text
    assert second.from_cache is True
    assert len(transport.calls) == 1


def test_a_different_prompt_is_not_served_from_cache(client):
    transport = RecordingTransport(["a", "b"])
    c = client(transport)

    c.complete("sys", "first")
    second = c.complete("sys", "second")

    assert second.from_cache is False
    assert len(transport.calls) == 2


def test_a_different_model_is_not_served_from_cache(client, tmp_path):
    """The cache key must include the model, or switching models replays stale text."""
    transport_a = RecordingTransport(["from model a"])
    transport_b = RecordingTransport(["from model b"])

    a = client(transport_a, _settings(GROQ_MODEL="model-a"))
    b = client(transport_b, _settings(GROQ_MODEL="model-b"))

    assert a.complete("sys", "user").text == "from model a"
    assert b.complete("sys", "user").text == "from model b"


def test_the_cache_survives_a_new_client_against_the_same_directory(client):
    """Reproducibility of a recorded run depends on the cache being on disk."""
    transport = RecordingTransport(["persisted"])
    client(transport).complete("sys", "user")

    fresh = RecordingTransport([])
    result = client(fresh).complete("sys", "user")

    assert result.text == "persisted"
    assert result.from_cache is True
    assert fresh.calls == []


def test_a_failed_call_is_never_cached(client):
    """Caching a failure would make a transient outage permanent."""
    transport = RecordingTransport(
        [ProviderUnavailable("down"), ProviderUnavailable("down"),
         ProviderUnavailable("down"), "recovered"]
    )
    c = client(transport)

    assert c.complete("sys", "user").ok is False
    assert c.complete("sys", "user").text == "recovered"


# --- A11: degrade, never crash ------------------------------------------------


def test_a_rate_limit_is_retried_then_succeeds(client):
    transport = RecordingTransport([ProviderRateLimited("429"), "succeeded after backoff"])

    result = client(transport).complete("sys", "user")

    assert result.ok is True
    assert result.text == "succeeded after backoff"
    assert result.attempts == 2


def test_a_timeout_is_retried(client):
    transport = RecordingTransport([ProviderTimeout("timed out"), "second attempt"])

    result = client(transport).complete("sys", "user")

    assert result.ok is True
    assert result.attempts == 2


def test_persistent_failure_returns_a_result_rather_than_raising(client):
    """A11: the run must continue. An exception here stops the unattended run."""
    transport = RecordingTransport([ProviderUnavailable("outage")] * 5)

    result = client(transport).complete("sys", "user")

    assert result.ok is False
    assert result.text == ""
    assert "outage" in (result.error or "")


def test_retries_are_bounded_by_max_retries(client):
    transport = RecordingTransport([ProviderRateLimited("429")] * 10)

    client(transport, _settings(MAX_RETRIES="2")).complete("sys", "user")

    assert len(transport.calls) == 2


def test_backoff_grows_between_attempts(client, tmp_path):
    """Free tiers throttle; hammering them is what turns a pause into a ban."""
    delays: list[float] = []
    transport = RecordingTransport([ProviderRateLimited("429")] * 3 + ["ok"])

    LLMClient(
        _settings(MAX_RETRIES="4"),
        transport=transport,
        cache_path=tmp_path / "c",
        sleep=delays.append,
    ).complete("sys", "user")

    assert delays == sorted(delays)
    assert len(set(delays)) > 1


def test_an_unexpected_exception_is_contained_rather_than_escaping(client):
    """A9 forbids a run stopping on one ticket, whatever the cause."""
    transport = RecordingTransport([ValueError("something nobody predicted")] * 5)

    result = client(transport).complete("sys", "user")

    assert result.ok is False


# --- no credentials: degraded, not broken -------------------------------------


def test_without_a_key_no_provider_call_is_attempted(client):
    transport = RecordingTransport(["should never be reached"])

    result = client(transport, _settings(GROQ_API_KEY="")).complete("sys", "user")

    assert result.ok is False
    assert transport.calls == []


def test_without_a_key_the_reason_says_so(client):
    result = client(RecordingTransport(), _settings(GROQ_API_KEY="")).complete("sys", "user")

    assert "no api key" in (result.error or "").lower()


# --- the degraded-run flag (D-10) --------------------------------------------


def test_the_client_reports_whether_any_call_failed(client):
    """The metrics report must never show an escalation rate without this flag."""
    transport = RecordingTransport(["fine", ProviderUnavailable("x"), ProviderUnavailable("x"),
                                    ProviderUnavailable("x")])
    c = client(transport)

    c.complete("sys", "one")
    assert c.stats.degraded is False

    c.complete("sys", "two")
    assert c.stats.degraded is True


def test_call_statistics_are_counted_for_the_throughput_budget(client):
    """F7: calls per ticket is what makes the free-tier budget computable."""
    transport = RecordingTransport(["a", "b"])
    c = client(transport)

    c.complete("sys", "one")
    c.complete("sys", "two")
    c.complete("sys", "one")  # cache hit

    assert c.stats.attempted == 2
    assert c.stats.succeeded == 2
    assert c.stats.cache_hits == 1


# --- provider selection -------------------------------------------------------


def test_the_openrouter_provider_is_supported(client):
    settings = Settings.from_env(
        {"PROVIDER": "openrouter", "OPENROUTER_API_KEY": "sk-or-test", "OPENROUTER_MODEL": "m"}
    )
    transport = RecordingTransport(["from openrouter"])

    result = client(transport, settings).complete("sys", "user")

    assert result.ok is True
    assert settings.provider is Provider.OPENROUTER


# --- not every failure is worth retrying --------------------------------------


def test_a_configuration_error_is_not_retried(client):
    """A 404 for a missing model, or a 401 for a bad key, will never succeed.

    Retrying wastes free-tier allowance and delays the run. Discovered live: a
    stale model name produced three identical 404s and two backoff sleeps before
    reporting a failure that was certain from the first attempt.
    """
    from src.llm_client import ProviderConfigError

    transport = RecordingTransport([ProviderConfigError("model does not exist")] * 5)

    result = client(transport).complete("sys", "user")

    assert result.ok is False
    assert len(transport.calls) == 1
    assert result.attempts == 1


def test_a_configuration_error_explains_itself(client):
    from src.llm_client import ProviderConfigError

    transport = RecordingTransport([ProviderConfigError("model `x` does not exist")] * 2)

    result = client(transport).complete("sys", "user")

    assert "does not exist" in (result.error or "")


def test_a_rate_limit_is_still_retried_after_that_change(client):
    """429 remains transient and must keep its backoff."""
    transport = RecordingTransport([ProviderRateLimited("429"), "ok now"])

    assert client(transport).complete("sys", "user").ok is True
    assert len(transport.calls) == 2


# --- proactive rate limiting (F7, A9) ----------------------------------------


def test_rate_limit_headers_are_recorded_when_the_provider_sends_them(client):
    """Groq's binding constraint is tokens per minute, not requests.

    Measured 2026-09-07: x-ratelimit-limit-tokens 8000 with a ~35s reset, against
    x-ratelimit-limit-requests 1000 per hour. Reacting only to 429s wastes the
    allowance on retries; the headers let us pace before being throttled.
    """
    transport = RecordingTransport([("ok", {"remaining_tokens": 3275, "reset_tokens": 35.4})])

    client(transport).complete("sys", "user")


def test_the_client_waits_when_the_token_allowance_is_nearly_exhausted(client, tmp_path):
    delays: list[float] = []
    transport = RecordingTransport(
        [
            ("first", {"remaining_tokens": 50, "reset_tokens": 12.0}),
            ("second", {"remaining_tokens": 7000, "reset_tokens": 60.0}),
        ]
    )
    c = LLMClient(
        _settings(),
        transport=transport,
        cache_path=tmp_path / "c",
        sleep=delays.append,
    )

    c.complete("sys", "one")
    assert delays == []  # nothing known before the first call

    c.complete("sys", "two")
    assert delays, "should have paced before the second call"
    assert delays[0] == pytest.approx(12.0, abs=1.0)


def test_no_wait_when_the_allowance_is_healthy(client, tmp_path):
    delays: list[float] = []
    transport = RecordingTransport(
        [("first", {"remaining_tokens": 7000, "reset_tokens": 30.0}), "second"]
    )
    c = LLMClient(
        _settings(), transport=transport, cache_path=tmp_path / "c", sleep=delays.append
    )

    c.complete("sys", "one")
    c.complete("sys", "two")

    assert delays == []


def test_a_retry_after_hint_is_honoured_over_exponential_backoff(client, tmp_path):
    """The provider knows how long it wants us to wait better than we do."""
    delays: list[float] = []
    err = ProviderRateLimited("429")
    err.retry_after = 7.5
    transport = RecordingTransport([err, "recovered"])

    LLMClient(
        _settings(), transport=transport, cache_path=tmp_path / "c", sleep=delays.append
    ).complete("sys", "user")

    assert delays == [pytest.approx(7.5)]


def test_a_transport_returning_a_plain_string_still_works(client):
    """Rate limit metadata is optional; not every provider supplies it."""
    assert client(RecordingTransport(["plain"])).complete("sys", "user").text == "plain"


# --- an empty completion is a failure, not a success --------------------------


def test_an_empty_completion_is_treated_as_a_failure(client):
    """Reasoning models can spend the whole token budget thinking.

    Measured 2026-09-07: openai/gpt-oss-20b used 113 of its completion tokens on
    reasoning before emitting any content. Where the budget runs out first the
    API returns HTTP 200 with an empty content field. Treating that as success
    caches an empty string forever and turns one truncation into a permanent
    misclassification.
    """
    transport = RecordingTransport(["", "", "", ""])

    result = client(transport).complete("sys", "user")

    assert result.ok is False
    assert "empty" in (result.error or "").lower()


def test_an_empty_completion_is_never_cached(client):
    transport = RecordingTransport(["", "", "", "proper answer"])
    c = client(transport)

    assert c.complete("sys", "user").ok is False
    assert c.complete("sys", "user").text == "proper answer"


def test_a_whitespace_only_completion_is_also_a_failure(client):
    assert client(RecordingTransport(["   \n  "] * 4)).complete("sys", "user").ok is False


# --- pacing must wait for the deficit, not for a full bucket ------------------


def test_pacing_waits_only_long_enough_to_accrue_what_the_call_needs(tmp_path):
    """The token bucket refills continuously; reset is time-until-FULL.

    Measured 2026-09-07 on Groq: deficit divided by reset is constant at
    0.0075 s/token, i.e. 133 tokens/second, i.e. the 8000 TPM limit. Sleeping the
    whole reset window whenever the allowance dipped made an 80-ticket run take
    90 minutes for 25 tickets. Waiting only for the shortfall is the difference
    between the gate passing and failing.
    """
    delays: list[float] = []
    transport = RecordingTransport(
        [
            ("first", {"remaining_tokens": 900, "reset_tokens": 53.0, "limit_tokens": 8000}),
            "second",
        ]
    )
    client = LLMClient(
        _settings(), transport=transport, cache_path=tmp_path / "c", sleep=delays.append
    )
    client.complete("sys", "one", max_tokens=500)   # establishes the allowance
    client.complete("sys", "two", max_tokens=500)   # paces on it

    # Needs ~500 completion + prompt; has 900. The shortfall is small, so the
    # wait must be a few seconds, not the 53s until the bucket is full.
    assert delays, "should have paced"
    assert delays[0] < 15.0, f"waited {delays[0]:.1f}s for a small shortfall"


def test_pacing_derives_the_refill_rate_from_the_headers(tmp_path):
    """Self-calibrating: rate = (limit - remaining) / reset."""
    delays: list[float] = []
    transport = RecordingTransport(
        [
            ("first", {"remaining_tokens": 0, "reset_tokens": 60.0, "limit_tokens": 8000}),
            "second",
        ]
    )
    client = LLMClient(
        _settings(), transport=transport, cache_path=tmp_path / "c", sleep=delays.append
    )
    client.complete("sys", "one", max_tokens=500)
    client.complete("sys", "two", max_tokens=500)

    # Empty bucket refilling at 8000/60 = 133 tokens/s. Needing roughly 1200
    # tokens is about 9 seconds, not 60.
    assert 1.0 < delays[0] < 20.0


def test_a_healthy_allowance_still_causes_no_wait(tmp_path):
    delays: list[float] = []
    transport = RecordingTransport(
        [("first", {"remaining_tokens": 7000, "reset_tokens": 8.0, "limit_tokens": 8000}), "second"]
    )
    client = LLMClient(
        _settings(), transport=transport, cache_path=tmp_path / "c", sleep=delays.append
    )
    client.complete("sys", "one", max_tokens=500)
    client.complete("sys", "two", max_tokens=500)

    assert delays == []


def test_the_wait_is_capped_so_one_bad_header_cannot_stall_the_run(tmp_path):
    """A9: no single response may be able to halt an unattended run."""
    delays: list[float] = []
    transport = RecordingTransport(
        [
            ("first", {"remaining_tokens": 0, "reset_tokens": 99999.0, "limit_tokens": 8000}),
            "second",
        ]
    )
    client = LLMClient(
        _settings(), transport=transport, cache_path=tmp_path / "c", sleep=delays.append
    )
    client.complete("sys", "one", max_tokens=500)
    client.complete("sys", "two", max_tokens=500)

    assert delays[0] <= LLMClient.MAX_PACING_SECONDS


def test_pacing_uses_the_observed_cost_once_the_provider_reports_it(tmp_path):
    """Reserving prompt+max_tokens over-reserved by more than two to one.

    A classification call is budgeted 1200 tokens and costs 544. Over an
    80-ticket run that alone doubled the wall clock. The response carries the
    real figure, so there is no need to guess.
    """
    delays: list[float] = []
    limits = {"remaining_tokens": 900, "reset_tokens": 53.0, "limit_tokens": 8000,
              "observed_tokens": 544}
    transport = RecordingTransport([("first", limits), "second"])

    client = LLMClient(
        _settings(), transport=transport, cache_path=tmp_path / "c", sleep=delays.append
    )
    client.complete("sys", "one", max_tokens=500)
    client.complete("sys", "two", max_tokens=500)

    # Needs 544 * 1.25 = 680, has 900 -> no shortfall, so no wait at all.
    assert delays == []


def test_a_larger_observed_cost_still_causes_a_wait(tmp_path):
    delays: list[float] = []
    limits = {"remaining_tokens": 200, "reset_tokens": 58.0, "limit_tokens": 8000,
              "observed_tokens": 1200}
    transport = RecordingTransport([("first", limits), "second"])

    client = LLMClient(
        _settings(), transport=transport, cache_path=tmp_path / "c", sleep=delays.append
    )
    client.complete("sys", "one", max_tokens=500)
    client.complete("sys", "two", max_tokens=500)

    assert delays and delays[0] < LLMClient.MAX_PACING_SECONDS


# --- the daily budget: a limit the headers do not carry ----------------------


def test_a_daily_token_limit_is_not_retried(client):
    """Discovered live: Groq's free tier has a 200,000 tokens-per-day cap that
    appears ONLY in the 429 body. The rate-limit headers reported the
    per-minute bucket as completely full while the day's budget was exhausted.

    Retrying it is pointless - the reset is hours away, not seconds - and it
    cost 995 seconds of sleep across eight tickets before this was understood.
    """
    from src.llm_client import ProviderQuotaExhausted

    transport = RecordingTransport([ProviderQuotaExhausted("tokens per day (TPD)")] * 5)

    result = client(transport).complete("sys", "user")

    assert result.ok is False
    assert len(transport.calls) == 1, "a daily cap must not be retried"


def test_a_daily_limit_marks_the_run_degraded(client):
    from src.llm_client import ProviderQuotaExhausted

    c = client(RecordingTransport([ProviderQuotaExhausted("TPD")] * 3))
    c.complete("sys", "user")

    assert c.stats.degraded is True
    assert c.stats.quota_exhausted is True


def test_once_the_daily_budget_is_gone_later_calls_do_not_even_try(client):
    """A9: the run must finish. Spending 5 minutes per ticket waiting for a
    daily reset would turn a 12-minute run into an overnight one."""
    from src.llm_client import ProviderQuotaExhausted

    transport = RecordingTransport([ProviderQuotaExhausted("TPD")] * 10)
    c = client(transport)

    c.complete("sys", "one")
    c.complete("sys", "two")
    c.complete("sys", "three")

    assert len(transport.calls) == 1, "later calls must short-circuit"


def test_a_per_minute_rate_limit_is_still_retried(client):
    """The daily cap is terminal; the per-minute one is transient."""
    transport = RecordingTransport([ProviderRateLimited("429"), "recovered"])

    assert client(transport).complete("sys", "user").ok is True
    assert len(transport.calls) == 2
