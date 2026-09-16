# Effort Log — Kshitiz Bhargava

## How the "Actual" column was produced — read this first

The Submission Guide asks for entries filled in as the work happens, and warns
that a log reconstructed at the end "is obvious and marked accordingly."

**This log is partly reconstructed, and I am marking it accordingly.** The task
rows and estimates were written as I went. The actual hours were not — I kept
building instead of filling in the column, which is exactly the failure the Guide
warns about. Rather than invent numbers now, I derived them from the git history,
which is contemporaneous evidence I cannot retrofit.

**Method.** Commits are grouped into working sessions with a two-hour idle
threshold: consecutive commits more than two hours apart start a new session.
Each session is measured from its first to its last commit, plus **45 minutes**
for the work that preceded the first commit of that session. Reproduce it with:

```bash
git log --reverse --pretty=format:"%ad" --date=format:"%Y-%m-%d %H:%M"
```

**What this measures, and what it misses.** It is a **lower bound**, and I would
rather understate than round up:

- Discovery on 4 September — reading seventeen documents and analysing four
  datasets — largely happened *before* the first commit, so only 45 minutes of it
  is counted against several hours of real work.
- Waiting for gate runs is not counted. Four full validation runs took roughly
  eight minutes each, and two were lost to the provider's daily token cap after
  several minutes of running.
- Thinking away from the keyboard is not counted at all.

The honest reading is: **~20 hours of measurable keyboard time, against a real
figure I would put nearer 30.** I am not going to write 30 in a column that says
"actual".

---

## Measured sessions

| Session | Commits | Measured |
|---|---|---|
| 04 Sep 09:03 → 12:05 | 12 | 3.8h |
| 06 Sep 21:21 → 21:47 | 2 | 1.2h |
| 07 Sep 00:26 → 01:11 | 4 | 1.5h |
| 07 Sep 09:59 → 10:34 | 2 | 1.3h |
| 07 Sep 18:03 | 1 | 0.8h |
| 08 Sep 10:43 → 13:16 | 6 | 3.3h |
| 08 Sep 15:32 | 1 | 0.8h |
| 08 Sep 17:33 | 1 | 0.8h |
| 09 Sep 19:08 → 20:40 | 6 | 2.3h |
| 10 Sep 18:50 | 1 | 0.8h |
| 11 Sep 00:57 → 02:49 | 3 | 2.6h |
| 11 Sep 10:23 | 1 | 0.8h |
| 16 Sep 17:45 → 17:47 | 3 | 0.8h |
| **Total** | **43** | **20.6h** |

Per day: 4 Sep 3.8h · 6 Sep 1.2h · 7 Sep 3.6h · 8 Sep 4.8h · 9 Sep 2.3h ·
10 Sep 0.8h · 11 Sep 3.4h · 16 Sep 0.8h.

> **The last session is the worst case for this method, and it is worth naming.**
> The packaging work ran across 14 and 16 September, but its commits were batched
> into two minutes at the end, so the git-derived figure covers only that window
> and reads 0.8h. Contemporaneous artifacts put the start two days earlier — the
> agent-time evidence file was generated at 21:35 on 14 September. The honest
> figure for that session is several hours; 0.8h is what the method can prove,
> and it is recorded as such rather than adjusted upward by memory.

Within a day, the per-row actuals below apportion that day's measured total
across its rows in proportion to the estimates. That apportionment is an
assumption, not a measurement — the day totals are the real figures.

---

## Entries

| Date | Stage | Task | Est. (h) | Actual (h) | Notes |
|---|---|---|---|---|---|
| 2026-09-04 | 1 — Discovery | Read the full capstone pack (17 documents, extracted from .docx) | 2.0 | 0.5 | Mostly before the first commit; see the method note |
| 2026-09-04 | 1 — Discovery | Quantitative analysis of all four datasets; tested each stakeholder claim against the ticket data | 2.0 | 0.5 | Found Ravi's enterprise-speed claim is contradicted by the data (369 min median, the slowest tier) |
| 2026-09-04 | 1 — Discovery | Established the FCR/escalation target ceiling (326/500 = 65.2%) | 1.0 | 0.25 | Escalation ≤30% is unreachable without a governance breach |
| 2026-09-04 | 0 — Setup | Verified the pack's requirements.txt is unresolvable; built and verified a replacement pin set | 1.0 | 0.25 | `ResolutionImpossible`: langchain-openai 0.0.7 vs openai 1.0.0 |
| 2026-09-04 | 0 — Setup | Design specification written | 2.0 | 0.5 | |
| 2026-09-04 | 0 — Setup | Validator review round 1 — BLOCKED; four load-bearing errors | 1.0 | 0.25 | Cheapest hour of the project |
| 2026-09-04 | 0 — Setup | Validator review round 2 — CLEARED WITH CONDITIONS; C1–C4 applied | 1.0 | 0.25 | |
| 2026-09-04 | 2 — Requirements | PRD v1 written (25 FRs, 8 NFRs, 15 evidence items, 7 assumptions) | 1.5 | 0.4 | |
| 2026-09-04 | 5 — Build | Day 1: venv, pinned deps, project structure | 0.5 | 0.15 | torch removed via Chroma's built-in ONNX MiniLM — saves ~2.5 GB |
| 2026-09-04 | 5 — Build | Day 1: domain models, four-channel ingest (A2), TDD | 1.5 | 0.4 | 21 ingest tests |
| 2026-09-04 | 5 — Build | Day 1: decision log with identity reconciliation (A8), TDD | 1.0 | 0.25 | 18 tests including duplicate-terminal-state rejection |
| 2026-09-04 | 5 — Build | Day 1: configuration, dual provider, kill switch plumbing, TDD | 1.0 | 0.25 | 17 tests |
| 2026-09-04 | 5 — Build | Day 1: real-data conformance tests against all 500 dev + 80 validation tickets | 1.0 | 0.25 | |
| 2026-09-04 | 5 — Build | Day 1: README, CI with secret scanning, effort log | 0.75 | 0.2 | |
| 2026-09-06 | 5 — Build | Day 2: retrieval, chunking, a derived relevance floor (A4, FR-06/07) | 2.5 | 0.9 | 95.2% any-hit@3 on 357 groundable dev tickets |
| 2026-09-06 | 5 — Build | Day 2 remediation: floor consistency 0.35 → 0.40, retrieval detail | 0.5 | 0.3 | Validator found the shipped floor disagreed with the evidence |
| 2026-09-07 | 5 — Build | Day 3: classification, model client, measured throughput budget | 2.0 | 1.0 | Three real-provider findings: TPM not RPM binds; reasoning models bill thinking against max_tokens; empty completions were cached as success |
| 2026-09-07 | 5 — Build | O-4: curated safety vocabulary chosen over a higher-scoring derived one | 1.0 | 0.5 | Derived vocabulary scored better in-sample and worse on a held-out split |
| 2026-09-07 | 5 — Build | Day 3 remediation: fix the evidence; environment template named a withdrawn model | 0.5 | 0.4 | The F7 artifact was a cache replay, not a measurement |
| 2026-09-07 | 5 — Build | Day 3 complete: router, both thresholds derived by sweep (A3, A5) | 1.5 | 0.8 | Confidence has no spread (99/100 in one band); routing moved to margin |
| 2026-09-07 | 5 — Build | Day 4: generation with re-resolved citations (A6), five blocking guardrails (A7) | 2.0 | 0.5 | |
| 2026-09-07 | 5 — Build | Day 5: pipeline, harness, and a gate failure fixed twice | 2.0 | 0.4 | Pacing stalled a run for 90 minutes; then over-reserved 2× |
| 2026-09-08 | 5 — Build | Fix two safety markers costing coverage and catching nothing | 1.0 | 0.6 | Prompted by being asked why targets were missed — see reflection |
| 2026-09-08 | 5 — Build | Day 6: A11 failure injection and a real gap it exposed | 1.5 | 0.9 | Per-node containment: a classify failure was discarding retrieval |
| 2026-09-08 | 5 — Build | Daily token budget handling; A8 reconciliation scoped to a run | 1.0 | 0.6 | The 200k/day cap appears only in a 429 body, never in a header |
| 2026-09-08 | 1 — Discovery | Stage 1 Discovery workbook; fairness audit built on a pre-registered method | 1.5 | 0.9 | Label baselines already exceed the 5-point condition, and invert between splits |
| 2026-09-08 | 3/4 — Governance | Governance framework, Stage 5 revision log, prompt library, sprint plan | 2.5 | 1.5 | |
| 2026-09-08 | 6 — Submission | Report draft, all ten prescribed sections | 2.0 | 0.8 | |
| 2026-09-08 | 5 — Build | A1 clean-checkout rehearsal; Windows MAX_PATH limit documented | 1.0 | 0.8 | Install failed at a 113-character checkout path |
| 2026-09-09 | 5 — Build | Fairness audit refuses to report a run it cannot trust | 1.0 | 0.5 | A degraded run reported every segment as biased |
| 2026-09-09 | 5 — Build | Daily token ledger; per-ticket provider-wait instrumentation | 1.5 | 0.8 | Three gate runs lost to the daily cap before this existed |
| 2026-09-09 | 6 — Submission | Withdraw every figure no committed artifact supports | 1.5 | 0.7 | The results table cited a run that had been overwritten |
| 2026-09-09 | 5 — Build | Make the ledger fail closed; fix three text defects | 0.5 | 0.3 | A truncated ledger healed into a blank day and reported full headroom |
| 2026-09-10 | 5 — Build | First non-degraded gate run, and the results rewritten around it | 1.5 | 0.8 | 80/80, no degradation, 0 deny-list violations |
| 2026-09-11 | 5 — Build | Guardrail that could not fire; paired statistics for the fairness claim | 1.5 | 1.2 | 4 blocked drafts reported as 0; nothing survives Holm correction |
| 2026-09-11 | 5 — Build | Substance check — a draft of `[1]` passed every guardrail | 0.5 | 0.4 | |
| 2026-09-11 | 6 — Submission | Retracted-claim sweep built as a test; validation-run log | 1.0 | 1.0 | Ninth instance of the same propagation defect |
| 2026-09-11 | 6 — Submission | Validator log brought current — twice, having gone stale again | 0.5 | 0.8 | |
| 2026-09-14 | 6 — Submission | Read the Submission Guide and Stage 2 template against every deliverable | 1.0 | 0.1 | Found the four-folder layout, the PDF requirements and a report body under the 20-page minimum |
| 2026-09-14 | 5 — Build | Figure 1: compute agent time from the data, draw the chart, test it | 2.0 | 0.1 | The report's largest number had no committed code behind it; it reproduced exactly |
| 2026-09-14 | 6 — Submission | Report: caption all tables, embed Figure 1, answer the hidden-set line, add the risk register and incident procedure | 2.0 | 0.2 | Only 1 of 9 tables had a caption; §8 had neither register nor procedure |
| 2026-09-14 | 2 — Requirements | Conform the PRD to the Stage 2 template without changing v1 | 1.5 | 0.1 | Columns and Open questions added, marked and dated |
| 2026-09-14 | 5 — Build | Tests for the five recovery handlers that had never run | 1.0 | 0.1 | Carried from review 10; the tests caught a defect in their own fixture |
| 2026-09-16 | 5 — Build | Validator review 12 and its twelve findings | 2.0 | 0.2 | The 95.2% retrieval figure was measured with no relevance floor; the shipped floor gives 92.7% |

---

## Totals by stage

Estimates are the sum of the rows above. Actuals are apportioned from the
measured day totals, so the stage split carries that assumption; the **19.8h
total is measured**.

| Stage | Estimated (h) | Actual (h) | Variance |
|---|---|---|---|
| 0 — Setup and design | 5.0 | 1.25 | −3.75 (measurement excludes pre-commit work) |
| 1 — Discovery | 6.5 | 2.15 | −4.35 (most of day 1 preceded the first commit) |
| 2 — Requirements | 1.5 | 0.4 | −1.1 |
| 3/4 — Prompt library, sprint plan, governance | 2.5 | 1.5 | −1.0 |
| 5 — Build and evaluation | 31.5 | 13.4 | −18.1 |
| 2 — Requirements (PRD conformance, 14 Sep) | 1.5 | 0.1 | −1.4 |
| 6 — Submission (report, packaging) | 10.0 | 3.7 | −6.3 |
| **Total** | **57.5** | **20.6** | **−36.9** |

The variance column is not a productivity result. It is the gap between estimated
task time and *measured keyboard time*, and the measurement systematically
excludes reading, analysis before the first commit, and waiting on runs. Treating
−27.2 as "finished early" would be exactly the kind of misreading this report
argues against elsewhere.

---

## Estimate accuracy — where the estimates were wrong

| What was underestimated or overestimated | By how much | Why |
|---|---|---|
| Reading and analysing the pack | Underestimated | The datasets repay quantitative analysis far more than skimming. Every one of the three headline discovery findings came from a query, not a read. |
| Design review | Underestimated | Two validator rounds found eight defects, four load-bearing. Cheapest hours in the project. |
| Provider behaviour on a free tier | **Badly underestimated** | Rate-limit pacing, an undocumented daily cap visible only in a 429 body, a withdrawn model, reasoning models returning HTTP 200 with empty content. Budgeted ~1h across the project; cost closer to 6h and three lost gate runs. |
| Getting documents to agree with each other | **Badly underestimated** | Nine separate instances of a corrected figure reaching some documents and not others. Budgeted nothing for it. It is now a test. |
| Writing the report | Roughly right | The structure was cheap because the decision log had been kept as the work happened. |
| Validator review cycles | Underestimated | Twelve reviews, seven BLOCKED. Every one produced a real fix, and none of it was in the plan. |
| Packaging and submission rules | **Badly underestimated** | Budgeted as a final tidy-up. Reading the Submission Guide properly found a missing figure, uncaptioned tables, two absent report sections and a workbook that did not match its template — none of which the twelve reviews had looked for, because they were pointed at the system rather than the submission. |

> **Note on the compressed timeline.** This project was started on 2026-09-04
> against a 13 September deadline — nine days rather than the three weeks the
> pack assumes. The commit history reflects that and has not been backdated. The
> consequences are discussed in the report's reflection section.
