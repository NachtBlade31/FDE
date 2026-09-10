"""The preflight's cost estimate and its refusal gate.

`check_env.py` had no test at all, and its gate is what is supposed to stop a
fourth run being lost to the daily token cap. The estimate feeding it is not a
decoration: if `estimated_run_cost` is too low, the gate opens on a day that
cannot take the run — the precise failure D-45 exists to prevent. So the property
under test is directional. The estimate must not be optimistic.

**The constants are checked against the artifacts, not against themselves.** An
earlier version of this file asserted `TOKENS_PER_PROVIDER_CALL == 646` and
`round(47774/74) == 646`, which is a literal restating its own literal: if the
artifact were regenerated with different figures, nothing would notice. That is
the drift this project has now had five separate incidents of, so these tests
parse the evidence files and derive the expected values.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

from src.token_budget import BudgetView, TokenLedger

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "evaluation" / "results"
HEALTHY_RUNS = [
    RESULTS / "2026-09-10-gate-run-1" / "metrics.json",
    RESULTS / "2026-09-10-gate-run-2" / "metrics.json",
]
SWEEP = RESULTS / "2026-09-07-routing-200.txt"


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_env", REPO / "scripts" / "check_env.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_env = _load()


# --- the constants must agree with the evidence files ------------------------


def _measured_costs_per_call() -> list[int]:
    """Every healthy run's cost per call, rounded up."""
    costs = []
    for path in HEALTHY_RUNS:
        if not path.exists():
            continue
        run = json.loads(path.read_text(encoding="utf-8"))["run"]
        assert not run["degraded"], f"{path} is degraded and must not set the estimate"
        costs.append(math.ceil(run["tokens_used"] / run["provider_calls_succeeded"]))
    return costs


def _shipped_fcr() -> float:
    """The FCR row for the margin the system actually ships (src/config.py)."""
    from src.config import DEFAULT_CONFIDENCE_THRESHOLD as shipped

    for line in SWEEP.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*(\d\.\d\d)\s*\|\s*([\d.]+)%\s*\|", line)
        if match and float(match.group(1)) == pytest.approx(shipped):
            return float(match.group(2)) / 100
    raise AssertionError(f"no sweep row for the shipped margin {shipped}")


def test_cost_per_call_is_at_least_what_every_healthy_run_measured():
    """Directional, not an equality.

    An equality against one artifact pins the constant to that artifact and
    forbids correcting it — which is how 646, taken from a degraded run, stayed
    in place until it was 5 tokens per call BELOW what healthy runs measured.
    The requirement is that the estimate is never optimistic.
    """
    costs = _measured_costs_per_call()
    assert costs, "no healthy run artifact to check against"
    assert check_env.TOKENS_PER_PROVIDER_CALL >= max(costs)
    # ...and not absurdly above it either, or the gate refuses everything.
    assert check_env.TOKENS_PER_PROVIDER_CALL <= max(costs) * 1.25


@pytest.mark.skipif(not SWEEP.exists(), reason="sweep artifact not present")
def test_calls_per_ticket_is_one_plus_the_shipped_configuration_s_fcr():
    """One classification always, plus one generation per auto-response.

    The multiplier must come from a HEALTHY artifact at the SHIPPED margin. It
    was briefly 1.35, taken from the degraded cold run's own auto-respond rate —
    a rate depressed by the 26 tickets that never reached the model, which let a
    run's failure make the next run look cheap.
    """
    assert check_env.CALLS_PER_TICKET == pytest.approx(1 + _shipped_fcr(), abs=0.01)
    assert check_env.CALLS_PER_TICKET > 1.35, "must not regress to the degraded rate"


def test_a_120_ticket_run_is_costed_at_more_than_half_the_daily_cap():
    from src.token_budget import DEFAULT_DAILY_CAP

    cost = check_env.estimated_run_cost(120)
    assert cost > DEFAULT_DAILY_CAP / 2, "two full runs must not appear to fit in a day"


def test_the_estimate_is_never_below_one_call_per_ticket():
    """The floor: even if nothing auto-responds, every ticket is classified."""
    for n in (1, 10, 80, 120):
        assert check_env.estimated_run_cost(n) >= n * check_env.TOKENS_PER_PROVIDER_CALL


def test_the_estimate_scales_with_ticket_count():
    assert check_env.estimated_run_cost(0) == 0
    assert check_env.estimated_run_cost(240) > check_env.estimated_run_cost(120)


# --- the gate itself ---------------------------------------------------------
#
# Previously the tests reached past the gate to `view.fits()` and asserted on
# that, which is not the same as asserting the script refuses. These drive
# `gate()` directly, and each refusal must say WHY — a bare "does not fit" sent
# someone looking at the wrong thing on 8 September.


def _view(**kw) -> BudgetView:
    base = dict(day="2026-09-10", spent=0, cap=200_000, complete=True, exhausted=False)
    return BudgetView(**{**base, **kw})


def test_a_fresh_day_opens_the_gate():
    allowed, why_not = check_env.gate(_view(), 120)

    assert allowed
    assert why_not == ""


def test_an_exhausted_day_is_refused_and_says_the_provider_refused_it():
    allowed, why_not = check_env.gate(_view(spent=47_774, exhausted=True), 120)

    assert not allowed
    assert "quota exhausted" in why_not
    assert "00:00 UTC" in why_not


def test_a_day_with_one_run_already_spent_refuses_a_second():
    spent = check_env.estimated_run_cost(120)
    allowed, why_not = check_env.gate(_view(spent=spent), 120)

    assert not allowed
    assert "remain on this UTC day" in why_not


def test_an_incomplete_ledger_refuses_and_names_that_as_the_reason():
    """Refusing on missing records must not be reported as arithmetic — the two
    have different fixes, and only one of them is 'wait'."""
    allowed, why_not = check_env.gate(_view(complete=False), 120)

    assert not allowed
    assert "never recorded" in why_not
    assert "token_ledger.json" in why_not


def test_the_gate_scales_with_the_run_requested():
    """A day with room for a small run but not a large one must say so."""
    spent = 200_000 - check_env.estimated_run_cost(30)
    view = _view(spent=spent)

    assert check_env.gate(view, 20)[0]
    assert not check_env.gate(view, 120)[0]


def test_the_gate_agrees_with_a_real_ledger(tmp_path):
    """End to end through TokenLedger rather than a hand-built view."""
    ledger = TokenLedger(path=tmp_path / "l.json", cap=200_000)
    assert check_env.gate(ledger.view(), 120)[0]

    ledger.record(10_000, exhausted=True)
    allowed, why_not = check_env.gate(ledger.view(), 120)
    assert not allowed
    assert "quota exhausted" in why_not


# --- reporting ---------------------------------------------------------------


def test_the_budget_report_names_the_reset_and_the_estimate(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_LEDGER_PATH", str(tmp_path / "l.json"))
    text = check_env.budget_report(120)

    assert "00:00 UTC" in text
    assert "cannot promise" in text


def test_the_probe_reserves_as_much_as_the_largest_real_call():
    """A probe that only clears classification's 500 does not show that
    generation's 700 will go through."""
    import inspect

    import src.generate as generate

    assert "max_tokens=700" in inspect.getsource(generate)
    assert check_env.PROBE_MAX_TOKENS == 700
