"""Guardrails — A7, FR-15, and Governance Framework section 4.

Five checks run on every generated response, in production, and every one can
block. The Governance Framework sets the standard plainly: "Guardrails that only
run in testing are not guardrails; they are tests." Build Spec §08 names the
matching failure: "Guardrails present in the code but disabled by a flag during
the run."

**There is no flag.** `Validator` takes no parameter that disables a check, and a
test asserts that its signature contains no such parameter. A guardrail that can
be switched off is not a control, and the demonstration for A7 has to show a real
block rather than a configuration.

| Guardrail | Checks | On fire |
|---|---|---|
| `pii` | Another customer's details, keys, tokens, account numbers | Block. Never redact and send |
| `grounding` | Every claim traceable to a passage that resolves | Block, with the unsupported part named |
| `instruction_integrity` | The ticket has not redirected the system | Block, and record the input for review |
| `tone_and_scope` | No commitment about refunds, credits or dates | Block |
| `confidence_floor` | The routing threshold was actually applied | Block |

Blocking routes the ticket to a human as `ESCALATED_AFTER_BLOCK`. Design §2.3
counts that inside the escalation rate rather than treating it as a third
outcome, because a blocked response still leaves a customer without an answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.generate import GeneratedAnswer
from src.models import DecisionRecord, NormalisedTicket, Stage

GUARDRAIL_NAMES = (
    "pii",
    "grounding",
    "instruction_integrity",
    "tone_and_scope",
    "confidence_floor",
)

# --- private data -------------------------------------------------------------
# Credential shapes and identifiers, not the words "key" or "password".
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_SECRET = re.compile(
    r"\b(?:gsk_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{12,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
)
# Long digit runs: card and account numbers, allowing spaces or dashes.
_ACCOUNT = re.compile(r"\b(?:\d[ -]?){13,19}\b")

# --- prompt injection ---------------------------------------------------------
# Phrases that attempt to redirect the system, rather than any use of "ignore".
_INJECTION = re.compile(
    r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+"
    r"(?:instructions?|rules?|prompts?)"
    r"|disregard\s+(?:your|all|the)\s+(?:rules?|instructions?|prompts?)"
    r"|forget\s+(?:the\s+above|your\s+instructions?|everything)"
    r"|you\s+are\s+now\s+(?:an?\s+)?(?:unrestricted|different|new)"
    r"|reveal\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?)"
    r"|print\s+your\s+instructions?"
    r"|^\s*system\s*:",
    re.IGNORECASE | re.MULTILINE,
)
# Text from our own system prompt appearing in an answer means it leaked.
_PROMPT_LEAK = re.compile(
    r"you draft replies for cloudserve|my instructions say|system prompt", re.IGNORECASE
)

# --- commitments --------------------------------------------------------------
# Statements about what CloudServe will do. Describing documentation is fine.
_COMMITMENT = re.compile(
    r"\b(?:we\s+(?:have\s+)?(?:issued|refunded|credited|will\s+(?:refund|credit|fix|resolve|deploy)))"
    r"|\bhas\s+been\s+(?:refunded|credited|issued)\b"
    # A refund or credit stated as done, with or without an actor: "Refund issued",
    # "a credit has been applied". Daniel: billing disputes "become contractual
    # quickly and nothing automated should be making commitments about money".
    r"|\b(?:refund|credit)s?\b[^.]{0,30}?\b(?:issued|processed|applied|granted|approved)\b"
    r"|\b(?:issued|processed|applied|granted|approved)\b[^.]{0,20}?\b(?:refund|credit)s?\b"
    r"|\bi\s+guarantee\b|\bwe\s+guarantee\b"
    r"|\bwill\s+be\s+(?:fixed|resolved|released|available)\s+(?:by|on|within)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardrailResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class ValidationResult:
    """What was checked, what was found, and whether anything may be sent."""

    checks: dict[str, GuardrailResult] = field(default_factory=dict)
    released_text: str = ""

    @property
    def blocked_by(self) -> tuple[str, ...]:
        return tuple(name for name, check in self.checks.items() if not check.passed)

    @property
    def passed(self) -> bool:
        return not self.blocked_by

    def to_decision_record(
        self, ticket_id: str, prompt_version: str = ""
    ) -> DecisionRecord:
        return DecisionRecord(
            ticket_id=ticket_id,
            stage=Stage.VALIDATION,
            action_taken="release" if self.passed else "block",
            reason=(
                "All guardrails passed; the response was released."
                if self.passed
                else "Blocked by " + ", ".join(self.blocked_by) + "."
            ),
            guardrail_results={
                name: ("pass" if check.passed else "block")
                for name, check in self.checks.items()
            },
            prompt_version=prompt_version,
            requirement_ids=["FR-15"],
        )


class Validator:
    """Runs every guardrail on every response. No check can be disabled."""

    def __init__(self, known_chunk_ids: set[str] | None = None) -> None:
        # When supplied, every citation is re-resolved against the corpus, which
        # is how A6 is actually checked: follow the citation to the passage.
        self._known_chunk_ids = known_chunk_ids

    def validate(
        self,
        answer: GeneratedAnswer,
        ticket: NormalisedTicket,
        confidence_applied: bool,
    ) -> ValidationResult:
        checks = {
            "pii": self._pii(answer, ticket),
            "grounding": self._grounding(answer),
            "instruction_integrity": self._instruction_integrity(answer, ticket),
            "tone_and_scope": self._tone_and_scope(answer),
            "confidence_floor": self._confidence_floor(confidence_applied),
        }
        blocked = any(not check.passed for check in checks.values())
        return ValidationResult(
            checks=checks,
            # Never redact and send: a blocked response releases nothing at all.
            released_text="" if blocked else answer.customer_text,
        )

    # -- 1. private data -------------------------------------------------------

    @staticmethod
    def _pii(answer: GeneratedAnswer, ticket: NormalisedTicket) -> GuardrailResult:
        """Block on identifiers the customer did not already supply.

        An address the customer wrote in their own ticket is not a leak, and
        treating it as one escalates a ticket that was fine.
        """
        text = answer.text
        supplied = set(_EMAIL.findall(ticket.search_text))

        found = [e for e in _EMAIL.findall(text) if e not in supplied]
        found += _SECRET.findall(text)
        found += [m for m in _ACCOUNT.findall(text) if len(re.sub(r"\D", "", m)) >= 13]

        if found:
            return GuardrailResult(
                "pii", False, f"Response contained {len(found)} identifier(s) not in the ticket."
            )
        return GuardrailResult("pii", True)

    # -- 2. grounding ----------------------------------------------------------

    def _grounding(self, answer: GeneratedAnswer) -> GuardrailResult:
        if not answer.citations:
            return GuardrailResult(
                "grounding", False, "Response carried no citation resolving to a retrieved passage."
            )
        if answer.unresolved_markers:
            markers = ", ".join(str(m) for m in answer.unresolved_markers)
            return GuardrailResult(
                "grounding", False, f"Response cited passage(s) it was never given: {markers}."
            )
        if self._known_chunk_ids is not None:
            missing = [
                c.chunk_id for c in answer.citations if c.chunk_id not in self._known_chunk_ids
            ]
            if missing:
                return GuardrailResult(
                    "grounding",
                    False,
                    f"Citation(s) did not resolve to the corpus: {', '.join(missing)}.",
                )
        return GuardrailResult("grounding", True)

    # -- 3. instruction integrity ---------------------------------------------

    @staticmethod
    def _instruction_integrity(
        answer: GeneratedAnswer, ticket: NormalisedTicket
    ) -> GuardrailResult:
        attempt = _INJECTION.search(ticket.search_text)
        if attempt:
            # Governance Framework: record the input for review.
            excerpt = ticket.search_text[:160]
            return GuardrailResult(
                "instruction_integrity",
                False,
                f"Ticket attempted to redirect the system. Input recorded: {excerpt!r}",
            )
        if _PROMPT_LEAK.search(answer.text):
            return GuardrailResult(
                "instruction_integrity", False, "Response echoed the system instructions."
            )
        return GuardrailResult("instruction_integrity", True)

    # -- 4. tone and scope -----------------------------------------------------

    @staticmethod
    def _tone_and_scope(answer: GeneratedAnswer) -> GuardrailResult:
        match = _COMMITMENT.search(answer.text)
        if match:
            return GuardrailResult(
                "tone_and_scope",
                False,
                f"Response made a commitment the system cannot make: {match.group(0)!r}",
            )
        return GuardrailResult("tone_and_scope", True)

    # -- 5. confidence floor ---------------------------------------------------

    @staticmethod
    def _confidence_floor(applied: bool) -> GuardrailResult:
        """A missing confidence score is not a high one (Governance Framework §4)."""
        if not applied:
            return GuardrailResult(
                "confidence_floor", False, "The routing threshold was not applied to this response."
            )
        return GuardrailResult("confidence_floor", True)
