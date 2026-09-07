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
import math
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


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval. Behaves sensibly at n=1, unlike the normal approximation."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def calibration_table(rows: list[tuple[float, bool]], bands: int = 5) -> float:
    """Print every bin with its interval; return population-weighted ECE.

    The headline is ECE rather than the largest single-bin gap. A sparse bin
    can otherwise declare a governance failure on the strength of one ticket:
    an earlier version of this report printed a 75.0% gap from a bin holding
    a single prediction, against a condition of five points.

    No bin is dropped. Dropping sparse bins is the failure the Evaluation
    Framework warns about; the honest treatment is to show them with their n
    and their interval, and to say that one ticket cannot support inference.
    """
    print(f"\n{'band':>10} | {'n':>4} | {'stated':>7} | {'observed':>8} | {'95% CI':>16} | {'gap':>7}")
    print("-" * 68)

    ece = 0.0
    total = len(rows)
    for i in range(bands):
        low, high = i / bands, (i + 1) / bands
        group = [r for r in rows if low <= r[0] < high or (i == bands - 1 and r[0] == 1.0)]
        if not group:
            print(f"{low:.1f}-{high:.1f}   |    0 |       - |        - |                - |       -")
            continue
        stated = sum(c for c, _ in group) / len(group)
        hits = sum(1 for _, ok in group if ok)
        observed = hits / len(group)
        lo, hi = _wilson(hits, len(group))
        gap = stated - observed
        ece += (len(group) / total) * abs(gap)
        note = "  <- n too small to infer" if len(group) < 5 else ""
        print(
            f"{low:.1f}-{high:.1f}   | {len(group):>4} | {stated:>6.1%} | {observed:>7.1%} | "
            f"[{lo:>5.1%},{hi:>6.1%}] | {gap:>+6.1%}{note}"
        )

    print(f"\n  ECE (population-weighted): {ece:.1%}   condition: within 5 points")
    print(f"  {'PASSES' if ece <= 0.05 else 'FAILS'} on ECE")
    return ece


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
    print_provenance(settings)
    if not settings.has_model_access:
        print("no model access — cannot evaluate the classifier")
        return 1

    client = LLMClient(settings, cache_path=REPO / "storage" / "cache")
    classifier = Classifier(client)

    started = time.perf_counter()
    latencies: list[float] = []
    paced_each: list[float] = []
    results = []
    for index, ticket in enumerate(tickets, 1):
        t0 = time.perf_counter()
        paced_before = client.stats.paced_seconds
        results.append((ticket, classifier.classify(ticket)))
        latencies.append(time.perf_counter() - t0)
        paced_each.append(client.stats.paced_seconds - paced_before)
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
    ece = calibration_table([(c.confidence, ok) for (_, c), ok in zip(results, correct)])
    print(
        "\n  Headline is ECE, not the largest single-bin gap: a bin holding one\n"
        "  ticket must not be able to declare a governance failure on its own.\n"
        f"  ECE = {ece:.1%}"
    )

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

    if client.stats.attempted == 0:
        # Every classification was replayed from cache. Accuracy above is still
        # valid, because a cache hit replays a real completion — but latency and
        # calls per ticket would measure dictionary lookups. The design notes the
        # hidden run has a cold cache by definition, so a warm rehearsal would
        # validate nothing about the run that is actually graded.
        print(
            "\n  *** NOT A THROUGHPUT MEASUREMENT ***\n"
            f"  All {client.stats.cache_hits} classifications came from cache.\n"
            "  Clear storage/cache and re-run for a cold figure.\n"
        )
        print(f"\nfallbacks: {Counter(bool(c.fallback_reason) for _, c in results)[True]}")
        return 0

    # Within-run cache hits are duplicate tickets, not a warm cache: the supplied
    # data is templated (D-23), so a cold run still de-duplicates. Those are
    # excluded from the latency profile, which is measured over live calls only,
    # and the de-duplication rate is disclosed because it flatters wall-clock.
    # Two different questions, and conflating them answers neither.
    #
    #   processing latency - what the p95 < 3s target means: how long the system
    #     takes to handle a ticket once it is working on it.
    #   wall clock - what the gate's "reasonable time" means: how long the whole
    #     unattended run takes, including waiting for the token allowance to reset.
    #
    # Under token-per-minute pacing these diverge sharply. Reporting only the
    # first hides the real run duration; reporting only the second fails a target
    # it was never measuring.
    live = [
        (latency, paced)
        for latency, paced, (_, classification) in zip(latencies, paced_each, results)
        if not classification.from_cache
    ]
    live_latencies = [latency - paced for latency, paced in live]
    live_wall = [latency for latency, _ in live]
    if client.stats.cache_hits:
        print(
            f"\n  NOTE: {client.stats.cache_hits} of {len(tickets)} tickets duplicated an\n"
            f"  earlier ticket in this same run and were served from cache. Latency\n"
            f"  below is measured over the {len(live_latencies)} live calls only.\n"
        )

    ordered = sorted(live_latencies or latencies)
    p95 = ordered[int(0.95 * len(ordered)) - 1]
    wall = sorted(live_wall or latencies)
    wall_p95 = wall[int(0.95 * len(wall)) - 1]

    print(f"  wall clock, total     : {elapsed:.0f}s for {len(tickets)} tickets")
    print(f"  of which rate-limit pacing: {client.stats.paced_seconds:.0f}s "
          f"in {client.stats.paced_count} waits")
    print()
    print("  PROCESSING LATENCY (excludes pacing waits) - this is the p95 < 3s target")
    print(f"    mean                : {sum(ordered) / len(ordered):.2f}s")
    print(f"    median              : {ordered[len(ordered) // 2]:.2f}s")
    print(f"    p95                 : {p95:.2f}s   "
          f"{'PASSES' if p95 < 3.0 else 'FAILS'} the < 3s target")
    print()
    print("  WALL CLOCK PER TICKET (includes pacing) - this is the run duration")
    print(f"    median              : {wall[len(wall) // 2]:.2f}s")
    print(f"    p95                 : {wall_p95:.2f}s")
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
