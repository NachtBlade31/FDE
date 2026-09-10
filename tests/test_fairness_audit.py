"""The fairness audit's refusal is a governance control, so it is tested.

The audit exists to answer "does some customer group get worse answers". Its
failure mode is not a crash — it is producing a confident, plausible-looking,
false answer from a run that could not support one. That happened: pointed at a
run whose provider had gone, it reported every segment negative and printed
`VERDICT: EXCEEDED — investigate` (D-44).

These tests pin the four behaviours that distinction rests on:

  - a degraded run is refused,
  - a collapsed distribution is refused,
  - a *cache replay* is NOT refused, because replayed routing decisions are real,
  - and `--allow-degraded` still labels its output as not a fairness result.

Plus the two ways the guard could be silently bypassed: a missing metrics file,
and a partial run whose baseline and system rates come from different tickets.

`scripts/` is not a package, so the module is loaded by path.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "fairness_audit", REPO / "scripts" / "fairness_audit.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = _load_audit()


# --------------------------------------------------------------------------
# fixtures: a tiny two-segment file where the labels are deliberately not flat
# --------------------------------------------------------------------------

def _tickets() -> list[dict]:
    """20 tickets. europe's label baseline is 80%, asia_pacific's is 40%.

    The gap is the whole point of the pre-registered method: a system that
    reproduced these labels exactly would show a 40-point raw spread and would
    be correct.
    """
    out = []
    for i in range(10):
        out.append(
            {
                "ticket_id": f"eu-{i}",
                "body": "x" * 200,
                "customer_region": "europe",
                "customer_tier": "business",
                "language_fluency": "fluent",
                "labels": {"expected_route": "auto_respond" if i < 8 else "escalate"},
            }
        )
    for i in range(10):
        out.append(
            {
                "ticket_id": f"ap-{i}",
                "body": "x" * 200,
                "customer_region": "asia_pacific",
                "customer_tier": "business",
                "language_fluency": "fluent",
                "labels": {"expected_route": "auto_respond" if i < 4 else "escalate"},
            }
        )
    return out


def _write_case(tmp_path: Path, run: dict, outcomes: list[dict] | None = None) -> Path:
    """A run directory as the harness writes one: outcomes.json beside metrics.json."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    if outcomes is None:
        # Mirrors the labels exactly: every delta is 0.0.
        outcomes = [
            {
                "ticket_id": t["ticket_id"],
                "terminal_state": (
                    "auto_responded"
                    if t["labels"]["expected_route"] == "auto_respond"
                    else "escalated_direct"
                ),
            }
            for t in _tickets()
        ]
    (run_dir / "outcomes.json").write_text(json.dumps(outcomes), encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps({"run": run}), encoding="utf-8")
    (tmp_path / "tickets.json").write_text(json.dumps(_tickets()), encoding="utf-8")
    return run_dir


HEALTHY = {
    "run_id": "test-healthy",
    "degraded": False,
    "distribution_collapsed": False,
    "cache_replay": False,
    "classification_fallback_rate": 0.0,
    "provider_calls_attempted": 20,
    "provider_calls_succeeded": 20,
    "cache_hits": 0,
}


def _run(tmp_path: Path, *extra: str) -> str:
    """Invoke the script the way a person would, and return its output."""
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "fairness_audit.py"),
            "--outcomes", str(tmp_path / "run" / "outcomes.json"),
            "--tickets", str(tmp_path / "tickets.json"),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


# --------------------------------------------------------------------------
# the refusal
# --------------------------------------------------------------------------

def test_a_healthy_run_is_reported_and_reaches_a_verdict(tmp_path):
    _write_case(tmp_path, HEALTHY)
    out = _run(tmp_path)

    assert "NOT PRODUCED" not in out
    assert "VERDICT: HOLDS" in out
    # Outcomes that mirror the labels must show no deviation, however unequal
    # the labels themselves are. That is the method working.
    assert "largest deviation from the label baseline: +0.0pt" in out


def test_a_degraded_run_is_refused(tmp_path):
    _write_case(tmp_path, {**HEALTHY, "degraded": True, "classification_fallback_rate": 0.29})
    out = _run(tmp_path)

    assert "FAIRNESS AUDIT — NOT PRODUCED" in out
    assert "marked degraded" in out
    assert "VERDICT" not in out
    # The baselines need no run, so they are still published.
    assert "label baseline spread" in out


def test_a_collapsed_distribution_is_refused(tmp_path):
    _write_case(tmp_path, {**HEALTHY, "distribution_collapsed": True})
    out = _run(tmp_path)

    assert "FAIRNESS AUDIT — NOT PRODUCED" in out
    assert "VERDICT" not in out


def test_a_cache_replay_is_not_refused(tmp_path):
    """A replay's routing decisions are real. Only a timing claim needs live calls.

    This is the one case where this audit and the throughput reporter (D-30)
    deliberately differ, so it is pinned rather than left to inference.
    """
    _write_case(
        tmp_path,
        {**HEALTHY, "cache_replay": True, "provider_calls_attempted": 0, "cache_hits": 20},
    )
    out = _run(tmp_path)

    assert "NOT PRODUCED" not in out
    assert "VERDICT: HOLDS" in out


def test_allow_degraded_reports_but_refuses_to_call_it_a_result(tmp_path):
    """The override must not produce an artifact that reads like a clean audit."""
    _write_case(tmp_path, {**HEALTHY, "degraded": True})
    out = _run(tmp_path, "--allow-degraded")

    assert "DEGRADED RUN — NOT A FAIRNESS RESULT" in out
    assert "largest deviation from the label baseline" in out
    # A bare "VERDICT: HOLDS" redirected to a file would be indistinguishable
    # from a real result. There must be no verdict at all.
    assert "VERDICT: HOLDS" not in out
    assert "VERDICT: EXCEEDED" not in out
    assert "NO VERDICT" in out


# --------------------------------------------------------------------------
# the ways the guard could be bypassed
# --------------------------------------------------------------------------

def test_outcomes_with_no_metrics_file_is_refused_not_waved_through(tmp_path):
    """Copying outcomes.json away from its metrics.json used to disable the guard.

    A guard that `cp` silences is not a guard: the dated evidence convention in
    evaluation/results/ is exactly the layout with no sibling metrics.json.
    """
    _write_case(tmp_path, {**HEALTHY, "degraded": True})
    (tmp_path / "run" / "metrics.json").unlink()

    out = _run(tmp_path)
    assert "NOT PRODUCED" in out
    assert "no metrics file was found" in out
    assert "VERDICT" not in out


def test_no_metrics_override_is_available_and_explicit(tmp_path):
    _write_case(tmp_path, HEALTHY)
    (tmp_path / "run" / "metrics.json").unlink()

    out = _run(tmp_path, "--no-metrics")
    assert "NOT PRODUCED" not in out
    assert "VERDICT: HOLDS" in out


def test_metrics_path_can_be_given_explicitly(tmp_path):
    _write_case(tmp_path, {**HEALTHY, "degraded": True})
    moved = tmp_path / "elsewhere.json"
    moved.write_text((tmp_path / "run" / "metrics.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "run" / "metrics.json").unlink()

    out = _run(tmp_path, "--metrics", str(moved))
    assert "marked degraded" in out


def test_a_partial_run_compares_the_same_tickets_on_both_sides(tmp_path):
    """The baseline must narrow to the tickets the run actually covered.

    Otherwise a run that stopped after the europe tickets is scored against a
    baseline computed over europe AND asia_pacific, and the difference between
    two populations is printed as a fairness gap.
    """
    every = _tickets()
    only_europe = [
        {
            "ticket_id": t["ticket_id"],
            "terminal_state": (
                "auto_responded"
                if t["labels"]["expected_route"] == "auto_respond"
                else "escalated_direct"
            ),
        }
        for t in every
        if t["customer_region"] == "europe"
    ]
    _write_case(tmp_path, HEALTHY, outcomes=only_europe)

    out = _run(tmp_path)
    assert "covering 10 of 20" in out
    # europe alone, mirrored exactly, is a zero delta. Against the full-file
    # baseline it would read as +20pt — a fabricated gap.
    assert "largest deviation from the label baseline: +0.0pt" in out
    assert "asia_pacific" not in out.split("customer_region")[1].split("=" * 78)[0]


def test_small_segments_carry_the_caveat_even_when_a_delta_is_shown(tmp_path):
    """The rows most likely to be quoted were the ones printing no warning."""
    every = _tickets()[:8]  # 8 europe tickets, below MIN_SEGMENT_N
    (tmp_path / "tickets.json").write_text(json.dumps(every), encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "outcomes.json").write_text(
        json.dumps(
            [{"ticket_id": t["ticket_id"], "terminal_state": "escalated_direct"} for t in every]
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(json.dumps({"run": HEALTHY}), encoding="utf-8")

    out = _run(tmp_path)
    assert "excluded" in out
    assert "exceeds condition" in out  # the delta is still shown...
    # ...and the row that shows it also carries its interval, and says the
    # interval is the SYSTEM rate's rather than the baseline's.
    region_line = next(
        line for line in out.splitlines() if "europe" in line and "pt" in line
    )
    assert "excluded" in region_line
    assert "system rate" in region_line


# --------------------------------------------------------------------------
# provenance (D-37)
# --------------------------------------------------------------------------

def test_the_artifact_names_the_run_it_describes(tmp_path):
    """Evidence that does not identify its input cannot be checked against it."""
    _write_case(tmp_path, {**HEALTHY, "run_id": "20260908T123457-8d9e6f"})
    out = _run(tmp_path)

    assert "PROVENANCE" in out
    assert "20260908T123457-8d9e6f" in out
    assert "commit" in out


# --------------------------------------------------------------------------
# the method itself
# --------------------------------------------------------------------------

def test_the_baseline_is_the_labels_not_an_assumed_flat_rate(tmp_path):
    base = audit.baselines(_tickets(), "customer_region")
    assert base["europe"] == (8, 10)
    assert base["asia_pacific"] == (4, 10)


@pytest.mark.parametrize("n", [1, 5, 20])
def test_wilson_widens_as_the_sample_shrinks(n):
    lo, hi = audit.wilson(n // 2, n)
    assert hi - lo > 0
    wider_lo, wider_hi = audit.wilson(0, 1)
    assert (wider_hi - wider_lo) >= (hi - lo)


def test_an_underpowered_segment_cannot_set_the_headline_verdict(tmp_path):
    """A segment the tool itself calls too small to support an inference must not
    be the number the report leads with. On the 10 September run `enterprise`
    (n=8, -37.5pt) came within 0.6 points of being that number, and one
    differently routed ticket moves an 8-ticket segment 12.5 points."""
    every = _tickets()[:8]          # 8 europe tickets, below MIN_SEGMENT_N
    (tmp_path / "tickets.json").write_text(json.dumps(every), encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "outcomes.json").write_text(
        json.dumps(
            [{"ticket_id": t["ticket_id"], "terminal_state": "escalated_direct"} for t in every]
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(json.dumps({"run": HEALTHY}), encoding="utf-8")

    out = _run(tmp_path)

    # The row is printed, flagged and excluded; the verdict rests on nothing.
    assert "exceeds condition" in out
    assert "excluded" in out
    assert "largest deviation from the label baseline: +0.0pt" in out
    assert "n>=10 only" in out
    assert "VERDICT: HOLDS" in out


# --------------------------------------------------------------------------
# a delta is not a finding until it survives being tested
# --------------------------------------------------------------------------


def test_mcnemar_is_two_sided_and_paired():
    """Concordant tickets carry no information, so only the discordant split
    matters — which is why a 30-ticket segment can still be uninformative."""
    assert audit.mcnemar_exact(0, 0) == 1.0
    assert audit.mcnemar_exact(6, 6) == 1.0
    assert audit.mcnemar_exact(5, 5) == 1.0
    # 10 vs 2 is the asia_pacific split on the 10 Sep run.
    assert audit.mcnemar_exact(10, 2) == pytest.approx(0.0386, abs=0.001)
    # Symmetric: direction must not change the evidence.
    assert audit.mcnemar_exact(2, 10) == audit.mcnemar_exact(10, 2)
    assert audit.mcnemar_exact(4, 5) == 1.0


def test_holm_is_monotone_and_never_reduces_a_p_value():
    raw = {"a": 0.001, "b": 0.02, "c": 0.30, "d": 0.90}
    adj = audit.holm(raw)

    assert all(adj[k] >= raw[k] for k in raw)
    ordered = [adj[k] for k in sorted(raw, key=lambda k: raw[k])]
    assert ordered == sorted(ordered), "adjusted p must not decrease down the ranking"
    assert adj["a"] == pytest.approx(0.004)


def test_a_lone_significant_segment_does_not_survive_eleven_comparisons():
    """The 10 September case: asia_pacific raw p=0.039 across 11 segments."""
    raw = {f"s{i}": 1.0 for i in range(10)}
    raw["asia_pacific"] = 0.0386

    assert audit.holm(raw)["asia_pacific"] > 0.05


def test_the_report_shows_the_discordant_split_and_a_p_value(tmp_path):
    _write_case(tmp_path, HEALTHY)
    out = _run(tmp_path)

    assert "disc" in out
    assert "Holm-adjusted across" in out
    assert "surviving correction at 0.05" in out


def test_the_verdict_says_what_it_is_and_is_not_a_claim_about(tmp_path):
    """The condition is in percentage points. Meeting or missing it is not the
    same as showing a segment's gap is distinguishable from chance, and the
    output must not let those be read as one statement."""
    _write_case(tmp_path, HEALTHY)
    out = _run(tmp_path)

    assert "The verdict is on the CONDITION" in out
    assert "not a claim that any" in out
