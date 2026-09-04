"""Decision log tests — acceptance criterion A8.

A8: "Every automated decision is written to a persistent log with the required
fields." Judged by opening the log and reconciling decisions against tickets
processed.

The record schema is fixed by the Governance Framework section 1. Two fields in
particular — prompt_version and requirement_ids — are what let the question "was
this behaviour intended?" be answered after an incident.

Reconciliation is by IDENTITY, not by multiplication. Stage counts legitimately
vary per ticket: a deny-listed ticket terminates at routing, an ungrounded ticket
escalates early, a kill-switched ticket makes no model call at all. See design
document section 4.1.
"""

import pytest

from src.logging_store import DecisionLog, ReconciliationError
from src.models import DecisionRecord, Stage, TerminalState


@pytest.fixture()
def log(tmp_path):
    return DecisionLog(f"sqlite:///{tmp_path / 'decisions.db'}")


def _record(ticket_id="DEV-0001", stage=Stage.CLASSIFICATION, **overrides):
    base = {
        "ticket_id": ticket_id,
        "stage": stage,
        "input_summary": "Cannot log in to the console",
        "model_name": "llama-3.3-70b-versatile",
        "prediction_value": "authentication_failure",
        "prediction_confidence": 0.91,
        "alternatives": [{"value": "account_access", "confidence": 0.06}],
        "sources_used": [{"doc_id": "DOC-AUTH-001", "score": 0.82}],
        "threshold_applied": 0.80,
        "action_taken": "auto_respond",
        "reason": "Confidence 0.91 above threshold 0.80 and answer grounded in DOC-AUTH-001.",
        "guardrail_results": {"pii": "pass", "grounding": "pass", "tone": "pass"},
        "prompt_version": "PR-02 v1.0",
        "requirement_ids": ["FR-03", "FR-07"],
    }
    base.update(overrides)
    return DecisionRecord(**base)


# --- the record survives a round trip with every governance field ------------


def test_record_round_trips_with_all_governance_fields(log):
    log.write(_record())

    [stored] = log.records_for("DEV-0001")

    assert stored.ticket_id == "DEV-0001"
    assert stored.stage is Stage.CLASSIFICATION
    assert stored.prediction_confidence == pytest.approx(0.91)
    assert stored.threshold_applied == pytest.approx(0.80)
    assert stored.action_taken == "auto_respond"
    assert stored.reason.startswith("Confidence 0.91")


def test_alternatives_are_preserved_not_only_the_chosen_option(log):
    """Build Spec 03 Classify: 'Records the alternatives it considered.'

    D1 layer 3 depends on this: abstention reads the distribution, not the top-1.
    """
    log.write(_record())

    [stored] = log.records_for("DEV-0001")

    assert stored.alternatives == [{"value": "account_access", "confidence": 0.06}]


def test_sources_and_scores_are_preserved_for_citation_audit(log):
    log.write(_record())

    [stored] = log.records_for("DEV-0001")

    assert stored.sources_used == [{"doc_id": "DOC-AUTH-001", "score": 0.82}]


def test_prompt_version_and_requirement_ids_are_recorded(log):
    """These answer 'was this behaviour intended?' after an incident."""
    log.write(_record())

    [stored] = log.records_for("DEV-0001")

    assert stored.prompt_version == "PR-02 v1.0"
    assert stored.requirement_ids == ["FR-03", "FR-07"]


def test_every_record_gets_a_unique_decision_id(log):
    log.write(_record(stage=Stage.CLASSIFICATION))
    log.write(_record(stage=Stage.ROUTING))

    ids = {r.decision_id for r in log.records_for("DEV-0001")}

    assert len(ids) == 2


def test_every_record_gets_a_timestamp(log):
    log.write(_record())

    [stored] = log.records_for("DEV-0001")

    assert stored.created_at is not None


def test_the_log_persists_across_reopening(log, tmp_path):
    """'Persistent log' means it survives the process that wrote it."""
    url = f"sqlite:///{tmp_path / 'persist.db'}"
    first = DecisionLog(url)
    first.write(_record())
    first.close()

    reopened = DecisionLog(url)

    assert len(reopened.records_for("DEV-0001")) == 1


# --- A8 reconciliation, by identity ------------------------------------------


def test_reconciliation_passes_when_every_ticket_has_at_least_one_record(log):
    log.write(_record("DEV-0001", Stage.CLASSIFICATION))
    log.write(_record("DEV-0002", Stage.CLASSIFICATION))

    log.reconcile({"DEV-0001", "DEV-0002"})  # must not raise


def test_reconciliation_fails_when_a_processed_ticket_was_never_logged(log):
    """Build Spec 08: 'A decision log written only for the tickets that succeeded.'"""
    log.write(_record("DEV-0001", Stage.CLASSIFICATION))

    with pytest.raises(ReconciliationError, match="DEV-0002"):
        log.reconcile({"DEV-0001", "DEV-0002"})


def test_reconciliation_fails_when_the_log_contains_an_unprocessed_ticket(log):
    """Identity is checked in both directions, not just one."""
    log.write(_record("DEV-0001", Stage.CLASSIFICATION))
    log.write(_record("DEV-0099", Stage.CLASSIFICATION))

    with pytest.raises(ReconciliationError, match="DEV-0099"):
        log.reconcile({"DEV-0001"})


def test_reconciliation_accepts_differing_stage_counts_between_tickets(log):
    """A deny-listed ticket terminates at routing and never reaches generation.

    A count-based assertion such as decisions == tickets * stages would fail
    here, on a run that is entirely correct.
    """
    log.write(_record("DEV-0001", Stage.CLASSIFICATION))
    log.write(_record("DEV-0001", Stage.ROUTING))
    log.write(_record("DEV-0001", Stage.GENERATION))
    log.write(_record("DEV-0001", Stage.VALIDATION))

    log.write(_record("DEV-0002", Stage.CLASSIFICATION))
    log.write(_record("DEV-0002", Stage.ROUTING, action_taken="escalate"))

    log.reconcile({"DEV-0001", "DEV-0002"})  # must not raise


def test_reconciliation_reports_every_missing_ticket_not_only_the_first(log):
    log.write(_record("DEV-0001", Stage.CLASSIFICATION))

    with pytest.raises(ReconciliationError) as exc:
        log.reconcile({"DEV-0001", "DEV-0002", "DEV-0003"})

    assert "DEV-0002" in str(exc.value)
    assert "DEV-0003" in str(exc.value)


# --- terminal state, which every rate in the metrics report derives from -----


def test_terminal_state_is_recorded_for_the_volume_counts(log):
    """Build Spec 04 requires four volume counts derived from one enum."""
    log.write(_record("DEV-0001", Stage.VALIDATION, terminal_state=TerminalState.AUTO_RESPONDED))

    [stored] = log.records_for("DEV-0001")

    assert stored.terminal_state is TerminalState.AUTO_RESPONDED


def test_terminal_states_are_counted_across_the_run(log):
    log.write(_record("DEV-0001", Stage.VALIDATION, terminal_state=TerminalState.AUTO_RESPONDED))
    log.write(_record("DEV-0002", Stage.ROUTING, terminal_state=TerminalState.ESCALATED_DIRECT))
    log.write(
        _record("DEV-0003", Stage.VALIDATION, terminal_state=TerminalState.ESCALATED_AFTER_BLOCK)
    )

    counts = log.terminal_counts()

    assert counts[TerminalState.AUTO_RESPONDED] == 1
    assert counts[TerminalState.ESCALATED_DIRECT] == 1
    assert counts[TerminalState.ESCALATED_AFTER_BLOCK] == 1


def test_records_without_a_terminal_state_are_not_counted_as_outcomes(log):
    """Intermediate stages must not inflate the volume counts."""
    log.write(_record("DEV-0001", Stage.CLASSIFICATION))
    log.write(_record("DEV-0001", Stage.VALIDATION, terminal_state=TerminalState.AUTO_RESPONDED))

    assert sum(log.terminal_counts().values()) == 1


# --- Build Spec section 04 volume counts -------------------------------------


def test_volume_counts_report_all_four_required_figures(log):
    """Build Spec 04: 'Tickets processed, answered automatically, escalated,
    blocked by guardrails.' All four derive from the one terminal enum."""
    log.write(_record("DEV-0001", Stage.VALIDATION, terminal_state=TerminalState.AUTO_RESPONDED))
    log.write(_record("DEV-0002", Stage.VALIDATION, terminal_state=TerminalState.AUTO_RESPONDED))
    log.write(_record("DEV-0003", Stage.ROUTING, terminal_state=TerminalState.ESCALATED_DIRECT))
    log.write(
        _record("DEV-0004", Stage.VALIDATION, terminal_state=TerminalState.ESCALATED_AFTER_BLOCK)
    )

    counts = log.volume_counts()

    assert counts == {
        "processed": 4,
        "answered_automatically": 2,
        "escalated": 2,
        "blocked_by_guardrails": 1,
    }


def test_blocked_is_counted_inside_escalated_not_alongside_it(log):
    """Design section 2.3: blocked is a subset of escalated, not a third bucket.

    Reporting it separately as well is what makes that choice auditable: a reader
    can recompute the rates under either taxonomy.
    """
    log.write(
        _record("DEV-0001", Stage.VALIDATION, terminal_state=TerminalState.ESCALATED_AFTER_BLOCK)
    )

    counts = log.volume_counts()

    assert counts["escalated"] == 1
    assert counts["blocked_by_guardrails"] == 1
    assert counts["processed"] == 1


def test_volume_counts_are_zero_on_an_empty_log(log):
    assert log.volume_counts() == {
        "processed": 0,
        "answered_automatically": 0,
        "escalated": 0,
        "blocked_by_guardrails": 0,
    }
