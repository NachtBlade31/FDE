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

**It refuses to produce a result from a run it cannot trust.** A run that lost its
provider mid-way escalates whatever it could not classify, which drags every
segment negative at once; published unqualified, that reports an outage as bias
against every customer group simultaneously. So the audit reads the run's
`metrics.json`, and refuses when the run is marked `degraded` or
`distribution_collapsed` — and refuses equally when there is *no* metrics file to
check, because a guard that a file copy can silence is not a guard (D-44).

Run:
    python scripts/fairness_audit.py --outcomes evaluation/results/<run>/outcomes.json \\
                                     --tickets  <the ticket file that run used>

With no outcomes file it reports the label baselines alone, which is the half
that needs no model calls and is worth having on its own.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import subprocess
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
MIN_SEGMENT_N = 10


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact p for a paired binary comparison.

    The system's decision and the label are made on the SAME ticket, so the two
    rates are paired and an unpaired comparison overstates the evidence. `b` and
    `c` are the discordant counts: tickets the label says auto-respond and the
    system escalated, and the reverse. Concordant tickets carry no information
    about the difference and drop out — which is why a 30-ticket segment can
    still be uninformative.

    Under the null the discordant pairs split 50/50, so this is a two-sided
    binomial test at p=0.5 on b of b+c.
    """
    n = b + c
    if n == 0:
        return 1.0
    from math import comb

    tail = sum(comb(n, k) for k in range(0, min(b, c) + 1))
    return min(1.0, 2 * tail / (2 ** n))


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values.

    Eleven segments are tested at once. Testing eleven things and reporting the
    smallest p as though one thing had been tested is how a table like this
    manufactures a finding, so the correction is applied and shown rather than
    left to the reader.
    """
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[name] = running
    return adjusted


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


def discordant(
    tickets: list[dict], outcomes: dict[str, str], field: str
) -> dict[str, tuple[int, int]]:
    """Per segment: (label said answer & system escalated, and the reverse).

    These are the only tickets that carry information about the difference
    between the two rates, because both are measured on the same tickets.
    """
    pairs: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    for ticket in tickets:
        state = outcomes.get(ticket.get("ticket_id"))
        labels = ticket.get("labels") or {}
        if state is None or not labels:
            continue
        pairs[segment_value(ticket, field)].append(
            (labels.get("expected_route") == "auto_respond", state == "auto_responded")
        )
    return {
        name: (
            sum(1 for lab, sys_ in v if lab and not sys_),
            sum(1 for lab, sys_ in v if sys_ and not lab),
        )
        for name, v in pairs.items()
    }


def report_field(
    tickets: list[dict], outcomes: dict[str, str] | None, field: str
) -> tuple[list[float], dict[str, tuple[float, int, int, int]]]:
    """One segment field. A delta is the system's rate minus that segment's baseline.

    Both rates are computed over the SAME tickets. If a run covered only part of
    the file, comparing a 23-ticket system rate against a 30-ticket baseline
    compares two different populations and reports the difference between them as
    a fairness gap — so on a partial run the baseline is narrowed to match.
    """
    covered = (
        [t for t in tickets if t.get("ticket_id") in outcomes] if outcomes else tickets
    )
    base = baselines(covered, field)
    system = system_rates(covered, outcomes, field) if outcomes else {}
    pairs = discordant(covered, outcomes, field) if outcomes else {}

    print(f"\n{field}")
    header = f"  {'segment':<18} {'n':>5} {'label baseline':>16}"
    if outcomes:
        header += f" {'system':>10} {'delta':>8} {'disc':>8} {'p':>7}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    deltas: list[float] = []
    stats: dict[str, tuple[float, int, int, int]] = {}
    for name in sorted(base):
        hits, total = base[name]
        rate = hits / total if total else 0.0
        line = f"  {name:<18} {total:>5} {rate:>15.1%}"
        if outcomes and name in system:
            s_hits, s_total = system[name]
            s_rate = s_hits / s_total if s_total else 0.0
            delta = (s_rate - rate) * 100
            b, c = pairs.get(name, (0, 0))
            p_value = mcnemar_exact(b, c)
            stats[name] = (delta, total, b, c)
            flag = "  <-- exceeds condition" if abs(delta) > CONDITION_POINTS else ""
            line += f" {s_rate:>9.1%} {delta:>+7.1f}pt {b:>3}/{c:<3} {p_value:>7.3f}{flag}"
            # Only well-powered segments may set the headline verdict. A segment
            # the tool itself declares too small to support an inference must not
            # be the number the report leads with — on the 10 Sep run `enterprise`
            # (n=8) came within 0.6pt of doing exactly that, and one differently
            # routed ticket moves that segment 12.5 points.
            if total >= MIN_SEGMENT_N:
                deltas.append(delta)
            # The interval belongs to whatever rate the row is about. Printing the
            # BASELINE's interval next to a SYSTEM rate invited the report to
            # quote it as the system's, which it did.
            lo, hi = wilson(s_hits, s_total)
        else:
            lo, hi = wilson(hits, total)
        # The small-sample caveat applies to a delta at least as much as to a
        # baseline: an 8-ticket segment moves 12.5 points per ticket. It used to
        # print only when there were NO outcomes, so exactly the rows most likely
        # to be quoted were the ones that carried no warning.
        if total < MIN_SEGMENT_N:
            label = "system rate" if outcomes and name in system else "baseline"
            line += f"   {label} [{lo:.0%},{hi:.0%}] n<{MIN_SEGMENT_N}, excluded"
        print(line)

    if base:
        rates = [h / t for h, t in base.values() if t]
        spread = (max(rates) - min(rates)) * 100
        print(f"  label baseline spread: {spread:.1f}pt")
    return deltas, stats


def git_commit() -> str:
    """The commit, marked `-dirty` when the working tree differs from it.

    This banner once named a commit that could not have produced the artifact:
    the audit was run from uncommitted code and stamped the previous HEAD, so the
    Holm-adjusted table in `2026-09-10-fairness-validation.txt` claimed a commit
    whose script had no Holm code in it (validator finding C-5).
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=REPO, timeout=10,
        ).stdout.strip() or "unknown"
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, cwd=REPO, timeout=10,
        ).stdout.strip()
        return f"{commit}-dirty" if dirty else commit
    except Exception:  # pragma: no cover - provenance must never break a run
        return "unknown"


def print_provenance(args, run: dict | None) -> None:
    """Name the run this artifact describes (D-37).

    An evidence file that does not identify its input cannot be checked against
    anything. The earlier version of this script recorded neither the run it read
    nor the commit it ran at, so its output could not be tied to any artifact.
    """
    print("=" * 78)
    print("PROVENANCE — what this artifact was produced from")
    print("=" * 78)
    print(f"  generated            : {datetime.datetime.now().isoformat(timespec='seconds')}")
    print(f"  commit               : {git_commit()}")
    print(f"  tickets              : {args.tickets}")
    print(f"  outcomes             : {args.outcomes or 'none — baselines only'}")
    if run:
        print(f"  run_id               : {run.get('run_id', 'unknown')}")
        print(f"  run generated_at     : {run.get('generated_at', 'unknown')}")
        print(f"  provider / model     : {run.get('provider')} / {run.get('model')}")
        print(f"  degraded             : {run.get('degraded')}")
        print(f"  cache replay         : {run.get('cache_replay')}")
        print(f"  provider calls       : {run.get('provider_calls_succeeded')} of "
              f"{run.get('provider_calls_attempted')} succeeded, "
              f"{run.get('cache_hits')} cache hits")
        print(f"  fallback rate        : {run.get('classification_fallback_rate', 0):.1%}")
    print(f"  condition            : within {CONDITION_POINTS:.0f} points of baseline")
    print("=" * 78)


def load_run(args) -> tuple[dict | None, str | None]:
    """Resolve the run's metrics and decide whether its outcomes may be reported.

    Returns (run_metrics, refusal_reason). A missing metrics file is itself a
    refusal: `outcomes.json` alone cannot say whether the run that produced it
    completed healthily, and copying it away from its sibling used to disable the
    guard with no warning at all.
    """
    metrics_path = args.metrics or (args.outcomes.parent / "metrics.json")
    if not metrics_path.exists():
        if args.no_metrics:
            return None, None
        return None, (
            f"no metrics file was found at {metrics_path}.\n"
            "  Without one there is no way to tell a healthy run from a degraded one;\n"
            "  outcomes.json alone does not say. Pass --metrics PATH to point at it,\n"
            "  or --no-metrics to accept the outcomes unverified."
        )

    run = json.loads(metrics_path.read_text(encoding="utf-8")).get("run", {})
    if run.get("degraded") or run.get("distribution_collapsed"):
        return run, (
            f"the run is marked degraded (classification fallback rate "
            f"{run.get('classification_fallback_rate', 0):.1%}; "
            f"{run.get('provider_calls_succeeded', 0)} of "
            f"{run.get('provider_calls_attempted', 0)} provider calls succeeded)."
        )
    # A cache replay is deliberately NOT a refusal. The outcomes in a replay are
    # real routing decisions that really were made; what a replay cannot support
    # is a timing or throughput claim (D-30), and this audit makes neither.
    return run, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcomes", type=Path, help="outcomes.json from a harness run")
    parser.add_argument(
        "--tickets", type=Path, default=PACK / "development_tickets.json"
    )
    parser.add_argument(
        "--metrics", type=Path, help="metrics.json for the run (default: beside --outcomes)"
    )
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help="report deltas even from a degraded run (inspection only; output is labelled)",
    )
    parser.add_argument(
        "--no-metrics",
        action="store_true",
        help="accept outcomes with no metrics file to check them against",
    )
    args = parser.parse_args()

    if not args.tickets.exists():
        print(f"not found: {args.tickets}")
        return 1
    tickets = json.loads(args.tickets.read_text(encoding="utf-8"))

    outcomes = None
    run = None
    refusal = None
    if args.outcomes and args.outcomes.exists():
        rows = json.loads(args.outcomes.read_text(encoding="utf-8"))
        outcomes = {r["ticket_id"]: r["terminal_state"] for r in rows}
        run, refusal = load_run(args)

    overridden = bool(refusal and args.allow_degraded)
    if refusal and not args.allow_degraded:
        print("=" * 78)
        print("FAIRNESS AUDIT — NOT PRODUCED")
        print("=" * 78)
        print(f"\n  Refusing to report per-segment deltas because {refusal}")
        print(
            "\n  A run that lost its provider escalates whatever it could not classify,\n"
            "  which drags every segment negative at once. Published unqualified, that\n"
            "  reports an outage as bias against every customer group simultaneously —\n"
            "  which is false, and, being uniformly negative, superficially plausible.\n"
            "\n  Re-run the harness on a healthy budget and repeat this audit.\n"
            "  Pass --allow-degraded to override, for inspection only."
        )
        print("\n  The label baselines below need no run and are always valid.")
        outcomes = None

    print_provenance(args, run)
    print("=" * 78)
    print("FAIRNESS AUDIT — Governance Framework section 3")
    print("=" * 78)
    if overridden:
        print("\n" + "!" * 78)
        print("DEGRADED RUN — NOT A FAIRNESS RESULT")
        print(f"  {refusal}")
        print("  Shown under --allow-degraded for inspection only. Do not quote these")
        print("  deltas as a fairness finding; they measure the outage, not the system.")
        print("!" * 78)

    covered = len([t for t in tickets if t.get("ticket_id") in outcomes]) if outcomes else 0
    print(f"\ntickets   : {args.tickets.name} (n={len(tickets)})")
    if outcomes:
        print(f"outcomes  : {args.outcomes.name} (covering {covered} of {len(tickets)})")
    else:
        print("outcomes  : none — baselines only")
    print(
        "\nMethod: system auto-respond rate MINUS the same split's label baseline,\n"
        "per segment, over the same tickets. Comparing system output against an\n"
        "assumed-flat baseline would report the labels' own variation as bias —\n"
        "see the spreads below."
    )

    print(
        "\n`disc` is the discordant split: tickets the label says answer and the\n"
        "system escalated, against the reverse. Only those carry information about\n"
        "the difference, because both rates are measured on the same tickets — so\n"
        "`p` is a two-sided exact paired test, not a comparison of two proportions."
    )

    all_deltas: list[float] = []
    all_stats: dict[str, tuple[float, int, int, int]] = {}
    for field in (*SEGMENTS, "ticket_length"):
        deltas, stats = report_field(tickets, outcomes, field)
        all_deltas += deltas
        all_stats.update(stats)

    if outcomes and all_stats:
        raw = {n: mcnemar_exact(b, c) for n, (_, _, b, c) in all_stats.items()}
        adjusted = holm(raw)
        print(f"\n{'-' * 78}")
        print(
            f"Holm-adjusted across {len(raw)} segments tested together — testing"
            " eleven things\nand quoting the smallest p is how a table like this"
            " manufactures a finding:"
        )
        survivors = [n for n, p in adjusted.items() if p < 0.05]
        for name, p_adj in sorted(adjusted.items(), key=lambda kv: kv[1])[:4]:
            print(f"  {name:<18} raw p={raw[name]:.3f}   adjusted p={p_adj:.3f}")
        print(
            f"  surviving correction at 0.05: "
            f"{', '.join(survivors) if survivors else 'NONE'}"
        )

    print(f"\n{'=' * 78}")
    if outcomes:
        worst = max(all_deltas, key=abs) if all_deltas else 0.0
        print(
            f"largest deviation from the label baseline: {worst:+.1f}pt"
            f"   (over segments with n>={MIN_SEGMENT_N} only)"
        )
        if overridden:
            print("NO VERDICT — the run was degraded. See the banner above.")
        else:
            print(f"governance condition: within {CONDITION_POINTS:.0f} points")
            print(
                "VERDICT:",
                "HOLDS" if abs(worst) <= CONDITION_POINTS else "EXCEEDED — investigate",
            )
            print(
                "\nThe verdict is on the CONDITION, which is stated in percentage\n"
                "points and is met or not met as measured. It is not a claim that any\n"
                "individual segment's gap is distinguishable from chance — see the\n"
                "adjusted p-values above before treating one segment as a finding."
            )
    else:
        print("Label baselines only. Re-run with --outcomes after a healthy harness")
        print("run to measure the system's deviation from them.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
