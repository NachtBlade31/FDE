"""Measure routing end to end against the development set.

Four questions, in order of importance:

  1. **Is the governance invariant held?** Zero tickets carrying
     `must_not_auto_respond` may be answered automatically. This is a condition,
     not a target: any violation is a failure regardless of the other numbers.
  2. What are the business outcomes — first contact resolution and escalation
     rate — against the 60% and 30% targets?
  3. Where does the margin threshold actually sit? Swept, so the value is
     derived rather than chosen (D4).
  4. Which conjunct is doing the work? D2 claims grounding and the deny-list
     carry the decision and the margin is the weakest leg; that is checkable.

Development set only. Classification is served from cache where available, so
repeat runs cost no allowance.

Run:  python scripts/evaluate_routing.py --limit 200
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from src.classify import Classifier  # noqa: E402
from src.config import DEFAULT_ABSTENTION_FLOOR, Settings  # noqa: E402
from src.ingest import normalise_batch  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402
from src.retrieve import Corpus, Retriever  # noqa: E402
from src.route import Action, Router  # noqa: E402

PACK = (
    REPO.parent
    / "FDE_Capstone_Complete-20260821T084330Z-1-001"
    / "FDE_Capstone_Complete"
    / "Capstone_Pack"
    / "05_Datasets"
)

THRESHOLDS = [0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]


def print_provenance(settings, extra=None):
    """State the configuration this artifact was produced under.

    An evidence file that does not name its configuration cannot be checked
    against the code, and three of ours drifted before this existed.
    """
    import datetime
    import subprocess

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=REPO, timeout=10,
        ).stdout.strip() or "unknown"
    except Exception:  # pragma: no cover - provenance must never break a run
        commit = "unknown"

    print("=" * 78)
    print("PROVENANCE — the configuration this artifact was produced under")
    print("=" * 78)
    print(f"  generated            : {datetime.datetime.now().isoformat(timespec='seconds')}")
    print(f"  commit               : {commit}")
    print(f"  provider / model     : {settings.provider.value} / {settings.model_name}")
    print(f"  confidence threshold : {settings.confidence_threshold}")
    print(f"  relevance floor      : {settings.relevance_floor}")
    from src.config import DEFAULT_ABSTENTION_FLOOR
    print(f"  abstention floor     : {DEFAULT_ABSTENTION_FLOOR}")
    for line in extra or []:
        print(f"  {line}")
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--abstention-floor", type=float, default=DEFAULT_ABSTENTION_FLOOR)
    parser.add_argument("--sweep-abstention", action="store_true")
    args = parser.parse_args()

    raw = json.loads((PACK / "development_tickets.json").read_text(encoding="utf-8"))[: args.limit]
    tickets, _ = normalise_batch(raw)

    settings = Settings.from_env()
    if not settings.has_model_access:
        print("no model access")
        return 1
    print(f"tickets: {len(tickets)}")
    print_provenance(settings)

    client = LLMClient(settings, cache_path=REPO / "storage" / "cache")
    classifier = Classifier(client)
    retriever = Retriever(
        Corpus.from_file(REPO / "data" / "documentation.json"),
        relevance_floor=settings.relevance_floor,
    )

    print("classifying and retrieving...")
    prepared = []
    for index, ticket in enumerate(tickets, 1):
        classification = classifier.classify(ticket)
        retrieval = retriever.search_detailed(ticket.search_text, top_k=3)
        prepared.append((ticket, classification, retrieval))
        if index % 50 == 0:
            print(f"  {index}/{len(tickets)}")
    print(f"  provider calls {client.stats.attempted}, cache hits {client.stats.cache_hits}")

    if args.sweep_abstention:
        print("\n" + "=" * 78)
        print(
            "ABSTENTION FLOOR SWEEP (D1 layer 3) — margin threshold held at "
            f"the shipped {settings.confidence_threshold}"
        )
        print("=" * 78)
        print(
            f"\n{'floor':>7} | {'FCR':>7} | {'route acc':>9} | {'auto prec':>9} | "
            f"{'alt escal':>9} | {'VIOLATIONS':>10}"
        )
        print("-" * 72)
        for floor in [0.0, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.01]:
            r = Router(margin_threshold=settings.confidence_threshold, abstention_floor=floor)
            ds = [r.route(t, c, rr) for t, c, rr in prepared]
            auto = [d for d in ds if d.action is Action.AUTO_RESPOND]
            fcr = len(auto) / len(ds)
            acc = sum(1 for (t, _, _), d in zip(prepared, ds)
                      if t.labels and (d.action is Action.AUTO_RESPOND) ==
                      (t.labels.expected_route == "auto_respond")) / len(ds)
            prec = (sum(1 for (t, _, _), d in zip(prepared, ds)
                        if d.action is Action.AUTO_RESPOND and t.labels
                        and t.labels.expected_route == "auto_respond") / len(auto)) if auto else 0.0
            alt_esc = sum(1 for d in ds if not d.checks.get("alternatives", True))
            viol = sum(1 for (t, _, _), d in zip(prepared, ds)
                       if d.action is Action.AUTO_RESPOND and t.labels and t.labels.must_not_auto_respond)
            flag = "  <-- FAIL" if viol else ""
            label = "off" if floor > 1 else f"{floor:.2f}"
            print(f"{label:>7} | {fcr:>6.1%} | {acc:>8.1%} | {prec:>8.1%} | "
                  f"{alt_esc:>9} | {viol:>10}{flag}")
        print()

    # --- the governance invariant, swept -------------------------------------
    print(f"\n{'=' * 78}")
    print("MARGIN THRESHOLD SWEEP (D4) — and the governance invariant at each point")
    print(f"{'=' * 78}")
    print(
        f"\n{'thresh':>7} | {'FCR':>7} | {'escal':>7} | {'route acc':>9} | "
        f"{'auto prec':>9} | {'VIOLATIONS':>10}"
    )
    print("-" * 70)

    best = None
    for threshold in THRESHOLDS:
        router = Router(margin_threshold=threshold, abstention_floor=args.abstention_floor)
        decisions = [router.route(t, c, r) for t, c, r in prepared]

        auto = [d for d in decisions if d.action is Action.AUTO_RESPOND]
        fcr = len(auto) / len(decisions)

        route_correct = sum(
            1
            for (t, _, _), d in zip(prepared, decisions)
            if t.labels
            and (
                (d.action is Action.AUTO_RESPOND) == (t.labels.expected_route == "auto_respond")
            )
        )
        route_acc = route_correct / len(decisions)

        auto_correct = sum(
            1
            for (t, _, _), d in zip(prepared, decisions)
            if d.action is Action.AUTO_RESPOND and t.labels and t.labels.expected_route == "auto_respond"
        )
        auto_prec = auto_correct / len(auto) if auto else 0.0

        violations = [
            t.ticket_id
            for (t, _, _), d in zip(prepared, decisions)
            if d.action is Action.AUTO_RESPOND and t.labels and t.labels.must_not_auto_respond
        ]

        flag = "  <-- FAIL" if violations else ""
        print(
            f"{threshold:>7.2f} | {fcr:>6.1%} | {1 - fcr:>6.1%} | {route_acc:>8.1%} | "
            f"{auto_prec:>8.1%} | {len(violations):>10}{flag}"
        )
        if not violations and (best is None or route_acc > best[1]):
            best = (threshold, route_acc, fcr, auto_prec)

    if best:
        print(
            f"\nbest routing accuracy with zero violations: threshold {best[0]:.2f} "
            f"-> route acc {best[1]:.1%}, FCR {best[2]:.1%}, auto precision {best[3]:.1%}"
        )

    # --- which conjunct is doing the work? -----------------------------------
    router = Router(
        margin_threshold=settings.confidence_threshold,
        abstention_floor=args.abstention_floor,
    )
    decisions = [router.route(t, c, r) for t, c, r in prepared]

    print(f"\n{'=' * 78}")
    print(
        "WHICH CONJUNCT ESCALATES? (shipped config: margin "
        f"{settings.confidence_threshold:.2f}, abstention {args.abstention_floor:.2f})"
    )
    print(f"{'=' * 78}")
    failed = Counter()
    for decision in decisions:
        if decision.action is Action.ESCALATE:
            for name, passed in decision.checks.items():
                if not passed:
                    failed[name] += 1
    escalated = sum(1 for d in decisions if d.action is Action.ESCALATE)
    print(f"\nescalated: {escalated} of {len(decisions)}")
    print("(a ticket can fail several checks, so these sum to more than the total)")
    for name, count in failed.most_common():
        print(f"  {name:<16} {count:>4}  ({count / max(1, escalated):.0%} of escalations)")

    # --- the governance check, stated plainly --------------------------------
    print(f"\n{'=' * 78}")
    print("GOVERNANCE CONDITION")
    print(f"{'=' * 78}")
    deny_listed = [t for t, _, _ in prepared if t.labels and t.labels.must_not_auto_respond]
    violations = [
        t.ticket_id
        for (t, _, _), d in zip(prepared, decisions)
        if d.action is Action.AUTO_RESPOND and t.labels and t.labels.must_not_auto_respond
    ]
    print(f"\n  deny-listed tickets in sample     : {len(deny_listed)}")
    print(f"  auto-answered despite the deny-list: {len(violations)}   (condition: zero)")
    print(f"  {'CONDITION HOLDS' if not violations else 'CONDITION VIOLATED: ' + ', '.join(violations)}")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
