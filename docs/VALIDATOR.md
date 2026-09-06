# Validator Charter and Verdict Log

## Purpose

An independent critic/validator reviews every phase **before** it is accepted.
No work proceeds to the next phase without a `CLEARED` verdict recorded below.

The validator exists to prevent two specific failure modes:

1. **Requirement drift** — the build quietly diverging from the Capstone Pack's twelve
   acceptance criteria, the marking scheme, or the submission format.
2. **Context loss** — decisions made in earlier phases being forgotten, contradicted, or
   silently reversed in later ones.

## Authoritative sources (precedence order)

The validator judges against these, in this order. Where they conflict, the higher wins.

1. `01_Read_First/02_Build_Specification.docx` — the twelve acceptance criteria (pass/fail)
2. `00_PROJECT_INSTRUCTIONS.docx` — rules, submission format, deadline
3. `01_Read_First/01_Project_Brief.docx` — targets, architecture, constraints
4. `03_Reference/Evaluation_Framework.docx` and `Governance_Framework.docx`
5. `04_Submission/Submission_Guide.docx` — deliverable format
6. `05_Datasets/Dataset_Guide.docx` — schemas and permitted use
7. `docs/superpowers/specs/2026-09-04-cloudserve-support-design.md` — the agreed design

Pack root:
`FDE_Capstone_Complete-20260821T084330Z-1-001/FDE_Capstone_Complete/Capstone_Pack/`

## The rules being enforced

- **Every phase ends in a testable, committed deliverable.** One step at a time.
- **No phase is accepted without a passing verification command** whose real output is shown.
- **No acceptance criterion may regress.** Once A-n passes, it keeps passing.
- **No hardcoded data paths.** The harness takes `--input` / `--output`.
- **No credentials** in code, config, or git history.
- **No guardrail disabled by flag** during a run.
- **No tuning against the validation set** to make a number look better.
- **Claims require evidence.** "Tests pass" must be accompanied by the command and its output.

## Verdict format

Each review returns one of:

- `CLEARED` — proceed to the next phase.
- `CLEARED WITH CONDITIONS` — proceed, but the listed items must be fixed within the next
  phase and are re-checked then.
- `BLOCKED` — do not proceed. Findings must be resolved and re-submitted.

## Verdict log

| # | Date | Phase reviewed | Verdict | Summary |
|---|---|---|---|---|
| 1 | 2026-09-04 | Phase 0 — Design specification | **BLOCKED** | All 15 quantitative claims verified correct. Blocked on: D1 safety gate probabilistic not deterministic (~3 expected governance failures on the hidden set against a zero threshold); §2.4 fairness baseline false on validation (−33pt, p=0.017); §2.3 right conclusion via wrong reasoning, ignored the Build Spec §04 three-outcome reading; A8 reconciliation formula fails on correct runs; effort log and PRD v1 absent from a plan deferring all workbooks past the build |
| 2 | 2026-09-04 | Phase 0 — remediation | **CLEARED WITH CONDITIONS** | All 8 clearing conditions genuinely met; F5 and F9 addressed early. Day 1 may begin. Four conditions carried: §11 declaration still calls the deny-list "deterministic", contradicting the rewritten D1 (fix immediately — two sentences, and it is the statement an assessor reads first); §5 omits the Build Spec §04 Volume group, which is what makes the blocked ⊆ escalated choice auditable; D1's "~3 tickets" overstates the residual ~3× because D2's grounding conjunction already screens it; alternatives-aware abstention recommended as the third D1 control |

| 3 | 2026-09-04 | Day 1 — models, ingest, decision log, config | **CLEARED WITH CONDITIONS** | Verification reproduced independently: `pytest` in the project venv gives 72 passed, 98% (302 stmts, 6 miss, 32 branch, 2 partial). Torch removal confirmed in `requirements.txt`. 11 commits in logical units; PRD v1 with 25 FRs traced to 15 evidence items. Quality is high — TDD throughout, governance invariants frozen as real-data tests, identity reconciliation implemented correctly. Six conditions below, three of them substantive: `.env.example` untracked (A1 risk, needs the user), `volume_counts()` counts records not tickets, and fairness segments degrade silently into the reference segment. All are Day-1 files: cheap now, expensive after Day 5 builds on them |

| 4 | 2026-09-04 | Day 2 — corpus, chunking, retrieval (A4) | **CLEARED WITH CONDITIONS** | Credential claim independently verified: exhaustive blob-level scan of all history returned two hits, both `ci.yml`'s own regex string in two versions — history is clean, `.env.example` is tracked and placeholders only, `.env` never committed. Suite reproduced at **144 passed in 181.90s** (reported 121 — see D2-C5). All four review-3 conditions verified applied in code, D1-C2 fixed at write time with `DuplicateTerminalStateError`, which is stronger than asked. Chunking decision is evidenced, not asserted. Five conditions, one substantive: the relevance floor ships as 0.35 while the evidence justifies 0.40 |

| 5 | 2026-09-07 | Day 3 — classification, model client (A3) | **CLEARED WITH CONDITIONS** | Suite reproduced at 180 passed. All five review-4 conditions applied. The data-regularity analysis is the best discovery work in the project so far and the three real-provider findings (TPM not RPM is binding; reasoning models bill thinking against max_tokens and return 200 with empty content; empty completions were being cached as success) are exactly what Day 3 exists to surface. Six conditions. Two are serious: the committed F7 artifact is a **cache replay** whose throughput section contradicts the reported figures, so F7 is not resolved; and a confidence threshold **cannot** be derived from self-reported confidence on this data (99/100 in one band), so the router must lean on margin plus grounding and the deny-list. **D2-C1 remains open and has grown worse** — `.env.example` now ships both a stale floor (0.35 vs 0.40) and a stale model (`llama-3.3-70b-versatile` vs the measured `openai/gpt-oss-20b`), so a graded run would use a different model than every number was measured on. Blocked on a permission rule, correctly escalated, needs the user |

## Carried into Phase 1 (re-checked there)

- **F5** urgency consumer — addressed in D2, verify it is actually wired at build time
- **F7** throughput budget — numbers must be stated before the Day 5 gate run
- **F9** validation-set discipline — checkpoint run count and dates must be logged
- **F10** incident procedure, R-05/R-07/R-08 — due Day 8
- **F11** report section mapping — added to §9.1, verify against the finished report
- **F12** fallback-class constraint on cutting intent classes
- **D1 marker vocabulary** — recall and false-positive rate unvalidated until measured on dev

## Resolution of review-2 conditions (2026-09-04, commit pending)

All four applied to the spec before Day 1 code, not deferred.

- **C1 §11** — declaration rewritten around four controls, three independent of the
  classifier. "Deterministic" retracted. Residual stated as ~1 ticket in 120 confined to the
  two groundable deny-list intents. ✅
- **C2 §5** — Tier 0 Volume group added with a three-value terminal enum
  (`auto_responded` / `escalated_direct` / `escalated_after_block`); all four Build Spec §04
  counts emitted and reconciling; FCR and escalation rate re-derived from the enum. §2.3 now
  also prices the third bucket at ≥24 abandoned tickets per 120. ✅
- **C3** — residual corrected from ~3 to ~1.1 with the per-intent grounding table. ✅
  **Correction to the validator's own figure:** the review states "35 of the 87 deny-list
  tickets are structurally protected". Recomputed: it is **56**. The 35 counts only the two
  wholly-ungrounded classes (`feature_request` 20, `unclear_request` 15) and omits the 12
  ungrounded `security_incident` and 9 ungrounded `compliance_request` tickets, which are
  equally protected. The ~1.1 residual is unaffected, since it correctly used the 31/87
  groundable fraction. Spec states 56.
- **C4** — alternatives-aware abstention added as D1 layer 3, with the independence argument
  (top-1 label / surface tokens / distribution). ✅

## Conditions from review 5 — Day 3 (D3-C1/C2 before the router; D3-C3 before Day 5)

- **D3-C1 derive the threshold from margin, not top-1 confidence** — answer (e). 99 of 100
  predictions sit in one band, so a sweep over self-reported confidence has nothing to sweep.
  Use `top1.confidence − best_alternative.confidence`, which has real spread and which the
  `alternatives` array already carries for C4. Report that raw self-reported confidence is
  non-discriminative on this data, with the calibration table as the evidence. This is a
  genuine Stage 5 PRD revision trigger: routing was assumed to rest on confidence, measurement
  showed it cannot.
- **D3-C2 report ECE, not max gap, as the calibration headline.** The committed artifact
  currently states "largest calibration gap: 75.0% (governance condition: within 5 points)" —
  i.e. it declares a governance failure on the strength of one ticket. Population-weighted ECE
  is **3.2%**, which passes. Report every bin with its n and a Wilson interval, never drop a
  bin, and headline ECE. The n=1 bin's 95% CI is [0.0%, 79.3%] — uninformative, which is a
  stronger and more honest statement than either dropping it or headlining it.
- **D3-C3 F7 is NOT resolved; the committed evidence is a cache replay.**
  `2026-09-07-classifier-100.txt` records `provider calls: 0 attempted`, `cache hits: 100`,
  `p95 0.01s`, `projected wall clock 0.0 min` — it measures dict lookups, not the provider,
  and contradicts the reported 1.86s p95 / 0.90 calls per ticket / 6.1 min. Accuracy, deny-list
  recall and calibration in that file remain valid (a cache hit replays a real completion);
  the throughput section does not. Re-run cold and commit that artifact. Systemic fix: the
  reporter must refuse to print a throughput budget when `cache_hits > 0`, or label it
  `CACHE REPLAY — NOT A THROUGHPUT MEASUREMENT`. This matters most on Day 5, where a warm
  rehearsal would validate nothing about a hidden run that is cold by definition.
- **D3-C4 intent-distribution collapse check** — answer (d). The degraded flag depends on
  failures being booked as failures, and the gpt-oss-20b finding shows a provider can return
  HTTP 200 with empty content. Add an independent invariant: if predicted intents collapse onto
  one class (or the fallback rate exceeds a few per cent), the run is broken regardless of the
  flag. Cheap, and it catches partial failure the flag misses.
- **D3-C5 `degraded` must reach the metrics report and void business metrics.** It currently
  reaches one `print` in `scripts/evaluate_classifier.py`. A degraded run must not be able to
  report FCR and escalation rate as though valid.
- **D3-C6 validation is less templated than dev, so 89% may not hold.** The regularity artifact
  concludes the figure "will hold there too" on the hidden set. Validation shows 25% duplicate
  bodies vs dev's 57%, opening ratio 1.5x vs 3.9x, Jaccard ratio 15.6x vs 19.0x. The same
  dev/validation divergence as design §2.4. Soften the claim to match the evidence.

## Conditions from review 4 — Day 2 (fix before the router is written)

- **D2-C1 the relevance floor has three values in four places.** `src/config.py`
  `DEFAULT_RELEVANCE_FLOOR = 0.40` (correct, derived); `src/retrieve.py:198` `Retriever` default
  `0.35` (stale); committed `.env.example` `RELEVANCE_FLOOR=0.35` (stale). Build Spec §06 step 4
  sets configuration from `.env.example`, so **the graded run uses 0.35 while the report defends
  0.40**, and any `Retriever` built without an explicit floor silently uses 0.35. D4's "derived,
  not chosen" claim requires the shipped value to be the derived one. Fix all three, and add a
  test asserting `Retriever`'s default equals `DEFAULT_RELEVANCE_FLOOR`.
- **D2-C2 expose pre-floor scores** — see review-4 answer (d). "Nothing cleared the floor" and
  "nothing was close" are different states. D3 requires escalations to say what the system was
  uncertain about; the Governance Framework's `sources_used` must make the decision
  reconstructable; calibration needs the rejected scores. Return a `RetrievalResult` carrying
  `passages` (above floor), `rejected` (below floor, with scores) and `top_score`. Keep rejected
  passages in a separate field so D7 can never cite one.
- **D2-C3 raise the hit-rate guard to any-hit@3 >= 0.90** against a measured 95.2%, and record
  the measured value and date beside it with a note that a failure means investigate, never
  lower the bound. 0.60 would not notice a catastrophic regression.
- **D2-C4 `Urgency` still falls back to an alias.** D1-C3 named tier, fluency *and* urgency;
  two of three were fixed. `Urgency.FALLBACK = "medium"` puts defaulted tickets into the largest
  bucket (226/500), and D2 makes urgency the escalation-payload priority and a metrics segment.
- **D2-C5 reconcile the test count.** Reported `121 passed`; reproduced `144 passed in 181.90s`.
  Favourable, but unreproducible verification output is what the charter's evidence rule exists
  to catch. Also note the suite went from 1.5s to ~3 minutes — the README should say so, or a
  grader at test-procedure step 10 may think it has hung.

## Conditions from review 3 — Day 1 (fix at the top of Day 2)

- **D1-C1 `.env.example` is untracked** — OPEN ITEM, needs the user, not the coordinator.
  A permission rule in this environment blocks git operations naming the file; the coordinator
  correctly refused to work around it and the validator could not read it either, so its
  contents are **unverified**. It is a required Submission Guide deliverable and Build Spec §06
  step 4 sets configuration from it. Untracked means a clean checkout does not have it, which
  fails A1 at step 4. Not a defect in the work; still fatal if it ships this way.
- **D1-C2 `volume_counts()` counts records, not tickets.** Demonstrated: two tickets with a
  stray second terminal record report `processed: 3`, and one ticket is counted in two terminal
  states. `reconcile()` passes anyway — it compares id sets only. Build Spec §06 step 9 opens
  the metrics report and the decision log and reconciles them against each other, so this is
  the exact check the grader runs. Enforce one terminal record per ticket and derive
  `processed` from distinct ticket ids.
- **D1-C3 fairness segments degrade into the reference segment silently.** `CustomerTier`
  falls back to `STANDARD` and `LanguageFluency` to `FLUENT` — both *aliases* of real members,
  so a defaulted ticket is indistinguishable from a genuine one. `Channel` and `CustomerRegion`
  do it correctly with a distinct `UNKNOWN`. Defaults flow into the majority segment
  (standard 50.6%, fluent 76.0%), which is where §2.4's pre-registered baseline is computed.
  Give tier, fluency and urgency an `UNKNOWN` member and report it as its own segment.
- **D1-C4 negative invariants can pass vacuously.** `test_no_deny_list_ticket_is_ever_labelled_auto_respond`
  builds an empty offender list if `labels` fails to parse. Assert the deny-list population is
  non-empty (87 on dev) so the test cannot pass on an empty set.
- **D1-C5 freeze the C3 premise as a test.** `feature_request` and `unclear_request` are
  0% `answerable_from_docs` (0/20 and 0/15 dev; 0/3 and 0/6 val). That fact is what makes 56 of
  the 87 deny-list tickets structurally protected by D2's grounding conjunction, and it is
  load-bearing for D1's residual estimate and §11. If it ever changes, the governance argument
  changes with it.
- **D1-C6 preflight the provider** — see review-3 answer (c). Fail loudly at start when a key
  is present but rejected, and when no key is present unless an explicit opt-in is set; degrade
  only on mid-run failure, which is what A11 actually asks for. The metrics report must carry a
  prominent `degraded_run` flag plus attempted/succeeded call counts, so a 100%-escalation run
  can never be mistaken for a confident one.

## Conditions from review 2 (fix in Phase 1)

- **C1 §11 declaration** — still says "the *deterministic* deny-list at routing (independent
  of any confidence score)", which is the exact claim D1 now retracts. Propagate D1's two-layer
  language into §11 and name the lexical pre-screen. Governance Framework §6 calls the
  declaration "the summary an assessor reads first". Fix before Day 1 ends.
- **C2 §5 Volume group** — Build Spec §04 requires four counts: processed, answered
  automatically, escalated, blocked by guardrails. §5 has Business/Technical/Governance but no
  Volume group. Report all four, with `escalated = escalated_direct + blocked` reconciling
  explicitly. This is what makes §2.3's blocked ⊆ escalated choice auditable rather than
  convenient.
- **C3 D1 residual** — "~3 tickets" ignores D2's grounding conjunction. `feature_request`
  (0/20 answerable) and `unclear_request` (0/15) cannot ground and are structurally safe; the
  residual is confined to `security_incident` (14/26 groundable) and `compliance_request`
  (17/26). True expected exposure on the hidden 120 ≈ **1.1 tickets**, not 3. Report deny-list
  recall for those two intents specifically.
- **C4 third D1 control** — alternatives-aware abstention: escalate if any deny-list intent
  appears in the classifier's top-k alternatives above a low floor, regardless of top-1. The
  `alternatives` array is already in the Governance Framework's minimum record and already
  required by D3, so the data exists. Independent of both current layers: layer 1 reads top-1,
  layer 2 reads surface tokens, layer 3 reads the distribution. Fires precisely on the
  co-failure case.
