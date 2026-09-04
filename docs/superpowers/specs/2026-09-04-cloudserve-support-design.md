# CloudServe Intelligent Support System — Design

**Date:** 2026-09-04
**Project:** Forward Deployed AI Engineering Capstone
**Deadline:** 13 September 2026, 23:59 (9 days from writing)
**Status:** Draft for review

---

## 1. Context and hard constraints

| Constraint | Detail | Consequence for design |
|---|---|---|
| Time | 9 days, not the 3 weeks the pack assumes | Gate-first sequencing; docs generated from real artefacts |
| Gate | Clean checkout on a foreign machine processes the full set unattended | Install simplicity is a feature, not a nicety |
| Harness | Must accept `--input` / `--output` paths | No hardcoded filenames anywhere |
| Cost | Free tiers only | Groq free tier + local embeddings + aggressive caching |
| Hidden set | 120 unseen tickets, same schema | No tuning to a visible number; harness must be schema-driven |
| Secrets | No key in code or git history | `.env` gitignored before first write; CI uses fixtures |
| Provider | Groq primary, retrieval-only fallback | A11 satisfied without extra installs on grader's machine |

### 1.1 Verified environment findings

Two findings were established by running the tools, not by assumption:

1. **The pack's `requirements.txt` is unresolvable.** `langchain-openai==0.0.7` requires
   `openai>=1.10` while the file pins `openai==1.0.0`. pip returns `ResolutionImpossible`.
   Additionally `sentence-transformers==2.2.2` fails at import against modern
   `huggingface_hub`. Following the Setup Guide literally fails at step one — which is
   precisely how acceptance criterion A1 is tested. We therefore ship our own pinned set
   and document the deviation in the report.

2. **A modern coherent set resolves cleanly in a fresh venv** (Python 3.11):
   `langchain 0.3.30`, `langgraph 0.6.7`, `langchain-core 0.3.86`, `langchain-groq 0.3.8`,
   `langchain-chroma 0.2.6`, `chromadb 1.1.0`, `langchain-huggingface 0.3.1`,
   `sentence-transformers 5.1.1`, `fastapi 0.118.0`, `uvicorn 0.37.0`, `pydantic 2.11.9`,
   `numpy 2.4.6`, `prometheus-client 0.23.1`, `scikit-learn 1.7.2`, `pytest 8.4.2`,
   `pytest-cov 7.0.0`.

**Open optimisation:** that set pulls `torch` (~2.5 GB) via `sentence-transformers`.
`chromadb` already ships `onnxruntime`, and Chroma's built-in embedder is
`all-MiniLM-L6-v2` — the exact model the brief specifies. Using it removes torch entirely
and materially de-risks the clean-checkout gate. To be validated in Phase 1; the
`sentence-transformers` path remains the documented fallback.

---

## 2. The problem

### 2.1 What the evidence says

Every claim below is checked against `development_tickets.json` (n=500), not inferred.

| Stakeholder claim | Data | Verdict |
|---|---|---|
| Sofia: "seven out of ten I could answer without looking up" | 71.4% `answerable_from_docs` | Correct |
| Marcus: "we're at 42% first contact resolution" | 43.8% | Correct |
| Daniel: "half of what reaches me tier one could have resolved" | 49.1% of escalations were answerable from docs; 32.7% were labelled `auto_respond` | Correct — and Marcus does not know it |
| Ravi: "enterprise colleague gets answers in about an hour" | Enterprise median 369 min — the **slowest** tier (business 141, standard 266) | **Incorrect** |

Three further findings that shape the build:

- **Ines's diagnosis is the mechanism.** Keyword search cannot bridge "my deployment keeps
  dying" to an article titled "Resolving container health check failures". Semantic
  retrieval closes exactly this gap. This is why the intervention is retrieval, not a chatbot.
- **The corpus is tiny**: 29 articles, 31,733 characters (~8k tokens) total. Answers exist.
  Delivery is what fails.
- **Marcus's fear is the binding constraint**: "I would rather it said nothing than said
  something wrong." This makes precision, not coverage, the objective function.

### 2.2 Problem statement

> CloudServe does not have an answer shortage; it has a delivery failure. Seventy-one per
> cent of incoming tickets are already answered in its own 29-article knowledge base, but
> keyword search cannot connect a customer's description of a symptom to the article that
> resolves it. Agents therefore reconstruct known answers from memory or private snippet
> files, and escalate when unsure rather than when the work is genuinely hard — with the
> result that roughly half of all escalations are questions the documentation already
> answers. The cost is an 8–12 hour first response against a 2-hour commitment, 43.8% first
> contact resolution, and a support function whose most experienced people spend their time
> re-answering solved problems.

The client asked for a chatbot. A chatbot is a delivery mechanism and would not address the
finding above, because it says nothing about where answers come from, whether they are
correct, or what happens when they are not known. What the evidence supports is a
**retrieval-grounded triage and drafting system** in which escalation is a first-class
output that carries context, not a failure branch.

### 2.3 The target contradiction (a finding, not a defect)

The brief sets two business targets: first contact resolution >= 60% **and** escalation rate
<= 30%. These cannot both hold.

| | Dev (500) | Validation (80) |
|---|---|---|
| Tickets labelled `expected_route = auto_respond` | 62.2% | 60.0% |
| Therefore minimum achievable escalation rate | **37.8%** | **40.0%** |

A perfect system reaches FCR 62.2% (target met) and escalation 37.8% (target missed by 7.8
points). The only route below 30% is auto-responding to tickets labelled `escalate`, 87 of
which carry `must_not_auto_respond` — security incidents and compliance requests. That is a
governance failure, not a scoring loss.

**Decision: we do not pursue escalation <= 30%.** We report the ceiling, show the arithmetic,
and defend the choice. This is recorded as a PRD revision trigger.

### 2.4 The fairness finding to test

The Governance Framework predicts retrieval systems perform worse on non-fluent English.
The historical data shows **no such gap**: non-fluent FCR is 45.8% versus fluent 43.2%, and
`answerable_from_docs` is near-identical (72.5% vs 71.1%). There is therefore no baseline
disparity — **any gap our system exhibits is one we introduced.** The fairness audit
measures our own delta against a flat baseline, which is a stronger and more honest test
than confirming an expected finding.

---

## 3. Architecture

Six LangGraph nodes in sequence over three cross-cutting concerns
(decision logging, metrics, configuration).

```
ingest -> classify -> retrieve -> route -> generate -> validate
```

Every node is a pure function of `(state, config)` returning a new state plus decision
records. State is a Pydantic model, so LangGraph transitions are type-checked and the
pipeline is testable node-by-node without a model provider.

### 3.1 Design decisions that carry the implementation marks

**D1 — The deterministic safety gate precedes anything probabilistic.**
The four `must_not_auto_respond` intents (`security_incident`, `compliance_request`,
`feature_request`, `unclear_request`; 87/500 tickets, zero label violations) are enforced
as a hard rule at routing. No confidence score can override it. Satisfies the brief's
requirement for "a stated position on what the system must never do, and the mechanism that
enforces it."

**D2 — Routing is a conjunction, not a threshold.**
Auto-respond requires *all* of:
- classifier confidence >= threshold, **and**
- intent not in the deny-list, **and**
- top retrieval score >= relevance floor, **and**
- grounding validation passed.

Any single failure escalates. This directly encodes Marcus's "rather it said nothing".

**D3 — Escalation carries context.**
Every escalation emits the drafted answer, the retrieved passages with scores, the predicted
intent with alternatives, and an explicit statement of what the system was uncertain about.
This is Daniel's stated requirement — "I don't need it to be right, I need it to show its
working" — and it is what converts escalation from a loss into a product feature.

**D4 — The threshold is derived, not chosen.**
Swept across dev tickets to produce a precision/coverage curve and a calibration table.
The chosen value is justified from that curve. The brief explicitly penalises "a threshold
chosen because it looked reasonable rather than because it was measured".

**D5 — Determinism (A5).**
`temperature=0`, fixed seed, and a content-addressed cache keyed on
`sha256(prompt + model + params)`. A test submits the same ticket twice and asserts an
identical routing decision. The cache is simultaneously the token-optimisation and
rate-limit defence.

**D6 — Retrieval may return nothing.**
143 of 500 tickets have no `expected_doc_ids`. Below the relevance floor, retrieval returns
an empty set and the ticket escalates. The Build Spec names "retrieval that returns
something for every query" as a failure mode.

**D7 — Citations resolve or the response is blocked.**
Citations are constructed from retrieved chunk IDs, never emitted free-form by the model.
The validator re-resolves every citation against the store; an unresolvable citation blocks
the response. This makes A6 structurally true rather than prompt-dependent.

### 3.2 Guardrails (A7)

All five run on every generated response, in production, and can block. A guardrail that
only warns is not a guardrail.

| Guardrail | Checks | On fire |
|---|---|---|
| PII | Emails, keys, account numbers, other customers' identifiers | Block + escalate. Never redact and send |
| Grounding | Every factual claim traceable to a retrieved passage | Block + escalate, unsupported claim flagged |
| Instruction integrity | Ticket content has not altered system instructions | Block + escalate + record input for review |
| Tone and scope | No commitments on refunds, timelines, or roadmap | Block |
| Confidence floor | Threshold actually applied; missing score is not a high one | Escalate |

### 3.3 Security posture

- **Prompt injection**: customer text is passed as a separate, delimited, clearly-labelled
  user message, never concatenated into the instruction block. The instruction-integrity
  guardrail is the second layer. Adversarial fixtures are part of the test suite.
- **Secrets**: `.env` in `.gitignore` before the first key is written; `.env.example` holds
  placeholders only; CI reads from GitHub encrypted secrets or uses fixtures. A secret scan
  runs in CI.
- **Input validation**: every ticket field validated by Pydantic at ingest. Missing subject,
  empty body, unusual characters and oversized input are handled, not raised (A11).
- **Injection into storage**: decision log writes are parameterised SQL.

### 3.4 Kill switch

A file sentinel (`storage/KILL`) plus `KILL_SWITCH=1` env var, checked once per ticket
before any model call.

| Question | Answer |
|---|---|
| Mechanism | Presence of `storage/KILL` or `KILL_SWITCH=1` |
| Who may operate it | Any on-call operator with filesystem or env access; no deployment needed |
| Time to take effect | Next ticket, under one second |
| Tickets in flight | Complete as escalations with full context; none dropped |
| How tested | A test asserts that with the switch set, every ticket escalates and zero model calls are made |

---

## 4. Data and persistence

### 4.1 Decision log

SQLite via SQLAlchemy, one row per decision, matching the Governance Framework's minimum
record exactly — including `prompt_version` and `requirement_ids`, which are what allow the
question "was this behaviour intended?" to be answered after an incident.

Every stage (`classification`, `routing`, `generation`, `validation`) writes a record.
**Coverage is reconciled automatically**: the harness asserts
`decisions_logged == tickets_processed * stages_executed` and fails loudly on a gap. A8 is
checked by counting, so we count it ourselves first.

### 4.2 Caching

Content-addressed on-disk cache for model responses and embeddings. Serves three purposes:
determinism (D5), free-tier preservation, and making the unattended run reproducible for
the video. Cache hits are recorded in metrics so token savings are measurable and reportable.

---

## 5. Evaluation

Produced by the harness automatically, never by hand (A10).

**Tier 1 — Business:** first contact resolution, mean/median/p95 time to first reply,
escalation rate, repeat contacts, satisfaction proxy (rubric-scored sample, method and
sample size stated).

**Tier 2 — Technical:** per-class classification precision and recall plus confusion
matrix, retrieval hit rate against `expected_doc_ids`, citation accuracy, hallucination rate
(sampled review, agreement rate reported), latency median and p95.

**Tier 3 — Governance:** PII occurrences (must be zero), cross-segment variation by tier /
region / fluency, decision log reconciliation, and the **calibration table** binning
predictions by confidence against observed accuracy — the check the brief notes students
usually skip and on which the whole threshold argument rests.

**Discipline:** development against the 500; validation set used freely for checking; the
harness is schema-driven so it runs unmodified against the hidden 120. Evaluation date and
run count are recorded automatically into the results file rather than remembered.

---

## 6. Testing

Single command: `pytest` (A12). CI runs it on every push via GitHub Actions.

- **Unit** — per node, with fixtures; no network required.
- **Contract** — one ticket per channel through ingest (A2); the four-channel normalisation.
- **Determinism** — same ticket twice, identical decision (A5).
- **Guardrail** — an engineered ticket per guardrail, asserting a block (A7).
- **Failure injection** — provider timeout, 429 rate limit, total outage, malformed JSON,
  empty body, empty retrieval (A11).
- **Safety** — no `must_not_auto_respond` ticket is ever auto-answered, asserted across the
  entire dev set.
- **Reconciliation** — logged decisions match processed tickets (A8).
- **Citation resolution** — every emitted citation resolves to a real passage (A6).

All tests run without a live API key using recorded fixtures, so CI is green on a fork and
the grader can run the suite before obtaining a key.

---

## 7. Repository layout

Follows the Setup Guide's prescribed structure so no reorganisation is needed later.

```
README.md              tested against a clean checkout
requirements.txt       our verified pins
.env.example           placeholders only
.gitignore             .env and storage/ from the first commit
src/                   ingest classify retrieve route generate guardrails
                       logging_store api config cache llm_client killswitch
prompts/               build/ evaluation/ + README.md register with versions
tests/
evaluation/harness.py  --input / --output, plus results/
docs/architecture.md
data/                  small samples only
.github/workflows/ci.yml
```

---

## 8. Nine-day plan

Gate-first: the unattended run works before anything is made good. Each day ends in a
testable, committed deliverable.

| Day | Deliverable | How it is verified |
|---|---|---|
| 1 | Repo, pinned env verified in clean venv, config, Pydantic models, ingest (A2), decision log schema | Ingest tests pass for all four channels |
| 2 | Corpus indexed, retrieval with resolvable IDs and relevance floor (A4), chunking comparison | Retrieval hit rate measured against `expected_doc_ids` |
| 3 | Classifier with calibrated confidence (A3), deterministic router with safety gate (A5) | Determinism + safety tests pass; threshold curve produced |
| 4 | Generation with resolved citations (A6), five guardrails blocking (A7) | Engineered ticket per guardrail blocks |
| 5 | **Harness end-to-end, unattended, full set, metrics auto-produced (A9, A10)** | **The gate: start it, leave, return to a report** |
| 6 | Failure injection (A11), kill switch, full suite + CI (A12), FastAPI + Prometheus | Provider disconnected, run still completes |
| 7 | Evaluation run, calibration, fairness audit, Stage 1 + 2 workbooks | Metrics report reconciles with decision log |
| 8 | Stages 3–5 workbooks, governance, risk register, PRD revision log, report draft | Traceability matrix generated |
| 9 | Report, video, clean-checkout rehearsal, packaging | Fresh clone, README followed literally |

**If behind at day 4:** cut intent classes, never the end-to-end run. The Build Spec is
explicit that a narrow system that completes the unattended run passes the gate, and a
broad one that has never processed more than five tickets does not.

---

## 9. Traceability

The chain `discovery evidence -> FR-nn -> prompt PR-nn -> code module -> test` is assessed
by picking an item at random and following it. We therefore maintain it as data rather than
prose: requirement IDs are recorded in the decision log, referenced in prompt front-matter,
and asserted in test names. A generated traceability matrix ships in the report appendix.

---

## 10. Assumptions and open questions

1. **Satisfaction proxy.** No live customers exist, so CSAT is a rubric-scored sample. Method
   and sample size stated; limits named in the report.
2. **Hallucination rate** requires human judgement. The brief asks for two assessors; as an
   individual project this will be one assessor plus an LLM-judge cross-check, with the
   deviation stated plainly rather than concealed.
3. **Response time** is measured as system processing latency, not wall-clock human
   response. Stated explicitly, since comparing a 2-second pipeline to an 8-hour human queue
   needs that caveat to be honest.
4. **Torch removal** via Chroma's ONNX MiniLM to be validated in Phase 1.
5. **Grader's machine** is assumed to have Python 3.10+ and network access to Groq, and no
   Ollama — hence the retrieval-only fallback.

---

## 11. What this system must never do

> It must never send a customer an answer that is not supported by a retrieved CloudServe
> documentation passage, and it must never auto-answer a security, compliance, feature
> request or unclear ticket.

Enforced by: the grounding guardrail (blocks unsupported claims), citation re-resolution
(blocks unresolvable references), and the deterministic deny-list at routing (independent
of any confidence score). The most likely residual harm is a *correctly cited but
misapplied* passage — a retrieved article that is genuinely relevant to the symptom but
wrong for that customer's configuration. Grounding checks cannot catch that, which is why
the fairness audit segments by tier and why we would not deploy without a human review
sample running continuously in production.
