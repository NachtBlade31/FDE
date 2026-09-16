"""The report's largest number, bound to the data that produces it.

"Escalations are 56.2% of tickets and consume 96.8% of agent minutes; 46.2% of
all agent time went to escalations the documentation already answered." Until
`scripts/analyse_agent_time.py` existed, no committed code produced those figures
— they were typed into a workbook and copied into the report. These tests make
the chain mechanical: synthetic cases pin the arithmetic (they run in CI, where
the pack's dataset is absent), and a real-data case pins the report to the
dataset when it is present.
"""

from __future__ import annotations

import importlib.util
import re
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "analyse_agent_time", REPO / "scripts" / "analyse_agent_time.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


at = _load()


def _ticket(escalated: bool, answerable: bool, minutes):
    return {
        "history": {"escalated": escalated, "resolution_time_minutes": minutes},
        "labels": {"answerable_from_docs": answerable},
    }


# --- the arithmetic ------------------------------------------------------------


def test_every_ticket_lands_in_exactly_one_bucket():
    tickets = [
        _ticket(True, True, 100),
        _ticket(True, False, 50),
        _ticket(False, True, 10),
        _ticket(False, False, 40),
    ]
    stats = at.agent_time(tickets)

    assert sum(b["tickets"] for b in stats["buckets"].values()) == 4
    assert sum(b["minutes"] for b in stats["buckets"].values()) == 200
    assert stats["buckets"]["resolved"] == {"tickets": 2, "minutes": 50}


def test_shares_are_taken_over_the_same_tickets():
    """A ticket with no recorded minutes counts as a ticket with zero minutes.

    Dropping it would compute the ticket share and the minute share over two
    different populations — the same defect the fairness audit had (D-44).
    """
    tickets = [_ticket(True, True, None), _ticket(False, False, 30)]
    stats = at.agent_time(tickets)

    assert stats["tickets"] == 2
    assert stats["escalated_ticket_share"] == Decimal("50.0")
    assert stats["escalated_minute_share"] == Decimal("0.0")


def test_percentages_round_half_up_like_the_report():
    assert at.pct(9, 16) == Decimal("56.3")   # 56.25: banker's rounding would give 56.2
    assert at.pct(7, 16) == Decimal("43.8")   # 43.75
    assert at.pct(0, 0) == Decimal("0.0")


# --- the figure ------------------------------------------------------------------


def _svg():
    tickets = [_ticket(True, True, 97), _ticket(True, False, 107), _ticket(False, False, 3)] * 10
    return at.render_svg(at.agent_time(tickets))


def test_the_figure_has_a_legend_for_every_series():
    svg = _svg()
    for _, label in at.SERIES.values():
        assert label in svg


def test_no_text_is_drawn_in_a_series_colour():
    """Text wears text tokens; identity comes from the mark beside it. A light
    series hue as text is illegible on the surface."""
    series_colours = {colour.lower() for colour, _ in at.SERIES.values()}
    for fill in re.findall(r'<text[^>]*fill="(#[0-9a-fA-F]{6})"', _svg()):
        assert fill.lower() not in series_colours


def test_all_text_uses_ink_tokens_that_clear_small_text_contrast():
    """Every glyph in the figure is ink or secondary ink on the surface, and both
    clear the 4.5:1 that 10-12px text needs."""
    fills = {f.lower() for f in re.findall(r'<text[^>]*fill="(#[0-9a-fA-F]{6})"', _svg())}

    assert fills <= {t.lower() for t in at.TEXT_TOKENS}
    for token in at.TEXT_TOKENS:
        assert at.contrast(token, at.SURFACE) >= 4.5


def test_no_value_label_sits_inside_a_filled_bar():
    """The first version placed labels inside the segments. Ink on the blue fill
    measured 4.46:1 and white 4.42:1 — both under 4.5:1 — so neither choice
    could make an in-fill label legible to the standard. Labels now sit above.
    """
    svg = _svg()
    bar_tops = {float(y) for y in re.findall(r'<path d="M[\d.]+,([\d.]+)', svg)}
    label_ys = [float(y) for y in re.findall(r'<text[^>]*y="([\d.]+)"[^>]*font-weight="600"', svg)]

    assert bar_tops and label_ys
    for label_y in label_ys:
        for top in bar_tops:
            assert not (top <= label_y <= top + at.BAR_HEIGHT), (
                f"a value label at y={label_y} is inside the bar spanning {top}-{top + at.BAR_HEIGHT}"
            )


def test_every_segment_carries_its_value_as_text_for_assistive_tech():
    """Colour is never the only channel: a <title> per segment and a <desc>."""
    svg = _svg()
    assert svg.count("<title>") == 6          # 3 segments x 2 bars
    assert "<desc>" in svg and 'role="img"' in svg


def test_the_figure_is_deterministic():
    """No timestamp inside the SVG, so regenerating it creates no diff.

    Two renders microseconds apart would match even if the file carried today's
    date, so the date itself is excluded rather than inferred from equality.
    """
    svg = _svg()
    assert svg == _svg()
    assert not re.search(r"20\d\d-\d\d-\d\d", svg), "the figure carries a date stamp"


# --- the real data, and the report --------------------------------------------


DEV = at.PACK / "development_tickets.json"


@pytest.mark.skipif(not DEV.exists(), reason="pack dataset not present (expected in CI)")
def test_the_headline_figures_reproduce_from_the_dataset():
    stats = at.agent_time(at.load(DEV))

    assert stats["tickets"] == 500
    assert stats["escalated_ticket_share"] == Decimal("56.2")
    assert stats["escalated_minute_share"] == Decimal("96.8")
    assert stats["answerable_escalation_minute_share"] == Decimal("46.2")


@pytest.mark.skipif(not DEV.exists(), reason="pack dataset not present (expected in CI)")
def test_the_committed_figure_is_what_the_script_produces_today():
    """Otherwise the report could show a chart the code no longer generates."""
    committed = (REPO / "docs" / "report" / "figures" / "figure1_agent_time.svg").read_text(
        encoding="utf-8"
    )

    assert committed == at.render_svg(at.agent_time(at.load(DEV)))


def test_the_report_quotes_the_figures_and_embeds_figure_1():
    report = (REPO / "docs" / "report" / "Report.md").read_text(encoding="utf-8")

    for figure in ("56.2%", "96.8%", "46.2%"):
        assert figure in report
    assert "figures/figure1_agent_time.svg" in report, "Figure 1 is cited, so it must exist"
    assert (REPO / "docs" / "report" / "figures" / "figure1_agent_time.svg").exists()


# --- provenance ----------------------------------------------------------------
#
# `git status --porcelain` counts untracked files, and redirecting a script's
# output creates one before the script runs — so every artifact saved that way was
# stamped `-dirty` even from a clean commit. The flag below is the fix, and these
# tests are why it cannot regress silently.


class _Result:
    def __init__(self, stdout):
        self.stdout = stdout


def test_a_dirty_tree_is_marked(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _Result("abc1234\n" if "rev-parse" in cmd else " M src/pipeline.py\n")

    monkeypatch.setattr(at.subprocess, "run", fake_run)

    assert at.git_commit() == "abc1234-dirty"


def test_untracked_files_alone_do_not_mark_the_tree_dirty(monkeypatch):
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return _Result("abc1234\n" if "rev-parse" in cmd else "")

    monkeypatch.setattr(at.subprocess, "run", fake_run)

    assert at.git_commit() == "abc1234"
    assert any("--untracked-files=no" in cmd for cmd in seen), (
        "without this flag, redirecting output to a new file marks the tree dirty"
    )


def test_provenance_never_raises(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("git is not installed")

    monkeypatch.setattr(at.subprocess, "run", boom)

    assert at.git_commit() == "unknown"
