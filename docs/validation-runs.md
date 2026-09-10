# Every run against the validation set

The Project Brief permits a small number of checkpoint runs against the
validation split and forbids tuning against it. Report §7.1 claimed these runs
were "logged". **They were not** — the claim was true of the decision log, which
records every run, but there was no document a reader could check, and a
discipline claim you cannot verify is not a discipline claim. The sixth validator
review found it. This file is that log, written from `storage/decisions.db`,
which has recorded every run since the first.

## The runs

Reconstructed by `SELECT run_id, count(*), count(DISTINCT ticket_id), min(created_at), max(created_at) FROM decisions GROUP BY run_id`.

| # | `run_id` | Started (UTC) | Duration | Cold or replay | Tokens | Artifact | Why it ran |
|---|---|---|---|---|---|---|---|
| 1 | `20260908T123457-8d9e6f` | 8 Sep 12:35 | 36s | replay | 0 | `2026-09-08-gate-run-degraded/` | Replay of an earlier live run whose artifact had been overwritten at a generic output path. Degraded; kept as the input the fairness audit refuses (D-44). |
| 2 | `20260908T180048-d61670` | 8 Sep 18:00 | 5m | cold | 47,774 | `2026-09-08-gate-run-cold/` | First cold gate attempt. Quota-exhausted at VAL-0054; degraded, business rates withheld (D-45). |
| 3 | `20260910T124603-e5dc08` | 10 Sep 12:46 | 8m | cold | 75,190 | `2026-09-10-gate-run-1/` | First healthy gate run. Guardrail accounting later found wrong — see that directory's `NOTE.md` (D-47). |
| 4 | `20260910T142951-97d609` | 10 Sep 14:29 | 8m | cold | 76,224 | `2026-09-10-gate-run-2/` | **The headline run.** Re-run cold after the D-47 fix. |
| 5 | `20260910T151952-17465c` | 10 Sep 15:19 | 48s | replay | 0 | none | Verification only. After changing `_validate` to distinguish an empty draft from a withheld one, replayed run 4 from cache to confirm the counts were unchanged: 45 / 35 / 4. Output written to a scratch directory. |
| 6 | `20260910T200725-d47fa0` | 10 Sep 20:07 | 21s | replay | 0 | none | Verification only. Same purpose after adding the substance check to `_grounding`: confirmed 45 / 35 / 4 again. Scratch directory. |

An eighth entry, `20260909T052547-37a82f`, is 8 tickets from `data/sample_tickets.json` — development data, not validation.

## What this shows, and what it does not

**Two runs produced no artifact.** Runs 5 and 6 were cache replays whose only
purpose was to confirm that a code change had not moved the numbers in run 4.
They made **no provider calls and spent no tokens** — the token ledger's
`2026-09-10` total of 151,968 is accounted for entirely by runs 3 and 4 plus a
554-token preflight probe. So they cannot have fitted anything to the validation
set: a replay returns decisions already made.

They still wrote to the shared decision log, which is why they appear here. That
is the correct behaviour — a log that omitted runs would be worse — but it means
the log alone overstates how many times the validation set was *exercised*.

**No parameter was tuned against this data.** Every threshold in `src/config.py`
was derived on development tickets and the derivations are committed
(`2026-09-07-routing-200.txt`, `2026-09-08-fairness-baselines-dev.txt`). The one
finding that came out of validation — the `asia_pacific` gap — is explicitly
**not** acted on, for exactly this reason (report §8.3, §10.2, D-46).

**The honest limit.** Six runs against an 80-ticket set is more than "a small
number of checkpoint runs" implies, even though four of them were forced by
provider failures and two were verification replays. A reader is entitled to
weigh that. The defence is that the artifacts show what each run was for, and
that nothing was changed in response to any of them except the two defects the
runs themselves exposed — both of which were bugs in the *measurement*, not
adjustments to the system's behaviour on this data.

## Keeping this current

`scripts/list_runs.py` regenerates the table from `storage/decisions.db`. Run it
before packaging.
