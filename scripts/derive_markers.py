"""Derive and measure the lexical pre-screen vocabulary — open decision O-4.

This is layer 2 of the D-04 safety gate: an intent-agnostic check over raw ticket
text that fires when classification fails. Layer 1 reads the predicted top-1
label and layer 3 reads the distribution, so both depend on the classifier
producing something sensible. Layer 2 does not, which is the whole point.

**Why this is measured on a held-out split rather than asserted.** An earlier
suggestion put this vocabulary at 94.3% recall with 0.0% false positives, derived
from a token-frequency scan over the entire development set. That is an upper
bound, not an estimate — the vocabulary was selected on the same tickets it was
scored against. Selecting markers on one half and scoring on the other is the
only version of this number worth reporting.

**Which way to tune.** A false positive costs one unnecessary escalation. A false
negative is a governance breach: a security or compliance ticket answered
automatically, against a stated threshold of zero. So the vocabulary is tuned for
recall and the false-positive rate is reported honestly rather than minimised.

Run:  python scripts/derive_markers.py
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
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

DENY_LIST = {"security_incident", "compliance_request", "feature_request", "unclear_request"}

WORD = re.compile(r"[a-z][a-z\-]{2,}")

# A marker must appear in at least this many deny-list tickets in the training
# half, and at most this share of its occurrences may fall outside the deny list.
MIN_SUPPORT = 3
MAX_LEAK = 0.10

FOLDS = 5


def tokens(text: str) -> set[str]:
    return set(WORD.findall(text.lower()))


def derive(train: list[dict]) -> set[str]:
    """Pick high-precision markers from the training half only."""
    inside: Counter[str] = Counter()
    outside: Counter[str] = Counter()

    for ticket in train:
        target = inside if ticket["labels"]["intent"] in DENY_LIST else outside
        for token in tokens(ticket["body"]):
            target[token] += 1

    markers = set()
    for token, hits in inside.items():
        if hits < MIN_SUPPORT:
            continue
        leak = outside[token] / (hits + outside[token])
        if leak <= MAX_LEAK:
            markers.add(token)
    return markers


def score(markers: set[str], held_out: list[dict]) -> tuple[int, int, int, int]:
    """Return (true positives, false negatives, false positives, true negatives)."""
    tp = fn = fp = tn = 0
    for ticket in held_out:
        fires = bool(markers & tokens(ticket["body"]))
        deny = ticket["labels"]["intent"] in DENY_LIST
        if deny and fires:
            tp += 1
        elif deny and not fires:
            fn += 1
        elif not deny and fires:
            fp += 1
        else:
            tn += 1
    return tp, fn, fp, tn


def main() -> int:
    print("=" * 78)
    print("THIS ARTIFACT DESCRIBES A VOCABULARY THAT WAS REJECTED")
    print("=" * 78)
    print()
    print("  The automatically derived vocabulary measured below is NOT what ships.")
    print("  src/markers.json holds a hand-curated list of 56 terms instead.")
    print()
    print("  The derived list scores higher overall but contains generic template")
    print("  artifacts - 'another', 'call', 'going', 'only', 'once', 'per', 'nobody'")
    print("  - which correlate with deny-list templates in this synthetic data and")
    print("  denote nothing. A safety control that fires on the word 'only' is not")
    print("  defensible. See docs/DECISIONS.md D-27 for the full argument.")
    print()
    print("  This file exists so the comparison can be re-run and audited. It is")
    print("  not a description of the shipped control.")
    print()
    print("=" * 78)

    path = PACK / "development_tickets.json"
    if not path.exists():
        print(f"not found: {path}")
        return 1

    tickets = json.loads(path.read_text(encoding="utf-8"))
    random.seed(0)
    shuffled = tickets[:]
    random.shuffle(shuffled)

    print(f"development tickets: {len(tickets)}")
    print(f"deny-listed        : {sum(1 for t in tickets if t['labels']['intent'] in DENY_LIST)}")
    print(f"\n{FOLDS}-fold cross-validation: markers derived on {FOLDS - 1} folds, scored on the held-out fold")
    print(f"\n{'fold':>5} | {'markers':>8} | {'recall':>8} | {'FP rate':>8} | {'TP':>4} {'FN':>4} {'FP':>4}")
    print("-" * 60)

    size = len(shuffled) // FOLDS
    totals = [0, 0, 0, 0]
    marker_counts = []

    for fold in range(FOLDS):
        held_out = shuffled[fold * size : (fold + 1) * size]
        train = [t for t in shuffled if t not in held_out]

        markers = derive(train)
        tp, fn, fp, tn = score(markers, held_out)
        totals = [a + b for a, b in zip(totals, (tp, fn, fp, tn))]
        marker_counts.append(len(markers))

        recall = tp / (tp + fn) if (tp + fn) else 0.0
        fp_rate = fp / (fp + tn) if (fp + tn) else 0.0
        print(
            f"{fold + 1:>5} | {len(markers):>8} | {recall:>7.1%} | {fp_rate:>7.1%} | "
            f"{tp:>4} {fn:>4} {fp:>4}"
        )

    tp, fn, fp, tn = totals
    recall = tp / (tp + fn)
    fp_rate = fp / (fp + tn)
    print("-" * 60)
    print(
        f"{'ALL':>5} | {sum(marker_counts) // FOLDS:>8} | {recall:>7.1%} | {fp_rate:>7.1%} | "
        f"{tp:>4} {fn:>4} {fp:>4}"
    )

    print(f"\nheld-out recall     : {recall:.1%}  ({tp} of {tp + fn} deny-listed tickets caught)")
    print(f"held-out FP rate    : {fp_rate:.1%}  ({fp} of {fp + tn} ordinary tickets escalated needlessly)")

    print("\nFor comparison, the in-sample figure (markers derived AND scored on all 500):")
    all_markers = derive(tickets)
    tp2, fn2, fp2, tn2 = score(all_markers, tickets)
    print(
        f"  markers {len(all_markers)}, recall {tp2 / (tp2 + fn2):.1%}, "
        f"FP rate {fp2 / (fp2 + tn2):.1%}   <- an upper bound, not an estimate"
    )

    print("\nFinal vocabulary, derived on the full development set:")
    print(f"  {len(all_markers)} markers")
    print("  " + ", ".join(sorted(all_markers)[:40]))
    if len(all_markers) > 40:
        print(f"  ... and {len(all_markers) - 40} more")

    # Deliberately NOT src/markers.json. This script measures the vocabulary that
    # was rejected; writing it to the shipped path would silently replace the
    # curated control with the one D-27 argued against. It did exactly that once.
    out = REPO / "evaluation" / "results" / "derived-markers-comparison.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sorted(all_markers), indent=2), encoding="utf-8")
    print(f"\nderived vocabulary written to {out.relative_to(REPO)} FOR COMPARISON ONLY.")
    print("The shipped vocabulary is the curated one in src/markers.json; see")
    print("docs/DECISIONS.md D-27 for why the higher-scoring derived list was rejected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
