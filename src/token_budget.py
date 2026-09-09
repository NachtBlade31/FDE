"""A local ledger of the provider's undocumented daily token cap.

The free tier publishes per-minute limits in response headers. It also enforces
a **daily** cap that appears in no header at all — it surfaces only in the body
of a 429, once you have already hit it (D-40). So there is no way to ask the
provider "will a 120-ticket run fit in what is left today?".

That question has now been answered wrongly twice, and both times it cost a gate
run. The second time is the instructive one: `check_env` made a full-sized live
call, it succeeded, and I read that as "the budget has reset". It had not. A
successful call proves exactly one thing — that *one call* fits. The run stopped
at ticket 54 of 80 with `provider quota exhausted`.

This module keeps the only record that can answer the question: what this
machine has actually spent, per UTC day, summed from the provider's own usage
figures. It is deliberately a local estimate and says so — it cannot see spend
from another machine or another key — so it is used to *refuse* a run that
certainly will not fit, never to promise one will.

A run that dies mid-way is the case worth spelling out, because it is the case
that happened. Such a run spends tokens and never reaches the code that records
them. The ledger cannot know how much was lost, but it can know that *something*
was: `begin()` writes a marker, `record()` clears it, and a marker still standing
makes `complete` False so the shortfall is stated rather than silently absorbed
into apparent headroom.

The reset is midnight UTC, which is 05:30 in the author's local time; a run
started in the evening is spending the same day's allowance as one started that
morning, which is precisely the trap above.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# The cap is not documented and not in any header. This figure comes from the
# body of an actual 429 (D-40); it is a floor on what is knowable, not a promise.
DEFAULT_DAILY_CAP = 200_000

# Anchored to the repository, not the working directory. As a relative path this
# resolved against the CWD, so running from anywhere else produced an empty
# ledger reporting a full day's headroom — silently discarding a recorded
# `exhausted`, which is the one thing this module promises it can never do.
DEFAULT_LEDGER = Path(__file__).resolve().parents[1] / "storage" / "token_ledger.json"


def utc_day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


@dataclass(frozen=True)
class BudgetView:
    """What is known about today's spend, and how confident that is."""

    day: str
    spent: int
    cap: int
    # False when spend is known to be missing from the count: either the ledger
    # file was unreadable, or a run announced itself and never came back to
    # record what it spent. The second case is the one that lost three runs on
    # 8 September, and it used to leave no trace at all — the field said
    # "complete" precisely when it was least entitled to.
    complete: bool
    # Set when a run actually received "quota exhausted" from the provider. This
    # is the ONE authoritative signal available: the local sum can only ever be
    # an underestimate (another machine, another key, an unrecorded run), but a
    # 429 is the provider saying the day is over. It outranks the arithmetic.
    exhausted: bool = False

    @property
    def remaining(self) -> int:
        if self.exhausted:
            return 0
        return max(0, self.cap - self.spent)

    def fits(self, estimated_cost: int) -> bool:
        """Whether a run of this size can be *ruled in*. Never a guarantee.

        Fails closed. An unreadable ledger, or one with a run still unaccounted
        for, returns False — because in both cases the recorded spend is known to
        be lower than the real spend, and the entire point of this class is that
        it may rule a run out but must never wave one through on a gap in its own
        records.
        """
        if self.exhausted or not self.complete:
            return False
        return estimated_cost <= self.remaining

    def explain(self, estimated_cost: int | None = None) -> str:
        lines = [
            f"  UTC day             : {self.day} (resets at 00:00 UTC)",
            f"  recorded spend      : {self.spent:,} of {self.cap:,} tokens",
            f"  remaining (local)   : {self.remaining:,}",
        ]
        if self.exhausted:
            lines.append(
                "  EXHAUSTED           : a run today was refused with 'quota exhausted'."
                " Wait for 00:00 UTC."
            )
        if not self.complete:
            lines.append(
                "  INCOMPLETE          : a run started and never recorded its spend,"
                " so the real figure is higher than this."
            )
        if estimated_cost is not None:
            verdict = "fits" if self.fits(estimated_cost) else "DOES NOT FIT"
            lines.append(f"  a {estimated_cost:,}-token run  : {verdict}")
            if not self.fits(estimated_cost) and not self.exhausted and not self.complete:
                lines.append(
                    "                        (refused on incomplete records, not on"
                    " arithmetic — resolve the entry above)"
                )
        lines.append(
            "  This ledger counts only what this machine recorded. It can rule a"
            " run out; it cannot promise one will complete."
        )
        return "\n".join(lines)


class TokenLedger:
    """Append-only per-UTC-day token counter, stored as small JSON."""

    def __init__(self, path: Path | None = None, cap: int | None = None) -> None:
        self.path = Path(path or os.environ.get("TOKEN_LEDGER_PATH") or DEFAULT_LEDGER)
        self.cap = int(cap or os.environ.get("DAILY_TOKEN_CAP") or DEFAULT_DAILY_CAP)

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt ledger must never stop a run. It degrades to "unknown",
            # which the view reports as incomplete rather than as zero spend.
            return {"_corrupt": True}

    # -- knowing about runs that never came back -----------------------------

    @staticmethod
    def _corrupt(data: dict) -> bool:
        return bool(data.get("_corrupt"))

    def begin(self, *, day: str | None = None) -> None:
        """Announce that a run is starting.

        Nothing else can detect the failure that actually happened: a run spends
        tokens for several minutes and then dies — killed, crashed, interrupted —
        before `record()` at the end of the harness. No spend is written, and the
        next `view()` used to report the untouched total as though the day were
        fresh. That reading is indistinguishable from a genuinely unused day and
        is exactly the wrong way round for a safety control.

        A marker written here and cleared by `record()` makes the gap visible.
        """
        data = self._read()
        if self._corrupt(data):
            # Refuse to write over a file we could not read. Rebuilding it from
            # scratch would erase every earlier day — including a recorded
            # `exhausted` — and present the result as a clean slate. `view()`
            # keeps reporting incomplete, which now rules runs out.
            return
        key = day or utc_day()
        entry = data.get(key) or {"tokens": 0, "runs": 0}
        entry["in_flight"] = int(entry.get("in_flight", 0)) + 1
        data[key] = entry
        self._write(data)

    def _write(self, data: dict) -> None:
        """Replace the ledger atomically.

        `write_text` truncates before it writes, so a process killed mid-write
        left a zero-byte or half-written file — and the recovery path below then
        rebuilt it as a blank day, discarding the `exhausted` flag that a 429 had
        put there. Losing the ledger to a crash is tolerable; silently converting
        it into apparent headroom is not, and "killed mid-run" is the exact
        scenario this module exists for.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def record(
        self,
        tokens: int,
        *,
        day: str | None = None,
        exhausted: bool = False,
        closes_run: bool = True,
    ) -> BudgetView:
        """Add a run's measured cost to today's total, and close its marker.

        `exhausted` records that the provider itself refused the run for the
        period. That fact survives independently of the token arithmetic,
        because the arithmetic is always an underestimate.

        `closes_run=False` for a caller that never called `begin()` — the
        preflight probe, which spends tokens but is not a run. Without it a probe
        cleared the in-flight marker of a run still executing, or worse, erased
        the marker a crashed run had left behind. Running the preflight is
        exactly what one does after losing a run, so that erasure hit the case
        the marker exists to record.
        """
        data = self._read()
        if self._corrupt(data):
            return self.view(day=day)
        key = day or utc_day()
        entry = data.get(key) or {"tokens": 0, "runs": 0}
        entry["tokens"] = int(entry.get("tokens", 0)) + max(0, int(tokens))
        entry["runs"] = int(entry.get("runs", 0)) + 1
        entry["exhausted"] = bool(entry.get("exhausted", False) or exhausted)
        if closes_run:
            # This run came back, so it is no longer unaccounted for. Note this
            # happens even when the run spent nothing: a full cache replay costs
            # zero tokens and is still a run that completed, and an early return
            # here used to leave its marker standing for the rest of the day.
            entry["in_flight"] = max(0, int(entry.get("in_flight", 0)) - 1)
        data[key] = entry
        self._write(data)
        return self.view(day=key)

    def view(self, *, day: str | None = None) -> BudgetView:
        data = self._read()
        key = day or utc_day()
        entry = data.get(key) or {}
        return BudgetView(
            day=key,
            spent=int(entry.get("tokens", 0)),
            cap=self.cap,
            complete=(
                not data.get("_corrupt", False)
                and int(entry.get("in_flight", 0)) == 0
            ),
            exhausted=bool(entry.get("exhausted", False)),
        )
