"""Where CloudServe's agent time actually goes — and report Figure 1.

The report's largest number — escalations are 56.2% of tickets but consume
96.8% of all agent minutes, and 46.2% of all agent time went to escalations the
documentation already answered — was, until this script existed, typed into the
Stage 1 workbook and copied from there. **No committed code produced it.** It
reproduced exactly when checked, but a headline figure that nothing computes is
one edit away from the kind of drift this project has had nine times, so the
figure is now computed here and the report's chart is drawn from the same pass.

Inputs are the pack's development tickets. Each ticket's `history` records
`escalated` and `resolution_time_minutes`; `labels.answerable_from_docs` says
whether the documentation already held the answer.

    python scripts/analyse_agent_time.py
    python scripts/analyse_agent_time.py --tickets path/to/tickets.json --figure out.svg

The SVG is deterministic — no timestamp inside it — so regenerating it produces
no diff unless the data changed. Provenance goes to stdout, which is what the
committed evidence file captures.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACK = (
    REPO.parent
    / "FDE_Capstone_Complete-20260821T084330Z-1-001"
    / "FDE_Capstone_Complete"
    / "Capstone_Pack"
    / "05_Datasets"
)
DEFAULT_FIGURE = REPO / "docs" / "report" / "figures" / "figure1_agent_time.svg"

# --- palette -----------------------------------------------------------------
# The first three categorical slots of the reference palette, light mode (the
# report is printed). Validated with the dataviz skill's validate_palette.js:
# every check passes; aqua sits at 2.74:1 against the surface, so the relief rule
# applies and every value is also printed as text — in the labels and the caption.
#
# Text never sits inside a fill. Ink on the blue fill measures 4.46:1 and white
# 4.42:1, both under the 4.5:1 that 11px text needs, so value labels go above the
# bars, in ink on the surface. Axis ticks use secondary ink rather than the
# palette's muted grey, which measures about 3.5:1 on this surface.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRIDLINE = "#e1e0d9"
SERIES = {
    "escalated_answerable": ("#2a78d6", "Escalated — answerable from docs"),
    "escalated_not_answerable": ("#eb6834", "Escalated — not answerable"),
    "resolved": ("#1baf7a", "Resolved at first contact"),
}
ORDER = ("escalated_answerable", "escalated_not_answerable", "resolved")
TEXT_TOKENS = (INK, INK_SECONDARY)

BAR_HEIGHT = 24.0


def pct(numerator: float, denominator: float) -> Decimal:
    """Share as a percentage, rounded half-UP to one place — the report's rule."""
    if not denominator:
        return Decimal("0.0")
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


def load(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("tickets", data) if isinstance(data, dict) else data


def agent_time(tickets: list[dict]) -> dict:
    """Split tickets and agent minutes three ways.

    Every ticket lands in exactly one bucket, so the three counts sum to the
    ticket total and the three minute totals sum to all agent minutes. A ticket
    with no recorded minutes contributes zero minutes rather than being dropped,
    so the ticket share and the minute share are always taken over the same set.
    """
    buckets = {key: {"tickets": 0, "minutes": 0} for key in ORDER}
    for ticket in tickets:
        history = ticket.get("history") or {}
        labels = ticket.get("labels") or {}
        minutes = history.get("resolution_time_minutes") or 0
        if history.get("escalated"):
            key = (
                "escalated_answerable"
                if labels.get("answerable_from_docs")
                else "escalated_not_answerable"
            )
        else:
            key = "resolved"
        buckets[key]["tickets"] += 1
        buckets[key]["minutes"] += minutes

    n = sum(b["tickets"] for b in buckets.values())
    total_minutes = sum(b["minutes"] for b in buckets.values())
    escalated = buckets["escalated_answerable"]["tickets"] + buckets["escalated_not_answerable"]["tickets"]
    escalated_minutes = (
        buckets["escalated_answerable"]["minutes"] + buckets["escalated_not_answerable"]["minutes"]
    )
    return {
        "tickets": n,
        "minutes": total_minutes,
        "buckets": buckets,
        "escalated_ticket_share": pct(escalated, n),
        "escalated_minute_share": pct(escalated_minutes, total_minutes),
        "answerable_escalation_minute_share": pct(
            buckets["escalated_answerable"]["minutes"], total_minutes
        ),
    }


# --- the figure ----------------------------------------------------------------


def _luminance(hex_colour: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two colours."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _segment_path(x: float, y: float, w: float, h: float, round_end: bool) -> str:
    """A rectangle, with a 4px rounded data-end when it is the last segment.

    Square at the baseline (left), rounded at the data end (right).
    """
    if not round_end:
        return f"M{x:.2f},{y:.2f}h{w:.2f}v{h:.2f}h{-w:.2f}z"
    r = min(4.0, w / 2, h / 2)
    return (
        f"M{x:.2f},{y:.2f}h{w - r:.2f}"
        f"a{r:.2f},{r:.2f} 0 0 1 {r:.2f},{r:.2f}v{h - 2 * r:.2f}"
        f"a{r:.2f},{r:.2f} 0 0 1 {-r:.2f},{r:.2f}h{-(w - r):.2f}z"
    )


def render_svg(stats: dict) -> str:
    width, height = 720, 176
    left, right = 150.0, 640.0
    span = right - left
    gap = 2.0
    char_w = 6.6  # ~0.6em at 11px; used to keep neighbouring labels apart

    rows = [
        ("Tickets", f"n = {stats['tickets']:,}", "tickets", 58.0),
        ("Agent minutes", f"{stats['minutes']:,} min", "minutes", 122.0),
    ]

    parts: list[str] = []
    desc_lines: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Figure 1: share of tickets and share of agent minutes by outcome" '
        'font-family="system-ui, -apple-system, \'Segoe UI\', sans-serif">'
    )
    parts.append("<!-- Generated by scripts/analyse_agent_time.py from development_tickets.json -->")
    parts.append(f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>')

    # legend - always present for two or more series
    lx = 0.0
    for key in ORDER:
        colour, label = SERIES[key]
        parts.append(f'<rect x="{lx:.1f}" y="8" width="10" height="10" rx="2" fill="{colour}"/>')
        parts.append(
            f'<text x="{lx + 16:.1f}" y="17" font-size="11" fill="{INK_SECONDARY}">{label}</text>'
        )
        lx += 16 + len(label) * 6.1 + 24

    # recessive hairline grid behind the bars; ticks below
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        gx = left + span * frac
        parts.append(
            f'<line x1="{gx:.1f}" y1="44" x2="{gx:.1f}" y2="150" stroke="{GRIDLINE}" stroke-width="1"/>'
        )
        anchor = "start" if frac == 0 else "end" if frac == 1 else "middle"
        parts.append(
            f'<text x="{gx:.1f}" y="166" font-size="10" fill="{INK_SECONDARY}" '
            f'text-anchor="{anchor}">{int(frac * 100)}%</text>'
        )

    for title, subtitle, measure, y in rows:
        total = stats["tickets"] if measure == "tickets" else stats["minutes"]
        parts.append(
            f'<text x="{left - 12:.1f}" y="{y + 11:.1f}" font-size="12" fill="{INK}" '
            f'text-anchor="end">{title}</text>'
        )
        parts.append(
            f'<text x="{left - 12:.1f}" y="{y + 24:.1f}" font-size="10" fill="{INK_SECONDARY}" '
            f'text-anchor="end">{subtitle}</text>'
        )

        cursor = left
        previous_right = -1e9
        for index, key in enumerate(ORDER):
            colour, label = SERIES[key]
            value = stats["buckets"][key][measure]
            share = pct(value, total)
            seg_w = span * float(value) / total if total else 0.0
            last = index == len(ORDER) - 1
            drawn_w = seg_w if last else max(0.0, seg_w - gap)
            unit = "tickets" if measure == "tickets" else "min"
            tooltip = f"{title} — {label}: {value:,} {unit} ({share}%)"
            desc_lines.append(tooltip)
            if drawn_w > 0:
                parts.append(
                    f'<path d="{_segment_path(cursor, y, drawn_w, BAR_HEIGHT, last)}" fill="{colour}">'
                    f"<title>{tooltip}</title></path>"
                )

            # value label above the segment, in ink on the surface, with a surface
            # halo so a gridline behind it never cuts through the glyphs
            text = f"{share}%"
            half = len(text) * char_w / 2
            cx = cursor + drawn_w / 2
            if cx - half < previous_right + 4:
                cx = previous_right + 4 + half
            previous_right = cx + half
            parts.append(
                f'<text x="{cx:.1f}" y="{y - 6:.1f}" font-size="11" font-weight="600" '
                f'fill="{INK}" stroke="{SURFACE}" stroke-width="3" stroke-linejoin="round" '
                f'paint-order="stroke" text-anchor="middle">{text}</text>'
            )
            cursor += seg_w

    parts.insert(3, "<desc>" + "; ".join(desc_lines) + "</desc>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# --- provenance ------------------------------------------------------------------


def git_commit() -> str:
    """The commit, marked dirty when the working tree differs from it.

    A banner that names HEAD while the code that ran was uncommitted ties the
    artifact to code that did not produce it (validator finding C-5).
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickets", type=Path, default=PACK / "development_tickets.json")
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--no-figure", action="store_true")
    args = parser.parse_args()

    if not args.tickets.exists():
        print(f"not found: {args.tickets}")
        return 1

    stats = agent_time(load(args.tickets))

    print("=" * 78)
    print("PROVENANCE")
    print("=" * 78)
    print(f"  generated : {datetime.datetime.now().isoformat(timespec='seconds')}")
    print(f"  commit    : {git_commit()}")
    print(f"  tickets   : {args.tickets.name}")
    print("=" * 78)
    print()
    print(f"tickets              : {stats['tickets']:,}")
    print(f"agent minutes        : {stats['minutes']:,}")
    print()
    print(f"{'bucket':34} {'tickets':>8} {'share':>7} {'minutes':>9} {'share':>7}")
    print("-" * 70)
    for key in ORDER:
        b = stats["buckets"][key]
        print(
            f"{SERIES[key][1]:34} {b['tickets']:>8,} {pct(b['tickets'], stats['tickets']):>6}% "
            f"{b['minutes']:>9,} {pct(b['minutes'], stats['minutes']):>6}%"
        )
    print()
    print(f"escalated share of tickets               : {stats['escalated_ticket_share']}%")
    print(f"escalated share of agent minutes         : {stats['escalated_minute_share']}%")
    print(f"answerable escalations, share of minutes : {stats['answerable_escalation_minute_share']}%")

    if not args.no_figure:
        args.figure.parent.mkdir(parents=True, exist_ok=True)
        args.figure.write_text(render_svg(stats), encoding="utf-8")
        shown = args.figure.relative_to(REPO) if args.figure.is_relative_to(REPO) else args.figure
        print(f"\nfigure written: {shown.as_posix() if hasattr(shown, 'as_posix') else shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
