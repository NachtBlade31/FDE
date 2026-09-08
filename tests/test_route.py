"""Routing tests — A5, FR-08, FR-09, FR-10, FR-16, FR-17, FR-22, and decisions D1/D2/D3.

A5: "Routing applies a threshold you set, and the same input produces the same
routing decision." Judged by running the same ticket twice.

Build Spec section 03 requires routing to:
  - decide between answering automatically and escalating, on a threshold
    determined from data
  - be deterministic
  - record the reason in language a support manager could read
  - carry the drafted summary and the retrieved sources into escalations

The router decides *eligibility* to auto-respond, before generation. Guardrails
run after generation and can still block, which is why a blocked response becomes
ESCALATED_AFTER_BLOCK rather than being decided here.
"""

from __future__ import annotations

import pytest

from src.classify import Classification
from src.models import ClassificationAlternative, NormalisedTicket, RetrievedPassage, Urgency
from src.retrieve import RetrievalResult
from src.route import Action, Router, RoutingDecision


def _ticket(body="We are seeing 429 responses from the api", **kw):
    return NormalisedTicket(
        ticket_id=kw.pop("ticket_id", "DEV-0001"),
        channel=kw.pop("channel", "email"),
        original_body=body,
        **kw,
    )


def _classification(intent="rate_limit", confidence=0.95, alternatives=(), **kw):
    return Classification(
        ticket_id=kw.pop("ticket_id", "DEV-0001"),
        intent=intent,
        urgency=kw.pop("urgency", Urgency.MEDIUM),
        confidence=confidence,
        alternatives=tuple(
            ClassificationAlternative(value=v, confidence=c) for v, c in alternatives
        ),
        **kw,
    )


def _passage(doc_id="DOC-API-001", score=0.72):
    return RetrievedPassage(
        doc_id=doc_id, chunk_id=f"{doc_id}#0", text="Rate limits apply per organisation.",
        title="Understanding rate limits", score=score, char_start=0, char_end=36,
    )


def _retrieval(passages=None, rejected=None, top_score=0.72, floor=0.40):
    return RetrievalResult(
        passages=list(passages if passages is not None else [_passage()]),
        rejected=list(rejected or []),
        top_score=top_score,
        floor_applied=floor,
    )


@pytest.fixture()
def router():
    return Router(margin_threshold=0.80)


def _route(router, ticket=None, classification=None, retrieval=None):
    return router.route(
        ticket or _ticket(),
        classification or _classification(),
        retrieval if retrieval is not None else _retrieval(),
    )


# --- the happy path -----------------------------------------------------------


def test_a_confident_grounded_ordinary_ticket_is_eligible_to_auto_respond(router):
    assert _route(router).action is Action.AUTO_RESPOND


def test_the_reason_is_readable_by_a_support_manager(router):
    """Build Spec 03: 'Records the reason for the decision in language a support
    manager could read.'"""
    reason = _route(router).reason

    assert "confidence" in reason.lower() or "margin" in reason.lower()
    assert "DOC-API-001" in reason


# --- D1 layer 1: the predicted intent is deny-listed --------------------------


@pytest.mark.parametrize(
    "intent",
    ["security_incident", "compliance_request", "feature_request", "unclear_request"],
)
def test_a_deny_listed_intent_always_escalates(router, intent):
    decision = _route(router, classification=_classification(intent=intent, confidence=0.99))

    assert decision.action is Action.ESCALATE
    assert decision.checks["deny_list"] is False


def test_no_confidence_can_override_the_deny_list(router):
    """The governance statement: this must never be auto-answered."""
    decision = _route(
        router, classification=_classification(intent="security_incident", confidence=1.0)
    )

    assert decision.action is Action.ESCALATE


# --- D1 layer 2: the lexical pre-screen, independent of the classifier --------


def test_marker_text_escalates_even_when_classification_says_otherwise(router):
    """The case layer 1 cannot catch: a misclassified security incident.

    The classifier is confidently wrong; the raw text still says 'breach'.
    """
    decision = _route(
        router,
        ticket=_ticket(body="We think there has been a breach of our account by a former employee"),
        classification=_classification(intent="account_access", confidence=0.99),
    )

    assert decision.action is Action.ESCALATE
    assert decision.checks["lexical_screen"] is False


def test_the_lexical_screen_names_the_term_that_fired(router):
    decision = _route(
        router,
        ticket=_ticket(body="our auditor has asked for a data retention policy statement"),
        classification=_classification(intent="billing_query", confidence=0.99),
    )

    assert "auditor" in decision.reason or "retention" in decision.reason


def test_ordinary_text_does_not_trip_the_lexical_screen(router):
    decision = _route(router, ticket=_ticket(body="how do I paginate the results endpoint"))

    assert decision.checks["lexical_screen"] is True


# --- D1 layer 3: alternatives-aware abstention --------------------------------


def test_a_deny_listed_alternative_escalates_regardless_of_the_top_choice(router):
    """Fires where layers 1 and 2 both miss: an uncertain misclassification."""
    decision = _route(
        router,
        classification=_classification(
            intent="account_access",
            confidence=0.55,
            alternatives=(("security_incident", 0.40),),
        ),
    )

    assert decision.action is Action.ESCALATE
    assert decision.checks["alternatives"] is False


def test_an_ordinary_alternative_does_not_escalate(router):
    decision = _route(
        router,
        classification=_classification(
            intent="rate_limit", confidence=0.95, alternatives=(("quota_or_overage", 0.03),)
        ),
    )

    assert decision.checks["alternatives"] is True


# --- D-29: the threshold is on margin, not raw confidence --------------------


def test_a_narrow_margin_escalates_even_at_high_confidence(router):
    """Self-reported confidence puts 99 of 100 predictions in one band, so the
    threshold is swept on the margin between top-1 and the best alternative."""
    decision = _route(
        router,
        classification=_classification(
            intent="rate_limit", confidence=0.95, alternatives=(("quota_or_overage", 0.45),)
        ),
    )

    assert decision.action is Action.ESCALATE
    assert decision.checks["margin"] is False


def test_a_wide_margin_passes_the_threshold(router):
    decision = _route(
        router,
        classification=_classification(
            intent="rate_limit", confidence=0.95, alternatives=(("quota_or_overage", 0.02),)
        ),
    )

    assert decision.checks["margin"] is True


def test_no_alternatives_means_the_margin_is_the_confidence(router):
    decision = _route(router, classification=_classification(confidence=0.90, alternatives=()))

    assert decision.checks["margin"] is True


def test_a_zero_confidence_fallback_escalates(router):
    """Governance Framework: a missing confidence score is not a high one."""
    decision = _route(
        router, classification=_classification(intent="rate_limit", confidence=0.0)
    )

    assert decision.action is Action.ESCALATE


# --- D6/FR-07: nothing retrieved means nothing to ground an answer in --------


def test_no_retrieved_passages_escalates(router):
    decision = _route(router, retrieval=_retrieval(passages=[], top_score=0.0))

    assert decision.action is Action.ESCALATE
    assert decision.checks["grounded"] is False


def test_the_escalation_says_whether_anything_was_close(router):
    """'Nothing cleared the floor' and 'nothing was close' are different answers
    at incident review, and only one of them is actionable for an agent."""
    decision = _route(
        router,
        retrieval=_retrieval(
            passages=[], rejected=[_passage(score=0.38)], top_score=0.38, floor=0.40
        ),
    )

    assert "0.38" in decision.reason
    assert "0.40" in decision.reason


def test_nothing_retrieved_at_all_is_reported_differently(router):
    decision = _route(router, retrieval=_retrieval(passages=[], rejected=[], top_score=0.0))

    assert "no documentation" in decision.reason.lower()


# --- FR-22: the kill switch ---------------------------------------------------


def test_the_kill_switch_forces_escalation(router):
    stopped = Router(margin_threshold=0.80, kill_switch=lambda: True)

    decision = _route(stopped)

    assert decision.action is Action.ESCALATE
    assert decision.checks["kill_switch"] is False


def test_the_kill_switch_reason_is_explicit(router):
    stopped = Router(margin_threshold=0.80, kill_switch=lambda: True)

    assert "kill switch" in _route(stopped).reason.lower()


def test_the_kill_switch_is_checked_before_anything_else(router):
    """No model call, no retrieval reasoning: it must short-circuit."""
    stopped = Router(margin_threshold=0.80, kill_switch=lambda: True)

    decision = _route(stopped, classification=_classification(confidence=0.99))

    assert decision.checks["kill_switch"] is False
    assert decision.checks.get("margin") is None  # never evaluated


# --- A5: determinism ----------------------------------------------------------


def test_the_same_input_produces_the_same_decision(router):
    ticket, classification, retrieval = _ticket(), _classification(), _retrieval()

    first = router.route(ticket, classification, retrieval)
    second = router.route(ticket, classification, retrieval)

    assert first.action == second.action
    assert first.reason == second.reason
    assert first.checks == second.checks


# --- D3/FR-16: escalation carries context ------------------------------------


def test_an_escalation_carries_the_retrieved_sources(router):
    decision = _route(router, classification=_classification(intent="security_incident"))

    assert decision.escalation is not None
    assert decision.escalation.sources[0].doc_id == "DOC-API-001"


def test_an_escalation_states_what_the_system_was_unsure_about(router):
    """Daniel: 'I do not need it to be right. I need it to show its working.'"""
    decision = _route(
        router,
        classification=_classification(
            intent="account_access", confidence=0.55,
            alternatives=(("security_incident", 0.40),),
        ),
    )

    assert decision.escalation.uncertainty


def test_an_escalation_carries_the_predicted_intent_and_alternatives(router):
    decision = _route(
        router,
        classification=_classification(
            intent="database_issue", confidence=0.5, alternatives=(("performance_degradation", 0.4),)
        ),
    )

    assert decision.escalation.predicted_intent == "database_issue"
    assert decision.escalation.alternatives[0].value == "performance_degradation"


def test_an_escalation_carries_urgency_as_priority(router):
    """FR-17. Ravi: 'Same queue, completely different cost to me.'"""
    decision = _route(
        router,
        classification=_classification(intent="security_incident", urgency=Urgency.HIGH),
    )

    assert decision.escalation.priority is Urgency.HIGH


def test_an_auto_respond_decision_carries_no_escalation_payload(router):
    assert _route(router).escalation is None


# --- the decision record (A8) -------------------------------------------------


def test_routing_produces_a_decision_record_naming_the_threshold(router):
    record = _route(router).to_decision_record()

    assert record.stage.value == "routing"
    assert record.threshold_applied == pytest.approx(0.80)
    assert record.action_taken == "auto_respond"
    assert "FR-09" in record.requirement_ids


def test_an_escalation_record_carries_the_sources_used(router):
    record = _route(
        router, classification=_classification(intent="security_incident")
    ).to_decision_record()

    assert record.action_taken == "escalate"
    assert record.sources_used[0].doc_id == "DOC-API-001"


def test_every_check_is_recorded_not_only_the_one_that_failed(router):
    """Build Spec 03 Validate: 'Records what it checked and what it found.'"""
    decision = _route(router, classification=_classification(intent="security_incident"))

    assert set(decision.checks) >= {"kill_switch", "deny_list", "lexical_screen", "alternatives"}


# --- the conjunction: any single failure escalates ---------------------------


def test_all_conjuncts_must_pass_to_auto_respond(router):
    """D2: routing is a conjunction, not a threshold."""
    decision = _route(router)
    assert decision.action is Action.AUTO_RESPOND
    assert all(v for v in decision.checks.values())


def test_an_empty_ticket_escalates(router):
    decision = _route(
        router,
        ticket=_ticket(body="   "),
        classification=_classification(intent="unclear_request", confidence=0.0),
    )

    assert decision.action is Action.ESCALATE


# --- layer 3 needs a floor, or it escalates almost everything ----------------


def test_a_negligible_deny_listed_alternative_does_not_escalate():
    """Measured: without a floor, layer 3 caused 66% of all escalations.

    A model asked for its alternatives will list a deny-listed class at trivial
    confidence on most tickets. Treating a 2% alternative as a safety signal is
    not caution, it is noise, and it drove first contact resolution down to 52%
    against a 60% target while adding nothing the other layers did not catch.
    """
    router = Router(margin_threshold=0.0, abstention_floor=0.10)

    decision = router.route(
        _ticket(),
        _classification(
            intent="rate_limit", confidence=0.95, alternatives=(("feature_request", 0.02),)
        ),
        _retrieval(),
    )

    assert decision.checks["alternatives"] is True
    assert decision.action is Action.AUTO_RESPOND


def test_a_substantial_deny_listed_alternative_still_escalates():
    """The case layer 3 exists for: the classifier was genuinely torn."""
    router = Router(margin_threshold=0.0, abstention_floor=0.10)

    decision = router.route(
        _ticket(),
        _classification(
            intent="account_access", confidence=0.55, alternatives=(("security_incident", 0.40),)
        ),
        _retrieval(),
    )

    assert decision.checks["alternatives"] is False
    assert decision.action is Action.ESCALATE


def test_an_alternative_exactly_on_the_floor_escalates():
    """Ties resolve towards escalation, because the costs are asymmetric."""
    router = Router(margin_threshold=0.0, abstention_floor=0.10)

    decision = router.route(
        _ticket(),
        _classification(
            intent="rate_limit", confidence=0.9, alternatives=(("compliance_request", 0.10),)
        ),
        _retrieval(),
    )

    assert decision.checks["alternatives"] is False


def test_the_abstention_floor_is_recorded_in_the_reason():
    router = Router(margin_threshold=0.0, abstention_floor=0.10)

    decision = router.route(
        _ticket(),
        _classification(
            intent="account_access", confidence=0.5, alternatives=(("security_incident", 0.45),)
        ),
        _retrieval(),
    )

    assert "security_incident" in decision.reason


# --- the shipped vocabulary must be the curated one, not the rejected one -----


def test_the_shipped_vocabulary_is_the_curated_one():
    """scripts/derive_markers.py once overwrote this file with the list D-27 rejected.

    That swap is silent: the router still loads a vocabulary and every other test
    still passes, but the safety control becomes the one that fires on the word
    "only". The shipped file carries provenance so the swap is detectable.
    """
    import json
    from pathlib import Path

    payload = json.loads(
        (Path(__file__).resolve().parents[1] / "src" / "markers.json").read_text(encoding="utf-8")
    )

    assert payload.get("decision") == "D-27", "markers.json lost its provenance"
    assert payload["measured"]["security_incident_recall"] == 1.0


def test_the_shipped_vocabulary_contains_no_generic_template_artifacts():
    """The rejected derived list contained these; the curated list must not."""
    from src.route import load_markers

    markers = load_markers()
    generic = {"another", "call", "calls", "going", "look", "only", "once", "per", "nobody"}

    assert not (markers & generic), (
        f"generic tokens in the safety vocabulary: {sorted(markers & generic)}. "
        "These are template artifacts, not safety signals — see D-27."
    )


def test_the_shipped_vocabulary_covers_the_two_groundable_deny_list_intents():
    """Layer 2's real job. feature_request and unclear_request cannot ground and
    are protected structurally, so recall there is not the control that matters."""
    from src.route import load_markers

    markers = load_markers()

    assert {"breach", "compromised", "unauthorised"} <= markers  # security
    assert {"audit", "compliance", "retention", "residency"} <= markers  # compliance


def test_markers_that_catch_nothing_are_not_shipped():
    """A marker with zero true positives is noise wearing a control's name.

    Measured on the 500 development tickets: 'planned' caught 0 deny-listed
    tickets while causing 5 false escalations, and 'request' caught 2 - neither
    groundable - while causing 6. Removing both saved 11 false escalations with
    no change to deny-list recall.
    """
    from src.route import load_markers

    assert {"planned", "request"} & load_markers() == set()
