# Product Requirements Document — v1.0

| Field | Value |
|---|---|
| Version | 1.0 |
| Written by | Kshitiz Bhargava |
| Date | 2026-09-04 |
| Status | Draft for review |
| Supersedes | — |

> **This document is deliberately written before the build.** Stage 5 requires a
> revision log showing what v1 got wrong and what triggered the change. A PRD
> written alongside v2 has no genuine trigger to record. Parts of this will turn
> out to be wrong; that is the point, and §8 records the assumptions most likely
> to fail.

---

## 1. Evidence register

Every requirement below traces to one of these. Interview citations name the
speaker; data citations were computed from `development_tickets.json` (n=500) and
`validation_tickets.json` (n=80) and are reproducible from the analysis scripts.

| ID | Evidence | Source |
|---|---|---|
| **E-01** | 71.4% of tickets are answerable from existing documentation | Data; corroborates Sofia ("seven out of ten") |
| **E-02** | Keyword search cannot bridge symptom wording to article titles — "my deployment keeps dying" vs "Resolving container health check failures" | Ines |
| **E-03** | 49.1% of historical escalations were answerable from docs; 32.7% were labelled `auto_respond` | Data; corroborates Daniel, contradicts Marcus's assumption |
| **E-04** | Escalations arrive as bare forwarded tickets with no summary or context | Daniel |
| **E-05** | "I would rather it said nothing than said something wrong" — a confidently wrong answer will be screenshotted publicly | Marcus |
| **E-06** | Agents escalate when unconfident, not only when the work is hard | Sofia |
| **E-07** | Customers accept automation if it is honest about being automated and shows its source | Ravi |
| **E-08** | Urgency is inverted: high-urgency tickets have *worse* FCR (39.7% vs 48.4%) and longer median resolution (342.5 vs 132.5 min) | Data; corroborates Ravi |
| **E-09** | Security, compliance, feature-request and unclear tickets must never be auto-answered (87/500, zero label violations) | Data; corroborates Daniel and Marcus |
| **E-10** | Marcus faces a compliance review and must be able to explain why the system did what it did | Marcus |
| **E-11** | Ines needs to know which article an answer came from, to tell whether the article or the system was wrong | Ines |
| **E-12** | Fluency disparity is split-dependent: +2.7pt on dev, −33.0pt on validation (p=0.017) | Data |
| **E-13** | Enterprise customers currently receive the *slowest* median resolution (369 min vs 141 business) | Data; contradicts Ravi's belief |
| **E-14** | 143/500 tickets have no supporting document; a manufactured answer is the wrong output | Data; corroborates Ines |
| **E-15** | The corpus is 29 articles / ~8k tokens — answers exist, delivery fails | Data |

---

## 2. The problem

> CloudServe does not have an answer shortage; it has a delivery failure. 71.4% of
> incoming tickets are already answered in its own 29-article knowledge base
> (E-01, E-15), but keyword search cannot connect a customer's description of a
> symptom to the article that resolves it (E-02). Agents therefore reconstruct
> known answers from memory and escalate when unsure rather than when the work is
> genuinely hard (E-06), so roughly half of all escalations are questions the
> documentation already answers (E-03). The cost is an 8–12 hour first response
> against a 2-hour commitment, 43.8% first contact resolution, and a support
> function whose most experienced people spend their time re-answering solved
> problems.

**Author's note:** this paragraph must be rewritten in Kshitiz's own words before
submission. The Project Instructions are explicit that the problem statement is
where the author's judgement is assessed and should not be model-produced.

---

## 3. Who this is for

| User group | What they need | What they do instead today | How we know it worked |
|---|---|---|---|
| Customers raising tickets | A fast, honest, sourced answer — or a clear handoff | Wait 8–12 hours; search docs themselves, succeeding ~half the time | Time to first reply; citation accuracy |
| Tier one agents (Sofia) | Not to re-answer the same question, and not to apologise for text they did not write (E-05, E-06) | Copy from personal snippet files | Share of tickets auto-resolved; zero unsupported claims released |
| Tier two engineers (Daniel) | Escalations that arrive with context and stated uncertainty (E-04) | Read the whole thread, re-ask the customer | Every escalation carries draft, sources and uncertainty |
| Head of Support (Marcus) | Reportable numbers and explainable decisions for a compliance review (E-10) | Reports a red number he cannot decompose | Decision log reconciles; metrics produced automatically |
| Technical writer (Ines) | To know which article produced an answer (E-11) | Discovers reconstructed articles by accident | Every answer cites resolvable doc IDs |

---

## 4. Functional requirements

Priority: **Must** — unacceptable without it. **Should** — expected, deferrable
with a stated consequence. **Could** — adds value if time allows.

| ID | Requirement | Priority | Evidence | Acceptance criteria |
|---|---|---|---|---|
| FR-01 | Ingest tickets from email, chat, docs_comment and forum | Must | A2 | One ticket per channel normalises without channel-specific handling |
| FR-02 | Normalise to a single internal representation preserving original text and channel | Must | A2 | `original_body` and `channel` survive; one type returned |
| FR-03 | Tolerate missing fields, empty bodies and unusual characters without failing | Must | A11 | Empty/malformed tickets produce a ticket, never an exception |
| FR-04 | Classify intent and urgency with a numeric confidence in [0,1] | Must | A3 | Every ticket carries class + confidence; defined fallback class on failure |
| FR-05 | Record the alternatives considered, not only the chosen class | Must | E-10, A3 | `alternatives` present in the decision log |
| FR-06 | Retrieve ranked passages with scores and resolvable document IDs | Must | E-02, A4 | Returned IDs resolve to real corpus passages |
| FR-07 | Return no passages when nothing clears the relevance floor | Must | E-14, A4 | Below-floor queries return empty and the ticket escalates |
| FR-08 | Route deterministically: same input, same decision | Must | A5 | Same ticket twice yields an identical decision |
| FR-09 | Auto-respond only if confidence ≥ threshold **and** intent not deny-listed **and** retrieval above floor **and** grounding passed | Must | E-05 | Any single failure escalates |
| FR-10 | Never auto-answer security, compliance, feature-request or unclear tickets, via three independent layers | Must | E-09 | Zero auto-answers on deny-listed tickets across the full dev set |
| FR-11 | Derive the routing threshold from data, not assumption | Must | E-05 | Precision/coverage curve and calibration table produced |
| FR-12 | Generate answers grounded in retrieved passages, with citations attached to claims | Must | E-11, A6 | Every citation resolves to a retrieved passage |
| FR-13 | State plainly when the answer is not known rather than filling the gap | Must | E-14 | Ungrounded tickets escalate rather than answer |
| FR-14 | Separate customer text from system instructions so ticket content cannot redirect the system | Must | A7 | Injection fixtures do not alter behaviour |
| FR-15 | Run five guardrails on every released response, each able to block | Must | E-05, A7 | Engineered ticket per guardrail is blocked, not warned |
| FR-16 | Attach context to every escalation: draft, sources, predicted intent, and what the system was unsure about | Must | E-04 | Escalation payload contains all four |
| FR-17 | Carry urgency into the escalation payload and segment metrics by it | Should | E-08 | Priority present; metrics segmented by urgency |
| FR-18 | Log every automated decision with the Governance Framework's minimum record | Must | E-10, A8 | Log reconciles by identity against tickets processed |
| FR-19 | Process an input file end to end unattended, taking input and output paths as arguments | Must | A9 | One command; no intervention; no ticket silently dropped |
| FR-20 | Produce the metrics report automatically at the end of the run | Must | A10 | Report file appears with all four metric groups |
| FR-21 | Degrade rather than crash on no retrieval hit, provider timeout, outage, rate limiting or malformed input | Must | A11 | Run completes with the provider disconnected |
| FR-22 | Provide a kill switch that forces escalation with no model call, without redeployment | Must | E-05 | Switch set → every ticket escalates, zero model calls |
| FR-23 | Disclose to the customer that the response was automated | Should | E-07 | Disclosure present in every auto-response |
| FR-24 | Run the full test suite from a single documented command | Must | A12 | `pytest` executes and reports |
| FR-25 | Support both Groq and OpenRouter, selected by configuration | Should | A1 | Either key works from `.env.example` |

### Deliberately out of scope (Will not)

| ID | Excluded | Why |
|---|---|---|
| WN-01 | A customer-facing conversational chatbot | The request, not the problem (§2). A chatbot is a delivery mechanism and addresses none of E-01 through E-04 |
| WN-02 | Learning from agents' private snippet files | Daniel: some are years out of date; training on them scales up a mistake |
| WN-03 | Writing to the knowledge base | Ines owns editorial control; an automated writer bypasses her review cycle |
| WN-04 | Multilingual translation | Not evidenced; the fluency issue (E-12) is a retrieval problem, not a translation one |
| WN-05 | Live ticketing-system integration | No such system is supplied; the harness is file-driven, which is what A9 requires |

---

## 5. Non-functional requirements

| ID | Requirement | Target | Evidence |
|---|---|---|---|
| NFR-01 | End-to-end latency, 95th percentile | < 3 s, reported with and without provider backoff | Brief §07 |
| NFR-02 | Availability, including provider failure | Degrades to retrieval-only; run always completes | Brief §07, A11 |
| NFR-03 | Cost | Zero — free tiers only | Brief §09 |
| NFR-04 | No credential in source or git history | Zero occurrences | Brief §09 |
| NFR-05 | Runs from clean checkout on an unfamiliar machine | Following README literally | A1 |
| NFR-06 | Private data in outbound responses | Zero occurrences | Governance Framework §3 |
| NFR-07 | Quality variation across customer groups | Reported as delta against the same split's baseline | E-12 |
| NFR-08 | Confidence calibration | Stated confidence within 5 points of observed accuracy | Evaluation Framework §3 |

---

## 6. Success measures

| Measure | Baseline | Target | Note |
|---|---|---|---|
| First contact resolution | 43.8% | ≥ 60% | Label ceiling is 65.2%; target is achievable |
| Escalation rate | 56.2% | ≤ 30% | **Not achievable without a governance breach.** Floor is 34.8%. See §8 |
| Time to first reply | 8–12 h | < 5 min | Measured as system latency; the schema has no `replied_at` field |
| Classification precision | — | ≥ 85% | Per class, with confusion matrix |
| Citation accuracy | — | ≥ 95% | Each citation checked against the sentence it supports |
| Private data occurrences | — | 0 | Condition, not a target |
| Deny-list recall | — | Reported for `security_incident` and `compliance_request` specifically | Aggregate would be diluted by structurally-safe classes |

---

## 7. The escalation target: stated position

The brief's two headline targets are FCR ≥ 60% and escalation ≤ 30%. Maximum
*defensible* automation is 326/500 = **65.2%**, giving an escalation floor of
**34.8%**. We therefore expect to meet the first target and miss the second by
roughly 5 points, deliberately. Reaching 30% would require auto-answering either
deny-listed tickets (a governance failure) or ungrounded ones (a violation of
FR-13). This is recorded here in v1 so that the position is on record before the
results are known, rather than constructed afterwards to explain them.

---

## 8. Assumptions, and what happens if they are wrong

| ID | Assumption | If wrong | Detection |
|---|---|---|---|
| AS-01 | Semantic retrieval bridges the symptom/title gap (E-02) | The central premise fails; the system escalates almost everything | Retrieval hit rate against `expected_doc_ids`, Day 2 |
| AS-02 | A confidence score from the classifier is calibrated enough to threshold on | The threshold is meaningless and routing is arbitrary | Calibration table, Day 3 |
| AS-03 | The hidden set resembles validation more than dev on fluency (E-12) | The fairness section's framing must change | Pre-registered method covers both outcomes |
| AS-04 | Free-tier rate limits permit 120 tickets in one unattended run | A9 fails — the gate | Throughput budget before Day 5 |
| AS-05 | Whole-document chunking suits a 29-article, ~8k-token corpus | Retrieval precision suffers | Compared on Day 2 |
| AS-06 | Deny-list marker vocabulary achieves high recall at low false-positive cost | Layer 2 of FR-10 adds noise without safety | Measured on dev, Day 3 |
| AS-07 | The grader's machine has network access to Groq or OpenRouter | Falls back to retrieval-only; run still completes | FR-21, FR-25 |

---

## 9. Traceability

The assessed chain is `evidence → FR → prompt → code → test`. It is maintained as
data rather than prose: `requirement_ids` is a column in the decision log,
prompts carry the FR they serve in front-matter, and test names reference the
criterion. A traceability matrix is generated for the report appendix.
