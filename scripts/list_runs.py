"""Every run in the decision log, so `docs/validation-runs.md` can be checked.

Report §7.1 claimed the validation checkpoint runs were "logged". They were —
in `storage/decisions.db`, which nobody could read without writing this query.
A discipline claim a reader cannot verify is not a discipline claim, so the
query is a script and its output is a committed document.

    python scripts/list_runs.py
    python scripts/list_runs.py --tickets 80    # validation-sized runs only
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=REPO / "storage" / "decisions.db")
    parser.add_argument(
        "--tickets", type=int, help="only runs covering exactly this many tickets"
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"no decision log at {args.db}")
        return 1

    rows = sqlite3.connect(args.db).execute(
        """
        SELECT run_id,
               COUNT(*)                    AS records,
               COUNT(DISTINCT ticket_id)   AS tickets,
               MIN(created_at)             AS started,
               MAX(created_at)             AS ended
        FROM decisions
        GROUP BY run_id
        ORDER BY started
        """
    ).fetchall()

    if args.tickets is not None:
        rows = [r for r in rows if r[2] == args.tickets]

    print(f"{'run_id':26} {'records':>8} {'tickets':>8}  started              duration")
    print("-" * 78)
    for run_id, records, tickets, started, ended in rows:
        try:
            from datetime import datetime

            fmt = "%Y-%m-%d %H:%M:%S.%f"
            seconds = (
                datetime.strptime(ended, fmt) - datetime.strptime(started, fmt)
            ).total_seconds()
            duration = f"{seconds:,.0f}s"
        except (ValueError, TypeError):  # pragma: no cover - defensive
            duration = "?"
        print(f"{run_id:26} {records:>8} {tickets:>8}  {started[:19]}  {duration:>8}")

    print(f"\n{len(rows)} run(s). Cross-check against docs/validation-runs.md.")
    print(
        "A run here that has no artifact and no row in that document is an "
        "undisclosed run;\nthe log is the source of truth, not the document."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
