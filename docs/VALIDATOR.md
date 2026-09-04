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
