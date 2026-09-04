"""Conformance tests against the real supplied data.

Fixture tests prove the code does what I expected. These prove it survives the
data as it actually is — which is the difference the Build Specification is
getting at when it warns that systems working one ticket at a time "collapse on
the fortieth consecutive ticket".

The full development and validation sets are not committed (the Submission Guide
asks for small samples only), so those tests skip when the pack is absent. The
committed sample and the documentation corpus always run, so CI stays meaningful
on a clean checkout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ingest import normalise_batch, normalise_ticket
from src.models import Channel

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
PACK = (
    REPO.parent
    / "FDE_Capstone_Complete-20260821T084330Z-1-001"
    / "FDE_Capstone_Complete"
    / "Capstone_Pack"
    / "05_Datasets"
)

DENY_LIST_INTENTS = {
    "security_incident",
    "compliance_request",
    "feature_request",
    "unclear_request",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _pack_tickets(name: str):
    path = PACK / name
    if not path.exists():
        pytest.skip(f"{name} not present (full sets are not committed)")
    return _load(path)


# --- the committed sample always runs ----------------------------------------


def test_sample_covers_all_four_channels():
    tickets, rejected = normalise_batch(_load(DATA / "sample_tickets.json"))

    assert rejected == []
    assert {t.channel for t in tickets} == {
        Channel.EMAIL,
        Channel.CHAT,
        Channel.DOCS_COMMENT,
        Channel.FORUM,
    }


def test_sample_covers_every_deny_list_intent():
    """D1 depends on these four classes, so the sample must exercise all of them."""
    tickets, _ = normalise_batch(_load(DATA / "sample_tickets.json"))
    intents = {t.labels.intent for t in tickets if t.labels}

    assert DENY_LIST_INTENTS <= intents


def test_documentation_corpus_loads_and_every_article_has_content():
    docs = _load(DATA / "documentation.json")

    assert len(docs) == 29
    assert all(d["content"].strip() for d in docs)
    assert all(d["doc_id"].startswith("DOC-") for d in docs)


def test_every_expected_doc_id_in_the_sample_resolves_to_the_corpus():
    """A6 is checked by following a citation. Unresolvable IDs must not exist."""
    corpus_ids = {d["doc_id"] for d in _load(DATA / "documentation.json")}
    tickets, _ = normalise_batch(_load(DATA / "sample_tickets.json"))

    for ticket in tickets:
        if ticket.labels:
            assert set(ticket.labels.expected_doc_ids) <= corpus_ids


# --- the full sets, when the pack is available -------------------------------


def test_all_500_development_tickets_normalise_without_rejection():
    tickets, rejected = normalise_batch(_pack_tickets("development_tickets.json"))

    assert rejected == []
    assert len(tickets) == 500


def test_all_80_validation_tickets_normalise_without_rejection():
    tickets, rejected = normalise_batch(_pack_tickets("validation_tickets.json"))

    assert rejected == []
    assert len(tickets) == 80


def test_no_development_ticket_normalises_to_an_unknown_channel():
    """An unknown channel would mean the schema shifted under us."""
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))

    assert [t.ticket_id for t in tickets if t.channel is Channel.UNKNOWN] == []


def test_every_development_ticket_yields_a_unique_id():
    """A8 reconciles by identity, so duplicate ids would break the accounting."""
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))

    ids = [t.ticket_id for t in tickets]
    assert len(ids) == len(set(ids))


def test_empty_subject_tickets_still_produce_search_text():
    """155 of the 500 have no subject; retrieval must still have something."""
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))
    subjectless = [t for t in tickets if not t.subject]

    assert len(subjectless) > 100
    assert all(t.search_text for t in subjectless)


def test_no_development_ticket_is_wholly_empty():
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))

    assert [t.ticket_id for t in tickets if t.is_empty] == []


def test_deny_list_labels_are_perfectly_consistent_across_the_development_set():
    """The premise of D1 layer 1: the four intents are exactly the forbidden set.

    If this ever fails, the safety gate's definition is wrong and the design
    document's governance argument needs revisiting.
    """
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))

    for ticket in tickets:
        assert ticket.labels is not None
        expected = ticket.labels.intent in DENY_LIST_INTENTS
        assert ticket.labels.must_not_auto_respond is expected, ticket.ticket_id


def test_no_deny_list_ticket_is_ever_labelled_auto_respond():
    """A governance invariant. Auto-answering any of these is a failure, not a loss."""
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))

    deny_listed = [t for t in tickets if t.labels and t.labels.must_not_auto_respond]

    # Guard against a vacuous pass: if label parsing ever regressed, `offenders`
    # would be empty and this test could never fail.
    assert len(deny_listed) == 87

    offenders = [t.ticket_id for t in deny_listed if t.labels.expected_route == "auto_respond"]

    assert offenders == []


def test_answerable_from_docs_agrees_with_expected_doc_ids():
    """Used by D2/D6: 'groundable' must mean the same thing in both fields."""
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))

    for ticket in tickets:
        assert ticket.labels is not None
        assert ticket.labels.answerable_from_docs is bool(ticket.labels.expected_doc_ids), (
            ticket.ticket_id
        )


def test_every_expected_doc_id_across_the_development_set_resolves():
    corpus_ids = {d["doc_id"] for d in _load(DATA / "documentation.json")}
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))

    unresolvable = {
        doc_id
        for t in tickets
        if t.labels
        for doc_id in t.labels.expected_doc_ids
        if doc_id not in corpus_ids
    }

    assert unresolvable == set()


# --- robustness against input the schema does not promise --------------------


def test_a_batch_containing_junk_keeps_the_good_tickets_and_records_the_rest():
    """A9: no ticket is silently dropped, and one bad record cannot stop a run."""
    raws = _load(DATA / "sample_tickets.json") + [
        {"channel": "email", "body": "no id here"},
        "not a ticket at all",
        {},
    ]

    tickets, rejected = normalise_batch(raws)

    assert len(tickets) == 8
    assert len(rejected) == 3
    assert all("index" in r and "reason" in r for r in rejected)


def test_a_ticket_of_pure_whitespace_is_flagged_not_dropped():
    ticket = normalise_ticket(
        {"ticket_id": "HID-0001", "channel": "chat", "subject": "  ", "body": "\n\t "}
    )

    assert ticket.is_empty is True
    assert ticket.ticket_id == "HID-0001"


def test_feature_request_and_unclear_request_can_never_ground():
    """The empirical basis of the ~1.1 residual in design D1 and section 11.

    D2's grounding conjunction requires a retrievable passage before anything can
    be auto-answered. These two intents have none, on either split, so they are
    structurally safe regardless of what the classifier does. Together with the
    ungrounded security_incident and compliance_request tickets that is 56 of the
    87 deny-list tickets protected by grounding alone.

    If this ever changes, the governance argument in section 11 weakens and the
    residual estimate must be recomputed.
    """
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))

    for intent in ("feature_request", "unclear_request"):
        population = [t for t in tickets if t.labels and t.labels.intent == intent]
        assert population, f"no {intent} tickets found — the premise cannot be tested"
        groundable = [t for t in population if t.labels.answerable_from_docs]
        assert groundable == [], f"{intent} is no longer structurally ungroundable"


def test_exactly_56_deny_list_tickets_are_structurally_protected_by_grounding():
    """Quantifies the claim made in design D1 and section 11."""
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))
    deny_listed = [t for t in tickets if t.labels and t.labels.must_not_auto_respond]

    ungroundable = [t for t in deny_listed if not t.labels.answerable_from_docs]

    assert len(deny_listed) == 87
    assert len(ungroundable) == 56


def test_no_development_ticket_needs_a_degraded_field():
    """The supplied data is clean; degradation should only fire on real anomalies."""
    tickets, _ = normalise_batch(_pack_tickets("development_tickets.json"))

    assert [t.ticket_id for t in tickets if t.degraded_fields] == []
