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
| Provider | **Groq or OpenRouter**, selected by `PROVIDER` env var; retrieval-only fallback | A11 satisfied without extra installs; removes an A1 gate risk (see below) |

**Dual provider is a gate requirement, not a nicety.** Build Spec §06 step 4 states that
configuration is set from *our* `.env.example` "with a working key substituted in", but the
Setup Guide's canonical `.env` uses `OPENROUTER_API_KEY`. A grader holding the pack's default
OpenRouter key against a Groq-only system would get the retrieval-only fallback — an
all-escalation run that reads as degraded. Both providers are OpenAI-compatible and both are
permitted by Brief §09, so supporting both is roughly an hour's work and removes the risk
entirely. `.env.example` states which key is needed and where to obtain one free.

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

### 2.3 The escalation target is unreachable without a governance breach

The brief sets two business targets: first contact resolution >= 60% **and** escalation rate
<= 30%. We meet the first comfortably and deliberately miss the second. The argument matters,
so it is set out precisely.

**First, the counter-reading, stated fairly.** It is *not* true that the two targets are
trivially contradictory. The baselines (42% FCR / 58% escalation) sum to 100, but the
targets (60 / 30) sum to only 90 — implying a 10-point third bucket. Build Specification §04
supports this: the required volume figures are "Tickets processed, answered automatically,
escalated, **blocked by guardrails**" — four counts, with blocked enumerated *separately*
from escalated. The Evaluation Framework's own FCR code
(`resolved = r.closed and not r.escalated`) likewise leaves room for a ticket that is
neither. Under that reading, 60% answered + 30% escalated + 10% blocked satisfies both
targets at once.

**We reject that reading by design choice, not by arithmetic.** Every guardrail in §3.2
routes to "block **and** escalate", because a blocked response still leaves a customer
waiting for an answer that a human must now write. Treating "blocked" as a third terminal
state would let the system meet its escalation target by failing silently, which is exactly
the accounting trick the brief warns against. Blocked is therefore a subset of escalated and
the third bucket is empty by construction.

**Second, the real ceiling.** Given that choice, maximum *defensible* automation is:

| Pool | Count |
|---|---|
| Labelled `auto_respond` | 311 |
| Labelled `escalate`, not deny-listed, **and** grounded in a retrievable doc | 15 |
| **Maximum defensible automation** | **326 / 500 = 65.2%** |
| **Implied escalation floor** | **34.8%** |

So FCR clears its 60% target with 5.2 points of headroom, while escalation still misses by
4.8 points. Reaching 30% requires moving 39 more tickets, and the only pools available are
the 87 deny-listed tickets (a governance failure) or the 87 unforbidden-but-ungrounded ones
(a violation of our own §11 "must never" statement, and blocked by our own grounding
guardrail anyway).

> **Note on a misleading coincidence.** Of the 189 `escalate`-labelled tickets, 87 are
> deny-listed and 102 are not; of those 102, exactly 87 are ungrounded. These two 87s are
> *different sets* and their equality is pure accident. An earlier draft of this document
> conflated them. The binding constraint is **grounding**, not the deny-list.

**Decision: we do not pursue escalation <= 30%.** We report the ceiling, show the arithmetic,
name the counter-reading and say why we rejected it. This is recorded as a PRD revision
trigger.

### 2.4 The fairness baseline is split-dependent — which is itself the finding

The Governance Framework predicts retrieval systems perform worse on non-fluent English.
The tempting move is to check the development set, find no gap, and conclude that any
disparity is self-inflicted. **That conclusion does not survive the validation set.**

| Segment | Dev (n=500) | Validation (n=80) |
|---|---|---|
| non-fluent FCR vs fluent | 45.8% vs 43.2% (**+2.7pt**) | 21.1% vs 54.1% (**−33.0pt**, Fisher p=0.017) |
| non-fluent `answerable_from_docs` vs fluent | 72.5% vs 71.1% (+1.4pt) | 47.4% vs 72.1% (**−24.8pt**) |
| non-fluent `auto_respond` vs fluent | 66.7% vs 60.8% (+5.9pt) | 42.1% vs 65.6% (**−23.5pt**) |

The two splits point in opposite directions. Since the hidden 120 is drawn from the same
population as validation, a large fluency gap may well appear that we did **not** introduce.
Pre-committing to "any gap is ours" would be the worst possible position to defend.

Nor is the baseline flat on other required segments, even within dev:

- **Region**: `answerable_from_docs` asia_pacific 63.9% vs europe 76.2% (**12.3pt**)
- **Tier**: FCR business 48.2% vs enterprise 37.3% (**10.9pt**)
- **Fluency, routing axis, dev**: +5.9pt — already breaching the brief's "<5 percentage
  points" governance condition *in the labels themselves*, before any system exists

**Method, pre-registered so it is valid whichever way the hidden set falls:** the fairness
audit reports **system outcome minus the label baseline of the same split**, per segment,
never system outcome against an assumed-flat baseline. Segments covered: customer tier,
region, language fluency, and **short vs. long tickets** (a named row in Governance
Framework §3). The dev/validation divergence is reported as a finding in its own right.

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

**D1 — Two independent safety layers, because one of them is probabilistic.**

The four deny-list intents (`security_incident`, `compliance_request`, `feature_request`,
`unclear_request`; 87/500 dev tickets, 100% consistently flagged, zero label violations) are
enforced as a hard rule at routing, which no confidence score can override.

**But a deny-list keyed on the *predicted* intent is not a deterministic control.** If a
`security_incident` is misclassified as `account_access`, the gate never fires — nothing was
"overridden", the rule simply never applied. The exposure is material and quantified:
deny-list intents are 17.4% of dev and 17.5% of validation, so at the brief's own 85%
classification target, roughly **3 tickets on the hidden 120 would be auto-answered that
must never be**. The governance threshold is **zero**. Describing this as a deterministic
gate would be describing a hope, which is precisely what the Governance Framework warns
against.

Therefore **two layers, OR-ed together, either of which escalates**:

1. **Classifier deny-list** — predicted intent in the forbidden set.
2. **Intent-agnostic lexical pre-screen** — high-precision marker tokens matched against the
   raw ticket text, independent of any model output. This layer still fires when
   classification fails.

Neither layer can be disabled by configuration. **Deny-list recall is reported as a named
governance metric in its own right** — overall classification precision would hide exactly
the failure that matters here — together with an honest residual false-negative rate.

*To validate in Phase 1:* the marker-token vocabulary and its recall/false-positive
trade-off must be measured on dev before being trusted. It is tuned for recall, since a
false positive costs one unnecessary escalation and a false negative costs a governance
breach.

**D2 — Routing is a conjunction, not a threshold.**
Auto-respond requires *all* of:
- classifier confidence >= threshold, **and**
- intent not in the deny-list, **and**
- top retrieval score >= relevance floor, **and**
- grounding validation passed.

Any single failure escalates. This directly encodes Marcus's "rather it said nothing".

Urgency is a first-class output, not a discarded field. It sets the **priority on the
escalation payload** (D3) and segments latency and handling in the metrics report. This is
Ravi's point — "same queue, completely different cost to me" — and the data shows the queue
is currently *inverted*: high-urgency tickets have **worse** FCR (39.7% vs 48.4% for low)
and **longer** median resolution (342.5 vs 132.5 minutes). That inversion is reported as a
discovery finding.

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

### 3.5 Incident procedure

The kill switch is a *mechanism*; the Governance Framework separately requires a six-step
*procedure* with an owner and a duration per step, written so someone unfamiliar with the
system could follow it at two in the morning. Delivered Day 8, covering detect → contain →
assess → notify → remediate → review.

Three risk-register rows need design-level answers rather than prose, and are recorded here
so they are not invented at the end:

- **R-05, documentation goes stale.** Daniel's warning — answers "correct two years ago"
  circulating in private files — is the sharpest version of this. Note that
  `last_reviewed_days_ago` is **0 for all 29 articles**, so staleness is undetectable in this
  data; the control is therefore design-level: surface document age alongside every citation
  so a reviewer can see it. The uniformly-zero field is stated rather than glossed.
- **R-07, latency under load.** Answered by the throughput budget in §5.
- **R-08, cost with volume.** Answered by the cache hit rate and the per-ticket call count,
  both reported in metrics.

---

## 4. Data and persistence

### 4.1 Decision log

SQLite via SQLAlchemy, one row per decision, matching the Governance Framework's minimum
record exactly — including `prompt_version` and `requirement_ids`, which are what allow the
question "was this behaviour intended?" to be answered after an incident.

Every stage (`classification`, `routing`, `generation`, `validation`) writes a record.

**Reconciliation is by identity, not by multiplication.** A count-based assertion such as
`decisions_logged == tickets * stages` is wrong, because the number of stages legitimately
varies per ticket: a deny-listed ticket terminates at `route` and never reaches `generate`
or `validate` (87/500 dev), an empty retrieval escalates early (143/500 have no retrievable
doc), and a kill-switched ticket makes no model call at all. Such an assertion would fail
loudly on every *correct* run. Instead the harness asserts:

1. `set(ticket_ids in log) == set(ticket_ids processed)` — exact identity, both directions
2. every ticket has at least one decision record
3. each ticket's recorded stage sequence is a valid pipeline prefix consistent with its
   terminal action

This catches the failure the Build Spec actually names — "a decision log written only for
the tickets that succeeded" — which a count-based check does not.

### 4.2 Caching

Content-addressed on-disk cache for model responses and embeddings. Serves three purposes:
determinism (D5), free-tier preservation, and making the unattended run reproducible for
the video. Cache hits are recorded in metrics so token savings are measurable and reportable.

---

## 5. Evaluation

Produced by the harness automatically, never by hand (A10).

Every figure has an operational definition fixed *before* the run, so no metric can be
quietly redefined once its value is known.

**Tier 1 — Business**

| Figure | Exact definition |
|---|---|
| First contact resolution | `auto_respond AND not blocked` ÷ tickets processed. Reported beside routing accuracy, since a confidently wrong auto-answer also counts here |
| Escalation rate | `1 − FCR`. Blocked responses count as escalated (see §2.3) |
| Time to first reply | System processing latency, arrival to response emitted. **Not** wall-clock: the schema has no `replied_at` field, so the Evaluation Framework's sample code cannot be run as written. The 8–12 hour baseline is Marcus's stated figure, not derivable from the data (median `resolution_time_minutes` is 214) |
| Repeat contacts | **Not measurable. Reported as such, with evidence.** Same-customer / same-intent within 7 days yields **2 pairs across 500 dev tickets** and 1 across 80 validation. A single pass over independent tickets cannot produce this metric; claiming it would be fabrication |
| Satisfaction proxy | Rubric-scored sample; sample size, rubric and scorer stated |

**Tier 2 — Technical**

| Figure | Exact definition |
|---|---|
| Classification precision / recall | Per class, plus confusion matrix. **Deny-list recall reported separately** (see D1) |
| Retrieval hit rate | `any-hit`: top-k intersects `expected_doc_ids`. Also reported as recall@k, since 90 dev tickets have multiple expected docs and the two figures differ materially |
| Citation accuracy | Cited passage re-resolved and checked against the sentence it supports |
| Hallucination rate | Sampled review; assessor count and agreement rate stated |
| Latency | Median and p95, end to end. **Reported twice: with and without provider backoff**, since the target is p95 < 3s and the hidden run has a cold cache |

**Tier 3 — Governance:** PII occurrences (must be zero), cross-segment variation by tier /
region / fluency, decision log reconciliation, and the **calibration table** binning
predictions by confidence against observed accuracy — the check the brief notes students
usually skip and on which the whole threshold argument rests.

**Discipline.** Development against the 500 only. The pack contradicts itself on the
validation set — the Dataset Guide says use it "as often as you like", the Project Brief
says "Do not look at these while building. Do not tune against them." The Brief outranks the
Dataset Guide, so we follow the Brief: validation is used for a **small number of explicitly
logged checkpoint runs**, with count and dates recorded. The conflict is named in the report
along with which document we followed and why. The harness is schema-driven, so it runs
unmodified against the hidden 120. Evaluation date and run count are written into the
results file automatically rather than remembered.

**Throughput budget (A9).** The hidden run has a **cold cache by definition**, so the
determinism cache in D5 provides no latency protection during the run that is actually
graded. Before Day 5 we state: model calls per ticket, the provider's free-tier rate limit,
resulting wall-clock for 120 tickets, and whether reported latency includes backoff. Build
Spec §04 requires the run to complete "in a reasonable time" and to explain itself if not.
Latency is reported both with and without backoff, since the p95 < 3s target is otherwise
unfalsifiable.

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
| 1 | Repo, pinned env verified in clean venv, config, Pydantic models, ingest (A2), decision log schema. **Plus: thin PRD v1 (FR-01…FR-nn, each traced to an interview line or computed statistic) and the effort log opened** | Ingest tests pass for all four channels; FR IDs exist to reference |
| 2 | Corpus indexed, retrieval with resolvable IDs and relevance floor (A4) | Retrieval hit rate measured against `expected_doc_ids` |
| 3 | Classifier with calibrated confidence (A3), deterministic router, **both D1 safety layers incl. lexical pre-screen** | Determinism + deny-list recall tests pass; threshold curve produced |
| 4 | Generation with resolved citations (A6), five guardrails blocking (A7) | Engineered ticket per guardrail blocks |
| 5 | **Harness end-to-end, unattended, full set, metrics auto-produced (A9, A10). Plus first clean-checkout rehearsal** | **The gate: start it, leave, return to a report.** Fresh clone, README followed literally |
| 6 | Failure injection (A11), kill switch, full suite + CI (A12), FastAPI | Provider disconnected, run still completes |
| 7 | Evaluation run, calibration, fairness audit, Stage 1 + 2 workbooks. **Video take one** | Metrics reconcile with decision log; take one exposes what cannot yet be explained |
| 8 | Stages 3–5 workbooks, governance, risk register, incident procedure, PRD revision log | Traceability matrix generated |
| 9 | **Video take two**, report finalised, second clean-checkout rehearsal, packaging | Archive matches the submission checklist item by item |

**Two things start on Day 1 because they cannot be reconstructed later.** The effort log
must show entries throughout ("a log written from memory is obvious and marked
accordingly"), and PRD v1 must predate the build or Stage 5 has no genuine revision trigger
to record — and §9's traceability chain has no FR IDs to reference. Both are cheap on Day 1
and impossible on Day 8.

**Cut list, in order, if behind:**

1. The chunking comparison. Documents are 860–1,336 characters and the whole corpus is
   ~7,900 tokens; whole-document chunking is obviously correct here and needs justifying,
   not benchmarking.
2. Prometheus/Grafana. Monitoring is not among the twelve criteria. FastAPI stays.
3. The LLM-judge hallucination cross-check. One assessor plus a stated deviation already
   satisfies the honesty requirement.

**Never cut**, in order of protection: the unattended run, the five guardrails, the decision
log, the D1 deny-list layers, the video.

**If behind at day 4:** cut intent *classes*, never the end-to-end run. Two constraints
apply: cutting a class means **mapping it to a defined fallback class**, never skipping the
ticket, because A3 requires every ticket to carry a class and a confidence; and **the four
deny-list intents can never be cut**, since D1 depends on them.

---

## 9. Traceability

The chain `discovery evidence -> FR-nn -> prompt PR-nn -> code module -> test` is assessed
by picking an item at random and following it. We therefore maintain it as data rather than
prose: requirement IDs are recorded in the decision log, referenced in prompt front-matter,
and asserted in test names. A generated traceability matrix ships in the report appendix.

---

### 9.1 Submission deliverables that are not code

These are tracked here because each is individually cheap and collectively they put a 10%
weighting at risk — and a missing `03_Workbooks` item makes the submission **incomplete
rather than deducted**.

| Item | Where | When |
|---|---|---|
| Effort log, task-level entries every second day | `03_Workbooks/` | **Opened Day 1**, filled throughout |
| Five stage workbooks, genuinely completed | `03_Workbooks/` | v1 PRD Day 1; rest Days 7–8 |
| AI tool use declaration (~half a page) | Report §, required checklist item | Day 8 |
| Attribution of model-generated code | Repo — explicit check, Build Spec §06 step 11 | Continuous |
| Report, 20–30pp, single PDF, prescribed 10-section order, every figure numbered and referenced | `02_Report/` | Days 8–9 |
| Video, 18–22 min, ≥7 min live demo, on camera at open and close | `01_Video/` | Take one Day 7, take two Day 9 |
| Hidden-set run date and run count stated | Report | Recorded automatically by the harness |

The report's ten prescribed sections map onto this design document almost directly:
§1→exec summary, §2.1–2.2→problem and discovery, §9→requirements and traceability,
§3→architecture, §6–7→implementation, §5→evaluation, §3.2–3.4 and §11→governance,
§2.3→the requirements revision.

**On commit history:** the Submission Guide reviews it for "steady work across the three
weeks". Nine days of commits cannot become three weeks and will not be backdated to look
like it. The compressed timeline is stated plainly in the report's reflection section.

---

## 10. Assumptions and open questions

1. **Satisfaction proxy.** No live customers exist, so CSAT is a rubric-scored sample. Method
   and sample size stated; limits named in the report.
2. **Hallucination rate** requires human judgement. The brief asks for two assessors; as an
   individual project this will be one assessor plus an LLM-judge cross-check, with the
   deviation stated plainly rather than concealed.
3. **Response time** is measured as system processing latency, not wall-clock human
   response. Stated explicitly, since comparing a 2-second pipeline to an 8-hour human queue
   needs that caveat to be honest. The schema has no `replied_at` field, so the Evaluation
   Framework's own sample code cannot be run as written.
4. **Repeat contacts cannot be measured** on a single pass over independent tickets
   (2 qualifying pairs in 500). Reported as unmeasurable with the evidence, not estimated.
5. **Torch removal** via Chroma's ONNX MiniLM to be validated in Phase 1.
6. **Grader's machine** is assumed to have Python 3.10+ and network access to Groq *or*
   OpenRouter, and no Ollama — hence dual-provider support and the retrieval-only fallback.
7. **The D1 marker-token vocabulary** is unvalidated until measured on dev in Phase 1. Its
   recall and false-positive rate must be established before it is relied upon.

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
