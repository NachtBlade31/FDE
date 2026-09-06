"""Resolve open decisions O-1 (chunking) and O-2 (relevance floor) by measurement.

The Project Brief penalises "a threshold chosen because it looked reasonable
rather than because it was measured", and the Setup Guide asks for at least two
chunking configurations to be compared rather than assumed. This script produces
the evidence for both, against the development set only.

The relevance floor faces two ways at once, which is what makes it interesting:

  - too low  -> ungroundable tickets receive passages anyway, and the system
                manufactures an answer for a question the corpus cannot support
  - too high -> groundable tickets lose their supporting passage and escalate
                needlessly, and the automation rate collapses

357 development tickets are groundable and 143 are not, so both directions are
measurable. A combined score is reported, but the decision is not purely
arithmetic: Marcus's "I would rather it said nothing than said something wrong"
means a lost hit costs less than a manufactured answer.

Run:  python scripts/tune_retrieval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.retrieve import ChunkStrategy, Corpus, Retriever  # noqa: E402

PACK = (
    REPO.parent
    / "FDE_Capstone_Complete-20260821T084330Z-1-001"
    / "FDE_Capstone_Complete"
    / "Capstone_Pack"
    / "05_Datasets"
)

FLOORS = [0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
TOP_K = 3


def load_tickets() -> list[dict]:
    path = PACK / "development_tickets.json"
    if not path.exists():
        raise SystemExit(f"development set not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def query_of(ticket: dict) -> str:
    return f"{ticket.get('subject', '')} {ticket.get('body', '')}".strip()


def evaluate(strategy: ChunkStrategy, tickets: list[dict]) -> tuple[float, float]:
    corpus = Corpus.from_file(REPO / "data" / "documentation.json", strategy)

    # Score every ticket once with no floor; the floor is applied afterwards in
    # Python, because embedding is the expensive part and scores do not depend
    # on the floor.
    retriever = Retriever(corpus, relevance_floor=0.0)
    scored = {t["ticket_id"]: retriever.search(query_of(t), top_k=TOP_K) for t in tickets}

    groundable = [t for t in tickets if t["labels"]["expected_doc_ids"]]
    ungroundable = [t for t in tickets if not t["labels"]["expected_doc_ids"]]

    print(f"\n{'=' * 72}")
    print(f"STRATEGY: {strategy.value}    chunks={len(corpus.chunks)}  docs={len(corpus.documents)}")
    print(f"{'=' * 72}")
    print(f"\n{'floor':>6} | {'any-hit@3':>9} | {'recall@3':>8} | {'rejected':>8} | {'combined':>8}")
    print("-" * 56)

    best = (0.0, -1.0)
    for floor in FLOORS:
        hits = 0
        recall_total = 0.0
        for ticket in groundable:
            expected = set(ticket["labels"]["expected_doc_ids"])
            found = {p.doc_id for p in scored[ticket["ticket_id"]] if p.score >= floor}
            if found & expected:
                hits += 1
            recall_total += len(found & expected) / len(expected)

        rejected = sum(
            1
            for t in ungroundable
            if not [p for p in scored[t["ticket_id"]] if p.score >= floor]
        )

        any_hit = hits / len(groundable)
        recall = recall_total / len(groundable)
        reject_rate = rejected / len(ungroundable)
        combined = (any_hit + reject_rate) / 2

        if combined > best[1]:
            best = (floor, combined)

        print(
            f"{floor:>6.2f} | {any_hit:>8.1%} | {recall:>7.1%} | "
            f"{reject_rate:>7.1%} | {combined:>7.1%}"
        )

    print(f"\nbest combined score at floor {best[0]:.2f} ({best[1]:.1%})")
    return best


def main() -> None:
    tickets = load_tickets()
    groundable = sum(1 for t in tickets if t["labels"]["expected_doc_ids"])
    print(f"development tickets: {len(tickets)}")
    print(f"  groundable   : {groundable}")
    print(f"  ungroundable : {len(tickets) - groundable}")
    print("\nany-hit@3  : share of groundable tickets where an expected doc appears in top 3")
    print("recall@3   : mean share of each ticket's expected docs found (90 have several)")
    print("rejected   : share of ungroundable tickets correctly given NOTHING")
    print("combined   : unweighted mean of any-hit and rejected")

    results = {}
    for strategy in (ChunkStrategy.WHOLE, ChunkStrategy.SECTION):
        results[strategy.value] = evaluate(strategy, tickets)

    print(f"\n{'=' * 72}")
    print("SUMMARY")
    print(f"{'=' * 72}")
    for name, (floor, score) in results.items():
        print(f"  {name:<8} best floor {floor:.2f}  combined {score:.1%}")


if __name__ == "__main__":
    main()
