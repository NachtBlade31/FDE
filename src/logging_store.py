"""The decision log — acceptance criterion A8, FR-18.

Every automated decision is written here, with enough context that it can be
reconstructed months later by someone who was not there. The schema is the
Governance Framework's minimum record (section 1).

Reconciliation is by identity rather than by count. Stage counts legitimately
vary per ticket — a deny-listed ticket terminates at routing, an ungrounded one
escalates before generation, a kill-switched one makes no model call — so an
assertion of the form `decisions == tickets * stages` would fail on a run that is
entirely correct. What A8 actually checks is that no processed ticket is missing
from the log, which is an identity comparison in both directions.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
)

from src.models import DecisionRecord, Stage, TerminalState


class ReconciliationError(AssertionError):
    """Raised when logged decisions do not match the tickets processed."""


_METADATA = MetaData()

decisions = Table(
    "decisions",
    _METADATA,
    Column("decision_id", String(36), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("ticket_id", String(64), nullable=False, index=True),
    Column("stage", String(32), nullable=False),
    Column("input_summary", Text, default=""),
    Column("model_name", String(128), default=""),
    Column("model_version", String(64), default=""),
    Column("prediction_value", Text, nullable=True),
    Column("prediction_confidence", Float, nullable=True),
    Column("alternatives", Text, default="[]"),
    Column("sources_used", Text, default="[]"),
    Column("threshold_applied", Float, nullable=True),
    Column("action_taken", String(64), default=""),
    Column("reason", Text, default=""),
    Column("guardrail_results", Text, default="{}"),
    Column("prompt_version", String(64), default=""),
    Column("requirement_ids", Text, default="[]"),
    Column("terminal_state", String(32), nullable=True, index=True),
)

# Columns stored as JSON text, with the default used when a row predates the field.
_JSON_COLUMNS: dict[str, Any] = {
    "alternatives": list,
    "sources_used": list,
    "guardrail_results": dict,
    "requirement_ids": list,
}


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _load(raw: Any, factory: Any) -> Any:
    if raw in (None, ""):
        return factory()
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return factory()


class DecisionLog:
    """A persistent, append-only log of automated decisions."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url, future=True)
        _METADATA.create_all(self._engine)

    # -- writing -------------------------------------------------------------

    def write(self, record: DecisionRecord) -> str:
        """Append one decision. Returns its decision_id."""
        decision_id = record.decision_id or str(uuid.uuid4())
        created_at = record.created_at or datetime.now(timezone.utc)

        values = {
            "decision_id": decision_id,
            "created_at": created_at,
            "ticket_id": record.ticket_id,
            "stage": record.stage.value,
            "input_summary": record.input_summary,
            "model_name": record.model_name,
            "model_version": record.model_version,
            "prediction_value": record.prediction_value,
            "prediction_confidence": record.prediction_confidence,
            "alternatives": _dump(record.alternatives),
            "sources_used": _dump(record.sources_used),
            "threshold_applied": record.threshold_applied,
            "action_taken": record.action_taken,
            "reason": record.reason,
            "guardrail_results": _dump(record.guardrail_results),
            "prompt_version": record.prompt_version,
            "requirement_ids": _dump(record.requirement_ids),
            "terminal_state": record.terminal_state.value if record.terminal_state else None,
        }

        with self._engine.begin() as conn:
            conn.execute(insert(decisions).values(**values))

        return decision_id

    # -- reading -------------------------------------------------------------

    def _to_record(self, row: Any) -> DecisionRecord:
        data = dict(row._mapping)
        for column, factory in _JSON_COLUMNS.items():
            data[column] = _load(data.get(column), factory)
        data["stage"] = Stage(data["stage"])
        if data.get("terminal_state"):
            data["terminal_state"] = TerminalState(data["terminal_state"])
        return DecisionRecord(**data)

    def records_for(self, ticket_id: str) -> list[DecisionRecord]:
        stmt = select(decisions).where(decisions.c.ticket_id == ticket_id)
        with self._engine.connect() as conn:
            return [self._to_record(row) for row in conn.execute(stmt)]

    def logged_ticket_ids(self) -> set[str]:
        stmt = select(decisions.c.ticket_id).distinct()
        with self._engine.connect() as conn:
            return {row[0] for row in conn.execute(stmt)}

    # -- A8 reconciliation ---------------------------------------------------

    def reconcile(self, processed_ticket_ids: Iterable[str]) -> None:
        """Assert the log covers exactly the tickets processed, both directions.

        Raises ReconciliationError naming every discrepancy, not only the first,
        so a gap can be diagnosed in one pass.
        """
        processed = set(processed_ticket_ids)
        logged = self.logged_ticket_ids()

        missing = sorted(processed - logged)
        unexpected = sorted(logged - processed)

        if not missing and not unexpected:
            return

        problems = []
        if missing:
            problems.append(f"processed but never logged: {', '.join(missing)}")
        if unexpected:
            problems.append(f"logged but not processed: {', '.join(unexpected)}")

        raise ReconciliationError(
            "decision log does not reconcile against tickets processed — " + "; ".join(problems)
        )

    # -- volume counts (Build Spec section 04) -------------------------------

    def terminal_counts(self) -> Counter[TerminalState]:
        """Count tickets by terminal state. Intermediate records are excluded."""
        stmt = select(decisions.c.terminal_state).where(decisions.c.terminal_state.isnot(None))
        with self._engine.connect() as conn:
            return Counter(TerminalState(row[0]) for row in conn.execute(stmt))

    def volume_counts(self) -> dict[str, int]:
        """The four counts Build Specification section 04 requires.

        `blocked_by_guardrails` is reported separately while still counting
        inside `escalated`. Design section 2.3 argues that a blocked response
        belongs in the escalation rate, because it still leaves a customer
        without an answer and a human who must write one. Emitting the separate
        count anyway is what makes that choice auditable rather than convenient:
        a reader can recompute the rates under either taxonomy.
        """
        counts = self.terminal_counts()
        auto = counts.get(TerminalState.AUTO_RESPONDED, 0)
        direct = counts.get(TerminalState.ESCALATED_DIRECT, 0)
        blocked = counts.get(TerminalState.ESCALATED_AFTER_BLOCK, 0)

        return {
            "processed": auto + direct + blocked,
            "answered_automatically": auto,
            "escalated": direct + blocked,
            "blocked_by_guardrails": blocked,
        }

    def close(self) -> None:
        self._engine.dispose()
