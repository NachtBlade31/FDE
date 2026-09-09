"""The daily token ledger — the control that would have prevented two lost runs.

Its job is narrow and its failure mode is specific: it must never report more
budget than it can justify. An over-optimistic ledger sends an unattended run
into a cap it cannot clear, which is how both gate runs on 8 Sep were lost.

So the tests below pin asymmetry: the ledger may say "this will not fit", and it
may say "I do not know"; it may never turn a gap in its own records into
apparent headroom.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.token_budget import DEFAULT_DAILY_CAP, BudgetView, TokenLedger, utc_day


@pytest.fixture
def ledger(tmp_path):
    return TokenLedger(path=tmp_path / "ledger.json", cap=200_000)


def test_a_fresh_day_starts_at_zero(ledger):
    view = ledger.view()

    assert view.spent == 0
    assert view.remaining == 200_000
    assert view.complete


def test_recording_accumulates_within_a_day(ledger):
    ledger.record(47_774)
    view = ledger.record(30_000)

    assert view.spent == 77_774
    assert view.remaining == 122_226


def test_spend_is_scoped_to_the_utc_day_not_the_local_one(ledger):
    """The reset is 00:00 UTC — 05:30 local. An evening run spends the same
    day's allowance as that morning's, which is the trap that cost run two."""
    ledger.record(50_000, day="2026-09-08")
    ledger.record(10_000, day="2026-09-09")

    assert ledger.view(day="2026-09-08").spent == 50_000
    assert ledger.view(day="2026-09-09").spent == 10_000


def test_a_run_that_would_exceed_the_cap_is_ruled_out(ledger):
    ledger.record(160_000)
    view = ledger.view()

    assert not view.fits(106_000)
    assert "DOES NOT FIT" in view.explain(106_000)


def test_a_run_that_fits_is_reported_as_fitting_but_not_promised(ledger):
    ledger.record(10_000)
    view = ledger.view()

    assert view.fits(106_000)
    text = view.explain(106_000)
    assert "fits" in text
    # The wording must never promise completion — it counts one machine only.
    assert "cannot promise" in text


def test_remaining_never_goes_negative(ledger):
    ledger.record(250_000)

    assert ledger.view().remaining == 0
    assert not ledger.view().fits(1)


def test_a_corrupt_ledger_reports_incomplete_rather_than_zero_spend(tmp_path):
    """The dangerous failure is a lost record read as 'nothing spent yet'."""
    path = tmp_path / "ledger.json"
    path.write_text("{not json", encoding="utf-8")
    ledger = TokenLedger(path=path, cap=200_000)

    view = ledger.view()
    assert not view.complete
    assert "started and never recorded" in view.explain()
    assert "higher than this" in view.explain()


def test_a_missing_ledger_file_does_not_raise(tmp_path):
    ledger = TokenLedger(path=tmp_path / "nope" / "ledger.json", cap=200_000)

    assert ledger.view().spent == 0


def test_recording_creates_the_directory(tmp_path):
    ledger = TokenLedger(path=tmp_path / "deep" / "nested" / "ledger.json")
    ledger.record(100)

    assert (tmp_path / "deep" / "nested" / "ledger.json").exists()


def test_zero_or_negative_tokens_are_not_recorded(ledger):
    ledger.record(0)
    ledger.record(-5)

    assert ledger.view().spent == 0
    # A run that recorded nothing must not create a run entry either.
    assert not ledger.path.exists() or json.loads(ledger.path.read_text()) == {}


def test_the_cap_is_the_figure_from_the_429_body(tmp_path):
    """Not a guess. D-40 took it from an actual quota-exhausted response."""
    assert DEFAULT_DAILY_CAP == 200_000
    assert TokenLedger(path=tmp_path / "l.json").cap == 200_000


def test_the_cap_can_be_overridden_for_a_different_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("DAILY_TOKEN_CAP", "1000000")

    assert TokenLedger(path=tmp_path / "l.json").cap == 1_000_000


def test_utc_day_is_a_date_string():
    assert utc_day(datetime(2026, 9, 8, 23, 59, tzinfo=timezone.utc)) == "2026-09-08"
    assert utc_day(datetime(2026, 9, 9, 0, 1, tzinfo=timezone.utc)) == "2026-09-09"


def test_the_explanation_names_the_reset_so_a_reader_can_plan(ledger):
    text = ledger.view().explain()

    assert "00:00 UTC" in text
    assert "resets" in text


def test_view_is_immutable():
    view = BudgetView(day="2026-09-08", spent=1, cap=2, complete=True)

    with pytest.raises(Exception):
        view.spent = 5  # type: ignore[misc]


# --------------------------------------------------------------------------
# the provider's own refusal outranks the local arithmetic
# --------------------------------------------------------------------------

def test_a_quota_exhausted_run_marks_the_day_spent_whatever_the_count_says(ledger):
    """The local sum is always an underestimate; the 429 is ground truth.

    The cold run on 8 Sep recorded 47,774 tokens — 24% of the cap — and was
    nonetheless refused at ticket 54, because earlier runs that day had spent
    the rest without recording it. Arithmetic said "plenty left"; the provider
    said no. The provider wins.
    """
    view = ledger.record(47_774, exhausted=True)

    assert view.spent == 47_774          # the count is kept, and is honest
    assert view.remaining == 0           # but it does not govern
    assert not view.fits(1)
    assert "EXHAUSTED" in view.explain()
    assert "00:00 UTC" in view.explain()


def test_exhaustion_persists_across_later_records_for_the_same_day(ledger):
    ledger.record(10_000, exhausted=True)
    view = ledger.record(500)

    assert view.exhausted
    assert view.remaining == 0


def test_exhaustion_does_not_leak_into_the_next_day(ledger):
    ledger.record(10_000, day="2026-09-08", exhausted=True)

    assert ledger.view(day="2026-09-08").exhausted
    assert not ledger.view(day="2026-09-09").exhausted
    assert ledger.view(day="2026-09-09").fits(106_000)


def test_exhaustion_is_recorded_even_when_no_tokens_were_counted(ledger):
    """A run refused on its first call spends nothing and must still be recorded."""
    view = ledger.record(0, exhausted=True)

    assert view.exhausted
    assert not view.fits(1)


# --------------------------------------------------------------------------
# a run that never came back
# --------------------------------------------------------------------------
#
# This is the failure that actually happened three times on 8 September, and the
# one the ledger previously could not see: tokens spent, then the run ends before
# the code that records them. `complete` used to stay True, so the shortfall was
# absorbed into apparent headroom — the wrong direction for a safety control.


def test_a_run_that_starts_and_never_records_is_flagged_incomplete(ledger):
    ledger.begin()

    view = ledger.view()
    assert not view.complete
    assert "started and never recorded" in view.explain()
    assert "higher than this" in view.explain()


def test_a_run_that_completes_clears_its_marker(ledger):
    ledger.begin()
    view = ledger.record(1_000)

    assert view.complete
    assert view.spent == 1_000


def test_a_second_run_does_not_clear_the_first_run_s_marker(ledger):
    ledger.begin()          # run A starts
    ledger.begin()          # run B starts
    view = ledger.record(1_000)   # only one of them comes back

    assert not view.complete, "one run is still unaccounted for"


def test_an_abandoned_marker_does_not_inflate_the_spend(ledger):
    """The count stays honest; only the confidence flag changes."""
    ledger.record(5_000)
    ledger.begin()

    view = ledger.view()
    assert view.spent == 5_000
    assert not view.complete


def test_an_abandoned_run_on_a_previous_day_does_not_taint_today(ledger):
    ledger.begin(day="2026-09-08")

    assert not ledger.view(day="2026-09-08").complete
    assert ledger.view(day="2026-09-09").complete


def test_begin_survives_a_corrupt_ledger(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text("{not json", encoding="utf-8")
    led = TokenLedger(path=path, cap=200_000)

    led.begin()  # must not raise
    assert not led.view().complete


# --------------------------------------------------------------------------
# the ledger must not forget an exhausted day because of where it was invoked
# --------------------------------------------------------------------------


def test_the_default_ledger_path_is_anchored_to_the_repository(monkeypatch, tmp_path):
    """As a CWD-relative path this silently reported a full day's headroom when
    run from any other directory — discarding a recorded `exhausted`, which is
    the one thing this module promises it can never do."""
    monkeypatch.delenv("TOKEN_LEDGER_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    from src.token_budget import DEFAULT_LEDGER

    assert TokenLedger().path == DEFAULT_LEDGER
    assert DEFAULT_LEDGER.is_absolute()
    assert DEFAULT_LEDGER.parent.name == "storage"
    # And nothing was created under the unrelated working directory.
    assert not (tmp_path / "storage").exists()
