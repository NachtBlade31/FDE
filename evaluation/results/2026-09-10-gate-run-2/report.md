# Evaluation run

- generated: 2026-09-10T14:29:56+00:00
- input: `..\FDE_Capstone_Complete-20260821T084330Z-1-001\FDE_Capstone_Complete\Capstone_Pack\05_Datasets\validation_tickets.json`
- tickets: 80
- model: groq / openai/gpt-oss-20b
- margin threshold 0.85, relevance floor 0.4
- wall clock: 453.9s (of which 330.1s rate-limit pacing)
- provider calls: 121 attempted, 12 served from cache
- tokens used: 76,224 (652 per provider call)

## Volume

| Figure | Count |
|---|---|
| Tickets processed | 80 |
| Answered automatically | 45 |
| Escalated | 35 |
| Blocked by guardrails | 4 |

Blocked responses are counted inside escalated and reported separately, so
the rates can be recomputed under either taxonomy.

## Business

| Measure | Target | Achieved |
|---|---|---|
| First contact resolution | ≥ 60% | 56.3% |
| Escalation rate | ≤ 30% | 43.8% |
| Repeat contacts | halved | not measurable |

_Not measurable. Same-customer, same-intent within seven days yields 2 pairs across 500 development tickets. A single pass over independent tickets cannot produce this figure; reporting one would be fabrication._

## Technical

| Measure | Target | Achieved |
|---|---|---|
| Classification accuracy | ≥ 85% | 85.0% |
| Retrieval hit rate | — | 94.3% |
| Citation resolution | 100% | 100.0% |
| Processing latency p95 | < 3s | 2.66s (excl. provider wait; 10.51s incl.) |
| Classification fallback rate | — | 0.0% |

## Governance

| Condition | Requirement | Result |
|---|---|---|
| Deny-list violations | zero | **0** |
| Decision log reconciles | exact | True |
| Responses blocked for private data | — | 0 |

Guardrail activations: {'grounding': 4}
