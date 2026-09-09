# Evaluation run

- generated: 2026-09-08T18:00:52+00:00
- input: `..\FDE_Capstone_Complete-20260821T084330Z-1-001\FDE_Capstone_Complete\Capstone_Pack\05_Datasets\validation_tickets.json`
- tickets: 80
- model: groq / openai/gpt-oss-20b
- margin threshold 0.85, relevance floor 0.4
- wall clock: 297.2s (of which 217.6s rate-limit pacing)
- provider calls: 77 attempted, 8 served from cache
- tokens used: 47,774 (597 per ticket)

## ⚠ THIS RUN WAS DEGRADED

Business rates are withheld. A provider failure produces 100% escalation,
which is indistinguishable in the output from a very conservative working
system, and would read as a catastrophic result rather than a broken run.

- provider degraded: True
- predictions collapsed onto one class: False

## Volume

| Figure | Count |
|---|---|
| Tickets processed | 80 |
| Answered automatically | 27 |
| Escalated | 53 |
| Blocked by guardrails | 0 |

Blocked responses are counted inside escalated and reported separately, so
the rates can be recomputed under either taxonomy.

## Business

| Measure | Target | Achieved |
|---|---|---|
| First contact resolution | ≥ 60% | withheld |
| Escalation rate | ≤ 30% | withheld |
| Repeat contacts | halved | not measurable |

_Not measurable. Same-customer, same-intent within seven days yields 2 pairs across 500 development tickets. A single pass over independent tickets cannot produce this figure; reporting one would be fabrication._

## Technical

| Measure | Target | Achieved |
|---|---|---|
| Classification accuracy | ≥ 85% | 57.5% |
| Retrieval hit rate | — | 94.3% |
| Citation resolution | 100% | 100.0% |
| Processing latency p95 | < 3s | 9.99s |
| Classification fallback rate | — | 32.5% |

## Governance

| Condition | Requirement | Result |
|---|---|---|
| Deny-list violations | zero | **0** |
| Decision log reconciles | exact | True |
| Responses blocked for private data | — | 0 |

Guardrail activations: none
