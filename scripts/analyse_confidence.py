"""Can a routing threshold be derived from this data? — open decision O-3.

Design decision D4 requires the threshold to be derived rather than chosen. That
presupposes a variable with enough spread to sweep. This script tests whether
self-reported confidence has any, and whether the margin between the top choice
and the best alternative has more.

Two things are reported that the earlier evaluation got wrong:

  ECE rather than the maximum gap. Headlining the largest single-bin gap lets one
  ticket in a sparse bin declare a governance failure. Expected Calibration Error
  weights each bin by its population, which is the figure the "within five points"
  condition should be read against. Every bin is still shown, with its n; none is
  dropped, because dropping sparse bins is the failure the Evaluation Framework
  warns about.

  Wilson intervals. A bin holding one ticket cannot support inference, and saying
  so is more honest than either deleting it or treating it as a finding.

Runs from cache, so it costs no allowance once the classifier has been evaluated.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from src.classify import Classifier  # noqa: E402
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


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval. Behaves sensibly at n=1, unlike the normal approximation."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def calibration(rows: list[tuple[float, bool]], label: str, bands: int = 5) -> float:
    """Print every bin with its interval, and return population-weighted ECE."""
    print(f"\n{label}")
    print(f"{'band':>10} | {'n':>4} | {'stated':>7} | {'observed':>8} | {'95% CI':>16} | {'gap':>7}")
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
        lo, hi = wilson(hits, len(group))
        gap = stated - observed
        ece += (len(group) / total) * abs(gap)
        note = "  <- n too small to infer" if len(group) < 5 else ""
        print(
            f"{low:.1f}-{high:.1f}   | {len(group):>4} | {stated:>6.1%} | {observed:>7.1%} | "
            f"[{lo:>5.1%},{hi:>6.1%}] | {gap:>+6.1%}{note}"
        )

    print(f"\n  ECE (population-weighted): {ece:.1%}   governance condition: within 5 points")
    print(f"  {'PASSES' if ece <= 0.05 else 'FAILS'} on ECE")
    return ece


def main() -> int:
    tickets, _ = normalise_batch(
        json.loads((PACK / "development_tickets.json").read_text(encoding="utf-8"))[:100]
    )
    settings = Settings.from_env()
    client = LLMClient(settings, cache_path=REPO / "storage" / "cache")
    classifier = Classifier(client)

    results = [(t, classifier.classify(t)) for t in tickets]
    live = client.stats.attempted
    print(f"tickets: {len(results)}   provider calls: {live}   cache hits: {client.stats.cache_hits}")
    if live:
        print("NOTE: some classifications were live; re-run for a pure cache read.")

    correct = [t.labels.intent == c.intent for t, c in results]
    print(f"accuracy: {sum(correct) / len(correct):.1%}")

    # --- is top-1 confidence sweepable? --------------------------------------
    top1 = [c.confidence for _, c in results]
    print(f"\n{'=' * 68}\nSPREAD\n{'=' * 68}")
    print(f"top-1 confidence : {len(set(top1))} distinct values, "
          f"min {min(top1):.2f} max {max(top1):.2f}")

    margins = []
    for _, c in results:
        best_alt = max((a.confidence for a in c.alternatives), default=0.0)
        margins.append(max(0.0, c.confidence - best_alt))
    print(f"margin (top1-alt): {len(set(margins))} distinct values, "
          f"min {min(margins):.2f} max {max(margins):.2f}")

    for name, values in (("top-1 confidence", top1), ("margin", margins)):
        in_top_band = sum(1 for v in values if v >= 0.8) / len(values)
        print(f"  {name:<18} share at or above 0.80: {in_top_band:.0%}")

    # --- calibration on both --------------------------------------------------
    print(f"\n{'=' * 68}\nCALIBRATION\n{'=' * 68}")
    ece_conf = calibration(list(zip(top1, correct)), "By self-reported top-1 confidence:")
    ece_margin = calibration(list(zip(margins, correct)), "By margin (top-1 minus best alternative):")

    # --- coverage / precision curve on margin --------------------------------
    print(f"\n{'=' * 68}\nPRECISION vs COVERAGE, sweeping MARGIN (D4)\n{'=' * 68}")
    print(f"{'threshold':>10} | {'coverage':>9} | {'precision':>10} | {'n above':>8}")
    print("-" * 48)
    for threshold in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        above = [ok for m, ok in zip(margins, correct) if m >= threshold]
        if not above:
            print(f"{threshold:>10.2f} |     0.0% |          - |        0")
            continue
        print(
            f"{threshold:>10.2f} | {len(above) / len(margins):>8.1%} | "
            f"{sum(above) / len(above):>9.1%} | {len(above):>8}"
        )

    print(f"\nECE by top-1 confidence: {ece_conf:.1%}   ECE by margin: {ece_margin:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
