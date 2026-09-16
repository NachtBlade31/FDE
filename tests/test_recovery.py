"""Every node's recovery path is executed — acceptance criterion A11.

`Pipeline._contained` wraps each graph node so that when it raises, only that
node is lost: it recovers into a defined state and the ticket carries on. That
wrapper is the mechanism A11 rests on. Until these tests existed, coverage showed
**five of its six recovery handlers had never run** — only `_recover_classify`
was exercised, because the classifier and generator swallow provider errors
internally, so their nodes return normally and the wrapper is never needed.

`_recover_validate` is the one that matters most and had the least cover: it is
what stops a response being *sent* when the validator itself crashes.

**Why every test asserts the failure was recorded.** Each node is replaced by one
that raises. If a test only checked that the ticket reached a terminal state, it
would pass just as well if the graph never reached that node at all — every ticket
reaches a terminal state. So each test also asserts that the injected node's own
failure appears in `outcome.failures`. That is the assertion that proves the
recovery handler under test actually ran.

The graph binds its node methods when the pipeline is constructed, so the node is
patched on the class *before* building; patching an instance afterwards would
silently change nothing.
"""

from __future__ import annotations

import pytest

from src.models import TerminalState
from src.pipeline import Pipeline
from src.retrieve import Corpus, Retriever

_CLASSIFY = (
    '{"intent": "rate_limit", "urgency": "medium", "confidence": 0.97, "alternatives": []}'
)
_ANSWER = "Rate limits apply per organisation rather than per key [1]."


class _Client:
    """Healthy provider: the only failure in each test is the injected one.

    Replies are chosen by what is being asked for, not by position in a queue.
    A queue desynchronises the moment a patched node skips its call: with
    `generate` raising, the answer reply is never consumed, so the *next*
    ticket's classifier receives answer prose, fails to parse, and escalates at
    routing before ever reaching `generate`. That made one of the tests below
    fail for a reason unrelated to the pipeline — and it was the
    `_recorded(...)` assertion, which exists to stop a test passing without
    reaching its node, that caught it.

    The pipeline reserves 500 tokens to classify (`src/classify.py`) and 700 to
    generate (`src/generate.py`), so the request size identifies the call.
    """

    def __init__(self):
        from src.llm_client import CallStats

        self.stats = CallStats()

    def complete(self, system, user, max_tokens=512):
        from src.llm_client import CompletionResult

        self.stats.attempted += 1
        self.stats.succeeded += 1
        return CompletionResult(text=_ANSWER if max_tokens >= 700 else _CLASSIFY, ok=True)


def _raw(**kw):
    base = {
        "ticket_id": "DEV-0001",
        "channel": "email",
        "subject": "",
        "body": "We are getting 429 responses from your api and traffic has not changed",
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
def pipeline_with(corpus, tmp_path, monkeypatch):
    """Build a pipeline in which the named node raises."""

    def _build(node_name: str):
        from src.logging_store import DecisionLog

        def explode(self, state):
            raise RuntimeError(f"injected failure in {node_name}")

        monkeypatch.setattr(Pipeline, f"_{node_name}", explode)
        log = DecisionLog(f"sqlite:///{tmp_path / 'd.db'}")
        pipeline = Pipeline(
            client=_Client(),
            retriever=Retriever(corpus, relevance_floor=0.40),
            log=log,
        )
        return pipeline, log

    return _build


def _recorded(outcome, node_name: str) -> bool:
    return any(f.startswith(f"{node_name}:") for f in outcome.failures)


# --- the control: the healthy path really does reach every node ---------------


def test_the_unpatched_ticket_reaches_generation_and_is_sent(corpus, tmp_path):
    """Without this, a test patching `generate` or `validate` could pass because
    routing escalated first and those nodes were never reached."""
    from src.logging_store import DecisionLog

    outcome = Pipeline(
        client=_Client(),
        retriever=Retriever(corpus, relevance_floor=0.40),
        log=DecisionLog(f"sqlite:///{tmp_path / 'd.db'}"),
    ).process(_raw())

    assert outcome.terminal_state is TerminalState.AUTO_RESPONDED
    assert "generate" in outcome.stages_run and "validate" in outcome.stages_run
    assert outcome.failures == ()


# --- each recovery handler ----------------------------------------------------


def test_an_ingest_failure_escalates_so_the_ticket_is_not_lost(pipeline_with):
    pipeline, log = pipeline_with("ingest")

    outcome = pipeline.process(_raw())

    assert _recorded(outcome, "ingest")
    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT
    assert "Could not be read as a ticket" in outcome.reason
    assert outcome.ticket_id == "DEV-0001", "the id must survive so the ticket can be found"
    assert log.records_for("DEV-0001"), "an escalation nobody logged is a lost ticket"


def test_a_retrieval_failure_escalates_instead_of_answering_ungrounded(pipeline_with):
    """Retrieval recovers to an empty result. With nothing to ground an answer
    in, routing must escalate — not generate from nothing."""
    pipeline, log = pipeline_with("retrieve")

    outcome = pipeline.process(_raw())

    assert _recorded(outcome, "retrieve")
    assert outcome.terminal_state is not TerminalState.AUTO_RESPONDED
    assert "generate" not in outcome.stages_run, "no passages, so no draft may be written"
    assert log.records_for("DEV-0001")


def test_a_routing_failure_escalates_with_what_is_known_attached(pipeline_with):
    pipeline, log = pipeline_with("route")

    outcome = pipeline.process(_raw())

    assert _recorded(outcome, "route")
    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT
    assert "Routing failed" in outcome.reason
    assert outcome.escalation is not None, "the human still gets the context"
    assert log.records_for("DEV-0001")


def test_a_generation_failure_produces_no_draft_and_escalates_directly(pipeline_with):
    """No draft exists, so nothing was withheld: a direct escalation, NOT a
    guardrail block. Counting it as a block would let an outage inflate the
    governance figures (D-47)."""
    pipeline, log = pipeline_with("generate")

    outcome = pipeline.process(_raw())

    assert _recorded(outcome, "generate")
    assert outcome.terminal_state is TerminalState.ESCALATED_DIRECT
    assert outcome.blocked_by == ()
    assert "No draft was produced at all" in outcome.reason
    assert log.records_for("DEV-0001")


def test_a_validator_crash_withholds_the_response(pipeline_with):
    """The one that matters most. If the validator itself fails, nothing was
    checked, so nothing may be sent — the draft exists and must be withheld."""
    pipeline, log = pipeline_with("validate")

    outcome = pipeline.process(_raw())

    assert _recorded(outcome, "validate")
    assert outcome.terminal_state is TerminalState.ESCALATED_AFTER_BLOCK
    assert outcome.terminal_state is not TerminalState.AUTO_RESPONDED
    assert outcome.blocked_by == ("validation_error",)
    assert not outcome.response_text, "no text may be released when nothing was checked"
    assert outcome.escalation is not None
    assert log.records_for("DEV-0001")


@pytest.mark.parametrize("node", ["ingest", "retrieve", "route", "generate", "validate"])
def test_no_injected_failure_can_produce_a_sent_answer(pipeline_with, node):
    """The invariant across all of them: a failure anywhere never results in a
    response going to a customer."""
    pipeline, _ = pipeline_with(node)

    outcome = pipeline.process(_raw())

    assert _recorded(outcome, node)
    assert outcome.terminal_state is not TerminalState.AUTO_RESPONDED
    assert not outcome.response_text


@pytest.mark.parametrize("node", ["ingest", "retrieve", "route", "generate", "validate"])
def test_one_failed_ticket_does_not_poison_the_next(pipeline_with, corpus, tmp_path, node):
    """A9 and A11 together: the run continues. A failure is contained to the
    ticket it happened on, and the pipeline object is still usable."""
    pipeline, _ = pipeline_with(node)

    first = pipeline.process(_raw(ticket_id="DEV-0001"))
    second = pipeline.process(_raw(ticket_id="DEV-0002"))

    assert first.terminal_state is not None
    assert second.terminal_state is not None
    assert second.ticket_id == "DEV-0002"
    assert _recorded(second, node)
    # Exactly one, or the message above would be untrue while the test passed:
    # a failures list that leaked across tickets would accumulate entries.
    assert sum(1 for f in second.failures if f.startswith(f"{node}:")) == 1
