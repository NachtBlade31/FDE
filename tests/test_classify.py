"""Classification tests — A3, FR-04, FR-05, FR-14, and decision D1.

A3: "Every ticket is classified for intent and urgency, with a numeric confidence
attached", judged by the output carrying a class and a confidence between zero
and one.

Build Spec section 03 adds three requirements that shape the design:
  - a defined fallback rather than an exception when it cannot classify
  - the alternatives it considered, not only the option it chose
  - a confidence that reflects the actual probability of being correct

The last is why the confidence a model reports about itself is never trusted on
its own. It is one input to the routing conjunction, and it is checked against
observed accuracy in the calibration table before any threshold is defended.
"""

from __future__ import annotations

import json

import pytest

from src.classify import (
    DENY_LIST_INTENTS,
    INTENT_CLASSES,
    UNCLEAR,
    Classifier,
    parse_classification,
)
from src.models import NormalisedTicket, Urgency


def _ticket(body="We are getting 429 responses from the api", **kw):
    return NormalisedTicket(
        ticket_id=kw.pop("ticket_id", "DEV-0001"),
        channel=kw.pop("channel", "email"),
        subject=kw.pop("subject", ""),
        original_body=body,
        **kw,
    )


class StubClient:
    """Stands in for LLMClient, returning scripted completion text."""

    def __init__(self, replies=None, ok=True):
        from src.llm_client import CallStats

        self._replies = list(replies or [])
        self._ok = ok
        self.calls: list[tuple[str, str]] = []
        self.stats = CallStats()

    def complete(self, system, user, max_tokens=512):
        from src.llm_client import CompletionResult

        self.calls.append((system, user))
        if not self._ok:
            return CompletionResult(ok=False, error="provider unavailable")
        text = self._replies.pop(0) if self._replies else json.dumps(
            {"intent": "rate_limit", "urgency": "medium", "confidence": 0.9, "alternatives": []}
        )
        return CompletionResult(text=text, ok=True)


# --- the class list is the contract -------------------------------------------


def test_there_are_twenty_two_intent_classes():
    assert len(INTENT_CLASSES) == 22


def test_the_deny_list_is_a_subset_of_the_intent_classes():
    assert DENY_LIST_INTENTS < INTENT_CLASSES


def test_the_deny_list_is_exactly_the_four_governed_intents():
    assert DENY_LIST_INTENTS == {
        "security_incident",
        "compliance_request",
        "feature_request",
        "unclear_request",
    }


# --- A3: every ticket gets a class, an urgency and a confidence ---------------


def test_a_ticket_is_classified_with_intent_urgency_and_confidence():
    result = Classifier(StubClient()).classify(_ticket())

    assert result.intent in INTENT_CLASSES
    assert isinstance(result.urgency, Urgency)
    assert 0.0 <= result.confidence <= 1.0


def test_the_alternatives_considered_are_recorded():
    reply = json.dumps(
        {
            "intent": "rate_limit",
            "urgency": "medium",
            "confidence": 0.7,
            "alternatives": [{"intent": "quota_or_overage", "confidence": 0.2}],
        }
    )
    result = Classifier(StubClient([reply])).classify(_ticket())

    assert result.alternatives[0].value == "quota_or_overage"
    assert result.alternatives[0].confidence == pytest.approx(0.2)


def test_the_ticket_text_is_sent_as_the_user_message_not_the_system_message():
    """FR-14: customer text must never be concatenated into the instructions."""
    client = StubClient()
    Classifier(client).classify(_ticket(body="CUSTOMER WROTE THIS"))

    system, user = client.calls[0]
    assert "CUSTOMER WROTE THIS" in user
    assert "CUSTOMER WROTE THIS" not in system


# --- Build Spec 03: a defined fallback, never an exception --------------------


def test_an_unparseable_reply_falls_back_rather_than_raising():
    result = Classifier(StubClient(["this is not json at all"])).classify(_ticket())

    assert result.intent == UNCLEAR
    assert result.confidence == 0.0
    assert result.fallback_reason


def test_an_unknown_intent_in_the_reply_falls_back():
    reply = json.dumps({"intent": "teleportation_error", "urgency": "high", "confidence": 0.99})
    result = Classifier(StubClient([reply])).classify(_ticket())

    assert result.intent == UNCLEAR


def test_a_provider_failure_falls_back_rather_than_raising():
    """A11: a classification failure must not stop the run."""
    result = Classifier(StubClient(ok=False)).classify(_ticket())

    assert result.intent == UNCLEAR
    assert result.confidence == 0.0
    assert "unavailable" in result.fallback_reason.lower()


def test_an_empty_ticket_is_classified_unclear_without_calling_the_model():
    """Nothing to classify. Spending a call on it wastes the free tier."""
    client = StubClient()
    result = Classifier(client).classify(_ticket(body="   ", subject=""))

    assert result.intent == UNCLEAR
    assert client.calls == []


def test_the_fallback_class_is_itself_deny_listed():
    """A ticket we could not classify must never be auto-answered.

    This is what makes the fallback safe: failing to classify routes into the
    deny-list rather than into a permissive default.
    """
    assert UNCLEAR in DENY_LIST_INTENTS


# --- confidence is bounded and coerced, never trusted blindly ----------------


def test_a_confidence_above_one_is_clamped():
    reply = json.dumps({"intent": "rate_limit", "urgency": "low", "confidence": 4.2})
    assert Classifier(StubClient([reply])).classify(_ticket()).confidence <= 1.0


def test_a_missing_confidence_is_treated_as_zero_not_as_certainty():
    """Governance Framework: 'A missing confidence score is not a high one.'"""
    reply = json.dumps({"intent": "rate_limit", "urgency": "low"})
    assert Classifier(StubClient([reply])).classify(_ticket()).confidence == 0.0


def test_an_unknown_urgency_degrades_to_unknown_not_to_medium():
    reply = json.dumps({"intent": "rate_limit", "urgency": "catastrophic", "confidence": 0.5})
    assert Classifier(StubClient([reply])).classify(_ticket()).urgency is Urgency.UNKNOWN


# --- parsing is robust to what models actually emit ---------------------------


def test_a_reply_wrapped_in_code_fences_is_parsed():
    reply = '```json\n{"intent": "billing_query", "urgency": "low", "confidence": 0.8}\n```'
    assert parse_classification(reply).intent == "billing_query"


def test_a_reply_with_prose_around_the_json_is_parsed():
    reply = 'Here is my answer:\n{"intent": "onboarding", "urgency": "low", "confidence": 0.6}\nHope that helps.'
    assert parse_classification(reply).intent == "onboarding"


def test_a_reply_with_no_json_returns_the_fallback():
    assert parse_classification("I could not decide").intent == UNCLEAR


# --- determinism (A5) ---------------------------------------------------------


def test_the_same_ticket_classifies_identically():
    ticket = _ticket()
    reply = json.dumps({"intent": "rate_limit", "urgency": "medium", "confidence": 0.9})

    first = Classifier(StubClient([reply])).classify(ticket)
    second = Classifier(StubClient([reply])).classify(ticket)

    assert (first.intent, first.urgency, first.confidence) == (
        second.intent,
        second.urgency,
        second.confidence,
    )


# --- the decision record it produces (A8) ------------------------------------


def test_classification_produces_a_decision_record_with_the_alternatives():
    reply = json.dumps(
        {
            "intent": "rate_limit",
            "urgency": "medium",
            "confidence": 0.9,
            "alternatives": [{"intent": "quota_or_overage", "confidence": 0.05}],
        }
    )
    result = Classifier(StubClient([reply])).classify(_ticket())

    record = result.to_decision_record(prompt_version="PR-01 v1.0")

    assert record.stage.value == "classification"
    assert record.prediction_value == "rate_limit"
    assert record.prediction_confidence == pytest.approx(0.9)
    assert record.alternatives[0].value == "quota_or_overage"
    assert "FR-04" in record.requirement_ids
