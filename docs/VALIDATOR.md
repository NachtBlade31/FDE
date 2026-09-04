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
| 1 | 2026-09-04 | Phase 0 — Design specification | _in review_ | Initial design review before any code is written |
