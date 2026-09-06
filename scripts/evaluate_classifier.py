"""Measure the classifier against the development set.

Produces four things:

  1. Overall and per-class accuracy (A3, and the 85% precision target).
  2. The calibration table — stated confidence against observed accuracy, binned.
     The Evaluation Framework calls this the check students usually skip, and it
     is what the routing threshold rests on: if confidence is not calibrated, the
     threshold is meaningless.
  3. Deny-list recall on `security_incident` and `compliance_request`
     specifically. Design D-04 reports these two rather than a four-class
     aggregate, because the aggregate is diluted by the 56 of 87 deny-list
     tickets that grounding protects structurally.
  4. The throughput budget (carried item F7): calls per ticket and wall-clock,
     which determines whether the Day 5 gate run takes minutes or hours.

Development set only. Validation is untouched until the parameters are frozen.

Run:  python scripts/evaluate_classifier.py --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from src.classify import DENY_LIST_INTENTS, Classifier  # noqa: E402
from src.config import Settings  # noqa: E402
from src.ingest import normalise_batch  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402

PACK = (
    REPO.parent
    / "FDE_Capstone_Complete-20260821T084330Z-1-001"
    / "FDE_Capstone_Complete"
    / "Capstone_Pack"
    / "05_Datasets"
)

GROUNDABLE_DENY = {"security_incident", "compliance_request"}


def calibration_table(rows: list[tuple[float, bool]], bands: int = 5) -> None:
    print(f"\n{'band':>12} | {'n':>5} | {'stated':>8} | {'observed':>9} | {'gap':>7}")
    print("-" * 52)
    worst = 0.0
    for i in range(bands):
        low, high = i / bands, (i + 1) / bands
        group = [r for r in rows if low <= r[0] < high or (i == bands - 1 and r[0] == 1.0)]
        if not group:
            continue
        stated = sum(c for c, _ in group) / len(group)
        observed = sum(1 for _, ok in group if ok) / len(group)
        gap = stated - observed
        worst = max(worst, abs(gap))
        print(
            f"  {low:.1f}-{high:.1f}   | {len(group):>5} | {stated:>7.1%} | "
            f"{observed:>8.1%} | {gap:>+6.1%}"
        )
    print(f"\nlargest calibration gap: {worst:.1%}  (governance condition: within 5 points)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--input", type=Path, default=PACK / "development_tickets.json")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"not found: {args.input}")
        return 1

    raw = json.loads(args.input.read_text(encoding="utf-8"))[: args.limit]
    tickets, rejected = normalise_batch(raw)
    print(f"tickets: {len(tickets)} (rejected {len(rejected)})")

    settings = Settings.from_env()
    print(f"provider: {settings.provider.value}  model: {settings.model_name}")
    if not settings.has_model_access:
        print("no model access — cannot evaluate the classifier")
        return 1

    client = LLMClient(settings, cache_path=REPO / "storage" / "cache")
    classifier = Classifier(client)

    started = time.perf_counter()
    latencies: list[float] = []
    results = []
    for index, ticket in enumerate(tickets, 1):
        t0 = time.perf_counter()
        results.append((ticket, classifier.classify(ticket)))
        latencies.append(time.perf_counter() - t0)
        if index % 25 == 0:
            print(f"  {index}/{len(tickets)}  elapsed {time.perf_counter() - started:.0f}s")
    elapsed = time.perf_counter() - started

    # --- accuracy -------------------------------------------------------------
    correct = [t.labels.intent == c.intent for t, c in results if t.labels]
    accuracy = sum(correct) / len(correct)
    print(f"\n{'=' * 60}\nACCURACY\n{'=' * 60}")
    print(f"overall intent accuracy: {accuracy:.1%}  ({sum(correct)}/{len(correct)})")

    per_class: dict[str, list[bool]] = defaultdict(list)
    for (ticket, classification), ok in zip(results, correct):
        per_class[ticket.labels.intent].append(ok)
    worst = sorted(per_class.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))[:5]
    print("\nweakest classes:")
    for intent, oks in worst:
        print(f"  {intent:<24} {sum(oks)}/{len(oks)} = {sum(oks) / len(oks):.0%}")

    # --- calibration ----------------------------------------------------------
    print(f"\n{'=' * 60}\nCALIBRATION\n{'=' * 60}")
    calibration_table([(c.confidence, ok) for (_, c), ok in zip(results, correct)])

    # --- deny-list recall (the governance metric) -----------------------------
    print(f"\n{'=' * 60}\nDENY-LIST RECALL (D-04)\n{'=' * 60}")
    for intent in sorted(DENY_LIST_INTENTS):
        population = [(t, c) for t, c in results if t.labels and t.labels.intent == intent]
        if not population:
            continue
        caught_top1 = sum(1 for _, c in population if c.is_deny_listed)
        caught_alts = sum(
            1 for _, c in population if c.is_deny_listed or c.alternatives_include_deny_listed
        )
        marker = "  <- groundable, real residual" if intent in GROUNDABLE_DENY else ""
        print(
            f"  {intent:<22} n={len(population):>3}  "
            f"layer1 {caught_top1}/{len(population)} = {caught_top1 / len(population):>5.0%}  "
            f"+layer3 {caught_alts}/{len(population)} = {caught_alts / len(population):>5.0%}"
            f"{marker}"
        )

    leaked = [
        t.ticket_id
        for t, c in results
        if t.labels and t.labels.must_not_auto_respond and not c.is_deny_listed
        and not c.alternatives_include_deny_listed
    ]
    print(f"\ndeny-listed tickets missed by BOTH classifier layers: {len(leaked)}")
    if leaked:
        print(f"  {', '.join(leaked[:10])}")
    print("  (the lexical pre-screen, D1 layer 2, is a further independent control)")

    # --- throughput budget (F7) ----------------------------------------------
    print(f"\n{'=' * 60}\nTHROUGHPUT BUDGET (F7)\n{'=' * 60}")
    ordered = sorted(latencies)
    p95 = ordered[int(0.95 * len(ordered)) - 1]
    print(f"  wall clock            : {elapsed:.0f}s for {len(tickets)} tickets")
    print(f"  per ticket, mean      : {elapsed / len(tickets):.2f}s")
    print(f"  per ticket, median    : {ordered[len(ordered) // 2]:.2f}s")
    print(f"  per ticket, p95       : {p95:.2f}s   (target < 3s end to end)")
    print(f"  provider calls        : {client.stats.attempted} attempted, "
          f"{client.stats.succeeded} ok, {client.stats.failed} failed")
    print(f"  cache hits            : {client.stats.cache_hits}")
    print(f"  retries               : {client.stats.retries}")
    print(f"  degraded              : {client.stats.degraded}")
    calls_per_ticket = client.stats.attempted / len(tickets)
    print(f"\n  calls per ticket      : {calls_per_ticket:.2f} (classification only)")
    print(f"  projected for 120     : {calls_per_ticket * 120:.0f} classification calls")
    print(f"  projected wall clock  : {elapsed / len(tickets) * 120:.0f}s "
          f"({elapsed / len(tickets) * 120 / 60:.1f} min) for classification alone")

    print(f"\nfallbacks: {Counter(bool(c.fallback_reason) for _, c in results)[True]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
