# Read this before quoting anything from this directory

This run is committed as evidence and **three of its recorded values are wrong**.
They are left as written rather than edited, because an artifact that has been
corrected after the fact is not an artifact. This note says what to distrust.

## What is wrong

This run predates the fix in **D-47**. An ungrounded draft short-circuited past
the validator, so four drafts that were generated and withheld were recorded as
tickets that never produced a draft, and the grounding guardrail — whose own
first condition covers exactly that case — was unreachable from the pipeline.

| Field | This artifact says | The truth for this run |
|---|---|---|
| `volume.blocked_by_guardrails` | `0` | **4** |
| `volume.escalated_without_a_block` | `37` | **33** |
| `governance.guardrail_activations` | `{}` | **`{"grounding": 4}`** |
| `governance.decisions_logged` | `934` | **334** |

The first three are D-47. The fourth is a separate defect: the count was not
scoped to a run, so it summed every run that had ever touched these 80 ticket
ids — three runs, 934 records — for a run that wrote 334.

The four affected tickets are **VAL-0023, VAL-0051, VAL-0062, VAL-0064**. In this
artifact they carry `terminal_state: escalated_direct` and the reason "No sendable
draft was produced"; they should be `escalated_after_block` with
`blocked_by: ["grounding"]`.

## What is NOT affected

Every rate. The defect only changed how four **escalations** were labelled — they
were escalations either way — so the following are sound and are quoted in the
report:

- first contact resolution 53.8%, escalation rate 46.3%
- classification accuracy 87.5%, fallback rate 0.0%
- retrieval hit rate @3 94.3%, citation resolution 100%
- processing latency p95 3.08s net of provider waiting, 11.32s raw
- deny-list violations 0; decision log reconciles 80/80

## Why it is kept

`2026-09-10-gate-run-2/` is the same 80 tickets re-run cold after the fix, and is
the headline artifact. This one is kept because the two runs **disagree about
whether the sub-3-second latency target is met** — 3.08s here, 2.66s there — and
reporting only the run that passes would be choosing the answer. Report §7.2
prints both.

See: `docs/DECISIONS.md` D-47, report §7.2 and §8.2.
