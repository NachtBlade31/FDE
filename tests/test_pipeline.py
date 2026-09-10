"""Pipeline tests — A8, A9, A11, and the end-to-end contract.

A9: "The system processes the full evaluation set in a single unattended run.
Started once and left alone. No manual intervention, no restarts, no skipped
tickets."

Build Spec section 04 states what that requires:
  - every ticket produces either a sent answer or a logged escalation
  - none are silently dropped
  - every decision is written to the log

So the property under test is not "the pipeline works" but "the pipeline cannot
stop". Every failure mode a ticket can present must resolve to a terminal state,
because one unhandled exception on ticket forty ends the run and fails the gate.
"""

from __future__ import annotations

import pytest

from src.models import TerminalState
from src.pipeline import Pipeline, TicketOutcome
from src.retrieve import Corpus, Retriever


class StubClient:
    """A model provider that can be told to misbehave."""

    def __init__(self, replies=None, ok=True, raises=None):
        from src.llm_client import CallStats

        self._replies = list(replies or [])
        self._ok = ok
        self._raises = raises
        self.stats = CallStats()
        self.calls = 0

    def complete(self, system, user, max_tokens=512):
        from src.llm_client import CompletionResult

        self.calls += 1
        if self._raises:
            raise self._raises
        if not self._ok:
            self.stats.degraded = True
            return CompletionResult(ok=False, error="provider unavailable")
        text = self._replies.pop(0) if self._replies else _CLASSIFY_REPLY
        return CompletionResult(text=text, ok=True)


_CLASSIFY_REPLY = (
    '{"intent": "rate_limit", "urgency": "medium", "confidence": 0.97, "alternatives": []}'
)
_ANSWER_REPLY = "Rate limits apply per organisation rather than per key [1]."


def _raw(ticket_id="DEV-0001", body="We are getting 429 responses from your api", **kw):
    base = {
        "ticket_id": ticket_id,
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
    def _build(client=None, kill_switch=None):
        from src.logging_store import DecisionLog

        return Pipeline(
            client=client or StubClient([_CLASSIFY_REPLY, _ANSWER_REPLY] * 50),
            retriever=Retriever(corpus, relevance_floor=0.40),
            log=DecisionLog(f"sqlite:///{tmp_path / 'd.db'}"),
            kill_switch=kill_switch or (lambda: False),
        )

    return _build


# --- every ticket reaches exactly one terminal state -------------------------


def test_a_normal_ticket_produces_an_outcome(build):
    outcome = build().process(_raw())

    assert isinstance(outcome, TicketOutcome)
    assert outcome.terminal_state in set(TerminalState)


def test_a_ticket_that_cannot_be_parsed_still_produces_an_outcome(build):
    """A9: no ticket is silently dropped, whatever it looks like."""
    outcome = build().process({"channel": "email", "body": "no id"})

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT
    assert outcome.ticket_id


def test_a_non_mapping_input_produces_an_outcome(build):
    outcome = build().process("this is not a ticket at all")

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


def test_an_empty_ticket_escalates_rather_than_failing(build):
    outcome = build().process(_raw(body="   ", subject=""))

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


# --- A11: nothing the provider does may stop the run -------------------------


def test_a_provider_outage_still_produces_an_outcome(build):
    outcome = build(client=StubClient(ok=False)).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


def test_a_provider_raising_an_exception_does_not_escape(build):
    """The unattended run must survive an error nobody predicted."""
    outcome = build(client=StubClient(raises=RuntimeError("something unforeseen"))).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


def test_a_provider_returning_nonsense_still_produces_an_outcome(build):
    outcome = build(client=StubClient(["not json", "not json"])).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


# --- A8: every decision is logged and reconciles ------------------------------


def test_every_stage_writes_a_decision_record(build):
    pipeline = build()
    pipeline.process(_raw())

    stages = {r.stage.value for r in pipeline.log.records_for("DEV-0001")}
    assert {"classification", "routing"} <= stages


def test_the_log_reconciles_against_the_tickets_processed(build):
    pipeline = build()
    for i in range(5):
        pipeline.process(_raw(ticket_id=f"DEV-{i:04d}"))

    pipeline.log.reconcile({f"DEV-{i:04d}" for i in range(5)}, require_terminal=True)


def test_exactly_one_terminal_record_is_written_per_ticket(build):
    pipeline = build()
    pipeline.process(_raw())

    terminal = [r for r in pipeline.log.records_for("DEV-0001") if r.terminal_state]
    assert len(terminal) == 1


def test_an_escalated_ticket_still_reconciles(build):
    pipeline = build(client=StubClient(ok=False))
    pipeline.process(_raw())

    pipeline.log.reconcile({"DEV-0001"}, require_terminal=True)


# --- the kill switch stops the system without stopping the run ---------------


def test_the_kill_switch_escalates_every_ticket(build):
    outcome = build(kill_switch=lambda: True).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT


def test_the_kill_switch_makes_no_model_call(build):
    """FR-22: it must take effect immediately, not after the work is done."""
    client = StubClient()
    build(client=client, kill_switch=lambda: True).process(_raw())

    assert client.calls == 0


# --- a blocked response is a distinct terminal state -------------------------


def test_a_guardrail_block_produces_escalated_after_block(build):
    """Design 2.3: blocked counts inside escalated, but is reported separately."""
    blocked_answer = "We have issued a refund to your account [1]."
    outcome = build(client=StubClient([_CLASSIFY_REPLY, blocked_answer])).process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_AFTER_BLOCK
    assert "tone_and_scope" in outcome.blocked_by


def test_a_blocked_response_sends_nothing(build):
    blocked_answer = "We have issued a refund [1]."
    outcome = build(client=StubClient([_CLASSIFY_REPLY, blocked_answer])).process(_raw())

    assert outcome.response_text == ""


# --- escalations carry context (D3, FR-16) -----------------------------------


def test_an_escalation_carries_context_for_the_agent(build):
    outcome = build(client=StubClient(ok=False)).process(_raw())

    assert outcome.escalation is not None
    assert outcome.escalation.uncertainty


# --- batch behaviour ----------------------------------------------------------


def test_a_batch_processes_every_ticket_even_when_some_are_malformed(build):
    pipeline = build()
    raws = [_raw(ticket_id="DEV-0001"), "junk", {}, _raw(ticket_id="DEV-0002")]

    outcomes = [pipeline.process(r) for r in raws]

    assert len(outcomes) == 4
    assert all(o.terminal_state is not None for o in outcomes)


def test_processing_is_deterministic_for_the_same_ticket(build):
    pipeline = build(client=StubClient([_CLASSIFY_REPLY, _ANSWER_REPLY] * 4))
    first = pipeline.process(_raw(ticket_id="DEV-A"))
    second = pipeline.process(_raw(ticket_id="DEV-B"))

    assert first.terminal_state == second.terminal_state


# --- a withheld draft is a block, and must be counted as one -----------------
#
# An ungrounded draft used to short-circuit past the validator to
# ESCALATED_DIRECT with an empty `blocked_by`. Two things were wrong with that:
# the grounding guardrail's own first condition (`not answer.citations`) became
# unreachable from the pipeline, and a draft that was produced and then withheld
# was counted as a ticket that never got as far as a draft. On the 10 September
# gate run this mislabelled four tickets and reported `blocked_by_guardrails: 0`
# when the true count was 4 — a governance count, understated, in the artifact
# the report leads with.


def test_a_draft_with_no_resolvable_citation_is_recorded_as_blocked(build):
    """The model answers confidently and cites nothing."""
    pipeline = build(
        client=StubClient([_CLASSIFY_REPLY, "Rate limits apply per organisation."])
    )

    outcome = pipeline.process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_AFTER_BLOCK
    assert "grounding" in outcome.blocked_by
    assert outcome.escalated


def test_a_draft_citing_a_passage_it_was_never_given_is_blocked(build):
    """A marker outside the retrieved set resolves to nothing."""
    pipeline = build(
        client=StubClient([_CLASSIFY_REPLY, "See the guidance [9]."])
    )

    outcome = pipeline.process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_AFTER_BLOCK
    assert "grounding" in outcome.blocked_by


def test_a_blocked_draft_still_carries_its_context_to_the_human(build):
    """Blocking must not throw away what the agent needs to answer."""
    pipeline = build(
        client=StubClient([_CLASSIFY_REPLY, "Rate limits apply per organisation."])
    )

    outcome = pipeline.process(_raw())

    assert outcome.escalation is not None
    assert outcome.escalation.sources, "the retrieved passages must survive the block"
    assert outcome.escalation.draft, "the withheld draft goes to the human, not the bin"


def test_a_grounded_draft_is_not_blocked(build):
    """The control must discriminate, not simply block everything."""
    outcome = build().process(_raw())

    assert outcome.terminal_state is TerminalState.AUTO_RESPONDED
    assert outcome.blocked_by == ()


def test_no_draft_at_all_is_not_counted_as_a_guardrail_block(build):
    """Two different events that were reported as one.

    A provider that returns nothing produces no draft, so nothing was withheld —
    that is a failure. A provider that returns prose citing nothing produces a
    draft that must not be sent — that is a block. Conflating them lets a
    provider outage inflate the guardrail activation count, which would make the
    governance numbers look busiest exactly when the system is least healthy.
    """
    pipeline = build(client=StubClient([_CLASSIFY_REPLY, ""]))

    outcome = pipeline.process(_raw())

    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT
    assert outcome.blocked_by == ()
    assert "No draft was produced at all" in outcome.reason
