"""Routing — A5, FR-08 to FR-10, FR-16, FR-17, FR-22, and decisions D1, D2, D3.

This is where most of the value and most of the danger sits. Answer too readily
and confident nonsense reaches a paying customer; escalate too readily and the
system has not reduced anyone's workload.

**Routing is a conjunction, not a threshold (D2).** Auto-responding requires
every check to pass. Any single failure escalates. The four conjuncts are not
equal, and the ranking is deliberate rather than implied:

  1. the kill switch, checked first and short-circuiting everything
  2. the deny-list, in three independent layers (D1)
  3. grounding — something retrievable above the relevance floor
  4. the margin threshold — the weakest leg, and known to be so

That last point is measured, not assumed. Self-reported confidence puts 99 of 100
predictions in a single band, so it cannot carry a threshold; the margin between
the top choice and the best alternative can, but only weakly (D-29). Grounding and
the deny-list are what actually hold the decision, and 56 of the 87 deny-listed
development tickets are protected by grounding alone regardless of the classifier.

**The router decides eligibility, not the final outcome.** Guardrails run after
generation and can still block, which is why a blocked response becomes
ESCALATED_AFTER_BLOCK and is not decided here.

**Escalation is a designed output (D3).** Daniel's requirement was explicit: "I do
not need it to be right. I need it to show its working." Every escalation carries
the retrieved sources, the predicted intent with its alternatives, the urgency as
a priority, and a plain statement of what the system was unsure about.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from src.classify import DENY_LIST_INTENTS, Classification
from src.config import DEFAULT_ABSTENTION_FLOOR, DEFAULT_CONFIDENCE_THRESHOLD
from src.models import (
    ClassificationAlternative,
    DecisionRecord,
    NormalisedTicket,
    RetrievedPassage,
    Stage,
    Urgency,
)
from src.retrieve import RetrievalResult

_MARKERS_PATH = Path(__file__).resolve().parent / "markers.json"


def load_markers(path: Path | None = None) -> frozenset[str]:
    """The curated safety vocabulary — D1 layer 2, decision D-27.

    Curated rather than derived. An automatically derived vocabulary scored
    higher overall (90.8% held-out against 73.6%) but contained generic template
    artifacts such as "only", "call" and "nobody". The curated list is 100% on
    `security_incident` and `compliance_request`, the only two deny-listed intents
    that can ground and therefore carry real residual risk.
    """
    try:
        payload = json.loads((path or _MARKERS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):  # pragma: no cover - shipped with the package
        return frozenset()
    return frozenset(payload.get("markers", []))


class Action(str, Enum):
    AUTO_RESPOND = "auto_respond"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class EscalationContext:
    """What a human receives alongside an escalated ticket (D3, FR-16).

    An escalation that arrives with a draft, the relevant page and a note on what
    the system was unsure about is worth more to a tier-two engineer than a raw
    forwarded ticket — which is what they get today.
    """

    predicted_intent: str
    alternatives: tuple[ClassificationAlternative, ...]
    sources: tuple[RetrievedPassage, ...]
    uncertainty: str
    priority: Urgency
    draft: str = ""


@dataclass(frozen=True)
class RoutingDecision:
    """The routing outcome, with every check it performed recorded."""

    ticket_id: str
    action: Action
    reason: str
    checks: dict[str, bool] = field(default_factory=dict)
    escalation: EscalationContext | None = None
    threshold_applied: float = 0.0
    sources: tuple[RetrievedPassage, ...] = ()

    def to_decision_record(self, prompt_version: str = "") -> DecisionRecord:
        return DecisionRecord(
            ticket_id=self.ticket_id,
            stage=Stage.ROUTING,
            prediction_value=self.action.value,
            threshold_applied=self.threshold_applied,
            sources_used=list(self.sources),
            action_taken=self.action.value,
            reason=self.reason,
            guardrail_results=dict(self.checks),
            prompt_version=prompt_version,
            requirement_ids=["FR-08", "FR-09", "FR-10"],
        )


class Router:
    """Decides whether a ticket may be answered automatically."""

    def __init__(
        self,
        margin_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        markers: frozenset[str] | None = None,
        kill_switch: Callable[[], bool] | None = None,
        abstention_floor: float = DEFAULT_ABSTENTION_FLOOR,
    ) -> None:
        self.margin_threshold = margin_threshold
        self.abstention_floor = abstention_floor
        self.markers = load_markers() if markers is None else markers
        self._kill_switch = kill_switch or (lambda: False)

    # -- the individual checks ------------------------------------------------

    @staticmethod
    def margin(classification: Classification) -> float:
        """Top-1 confidence minus the best alternative.

        D-29: raw confidence has no spread to threshold on, the margin does.
        With no alternatives offered, the margin is the confidence itself.
        """
        best_alternative = max((a.confidence for a in classification.alternatives), default=0.0)
        return max(0.0, classification.confidence - best_alternative)

    def _deny_listed_alternatives(self, classification: Classification) -> set[str]:
        """Layer 3, with a floor. Without one it escalates almost everything.

        Measured over 200 development tickets: treating *any* deny-listed
        alternative as a safety signal made this check responsible for 66% of all
        escalations and held first contact resolution at 52% against a 60%
        target. A model asked for its alternatives will name a deny-listed class
        at trivial confidence on most tickets; a 2% alternative is noise, not
        caution, and the other layers already catch what it was adding.

        Ties resolve towards escalation, because the costs are asymmetric.
        """
        return {
            a.value
            for a in classification.alternatives
            if a.value in DENY_LIST_INTENTS and a.confidence >= self.abstention_floor
        }

    def matched_markers(self, ticket: NormalisedTicket) -> set[str]:
        """Layer 2: read the raw text, independent of any model output."""
        words = {w.strip(".,;:!?()[]\"'") for w in ticket.search_text.lower().split()}
        return {m for m in self.markers if m in words}

    # -- the decision ---------------------------------------------------------

    def route(
        self,
        ticket: NormalisedTicket,
        classification: Classification,
        retrieval: RetrievalResult,
    ) -> RoutingDecision:
        checks: dict[str, bool] = {}

        # 1. Kill switch, first and short-circuiting. FR-22 requires it to take
        #    effect without a deployment, so nothing below it may run.
        if self._kill_switch():
            checks["kill_switch"] = False
            return self._escalate(
                ticket,
                classification,
                retrieval,
                checks,
                "The kill switch is engaged, so no ticket is answered automatically. "
                "Escalated to a human with the retrieved context attached.",
                "The kill switch was engaged; the system did not evaluate this ticket.",
            )
        checks["kill_switch"] = True

        # 2. The deny-list, three independent layers (D1).
        checks["deny_list"] = classification.intent not in DENY_LIST_INTENTS
        matched = self.matched_markers(ticket)
        checks["lexical_screen"] = not matched
        checks["alternatives"] = not self._deny_listed_alternatives(classification)

        # 3. Grounding: something must be retrievable above the floor (D6).
        checks["grounded"] = bool(retrieval.passages)

        # 4. The margin threshold — the weakest conjunct, and known to be.
        margin = self.margin(classification)
        checks["margin"] = margin >= self.margin_threshold

        if all(checks.values()):
            citations = ", ".join(sorted({p.doc_id for p in retrieval.passages}))
            return RoutingDecision(
                ticket_id=ticket.ticket_id,
                action=Action.AUTO_RESPOND,
                reason=(
                    f"Answering automatically. Classified as {classification.intent} with a "
                    f"confidence margin of {margin:.2f} against a threshold of "
                    f"{self.margin_threshold:.2f}; the answer can be grounded in {citations}; "
                    f"no safety rule applied."
                ),
                checks=checks,
                threshold_applied=self.margin_threshold,
                sources=tuple(retrieval.passages),
            )

        return self._escalate(
            ticket,
            classification,
            retrieval,
            checks,
            self._escalation_reason(classification, retrieval, checks, matched, margin),
            self._uncertainty(classification, retrieval, checks, matched, margin),
        )

    # -- explanation ----------------------------------------------------------

    def _escalation_reason(
        self,
        classification: Classification,
        retrieval: RetrievalResult,
        checks: dict[str, bool],
        matched: set[str],
        margin: float,
    ) -> str:
        """Why this went to a human, in language a support manager could read."""
        causes = []
        if not checks["deny_list"]:
            causes.append(
                f"tickets classified as {classification.intent} are never answered automatically"
            )
        if not checks["lexical_screen"]:
            terms = ", ".join(sorted(matched))
            causes.append(f"the ticket text contains terms requiring human review ({terms})")
        if not checks["alternatives"]:
            flagged = ", ".join(sorted(self._deny_listed_alternatives(classification)))
            causes.append(
                f"the classifier considered {flagged}, which is never answered automatically"
            )
        if not checks["grounded"]:
            if retrieval.rejected:
                causes.append(
                    f"the closest documentation scored {retrieval.top_score:.2f}, below the "
                    f"relevance floor of {retrieval.floor_applied:.2f}"
                )
            else:
                causes.append("no documentation matched this ticket at all")
        if not checks["margin"]:
            causes.append(
                f"the confidence margin was {margin:.2f}, below the threshold of "
                f"{self.margin_threshold:.2f}"
            )

        return "Escalated to a human because " + "; and ".join(causes) + "."

    @staticmethod
    def _uncertainty(
        classification: Classification,
        retrieval: RetrievalResult,
        checks: dict[str, bool],
        matched: set[str],
        margin: float,
    ) -> str:
        """What to tell the agent the system was unsure about (D3)."""
        if not checks["deny_list"] or not checks["lexical_screen"]:
            return (
                "This ticket is in a category that always goes to a person. The system has "
                "not attempted an answer."
            )
        if not checks["alternatives"]:
            return (
                f"The classifier chose {classification.intent} but also considered a category "
                "that always goes to a person, so it did not answer."
            )
        if not checks["grounded"]:
            if retrieval.rejected:
                best = retrieval.rejected[0]
                return (
                    f"No documentation was close enough to answer from. The nearest article was "
                    f"{best.doc_id} ({best.title}) at {best.score:.2f}, below the "
                    f"{retrieval.floor_applied:.2f} floor — it may still be worth a look."
                )
            return "No documentation matched this ticket, so there was nothing to answer from."
        return (
            f"The system was not confident enough to answer: it chose "
            f"{classification.intent} by a margin of only {margin:.2f}."
        )

    @staticmethod
    def _escalate(
        ticket: NormalisedTicket,
        classification: Classification,
        retrieval: RetrievalResult,
        checks: dict[str, bool],
        reason: str,
        uncertainty: str,
    ) -> RoutingDecision:
        return RoutingDecision(
            ticket_id=ticket.ticket_id,
            action=Action.ESCALATE,
            reason=reason,
            checks=checks,
            escalation=EscalationContext(
                predicted_intent=classification.intent,
                alternatives=classification.alternatives,
                sources=tuple(retrieval.passages or retrieval.rejected),
                uncertainty=uncertainty,
                priority=classification.urgency,
            ),
            sources=tuple(retrieval.passages or retrieval.rejected),
        )
