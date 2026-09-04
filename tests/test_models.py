"""Typed values shared across component boundaries.

Two of these are defined before the components that produce them, because both
are read by later stages and retrofitting a type after untyped dicts are already
flowing through the pipeline is expensive.

`RetrievedPassage` is what makes design decision D7 enforceable: citations are
constructed from retrieved chunk identifiers and re-resolved against the store,
never emitted free-form by the model. A6 is checked by following a citation to
the passage it claims to support, so the passage must carry enough to be found
again.

`ClassificationAlternative` is read by D1 layer 3 (alternatives-aware
abstention), which escalates when a deny-listed intent appears anywhere in the
classifier's alternatives regardless of the top-1 label.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import ClassificationAlternative, DecisionRecord, RetrievedPassage, Stage


def _passage(**overrides):
    base = {
        "doc_id": "DOC-AUTH-001",
        "chunk_id": "DOC-AUTH-001#0",
        "title": "Resolving invalid credential errors on login",
        "text": "A locked account displays a red banner and unlocks automatically after thirty minutes.",
        "score": 0.82,
        "char_start": 0,
        "char_end": 86,
    }
    base.update(overrides)
    return RetrievedPassage(**base)


# --- RetrievedPassage: enough to re-resolve a citation (A6, D7) ---------------


def test_a_passage_carries_the_document_it_came_from():
    assert _passage().doc_id == "DOC-AUTH-001"


def test_a_passage_carries_a_chunk_id_so_the_exact_span_can_be_found_again():
    assert _passage().chunk_id == "DOC-AUTH-001#0"


def test_a_passage_carries_character_offsets_for_verification():
    """Re-resolution checks the cited span against the corpus, not just the doc."""
    passage = _passage(char_start=120, char_end=240)

    assert passage.char_start == 120
    assert passage.char_end == 240


def test_a_score_outside_zero_to_one_is_rejected():
    """A relevance floor is meaningless if scores are not on a known scale."""
    with pytest.raises(ValidationError):
        _passage(score=1.4)


def test_a_negative_score_is_rejected():
    with pytest.raises(ValidationError):
        _passage(score=-0.1)


def test_a_passage_without_a_doc_id_is_rejected_because_it_could_not_be_cited():
    with pytest.raises(ValidationError):
        RetrievedPassage(chunk_id="x#0", text="orphan", score=0.5)


def test_the_citation_reference_is_the_document_id():
    """What appears in the answer text. Readers cite documents, not chunks."""
    assert _passage().citation == "DOC-AUTH-001"


def test_passages_are_immutable_so_a_later_stage_cannot_rewrite_a_citation():
    passage = _passage()

    with pytest.raises(ValidationError):
        passage.doc_id = "DOC-BILL-003"


# --- ClassificationAlternative: read by D1 layer 3 ----------------------------


def test_an_alternative_carries_a_value_and_a_confidence():
    alternative = ClassificationAlternative(value="account_access", confidence=0.06)

    assert alternative.value == "account_access"
    assert alternative.confidence == pytest.approx(0.06)


def test_an_alternative_confidence_outside_zero_to_one_is_rejected():
    with pytest.raises(ValidationError):
        ClassificationAlternative(value="account_access", confidence=1.2)


# --- both flow through the decision record ------------------------------------


def test_a_decision_record_accepts_typed_passages_and_alternatives():
    record = DecisionRecord(
        ticket_id="DEV-0001",
        stage=Stage.RETRIEVAL,
        sources_used=[_passage()],
        alternatives=[ClassificationAlternative(value="account_access", confidence=0.06)],
    )

    assert record.sources_used[0].doc_id == "DOC-AUTH-001"
    assert record.alternatives[0].value == "account_access"


def test_a_decision_record_coerces_plain_dicts_into_typed_values():
    """The log stores JSON, so reading a record back must rebuild the types."""
    record = DecisionRecord(
        ticket_id="DEV-0001",
        stage=Stage.RETRIEVAL,
        sources_used=[{"doc_id": "DOC-API-001", "chunk_id": "DOC-API-001#1", "score": 0.7}],
        alternatives=[{"value": "rate_limit", "confidence": 0.11}],
    )

    assert isinstance(record.sources_used[0], RetrievedPassage)
    assert isinstance(record.alternatives[0], ClassificationAlternative)
