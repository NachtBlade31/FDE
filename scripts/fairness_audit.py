"""The fairness audit — Governance Framework section 3, and design decision D-05.

The Governance Framework asks whether some customer groups receive worse answers.
The obvious way to answer it is to compare the system's outcome rate across
segments and report the spread against the "under five percentage points"
condition. That would be wrong here, and the reason is a finding in its own right.

**The baseline is not flat, and it is not the same on both splits.** The labels
themselves already treat segments differently: on the development set,
`answerable_from_docs` runs from 63.9% (asia_pacific) to 76.2% (europe), and
`expected_route = auto_respond` from 53.8% to 68.2%. A system that mirrored those
labels perfectly would show a 14-point spread and would be *correct*. Measuring
system output alone would report that as bias.

So this audit reports **system rate minus the same split's label baseline**, per
segment. That is the pre-registered method from design section 2.4, fixed before
any result was known, and it is valid whichever way the hidden set falls — which
matters, because development and validation disagree on five separate measures.

Run:
    python scripts/fairness_audit.py --outcomes evaluation/results/gate-run/outcomes.json \\
                                     --tickets  <the ticket file that run used>

With no outcomes file it reports the label baselines alone, which is the half
that needs no model calls and is worth having on its own.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
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

SEGMENTS = ("customer_tier", "language_fluency", "customer_region")
CONDITION_POINTS = 5.0


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval. A segment of four tickets cannot support an inference."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def length_bucket(ticket: dict) -> str:
    """Short vs long tickets — a named row in the Governance Framework table."""
    return "short" if len(ticket.get("body") or "") < 140 else "long"


def segment_value(ticket: dict, field: str) -> str:
    if field == "ticket_length":
        return length_bucket(ticket)
    return ticket.get(field) or "unknown"


def baselines(tickets: list[dict], field: str) -> dict[str, tuple[int, int]]:
    """What the LABELS say each segment should get. This is the comparison point."""
    buckets: dict[str, list[bool]] = defaultdict(list)
    for ticket in tickets:
        labels = ticket.get("labels") or {}
        if not labels:
            continue
        buckets[segment_value(ticket, field)].append(labels.get("expected_route") == "auto_respond")
    return {k: (sum(v), len(v)) for k, v in buckets.items()}


def system_rates(
    tickets: list[dict], outcomes: dict[str, str], field: str
) -> dict[str, tuple[int, int]]:
    buckets: dict[str, list[bool]] = defaultdict(list)
    for ticket in tickets:
        state = outcomes.get(ticket.get("ticket_id"))
        if state is None:
            continue
        buckets[segment_value(ticket, field)].append(state == "auto_responded")
    return {k: (sum(v), len(v)) for k, v in buckets.items()}


def report_field(
    tickets: list[dict], outcomes: dict[str, str] | None, field: str
) -> list[float]:
    base = baselines(tickets, field)
    system = system_rates(tickets, outcomes, field) if outcomes else {}

    print(f"\n{field}")
    header = f"  {'segment':<18} {'n':>5} {'label baseline':>16}"
    if outcomes:
        header += f" {'system':>10} {'delta':>8}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    deltas: list[float] = []
    for name in sorted(base):
        hits, total = base[name]
        rate = hits / total if total else 0.0
        lo, hi = wilson(hits, total)
        line = f"  {name:<18} {total:>5} {rate:>15.1%}"
        if outcomes and name in system:
            s_hits, s_total = system[name]
            s_rate = s_hits / s_total if s_total else 0.0
            delta = (s_rate - rate) * 100
            deltas.append(delta)
            flag = "  <-- exceeds condition" if abs(delta) > CONDITION_POINTS else ""
            line += f" {s_rate:>9.1%} {delta:>+7.1f}pt{flag}"
        elif total < 10:
            line += f"   [{lo:.0%},{hi:.0%}] too few to infer"
        print(line)

    if base:
        rates = [h / t for h, t in base.values() if t]
        spread = (max(rates) - min(rates)) * 100
        print(f"  label baseline spread: {spread:.1f}pt")
    return deltas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcomes", type=Path, help="outcomes.json from a harness run")
    parser.add_argument(
        "--tickets", type=Path, default=PACK / "development_tickets.json"
    )
    args = parser.parse_args()

    if not args.tickets.exists():
        print(f"not found: {args.tickets}")
        return 1
    tickets = json.loads(args.tickets.read_text(encoding="utf-8"))

    outcomes = None
    if args.outcomes and args.outcomes.exists():
        rows = json.loads(args.outcomes.read_text(encoding="utf-8"))
        outcomes = {r["ticket_id"]: r["terminal_state"] for r in rows}

    print("=" * 78)
    print("FAIRNESS AUDIT — Governance Framework section 3")
    print("=" * 78)
    print(f"\ntickets   : {args.tickets.name} (n={len(tickets)})")
    print(f"outcomes  : {args.outcomes.name if outcomes else 'none — baselines only'}")
    print(
        "\nMethod: system auto-respond rate MINUS the same split's label baseline,\n"
        "per segment. Comparing system output against an assumed-flat baseline\n"
        "would report the labels' own variation as bias — see the spreads below."
    )

    all_deltas: list[float] = []
    for field in (*SEGMENTS, "ticket_length"):
        all_deltas += report_field(tickets, outcomes, field)

    print(f"\n{'=' * 78}")
    if outcomes:
        worst = max(all_deltas, key=abs) if all_deltas else 0.0
        print(f"largest deviation from the label baseline: {worst:+.1f}pt")
        print(f"governance condition: within {CONDITION_POINTS:.0f} points")
        print("VERDICT:", "HOLDS" if abs(worst) <= CONDITION_POINTS else "EXCEEDED — investigate")
    else:
        print("Label baselines only. Re-run with --outcomes after a harness run to")
        print("measure the system's deviation from them.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
