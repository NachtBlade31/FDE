"""The pipeline — A8, A9, A11, and the six components in sequence.

    ingest -> classify -> retrieve -> route -> generate -> validate

Built as a LangGraph state machine, which is what the Project Brief recommends
for the multi-step routing. The conditional edge after `route` is the reason it
earns its place: an escalated ticket skips generation and validation entirely
rather than running them and discarding the result, so a deny-listed ticket costs
no model call and the stage sequence in the decision log reflects what actually
happened.

**The property this module is built around is that it cannot stop.** A9 requires
the full set processed in a single unattended run with no intervention and no
skipped tickets, and Build Spec §04 adds that every ticket must produce either a
sent answer or a logged escalation. One unhandled exception on the fortieth
ticket ends the run and fails the gate.

So every node is wrapped: an exception anywhere resolves the ticket to
`ESCALATED_DIRECT` with the failure recorded, rather than propagating. That is
not defensive habit — it is the acceptance criterion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.classify import Classification, Classifier
from src.config import DEFAULT_ABSTENTION_FLOOR, DEFAULT_CONFIDENCE_THRESHOLD
from src.generate import GeneratedAnswer, Generator
from src.guardrails import Validator
from src.ingest import IngestError, normalise_ticket
from src.logging_store import DecisionLog
from src.models import DecisionRecord, NormalisedTicket, Stage, TerminalState
from src.retrieve import RetrievalResult, Retriever
from src.route import Action, EscalationContext, Router, RoutingDecision


@dataclass
class TicketOutcome:
    """What happened to one ticket. Every field is populated on every path."""

    ticket_id: str
    terminal_state: TerminalState
    response_text: str = ""
    reason: str = ""
    escalation: EscalationContext | None = None
    blocked_by: tuple[str, ...] = ()
    classification: Classification | None = None
    retrieval: RetrievalResult | None = None
    routing: RoutingDecision | None = None
    answer: GeneratedAnswer | None = None
    latency_seconds: float = 0.0
    # Of `latency_seconds`, how much was spent asleep waiting for the free tier's
    # token allowance rather than doing work. The <3s target is about the system;
    # a queueing delay imposed by an unpaid tier is a deployment property, and
    # conflating them makes the figure meaningless in both directions.
    provider_wait_seconds: float = 0.0
    degraded: bool = False
    stages_run: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()

    @property
    def escalated(self) -> bool:
        return self.terminal_state is not TerminalState.AUTO_RESPONDED


@dataclass
class _State:
    """Carried between graph nodes."""

    raw: Any
    ticket: NormalisedTicket | None = None
    classification: Classification | None = None
    retrieval: RetrievalResult | None = None
    routing: RoutingDecision | None = None
    answer: GeneratedAnswer | None = None
    records: list[DecisionRecord] = field(default_factory=list)
    outcome: TicketOutcome | None = None
    stages: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class Pipeline:
    """Processes one ticket end to end, and never raises."""

    def __init__(
        self,
        client: Any,
        retriever: Retriever,
        log: DecisionLog,
        margin_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        abstention_floor: float = DEFAULT_ABSTENTION_FLOOR,
        kill_switch: Callable[[], bool] | None = None,
        top_k: int = 3,
        run_id: str = "",
    ) -> None:
        self.client = client
        self._kill_switch = kill_switch or (lambda: False)
        self.retriever = retriever
        self.log = log
        self.top_k = top_k
        # Stamped on every record so A8 reconciles within this run. The log
        # is persistent and accumulates across runs by design.
        self.run_id = run_id
        self.classifier = Classifier(client)
        self.generator = Generator(client)
        self.router = Router(
            margin_threshold=margin_threshold,
            abstention_floor=abstention_floor,
            kill_switch=kill_switch,
        )
        self.validator = Validator(
            known_chunk_ids={c.chunk_id for c in retriever.corpus.chunks}
        )
        self._graph = self._build_graph()

    # -- the graph -------------------------------------------------------------

    def _contained(self, name, node, recover):
        """Run a node so that its failure costs only that node.

        Catching only at the top of the graph was not enough. A11 asks the
        system to *degrade and continue*, and a classification failure that
        aborts the graph also loses retrieval — so the escalation arrives
        without the documentation that the retrieval-only fallback exists to
        attach. Retrieval is local and has no reason to fail just because the
        model provider did.

        Each node therefore recovers into a defined state and the pipeline
        carries on to the next stage.
        """

        def run(state: _State) -> _State:
            try:
                return node(state)
            except Exception as exc:  # noqa: BLE001 - A11: continue, do not stop
                state.failures.append(f"{name}: {type(exc).__name__}: {exc}")
                return recover(state)

        return run

    def _build_graph(self):
        """Wire the six components. Escalation short-circuits generation."""
        from langgraph.graph import END, StateGraph

        graph = StateGraph(_State)
        graph.add_node("ingest", self._contained("ingest", self._ingest, self._recover_ingest))
        graph.add_node(
            "classify", self._contained("classify", self._classify, self._recover_classify)
        )
        graph.add_node(
            "retrieve", self._contained("retrieve", self._retrieve, self._recover_retrieve)
        )
        graph.add_node("route", self._contained("route", self._route, self._recover_route))
        graph.add_node(
            "generate", self._contained("generate", self._generate, self._recover_generate)
        )
        graph.add_node(
            "validate", self._contained("validate", self._validate, self._recover_validate)
        )

        graph.set_entry_point("ingest")
        graph.add_conditional_edges(
            "ingest", lambda s: END if s.outcome else "classify", {END: END, "classify": "classify"}
        )
        graph.add_edge("classify", "retrieve")
        graph.add_edge("retrieve", "route")
        # A ticket that escalates never reaches generation, so it costs no model
        # call and its logged stage sequence reflects the path it actually took.
        graph.add_conditional_edges(
            "route",
            lambda s: END if s.outcome else "generate",
            {END: END, "generate": "generate"},
        )
        graph.add_edge("generate", "validate")
        graph.add_edge("validate", END)
        return graph.compile()

    # -- recovery: what each node degrades to ---------------------------------

    @staticmethod
    def _recover_ingest(state: _State) -> _State:
        state.outcome = TicketOutcome(
            ticket_id=_fallback_id(state.raw),
            terminal_state=TerminalState.ESCALATED_DIRECT,
            reason="Could not be read as a ticket; escalated so it is not lost.",
        )
        return state

    @staticmethod
    def _recover_classify(state: _State) -> _State:
        # The fallback class is itself deny-listed, so failing to classify and
        # failing safely are the same path. Retrieval still runs.
        state.classification = _fallback_classification(state)
        return state

    @staticmethod
    def _recover_retrieve(state: _State) -> _State:
        state.retrieval = RetrievalResult(passages=[], rejected=[], top_score=0.0, floor_applied=0.0)
        return state

    def _recover_route(self, state: _State) -> _State:
        state.outcome = TicketOutcome(
            ticket_id=state.ticket.ticket_id if state.ticket else _fallback_id(state.raw),
            terminal_state=TerminalState.ESCALATED_DIRECT,
            reason="Routing failed; escalated for human handling.",
            escalation=_context_from(state, GeneratedAnswer(reason="Routing failed.")),
        )
        return state

    @staticmethod
    def _recover_generate(state: _State) -> _State:
        state.answer = GeneratedAnswer(reason="Generation failed; no draft was produced.")
        return state

    def _recover_validate(self, state: _State) -> _State:
        # Validation failing means nothing was checked, so nothing may be sent.
        state.outcome = TicketOutcome(
            ticket_id=state.ticket.ticket_id if state.ticket else _fallback_id(state.raw),
            terminal_state=TerminalState.ESCALATED_AFTER_BLOCK,
            reason="Validation failed, so the response was withheld and escalated.",
            blocked_by=("validation_error",),
            escalation=_context_from(state, state.answer or GeneratedAnswer()),
        )
        return state

    # -- nodes -----------------------------------------------------------------

    def _ingest(self, state: _State) -> _State:
        state.stages.append("ingest")

        # FR-22: checked once per ticket, before any model call. Checking it at
        # routing would be too late - classification would already have spent a
        # call, and the switch exists to stop the system answering immediately.
        if self._kill_switch():
            state.outcome = TicketOutcome(
                ticket_id=_fallback_id(state.raw),
                terminal_state=TerminalState.ESCALATED_DIRECT,
                reason=(
                    "The kill switch is engaged. No ticket is answered automatically "
                    "and no model call was made; escalated for human handling."
                ),
            )
            return state

        try:
            state.ticket = normalise_ticket(state.raw)
        except IngestError as exc:
            # No usable identity. It still must not vanish: A9 requires every
            # input record to be accounted for.
            state.outcome = TicketOutcome(
                ticket_id=_fallback_id(state.raw),
                terminal_state=TerminalState.ESCALATED_DIRECT,
                reason=f"Could not be read as a ticket: {exc}",
            )
        return state

    def _classify(self, state: _State) -> _State:
        state.stages.append("classify")
        state.classification = self.classifier.classify(state.ticket)
        state.records.append(
            state.classification.to_decision_record(
                prompt_version=Classifier.PROMPT_VERSION,
                model_name=getattr(self.client, "settings", None)
                and self.client.settings.model_name
                or "",
            )
        )
        return state

    def _retrieve(self, state: _State) -> _State:
        state.stages.append("retrieve")
        state.retrieval = self.retriever.search_detailed(
            state.ticket.search_text, top_k=self.top_k
        )
        state.records.append(
            DecisionRecord(
                ticket_id=state.ticket.ticket_id,
                stage=Stage.RETRIEVAL,
                sources_used=list(state.retrieval.passages),
                threshold_applied=state.retrieval.floor_applied,
                action_taken="retrieved" if state.retrieval.passages else "no_match",
                reason=(
                    f"Retrieved {len(state.retrieval.passages)} passage(s) above the "
                    f"{state.retrieval.floor_applied:.2f} relevance floor; best score "
                    f"{state.retrieval.top_score:.2f}."
                ),
                requirement_ids=["FR-06", "FR-07"],
            )
        )
        return state

    def _route(self, state: _State) -> _State:
        state.stages.append("route")
        state.routing = self.router.route(state.ticket, state.classification, state.retrieval)
        record = state.routing.to_decision_record()
        if state.routing.action is Action.ESCALATE:
            record.terminal_state = TerminalState.ESCALATED_DIRECT
            state.outcome = TicketOutcome(
                ticket_id=state.ticket.ticket_id,
                terminal_state=TerminalState.ESCALATED_DIRECT,
                reason=state.routing.reason,
                escalation=state.routing.escalation,
            )
        state.records.append(record)
        return state

    def _generate(self, state: _State) -> _State:
        state.stages.append("generate")
        state.answer = self.generator.generate(state.ticket, list(state.retrieval.passages))
        state.records.append(
            state.answer.to_decision_record(
                ticket_id=state.ticket.ticket_id, prompt_version=Generator.PROMPT_VERSION
            )
        )
        return state

    def _validate(self, state: _State) -> _State:
        state.stages.append("validate")
        answer = state.answer

        # There are two ways generation can fail to yield a sendable answer, and
        # they are different events that were being reported as the same one.
        #
        #   no text at all      — the provider returned nothing. No draft exists,
        #                         so nothing was withheld. That is a failure, and
        #                         counting it as a guardrail block would let a
        #                         provider outage inflate the block count.
        #   text, no citations  — a draft WAS produced and must not be sent. That
        #                         is exactly `Validator._grounding`'s first
        #                         condition, and it is a block.
        #
        # Both used to short-circuit here to ESCALATED_DIRECT with an empty
        # `blocked_by`, which made the grounding branch unreachable from the
        # pipeline: it fires only when `citations` is empty, while reaching the
        # validator required `is_answerable`, which requires citations. On the 10
        # September gate run that reported `blocked_by_guardrails: 0` where four
        # drafts had been generated and withheld (D-47).
        if not answer.text.strip():
            record = DecisionRecord(
                ticket_id=state.ticket.ticket_id,
                stage=Stage.VALIDATION,
                action_taken="escalate",
                reason=f"No draft was produced at all: {answer.reason}",
                terminal_state=TerminalState.ESCALATED_DIRECT,
                requirement_ids=["FR-13"],
            )
            state.records.append(record)
            state.outcome = TicketOutcome(
                ticket_id=state.ticket.ticket_id,
                terminal_state=TerminalState.ESCALATED_DIRECT,
                reason=record.reason,
                escalation=_context_from(state, answer),
            )
            return state

        result = self.validator.validate(answer, state.ticket, confidence_applied=True)
        record = result.to_decision_record(ticket_id=state.ticket.ticket_id)

        if result.passed:
            record.terminal_state = TerminalState.AUTO_RESPONDED
            state.outcome = TicketOutcome(
                ticket_id=state.ticket.ticket_id,
                terminal_state=TerminalState.AUTO_RESPONDED,
                response_text=result.released_text,
                reason=state.routing.reason,
            )
        else:
            record.terminal_state = TerminalState.ESCALATED_AFTER_BLOCK
            state.outcome = TicketOutcome(
                ticket_id=state.ticket.ticket_id,
                terminal_state=TerminalState.ESCALATED_AFTER_BLOCK,
                reason=record.reason,
                blocked_by=result.blocked_by,
                escalation=_context_from(state, answer),
            )
        state.records.append(record)
        return state

    # -- the one public call ---------------------------------------------------

    def process(self, raw: Any) -> TicketOutcome:
        """Process one ticket. Never raises, whatever the input or the provider does."""
        import time

        started = time.perf_counter()
        stats = getattr(self.client, "stats", None)
        paced_before = getattr(stats, "paced_seconds", 0.0) if stats else 0.0
        state = _State(raw=raw)

        try:
            final = self._graph.invoke(state)
            state = final if isinstance(final, _State) else _State(**dict(final))
        except Exception as exc:  # noqa: BLE001 - A9: the run must not stop
            state.outcome = TicketOutcome(
                ticket_id=_fallback_id(raw),
                terminal_state=TerminalState.ESCALATED_DIRECT,
                reason=f"Pipeline error, escalated for human handling: {type(exc).__name__}: {exc}",
            )

        outcome = state.outcome or TicketOutcome(
            ticket_id=_fallback_id(raw),
            terminal_state=TerminalState.ESCALATED_DIRECT,
            reason="Pipeline produced no outcome; escalated so the ticket is not lost.",
        )

        outcome.latency_seconds = time.perf_counter() - started
        outcome.provider_wait_seconds = (
            (getattr(stats, "paced_seconds", 0.0) - paced_before) if stats else 0.0
        )
        outcome.classification = state.classification
        outcome.retrieval = state.retrieval
        outcome.routing = state.routing
        outcome.answer = state.answer
        outcome.stages_run = tuple(state.stages)
        outcome.failures = tuple(state.failures)
        outcome.degraded = bool(getattr(self.client, "stats", None) and self.client.stats.degraded)

        self._write_log(outcome, state.records)
        return outcome

    def _write_log(self, outcome: TicketOutcome, records: list[DecisionRecord]) -> None:
        """Persist every decision, and guarantee exactly one terminal record.

        A8 reconciles logged decisions against tickets processed, so a logging
        failure must not silently drop a ticket from the log either.
        """
        wrote_terminal = False
        for record in records:
            record.ticket_id = record.ticket_id or outcome.ticket_id
            record.run_id = self.run_id
            if record.terminal_state:
                if wrote_terminal:
                    record.terminal_state = None
                else:
                    wrote_terminal = True
            try:
                self.log.write(record)
            except Exception:  # noqa: BLE001 - never stop the run for a log write
                continue

        if not wrote_terminal:
            try:
                self.log.write(
                    DecisionRecord(
                        ticket_id=outcome.ticket_id,
                        run_id=self.run_id,
                        stage=Stage.VALIDATION,
                        action_taken=outcome.terminal_state.value,
                        reason=outcome.reason or "Terminal state recorded.",
                        terminal_state=outcome.terminal_state,
                        requirement_ids=["FR-18"],
                    )
                )
            except Exception:  # noqa: BLE001
                pass


def _fallback_classification(state: _State) -> Classification:
    """The safe class. It is deny-listed, so it routes to a human."""
    from src.classify import UNCLEAR

    return Classification(
        ticket_id=state.ticket.ticket_id if state.ticket else "",
        intent=UNCLEAR,
        fallback_reason="Classification raised; degraded to the safe class.",
    )


def _context_from(state: _State, answer: GeneratedAnswer) -> EscalationContext:
    return EscalationContext(
        predicted_intent=state.classification.intent if state.classification else "",
        alternatives=state.classification.alternatives if state.classification else (),
        sources=tuple(state.retrieval.passages) if state.retrieval else (),
        uncertainty=answer.reason or "No grounded answer could be drafted.",
        priority=state.classification.urgency if state.classification else None,
        draft=answer.text,
    )


def _fallback_id(raw: Any) -> str:
    """An identity for a record that has none, so nothing vanishes from the log."""
    if isinstance(raw, dict):
        value = str(raw.get("ticket_id") or "").strip()
        if value:
            return value
    import hashlib

    return "UNPARSED-" + hashlib.sha256(repr(raw).encode("utf-8")).hexdigest()[:10]
