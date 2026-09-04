# Effort Log — Kshitiz Bhargava

Actual hours worked, recorded as the work happens. The Submission Guide asks for
entries at the level of a task within a day, filled in at least every second day,
and notes that a log reconstructed from memory at the end "is obvious and marked
accordingly."

**Fill this in at the end of each working session.** It takes two minutes and it
supplies the material for the reflection section of the report.

---

## Entries

| Date | Stage | Task | Est. (h) | Actual (h) | Notes |
|---|---|---|---|---|---|
| 2026-09-04 | 1 — Discovery | Read the full capstone pack (17 documents, extracted from .docx) | 2.0 | | |
| 2026-09-04 | 1 — Discovery | Quantitative analysis of all four datasets; tested each stakeholder claim against the ticket data | 2.0 | | Found Ravi's enterprise-speed claim is contradicted by the data (369 min median, the slowest tier) |
| 2026-09-04 | 1 — Discovery | Established the FCR/escalation target ceiling (326/500 = 65.2%) | 1.0 | | Escalation ≤30% is unreachable without a governance breach |
| 2026-09-04 | 0 — Setup | Verified the pack's requirements.txt is unresolvable; built and verified a replacement pin set | 1.0 | | `ResolutionImpossible`: langchain-openai 0.0.7 vs openai 1.0.0 |
| 2026-09-04 | 0 — Setup | Design specification written | 2.0 | | |
| 2026-09-04 | 0 — Setup | Independent validator review round 1 — BLOCKED; four load-bearing errors found and remediated | 1.5 | | Fairness baseline was false on validation; safety gate was not deterministic |
| 2026-09-04 | 0 — Setup | Validator review round 2 — CLEARED WITH CONDITIONS; C1–C4 applied | 1.0 | | §11 still contained the retracted claim — a propagation miss |
| 2026-09-04 | 2 — Requirements | PRD v1 written (25 FRs, 8 NFRs, 15 evidence items, 7 assumptions) | 1.5 | | Written before the build so Stage 5 has a genuine revision trigger |
| 2026-09-04 | 5 — Build | Day 1: venv, pinned deps, project structure | 0.5 | | torch removed via Chroma's ONNX MiniLM — install cut by ~2.5 GB |
| 2026-09-04 | 5 — Build | Day 1: domain models, four-channel ingest (A2), TDD | 1.5 | | 21 ingest tests |
| 2026-09-04 | 5 — Build | Day 1: decision log with identity reconciliation (A8), TDD | 1.0 | | 18 tests incl. Build Spec §04 volume counts |
| 2026-09-04 | 5 — Build | Day 1: configuration, dual provider, kill switch plumbing, TDD | 1.0 | | 17 tests |
| 2026-09-04 | 5 — Build | Day 1: real-data conformance tests against all 500 dev + 80 validation tickets | 0.75 | | Governance invariants asserted as tests, not just analysis |
| 2026-09-04 | 5 — Build | Day 1: README, CI with secret scanning, effort log | 0.75 | | |

---

## Totals by stage

Complete this as the project progresses.

| Stage | Estimated (h) | Actual (h) | Variance |
|---|---|---|---|
| 0 — Setup and design | | | |
| 1 — Discovery | | | |
| 2 — Requirements | | | |
| 3 — Prompt library | | | |
| 4 — Sprint plan | | | |
| 5 — Build and evaluation | | | |
| 6 — Submission (report, video, packaging) | | | |
| **Total** | | | |

---

## Estimate vs. reality — for the reflection section

Record here, as they happen, the places where the estimate was wrong and by how
much. A log in which every stage lands on estimate is not credible; the useful
material is in the misses.

| What was underestimated or overestimated | By how much | Why |
|---|---|---|
| Reading and analysing the pack | Underestimated | The datasets repay quantitative analysis far more than skimming; several stakeholder claims are settleable only by computation |
| Design review | Underestimated | Two validator rounds found eight defects, four of them load-bearing. Cheaper here than in the report |
| | | |

> **Note on the compressed timeline.** This project was started on 2026-09-04
> against a 13 September deadline — nine days rather than the three weeks the
> pack assumes. The commit history reflects that and has not been backdated. The
> consequences are discussed in the report's reflection section.
