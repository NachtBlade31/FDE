"""Measure how templated the supplied ticket data is.

This exists because a spike produced a result too good to accept: a k-nearest-
neighbour classifier over ticket embeddings scored 99.4% leave-one-out accuracy
against a brief that targets 85% precision. A number that far above target is
evidence about the data, not about the classifier.

What it establishes is reported in the evaluation section under the limits of
what was measured. The Evaluation Framework asks for a sentence beginning "the
figures above should be treated with caution because"; this script produces the
rest of that sentence.

Run:  python scripts/analyse_data_regularity.py
"""

from __future__ import annotations

import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

PACK = (
    REPO.parent
    / "FDE_Capstone_Complete-20260821T084330Z-1-001"
    / "FDE_Capstone_Complete"
    / "Capstone_Pack"
    / "05_Datasets"
)

WORD = re.compile(r"[a-z]{4,}")


def tokens(text: str) -> set[str]:
    return set(WORD.findall(text.lower()))


def report(name: str, tickets: list[dict]) -> None:
    print(f"\n{'=' * 70}")
    print(f"{name}  (n={len(tickets)})")
    print(f"{'=' * 70}")

    bodies = Counter(t["body"].strip().lower() for t in tickets)
    repeated = {b: n for b, n in bodies.items() if n > 1}
    duplicated_tickets = sum(n for n in repeated.values()) - len(repeated)

    print(f"\ndistinct ticket bodies        : {len(bodies)} of {len(tickets)}")
    print(f"bodies appearing more than once: {len(repeated)}")
    print(
        f"tickets that duplicate another : {duplicated_tickets} "
        f"({duplicated_tickets / len(tickets):.1%})"
    )

    by_intent: dict[str, list[dict]] = defaultdict(list)
    for ticket in tickets:
        by_intent[ticket["labels"]["intent"]].append(ticket)

    random.seed(0)
    within, across = [], []
    for group in by_intent.values():
        if len(group) < 4:
            continue
        for _ in range(40):
            a, b = random.sample(group, 2)
            ta, tb = tokens(a["body"]), tokens(b["body"])
            if ta or tb:
                within.append(len(ta & tb) / max(1, len(ta | tb)))
    for _ in range(2000):
        a, b = random.sample(tickets, 2)
        if a["labels"]["intent"] == b["labels"]["intent"]:
            continue
        ta, tb = tokens(a["body"]), tokens(b["body"])
        if ta or tb:
            across.append(len(ta & tb) / max(1, len(ta | tb)))

    same = statistics.mean(within)
    diff = statistics.mean(across)
    print(f"\nmean token Jaccard, same intent     : {same:.3f}")
    print(f"mean token Jaccard, different intent: {diff:.3f}")
    print(f"ratio                                : {same / diff:.1f}x")

    print("\ndistinct 5-word openings per intent (a proxy for template count):")
    print(f"  {'intent':<24} {'tickets':>8} {'openings':>9} {'ratio':>7}")
    total_t = total_o = 0
    for intent, group in sorted(by_intent.items()):
        openings = len({" ".join(t["body"].lower().split()[:5]) for t in group})
        total_t += len(group)
        total_o += openings
        print(f"  {intent:<24} {len(group):>8} {openings:>9} {len(group) / openings:>6.1f}x")
    print(f"  {'TOTAL':<24} {total_t:>8} {total_o:>9} {total_t / total_o:>6.1f}x")


def main() -> None:
    for name in ("development_tickets.json", "validation_tickets.json"):
        path = PACK / name
        if not path.exists():
            print(f"skipping {name}: not present")
            continue
        report(name, json.loads(path.read_text(encoding="utf-8")))

    print(f"\n{'=' * 70}")
    print("WHAT THIS MEANS")
    print(f"{'=' * 70}")
    print(
        """
The ticket corpus is generated from a small number of templates per intent, with
surface variation. Same-intent tickets share an order of magnitude more
vocabulary than different-intent tickets, and a large share of bodies are exact
duplicates of another ticket.

Consequences that must be stated in the report rather than quietly enjoyed:

1. Any classifier will score implausibly well. A k-NN over embeddings reaches
   99.4% leave-one-out, against a brief that targets 85%. That measures template
   regularity, not classification capability.

2. The hidden set is drawn from the same population, but NOT necessarily to
   the same degree. Validation is markedly less templated than development:
   25% duplicate bodies against 57%. If the hidden set resembles validation,
   a figure measured on development is OPTIMISTIC. This is the third metric
   on which development and validation diverge (see design section 2.4 for
   first contact resolution and answerable_from_docs), which makes it a
   finding about the pack's data rather than a quirk of one measure.

3. Reported classification precision therefore describes performance on
   synthetic, templated data. Any claim about real-world performance is an
   extrapolation, and is labelled as one.
"""
    )


if __name__ == "__main__":
    main()
