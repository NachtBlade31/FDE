"""Domain models.

Every value crossing a component boundary is one of these. Pydantic validates at
the edge so that malformed input becomes a defined value rather than an exception
deep in the pipeline (A11), and so that LangGraph transitions are type-checked.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_WHITESPACE = re.compile(r"\s+")


class _FallbackStr(str, Enum):
    """A string enum whose unknown values resolve to a defined fallback member.

    The hidden evaluation set uses the documented schema, but a run must never
    stop because a field carried an unexpected value (A11).

    Each subclass declares FALLBACK with the same value as one of its canonical
    members, which makes it an alias rather than a new member — so it does not
    appear in iteration, and equality with the canonical member holds.
    """

    @classmethod
    def _missing_(cls, value: object) -> "_FallbackStr":
        return cls.FALLBACK  # type: ignore[attr-defined]


class Channel(_FallbackStr):
    EMAIL = "email"
    CHAT = "chat"
    DOCS_COMMENT = "docs_comment"
    FORUM = "forum"
    UNKNOWN = "unknown"
    FALLBACK = "unknown"


class Urgency(_FallbackStr):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    FALLBACK = "medium"


class CustomerTier(_FallbackStr):
    """A fairness-audit segment, so its fallback must be distinguishable.

    Falling back to STANDARD would move degraded tickets into the majority
    segment (50.6% of the development set) — precisely where design section 2.4
    computes its pre-registered baseline — and would make a defaulted ticket
    indistinguishable from a genuine one.
    """

    ENTERPRISE = "enterprise"
    BUSINESS = "business"
    STANDARD = "standard"
    UNKNOWN = "unknown"
    FALLBACK = "unknown"


class CustomerRegion(_FallbackStr):
    NORTH_AMERICA = "north_america"
    EUROPE = "europe"
    ASIA_PACIFIC = "asia_pacific"
    LATIN_AMERICA = "latin_america"
    UNKNOWN = "unknown"
    FALLBACK = "unknown"


class LanguageFluency(_FallbackStr):
    """A fairness-audit segment. See CustomerTier for why UNKNOWN is distinct."""

    FLUENT = "fluent"
    NON_FLUENT = "non_fluent"
    UNKNOWN = "unknown"
    FALLBACK = "unknown"


class Stage(str, Enum):
    """Pipeline stages. Each writes at least one decision record."""

    INGEST = "ingest"
    CLASSIFICATION = "classification"
    RETRIEVAL = "retrieval"
    ROUTING = "routing"
    GENERATION = "generation"
    VALIDATION = "validation"


class TerminalState(str, Enum):
    """Exactly one per ticket. Every volume count and rate derives from this.

    Build Specification section 04 requires four volume counts. Deriving them all
    from a single enum makes the arithmetic unambiguous and prevents
    double-counting. `escalated_after_block` is reported separately as
    `blocked_by_guardrails` while still counting inside `escalated`.
    """

    AUTO_RESPONDED = "auto_responded"
    ESCALATED_DIRECT = "escalated_direct"
    ESCALATED_AFTER_BLOCK = "escalated_after_block"


class TicketLabels(BaseModel):
    """Ground-truth labels. Absent on the hidden set, so always optional."""

    model_config = ConfigDict(extra="allow")

    intent: str | None = None
    urgency: str | None = None
    expected_route: str | None = None
    answerable_from_docs: bool | None = None
    expected_doc_ids: list[str] = Field(default_factory=list)
    must_not_auto_respond: bool = False


class TicketHistory(BaseModel):
    """What happened when a human handled this ticket. The baseline, not a target."""

    model_config = ConfigDict(extra="allow")

    first_contact_resolution: bool | None = None
    resolution_time_minutes: float | None = None
    csat_rating: float | None = None
    escalated: bool | None = None
    repeat_contact: bool | None = None


class NormalisedTicket(BaseModel):
    """One internal representation, regardless of source channel (A2)."""

    model_config = ConfigDict(frozen=True)

    ticket_id: str
    channel: Channel
    subject: str = ""
    original_body: str = ""
    received_at: datetime | None = None

    customer_id: str = ""
    customer_name: str = ""
    customer_tier: CustomerTier = CustomerTier.UNKNOWN
    customer_region: CustomerRegion = CustomerRegion.UNKNOWN
    language_fluency: LanguageFluency = LanguageFluency.UNKNOWN

    labels: TicketLabels | None = None
    history: TicketHistory | None = None

    # Fields that were absent or unrecognised and were coerced to a fallback.
    # Without this residue the coercion is unrecoverable after ingest, and a
    # widened or narrowed fairness gap could not be told apart from silent
    # segment migration.
    degraded_fields: tuple[str, ...] = ()

    @property
    def search_text(self) -> str:
        """Subject and body as one whitespace-normalised string for retrieval."""
        return _WHITESPACE.sub(" ", f"{self.subject} {self.original_body}").strip()

    @property
    def is_empty(self) -> bool:
        """True when there is no signal at all to classify or retrieve on."""
        return not self.search_text


class RetrievedPassage(BaseModel):
    """One passage returned by retrieval, carrying enough to be found again.

    This type is what makes decision D7 enforceable. Citations are constructed
    from these identifiers rather than emitted free-form by the model, and the
    validator re-resolves each one against the store before a response is
    released. A6 is checked by following a citation to the text it claims to
    support, so `chunk_id` and the character offsets are not decoration — they
    are how that check is performed.
    """

    model_config = ConfigDict(frozen=True)

    doc_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    text: str = ""
    title: str = ""
    score: float = Field(ge=0.0, le=1.0)
    char_start: int = Field(default=0, ge=0)
    char_end: int = Field(default=0, ge=0)

    @property
    def citation(self) -> str:
        """What appears in the answer text. Readers cite documents, not chunks."""
        return self.doc_id


class ClassificationAlternative(BaseModel):
    """A class the classifier considered but did not choose.

    Build Spec section 03 requires the alternatives to be recorded, not only the
    chosen option. D1 layer 3 reads them: abstention fires when a deny-listed
    intent appears anywhere in the distribution, regardless of the top-1 label,
    which is the case where layers 1 and 2 can both miss.
    """

    model_config = ConfigDict(frozen=True)

    value: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class DecisionRecord(BaseModel):
    """The Governance Framework's minimum record (section 1).

    `prompt_version` and `requirement_ids` are what let the question "was this
    behaviour intended?" be answered after an incident.
    """

    model_config = ConfigDict(use_enum_values=False)

    decision_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ticket_id: str
    stage: Stage

    input_summary: str = ""
    model_name: str = ""
    model_version: str = ""

    prediction_value: str | None = None
    prediction_confidence: float | None = None
    alternatives: list[ClassificationAlternative] = Field(default_factory=list)
    sources_used: list[RetrievedPassage] = Field(default_factory=list)
    threshold_applied: float | None = None

    action_taken: str = ""
    reason: str = ""
    guardrail_results: dict[str, Any] = Field(default_factory=dict)

    prompt_version: str = ""
    requirement_ids: list[str] = Field(default_factory=list)

    terminal_state: TerminalState | None = None
