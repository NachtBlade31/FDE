"""The preflight's cost estimate and its refusal branch.

`check_env.py` had no test at all, and its refusal branch is the gate that is
supposed to stop a fourth run being lost to the daily token cap. The estimate it
feeds is not a decoration: if `estimated_run_cost` is too low, `fits()` returns
True on a day that cannot take the run, and the gate waves through exactly what
it exists to stop.

So the property under test is directional. The estimate must not be optimistic.

The module makes a live provider call at import-time only inside `main()`, so the
pure functions are safe to import and exercise directly.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.token_budget import TokenLedger

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_env", REPO / "scripts" / "check_env.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_env = _load()


# --- the estimate is anchored to artifacts -----------------------------------


def test_cost_per_call_is_the_measured_figure():
    """47,774 tokens over 74 successful calls in the 8 Sep cold run."""
    assert check_env.TOKENS_PER_PROVIDER_CALL == 646
    assert round(47_774 / 74) == check_env.TOKENS_PER_PROVIDER_CALL


def test_calls_per_ticket_is_one_plus_the_shipped_fcr():
    """One classification always, plus one generation per auto-response.

    The multiplier must come from a HEALTHY artifact. It was briefly 1.35, taken
    from the degraded cold run's own auto-respond rate — a rate depressed by the
    26 tickets that never reached the model. That let a run's failure make the
    next run look cheap, which is the wrong direction for this number.
    """
    shipped_fcr = 0.64  # margin 0.85, 2026-09-07-routing-200.txt
    assert check_env.CALLS_PER_TICKET == pytest.approx(1 + shipped_fcr, abs=0.01)
    assert check_env.CALLS_PER_TICKET > 1.35, "must not regress to the degraded rate"


def test_a_120_ticket_run_is_costed_at_more_than_half_the_daily_cap():
    cost = check_env.estimated_run_cost(120)

    assert cost == pytest.approx(127_000, abs=2_000)
    assert cost > 200_000 / 2, "two full runs must not appear to fit in one day"


def test_the_estimate_scales_with_ticket_count():
    assert check_env.estimated_run_cost(240) == pytest.approx(
        2 * check_env.estimated_run_cost(120), rel=0.01
    )
    assert check_env.estimated_run_cost(0) == 0


def test_the_estimate_is_never_below_one_call_per_ticket():
    """The floor case: even if nothing auto-responds, every ticket is classified."""
    for n in (1, 10, 80, 120):
        assert check_env.estimated_run_cost(n) >= n * check_env.TOKENS_PER_PROVIDER_CALL


# --- the refusal branch -------------------------------------------------------


def test_an_exhausted_day_refuses_a_run(tmp_path):
    ledger = TokenLedger(path=tmp_path / "l.json", cap=200_000)
    ledger.record(47_774, exhausted=True)

    assert not ledger.view().fits(check_env.estimated_run_cost(120))


def test_a_day_with_one_run_already_spent_refuses_a_second(tmp_path):
    """The whole point: 127,000 of 200,000 leaves no room for another 127,000."""
    ledger = TokenLedger(path=tmp_path / "l.json", cap=200_000)
    ledger.record(check_env.estimated_run_cost(120))

    assert not ledger.view().fits(check_env.estimated_run_cost(120))


def test_a_fresh_day_admits_one_run(tmp_path):
    ledger = TokenLedger(path=tmp_path / "l.json", cap=200_000)

    assert ledger.view().fits(check_env.estimated_run_cost(120))


def test_the_budget_report_names_the_reset_and_the_estimate(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_LEDGER_PATH", str(tmp_path / "l.json"))
    text = check_env.budget_report(120)

    assert "00:00 UTC" in text
    assert "cannot promise" in text
    assert "fits" in text  # either "fits" or "DOES NOT FIT"


# --- the probe size matches the largest call the pipeline makes ---------------


def test_the_probe_reserves_as_much_as_the_largest_real_call():
    """A probe that only clears classification's 500 does not show that
    generation's 700 will go through."""
    from src.classify import Classifier  # noqa: F401
    import inspect

    import src.generate as generate

    source = inspect.getsource(generate)
    assert "max_tokens=700" in source
    assert check_env.PROBE_MAX_TOKENS == 700
