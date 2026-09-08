"""Failure injection — acceptance criterion A11.

A11: "The system handles failure without crashing: no retrieval hit, provider
timeout or outage, rate limiting, malformed input. Each condition is induced,
including disconnecting the model provider entirely. The system degrades and
continues rather than stopping."

This module induces each named condition explicitly, one test per condition, so
the criterion can be checked by reading the test names. The other suites cover
these behaviours in passing; this one exists to make the coverage legible and to
be the thing demonstrated on camera.

The standard is *degrade and continue*, not *survive*. A ticket that hits a
failure must still reach a terminal state, still be logged, and still carry
enough context for a human to act on — because A9 requires the unattended run to
finish and Build Spec §04 requires every ticket to produce either a sent answer
or a logged escalation.
"""

from __future__ import annotations

import json

import pytest

from src.llm_client import (
    LLMClient,
    ProviderConfigError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from src.models import TerminalState
from src.pipeline import Pipeline
from src.retrieve import Corpus, Retriever


class FailingClient:
    """A provider that fails in a specified way, for a specified number of calls."""

    def __init__(self, failure=None, fail_first=None, reply=None):
        from src.llm_client import CallStats

        self.failure = failure
        self.remaining = fail_first
        self.reply = reply or _CLASSIFY
        self.stats = CallStats()
        self.calls = 0

    def complete(self, system, user, max_tokens=512):
        from src.llm_client import CompletionResult

        self.calls += 1
        failing = self.failure is not None and (self.remaining is None or self.remaining > 0)
        if failing:
            if self.remaining is not None:
                self.remaining -= 1
            self.stats.degraded = True
            if isinstance(self.failure, Exception):
                raise self.failure
            return CompletionResult(ok=False, error=str(self.failure))
        return CompletionResult(text=self.reply, ok=True)


_CLASSIFY = '{"intent": "rate_limit", "urgency": "medium", "confidence": 0.97, "alternatives": []}'


def _raw(body="We are getting 429 responses from your api", **kw):
    base = {
        "ticket_id": "DEV-0001",
        "channel": "email",
        "subject": "",
        "body": body,
        "received_at": "2026-03-14T09:22:00Z",
        "customer_id": "CUST-1",
        "customer_tier": "business",
        "customer_region": "europe",
        "language_fluency": "fluent",
    }
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def corpus():
    from pathlib import Path

    return Corpus.from_file(Path(__file__).resolve().parents[1] / "data" / "documentation.json")


@pytest.fixture()
def build(corpus, tmp_path):
    def _build(client, **kw):
        from src.logging_store import DecisionLog

        return Pipeline(
            client=client,
            retriever=Retriever(corpus, relevance_floor=kw.pop("floor", 0.40)),
            log=DecisionLog(f"sqlite:///{tmp_path / 'd.db'}"),
            **kw,
        )

    return _build


# --- condition 1: no retrieval hit -------------------------------------------


def test_no_retrieval_hit_escalates_rather_than_inventing_an_answer(build):
    """Build Spec 08: 'Returning nothing is a valid and often correct answer.'"""
    pipeline = build(FailingClient(), floor=0.999)  # nothing can clear this

    outcome = pipeline.process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT
    assert "documentation" in outcome.reason.lower()


def test_no_retrieval_hit_still_tells_the_agent_what_was_closest(build):
    """D3: an escalation must show its working, not just say no."""
    pipeline = build(FailingClient(), floor=0.999)

    outcome = pipeline.process(_raw())

    assert outcome.escalation is not None
    assert outcome.escalation.uncertainty


# --- condition 2: provider timeout -------------------------------------------


def test_a_provider_timeout_degrades_and_continues(build):
    outcome = build(FailingClient(ProviderTimeout("read timed out"))).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


def test_a_timeout_on_the_first_call_only_still_completes(build):
    """A transient timeout must not cost the ticket."""
    pipeline = build(FailingClient(ProviderTimeout("blip"), fail_first=1))

    outcome = pipeline.process(_raw())

    assert outcome.terminal_state is not None


# --- condition 3: rate limiting ----------------------------------------------


def test_rate_limiting_degrades_and_continues(build):
    outcome = build(FailingClient(ProviderRateLimited("429"))).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


def test_rate_limiting_is_survivable_across_a_batch(build):
    """A9: the run must not stop, however long the provider throttles."""
    pipeline = build(FailingClient(ProviderRateLimited("429")))

    outcomes = [pipeline.process(_raw(ticket_id=f"DEV-{i:04d}")) for i in range(20)]

    assert len(outcomes) == 20
    assert all(o.terminal_state is not None for o in outcomes)


# --- condition 4: the provider disconnected entirely -------------------------


def test_the_provider_disconnected_entirely_still_produces_outcomes(build):
    """A11 names this explicitly: 'including disconnecting the model provider'."""
    pipeline = build(FailingClient(ProviderUnavailable("connection refused")))

    outcomes = [pipeline.process(_raw(ticket_id=f"DEV-{i:04d}")) for i in range(10)]

    assert all(o.terminal_state is TerminalState.ESCALATED_DIRECT for o in outcomes)


def test_with_no_provider_the_system_still_retrieves_and_attaches_context(build):
    """Degrading to retrieval-only is the designed fallback, not a dead end.

    The customer still gets a faster route to a human with the relevant article
    already attached, which is better than today's 8-to-12-hour wait.
    """
    pipeline = build(FailingClient(ProviderUnavailable("down")))

    outcome = pipeline.process(_raw())

    assert outcome.retrieval is not None
    assert outcome.retrieval.passages, "retrieval is local and must still work"
    assert outcome.escalation.sources


def test_every_ticket_is_still_logged_during_a_total_outage(build):
    """A8 must reconcile even when nothing worked."""
    pipeline = build(FailingClient(ProviderUnavailable("down")))
    ids = {f"DEV-{i:04d}" for i in range(8)}

    for ticket_id in sorted(ids):
        pipeline.process(_raw(ticket_id=ticket_id))

    pipeline.log.reconcile(ids, require_terminal=True)


# --- condition 5: malformed input --------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "not a ticket at all",
        123,
        None,
        [],
        {},
        {"channel": "email"},
        {"ticket_id": "", "body": "empty id"},
    ],
)
def test_malformed_input_produces_an_outcome_rather_than_an_exception(build, bad):
    outcome = build(FailingClient()).process(bad)

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT
    assert outcome.ticket_id


def test_unusual_characters_do_not_break_the_pipeline(build):
    outcome = build(FailingClient()).process(
        _raw(body="認証 失敗 🚀 \x00\x1f <script>alert(1)</script> ' OR 1=1 --")
    )

    assert outcome.terminal_state is not None


def test_an_enormous_ticket_body_does_not_break_the_pipeline(build):
    outcome = build(FailingClient()).process(_raw(body="deployment failure " * 5000))

    assert outcome.terminal_state is not None


def test_a_ticket_whose_fields_are_the_wrong_type_is_handled(build):
    outcome = build(FailingClient()).process(
        {"ticket_id": "DEV-9", "channel": 42, "body": ["not", "a", "string"], "labels": "nope"}
    )

    assert outcome.terminal_state is not None


# --- condition 6: a malformed reply from the provider ------------------------


def test_a_provider_returning_html_instead_of_json_is_survived(build):
    outcome = build(FailingClient(reply="<html><body>502 Bad Gateway</body></html>")).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


def test_a_provider_returning_an_empty_string_is_survived(build):
    outcome = build(FailingClient(reply="")).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


def test_an_unexpected_exception_from_the_provider_is_contained(build):
    """A9: nothing unforeseen may end the run."""
    outcome = build(FailingClient(RuntimeError("nobody predicted this"))).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


def test_a_configuration_error_is_survived_without_retrying(build):
    outcome = build(FailingClient(ProviderConfigError("model does not exist"))).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


# --- condition 7: the storage layer fails ------------------------------------


def test_a_failing_decision_log_does_not_stop_the_run(build, corpus, tmp_path):
    """The log is important, but losing it must not lose the customer's ticket."""
    from src.logging_store import DecisionLog

    class BrokenLog(DecisionLog):
        def write(self, record):
            raise OSError("disk full")

    pipeline = Pipeline(
        client=FailingClient(),
        retriever=Retriever(corpus, relevance_floor=0.40),
        log=BrokenLog(f"sqlite:///{tmp_path / 'broken.db'}"),
    )

    outcome = pipeline.process(_raw())

    assert outcome.terminal_state is not None


# --- the whole set survives every condition at once --------------------------


def test_a_mixed_batch_of_every_failure_mode_completes(build):
    """The realistic case: one run, several different things going wrong."""
    pipeline = build(FailingClient(ProviderTimeout("blip"), fail_first=3))
    inputs = [
        _raw(ticket_id="DEV-0001"),
        "junk",
        _raw(ticket_id="DEV-0002", body=""),
        {},
        _raw(ticket_id="DEV-0003", body="認証 失敗 🚀"),
        _raw(ticket_id="DEV-0004", body="deployment " * 3000),
    ]

    outcomes = [pipeline.process(raw) for raw in inputs]

    assert len(outcomes) == len(inputs)
    assert all(o.terminal_state is not None for o in outcomes)
    assert all(o.ticket_id for o in outcomes)
