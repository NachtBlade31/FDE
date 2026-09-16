"""Retrieval tests — acceptance criterion A4, FR-06, FR-07.

A4: "Retrieval runs against the supplied documentation corpus and returns
identifiable source passages", judged by following the returned identifiers back
to real passages in the corpus rather than to invented references.

Build Specification section 03 additionally requires retrieval to:
  - return ranked passages with scores
  - return identifiers that resolve to the real corpus
  - apply a relevance threshold and return NOTHING rather than something irrelevant

That last point is a named failure mode in Build Spec section 08: "Retrieval that
returns something for every query regardless of relevance... Always returning
something hides failure." Design decision D6 makes it explicit, and 143 of the 500
development tickets have no supporting document at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models import RetrievedPassage
from src.retrieve import Corpus, Retriever

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return Corpus.from_file(DATA / "documentation.json")


@pytest.fixture(scope="module")
def retriever(corpus: Corpus) -> Retriever:
    return Retriever(corpus, relevance_floor=0.0)


# --- the corpus loads and is chunked into resolvable units -------------------


def test_the_corpus_loads_every_supplied_article(corpus):
    assert len(corpus.documents) == 29


def test_every_chunk_belongs_to_a_real_document(corpus):
    doc_ids = {d.doc_id for d in corpus.documents}

    assert all(chunk.doc_id in doc_ids for chunk in corpus.chunks)


def test_every_chunk_id_is_unique(corpus):
    ids = [chunk.chunk_id for chunk in corpus.chunks]

    assert len(ids) == len(set(ids))


def test_a_chunk_id_resolves_back_to_its_exact_text(corpus):
    """A6 is checked by following a citation. Resolution must be exact."""
    chunk = corpus.chunks[0]

    resolved = corpus.resolve(chunk.chunk_id)

    assert resolved is not None
    assert resolved.text == chunk.text


def test_an_unknown_chunk_id_resolves_to_nothing_rather_than_guessing(corpus):
    assert corpus.resolve("DOC-NOT-REAL#99") is None


def test_chunk_offsets_locate_the_text_inside_the_source_document(corpus):
    """The offsets are how a citation is verified against the original article."""
    chunk = corpus.chunks[0]
    document = corpus.document(chunk.doc_id)

    assert document is not None
    assert document.content[chunk.char_start : chunk.char_end] == chunk.text


# --- search returns ranked, typed, resolvable passages -----------------------


def test_search_returns_typed_passages(retriever):
    results = retriever.search("I cannot log in, invalid credentials")

    assert results
    assert all(isinstance(r, RetrievedPassage) for r in results)


def test_results_are_ranked_by_descending_score(retriever):
    results = retriever.search("my deployment keeps rolling back")

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_scores_are_within_zero_and_one(retriever):
    results = retriever.search("rate limit exceeded on the api")

    assert all(0.0 <= r.score <= 1.0 for r in results)


def test_top_k_limits_the_number_of_results(retriever):
    assert len(retriever.search("authentication", top_k=2)) <= 2


def test_every_returned_passage_resolves_to_the_corpus(retriever, corpus):
    """The core of A4: identifiers must not be invented."""
    results = retriever.search("invoice is higher than expected")

    for passage in results:
        assert corpus.resolve(passage.chunk_id) is not None
        assert corpus.document(passage.doc_id) is not None


# --- FR-07 / D6: returning nothing is a valid and often correct answer -------


def test_a_query_below_the_relevance_floor_returns_nothing(corpus):
    """Build Spec 08 names 'always returning something' as a failure mode."""
    strict = Retriever(corpus, relevance_floor=0.99)

    assert strict.search("please add dark mode to the dashboard") == []


def test_an_empty_query_returns_nothing_rather_than_arbitrary_passages(retriever):
    assert retriever.search("") == []
    assert retriever.search("   ") == []


def test_the_relevance_floor_is_applied_to_every_result(corpus):
    floored = Retriever(corpus, relevance_floor=0.15)

    results = floored.search("deployment health check failing")

    assert all(r.score >= 0.15 for r in results)


# --- retrieval quality: it must actually bridge symptom to article -----------


def test_retrieval_bridges_symptom_wording_to_the_article_title(retriever):
    """The central premise of the whole design, from Ines's interview.

    Keyword search cannot connect "my deployment keeps dying" to an article
    called "Resolving container health check failures". If semantic retrieval
    cannot either, assumption AS-01 has failed and the design needs revisiting.
    """
    results = retriever.search("my deployment keeps dying", top_k=5)

    assert results
    assert any(r.doc_id.startswith("DOC-DEPLOY") for r in results)


def test_an_authentication_symptom_retrieves_an_authentication_article(retriever):
    results = retriever.search("console says invalid credentials but my password is right", top_k=5)

    assert any(r.doc_id.startswith("DOC-AUTH") for r in results)


def test_a_rate_limit_symptom_retrieves_an_api_article(retriever):
    """A second structural case, from a different category.

    Aggregate guards catch magnitude; structural guards catch meaning. Two cases
    from different categories mean one lucky embedding cannot carry the claim.
    """
    results = retriever.search("getting 429 errors when calling your endpoints", top_k=5)

    assert any(r.doc_id.startswith("DOC-API") for r in results)


def test_a_billing_question_retrieves_a_billing_article(retriever):
    results = retriever.search("why is my invoice higher this month", top_k=5)

    assert any(r.doc_id.startswith("DOC-BILL") for r in results)


# --- determinism (A5 depends on this) ----------------------------------------


def test_the_same_query_returns_the_same_results(retriever):
    """A5 requires the same input to produce the same routing decision, which
    cannot hold if retrieval is not itself deterministic."""
    first = retriever.search("api key rotation")
    second = retriever.search("api key rotation")

    assert [(r.chunk_id, r.score) for r in first] == [(r.chunk_id, r.score) for r in second]


# --- robustness (A11) ---------------------------------------------------------


def test_a_very_long_query_does_not_fail(retriever):
    assert retriever.search("deployment " * 2000) is not None


def test_unusual_characters_in_a_query_do_not_fail(retriever):
    assert retriever.search("認証 失敗 🚀 <script>alert(1)</script>") is not None


def test_a_query_of_only_punctuation_returns_nothing(retriever):
    assert retriever.search("!!! ??? ...") == []


# --- measured retrieval quality against the labelled data --------------------


def _pack(name: str):
    path = (
        Path(__file__).resolve().parents[2]
        / "FDE_Capstone_Complete-20260821T084330Z-1-001"
        / "FDE_Capstone_Complete"
        / "Capstone_Pack"
        / "05_Datasets"
        / name
    )
    if not path.exists():
        pytest.skip(f"{name} not present")
    return json.loads(path.read_text(encoding="utf-8"))


def test_retrieval_hit_rate_on_groundable_development_tickets(retriever):
    """AS-01: semantic retrieval bridges the symptom/title gap.

    Measured on the tickets that have an expected document. This is the number
    the whole design rests on; if it collapses, the premise is wrong.
    """
    tickets = [t for t in _pack("development_tickets.json") if t["labels"]["expected_doc_ids"]]
    assert tickets

    hits = 0
    for ticket in tickets:
        query = f"{ticket['subject']} {ticket['body']}".strip()
        found = {r.doc_id for r in retriever.search(query, top_k=3)}
        if found & set(ticket["labels"]["expected_doc_ids"]):
            hits += 1

    hit_rate = hits / len(tickets)
    print(f"\nretrieval any-hit@3 on {len(tickets)} groundable dev tickets: {hit_rate:.1%}")

    # 0.90, not 0.60. Review 4 asked for this bound (D2-C3) and review 5 recorded
    # it as applied; it was still 0.60 when review 12 checked. Measured 95.2% on
    # 2026-09-04 and unchanged since, so 0.60 could have halved before failing.
    # This fixture retrieves at floor 0.0, so it measures ranking; the shipped
    # 0.40 floor yields 92.7% and is covered by the report and D-21.
    assert hit_rate >= 0.90, f"any-hit@3 fell to {hit_rate:.1%}; AS-01 is in doubt"


# --- D2-C1: the derived floor must be the shipped floor ----------------------


def test_the_retriever_default_floor_equals_the_derived_configuration_value():
    """D4 claims the threshold is derived, not chosen.

    That claim only holds if the derived value is the one that actually runs.
    Three copies of this number previously disagreed, so the graded run would
    have used a floor the report did not defend.
    """
    import inspect

    from src.config import DEFAULT_RELEVANCE_FLOOR

    default = inspect.signature(Retriever.__init__).parameters["relevance_floor"].default

    assert default == DEFAULT_RELEVANCE_FLOOR


def test_a_retriever_built_without_a_floor_uses_the_derived_value(corpus):
    from src.config import DEFAULT_RELEVANCE_FLOOR

    assert Retriever(corpus).relevance_floor == DEFAULT_RELEVANCE_FLOOR


# --- D2-C2: "nothing cleared the floor" vs "nothing was close" ----------------


def test_search_detailed_reports_passages_that_fell_below_the_floor(corpus):
    """An escalation must be able to say WHY nothing was usable.

    The Governance Framework's minimum record carries sources_used with scores.
    If sub-floor results are discarded inside search(), an escalation logs an
    empty list and "the best match scored 0.38, just under the floor" becomes
    unrecoverable at incident review.
    """
    strict = Retriever(corpus, relevance_floor=0.99)

    result = strict.search_detailed("console says invalid credentials")

    assert result.passages == []
    assert result.rejected, "sub-floor candidates must be retained, not discarded"
    assert result.top_score > 0.0


def test_search_detailed_records_the_floor_that_was_applied(corpus):
    result = Retriever(corpus, relevance_floor=0.42).search_detailed("deployment failing")

    assert result.floor_applied == pytest.approx(0.42)


def test_rejected_passages_are_never_merged_into_accepted_ones(corpus):
    """D7 builds citations from retrieved chunk ids.

    A sub-floor passage reachable from the citation path would be a latent A6
    violation, so the two collections must stay separate.
    """
    strict = Retriever(corpus, relevance_floor=0.99)

    result = strict.search_detailed("invoice higher than expected")

    accepted_ids = {p.chunk_id for p in result.passages}
    rejected_ids = {p.chunk_id for p in result.rejected}
    assert accepted_ids & rejected_ids == set()


def test_a_genuinely_empty_query_reports_no_top_score(corpus):
    """Distinguishes 'nothing was close' from 'there was nothing to search for'."""
    result = Retriever(corpus).search_detailed("   ")

    assert result.passages == []
    assert result.rejected == []
    assert result.top_score == 0.0


def test_search_remains_the_simple_accessor(retriever):
    """search() stays the ergonomic path; search_detailed() is for the log."""
    query = "my deployment keeps dying"

    assert [p.chunk_id for p in retriever.search(query)] == [
        p.chunk_id for p in retriever.search_detailed(query).passages
    ]
