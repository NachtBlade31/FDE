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
