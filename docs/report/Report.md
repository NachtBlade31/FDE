# An intelligent support system for CloudServe Solutions

**Kshitiz Bhargava**
Forward Deployed AI Engineering — Capstone Report
September 2026

---

> **Two sections of this report must be rewritten in the author's own words
> before submission: §2 (the problem) and §10.3 (the reflection). The Project
> Instructions state that the problem statement, evaluation interpretation and
> reflection are where the author's judgement is assessed and should not be
> model-produced. They are drafted here from the evidence so the structure is
> complete; the wording is a placeholder.**

---

## 1. Executive summary

CloudServe Solutions asked for a chatbot. Their support function receives over
500 tickets a week, replies in 8–12 hours against a two-hour commitment, and
resolves 43.8% on first contact.

**They do not have an answer shortage. They have a delivery failure.** 71.4% of
incoming tickets are already answered somewhere in their own twenty-nine
knowledge base articles, but their internal search matches article titles and
customers describe symptoms. Agents therefore answer from memory and escalate
when unsure rather than when the work is hard — with the result that **49.1% of
everything reaching a senior engineer is a question the documentation already
answered**, and those escalations consume **96.8% of all agent time**.

What was built is not a chatbot. It is a retrieval-grounded triage system that
finds the existing answer, sends it only when four independent conditions agree,
and otherwise hands the ticket to a person with the relevant article attached and
an honest statement of what it was uncertain about.

**What it achieved**, on the 80-ticket validation set, in a single unattended run.
Every row here is reproducible from a committed artifact; the rows that are not
are named as such rather than filled in, and §7.2 gives the reason.

| | Target | Achieved |
|---|---|---|
| **Deny-listed tickets auto-answered** | **0** | **0** |
| Citation resolution | 100% | **100%** |
| Retrieval hit rate @3 | — | **94.3%** |
| Decision log reconciliation | exact | **passes** |
| Tickets processed unattended | 80 | **80** |
| Classification accuracy | ≥ 85% | 85.2% *(of the 54 tickets that reached the model)* |
| Processing latency p95 | < 3s | *see §7.2* — 74% of measured time was rate-limit waiting |
| First contact resolution | ≥ 60% | *withheld — run degraded* |
| Escalation rate | ≤ 30% | *withheld — run degraded* |

Three attempts at a clean validation run on 8 September were lost to the free
tier's undocumented daily token cap (§7.2, D-45). The last completed all 80
tickets but lost the provider at ticket 54, so the reporter withheld its business
rates rather than publishing an escalation rate produced by an outage. **The
governance and functional results are unaffected and are measured; the business
rates are outstanding.**

**The single most important caveat.** The escalation target of ≤30% is
unreachable without a governance breach, and this was established from the labels
on day zero rather than discovered as an excuse afterwards. Maximum *defensible*
automation on the development set is 65.2%, giving an escalation floor of 34.8%;
the built system reaches 64.0% / 36.0% at its shipped configuration, within 1.2
points of that prediction. On
validation the ceiling is lower still. Reaching 30% would require auto-answering
either security and compliance tickets or ungrounded ones. I chose to miss the
target and explain it.

---

## 2. The problem

*(To be rewritten in the author's own words. Draft follows.)*

CloudServe asked for a chatbot because a chatbot is the part of the solution they
could picture. It is a delivery mechanism: it says nothing about where an answer
comes from, whether it is correct, what happens when it is unknown, or who is
accountable when it is wrong.

Working backwards from the mechanism to the outcome, what CloudServe need is that
fewer tickets require a person at all; that the ones which do arrive with useful
context; and that customers stop waiting most of a day for an answer that already
existed.

The gap between request and need is measurable. Building a better conversational
surface would address none of the three findings in §3. Building retrieval that
bridges the symptom-to-title gap addresses all three.

---

## 3. Discovery findings

Five stakeholder interviews and 580 labelled tickets. Every figure below was
computed from the data rather than taken from the pack's summary tables; the
scripts are in `scripts/` and the saved outputs in `evaluation/results/`.

### 3.1 The answers already exist — the search does not reach them

**71.4%** of development tickets are answerable from the existing twenty-nine
articles. Sofia, the tier-one agent, estimated "seven out of ten" from
experience; she was right to within a point.

Ines, who wrote the articles, supplied the mechanism without recognising it as
the central finding:

> "Someone writes *my deployment keeps dying* and my article is called
> *resolving container health check failures*. There is no path between those two
> phrases in a keyword search."

That sentence is the design brief. Semantic retrieval is exactly the path between
those two phrases, and it works: **95.2% any-hit@3** across the 357 groundable
development tickets (Table 1).

### 3.2 Half of all escalations were already answered — and the Head of Support cannot see it

Daniel, tier two, said about half of what reaches him could have been resolved at
tier one. The data settles it: of 281 historically escalated tickets, **138
(49.1%)** are answerable from documentation, and **92 (32.7%)** are labelled as
tickets that should have been auto-answered.

Marcus, who owns the numbers, never mentions this. He sees the escalation rate,
not its composition — and he said so: *"If you asked me for a breakdown I would be
guessing."*

**The cost of that blind spot is the largest number in this report.** Escalated
tickets are 56.2% of volume but consume **96.8% of all agent minutes**, and
**46.2% of every hour worked went to escalations the documentation already
answered** (Figure 1).

### 3.3 Enterprise customers are the worst served, and everyone believes the opposite

Marcus feared enterprise customers would notice if they got worse service. Ravi,
a business-plan customer, believed an enterprise colleague got replies in about
an hour and worried the gap would widen.

Both are wrong, in the same direction:

| Tier | Median resolution | First contact resolution |
|---|---|---|
| Business | **141 min** | 48.2% |
| Standard | 266 min | 43.1% |
| **Enterprise** | **369 min** | **37.3%** |

Enterprise is already the slowest and least-resolved tier. The fairness risk
Marcus is guarding against has already happened, in reverse, and it is a renewal
risk today rather than a future one.

### 3.4 Two findings about the data itself

**The evaluation data is templated.** 57% of development ticket bodies duplicate
another ticket verbatim, and same-intent vocabulary overlap is 19× cross-intent.
A k-nearest-neighbour classifier over embeddings scores **99.4%** leave-one-out
against an 85% target — which measures template regularity, not capability. That
classifier was deliberately not shipped. Every accuracy figure in this report
describes performance on synthetic, templated data, and any claim beyond that is
an extrapolation.

**Development and validation diverge on five separate measures**, sometimes
inverting. Non-fluent English tickets are labelled slightly *better* than fluent
on development and 23.5 points *worse* on validation. `asia_pacific` is the
lowest-served region on development and the highest on validation. This shaped
the fairness method (§8.3) and every generalisation in this report is qualified
by it.

---

## 4. Requirements

Twenty-five functional and eight non-functional requirements, each traced to a
numbered discovery finding. PRD v1.0 was written on day one, **before any code**,
specifically so the compulsory revision in §9 would have a genuine trigger.

Selected requirements and their evidence:

| ID | Requirement | Evidence |
|---|---|---|
| FR-06 | Retrieve ranked passages with resolvable document ids | §3.1 — Ines on the search gap |
| FR-07 | Return **nothing** when nothing clears the relevance floor | §3.4 — 28.6% of tickets have no supporting article |
| FR-10 | Never auto-answer security, compliance, feature-request or unclear tickets | Daniel and Marcus; 87/500 tickets, zero label violations |
| FR-13 | State plainly when the answer is not known | Marcus: *"I would rather it said nothing than said something wrong"* |
| FR-16 | Every escalation carries the draft, the sources, and what the system was unsure about | Daniel: *"I do not need it to be right. I need it to show its working"* |
| FR-23 | Disclose that the reply was automated | Ravi: *"I calibrate how much I trust it. Hiding that would be the thing that annoys me"* |

**Deliberately out of scope:** a conversational chatbot; learning from agents'
unreviewed private answer files (Daniel: *"you will scale up a mistake"*); writing
to the knowledge base (Ines owns editorial control); translation.

The full traceability chain — requirement → prompt → implementation → test — is
in the Stage 3 workbook, generated against the code. It names five requirements
that are implemented and tested but untagged in source.

---

## 5. Architecture and design

Six components in sequence, built as a LangGraph state machine:

```
ingest → classify → retrieve → route → generate → validate
```

### 5.1 The decision that shapes everything: routing is a conjunction

Auto-responding requires **four independent conditions to agree**: a confidence
margin above threshold, an intent not on the deny-list, a retrieved passage above
the relevance floor, and grounding validated. Any single failure escalates.

Measured over 200 development tickets, the conjuncts are **not** equal:

| Conjunct | Share of escalations |
|---|---|
| deny-list | 54% |
| lexical screen | 50% |
| alternatives | 36% |
| **margin (confidence)** | **29%** |
| grounded | 14% |

The confidence threshold — the thing most such systems are built around — turned
out to be the weakest leg. §9 explains how that was discovered.

### 5.2 Citations are constructed, not written

The model is given numbered passages and cites positions — `[1]`, `[2]` — which
the code maps back to the `chunk_id` and `doc_id` that produced them. **The model
never writes a document identifier, so it cannot invent one.**

This makes citation accuracy structural rather than prompt-dependent. An
out-of-range marker is arithmetic; a plausible-looking document name would be a
judgement call. The Build Specification names "citations generated as
plausible-looking references" as a failure mode; this design makes it
unreachable.

### 5.3 Escalation is a designed output

An escalation carries the drafted answer, the retrieved sources with scores, the
predicted intent with alternatives, the urgency as a priority, and a plain
statement of what the system was unsure about. That is Daniel's stated
requirement, and it is what converts escalation from a loss into a product
feature.

### 5.4 Alternatives considered

| Alternative | Why not |
|---|---|
| k-NN classifier over ticket embeddings (99.4%) | Memorises templates. Would score brilliantly on the hidden set and generalise to nothing |
| Automatically derived safety vocabulary (90.8% held-out vs 73.6%) | Contains `only`, `call`, `nobody` — generic words correlating with deny-list templates. A security control that fires on the word "only" is not defensible |
| Whole-corpus prompting (the corpus is only ~8k tokens) | Would satisfy no retrieval criterion and produce no resolvable citations |
| Section-level chunking | Measured: 92.7% any-hit against 95.2% for whole documents, and more complex |

---

## 6. Implementation

369 tests, 91% branch coverage, one command (`pytest`), green on a clean checkout
without an API key.

**What was difficult** — in each case the defect was invisible until the whole
pipeline ran at volume:

1. **The provider is not deterministic at temperature 0.** 1 of 20 intents and 3
   of 20 confidences differ across identical inputs. A5 requires the same ticket
   to produce the same decision twice, so **the content-addressed cache is what
   satisfies that criterion**, not the model.
2. **A reasoning model bills its thinking against `max_tokens`.** With a 200-token
   budget, harder tickets spent it all reasoning and returned HTTP 200 with empty
   content — which was being cached as success, making one truncation permanent.
3. **Two rate-limit defects, then a third limit nobody documents.** The provider's
   `reset` header is time-until-full and the bucket refills continuously; sleeping
   the whole window to buy a few hundred tokens took the first gate run to 25
   tickets in 90 minutes. Fixing that revealed a **200,000 tokens/day cap that
   appears only in the 429 body** — every rate-limit header describes the
   per-minute bucket, which was full.
4. **Catching exceptions only at the top of the graph was not enough.** A
   classification failure aborted the pipeline and therefore also lost retrieval —
   so the retrieval-only fallback arrived without the documentation it exists to
   attach. Each node is now contained separately.

**What I would restructure.** The pacing logic accumulated three fixes and should
be one component with a single owner of "how many tokens may I spend now". And
the harness grew report-generation, health checks and orchestration in one file;
the report builder is already pure and should be separated properly.

---

## 7. Evaluation

### 7.1 Method

Development set (500) for all development and threshold derivation. Validation
(80) held back and used for a small number of logged checkpoint runs, following
the Project Brief's instruction rather than the Dataset Guide's looser wording —
a conflict named here because the two documents disagree. **The hidden set has
not been run.**

Every threshold was derived by sweep, not chosen. Evidence files carry a
provenance banner naming the commit, model and all three thresholds they were
produced under.

### 7.2 Results

*Table 1 — validation set, 80 tickets. Every row names the committed artifact
it comes from. Rows whose artifact no longer exists are marked as such rather
than restated.*

| Measure | Baseline | Target | Achieved | Source artifact |
|---|---|---|---|---|
| Retrieval hit rate @3 | — | — | **94.3%** | `2026-09-08-gate-run-cold/metrics.json` (53 eligible) |
| Citation resolution | — | 100% | **100%** | same run; 27 answers, re-resolved |
| Deny-list violations | — | 0 | **0** | same run, and every threshold in `2026-09-07-routing-200.txt` |
| Decision log reconciliation | — | exact | **passes** | same run; 80 of 80 tickets |
| Processing latency p95 | 8–12 hrs | <3s | **see below** | same run — 9.99s raw, 74% of it rate-limit sleep |
| First contact resolution | 43.8% | ≥60% | *withheld* | run degraded; rates correctly suppressed |
| Escalation rate | 56.2% | ≤30% | *withheld* | as above; see §7.4 for why the target is unreachable |
| Classification accuracy | — | ≥85% | *pending* | see note |

**Why four rows are not numbers.** Three attempts at a full validation run on
8 September were lost to the free tier's undocumented daily token cap (D-45); the
last stopped at ticket 54 of 80 and was correctly marked degraded, so its business
rates were withheld by the reporter rather than published. An earlier, healthier
validation run *did* produce 48.8% FCR, 51.2% escalation and 82.5% accuracy — the
figures previously printed here — but it wrote to a generic output directory that
a later run overwrote, so no committed artifact supports them. **They are
therefore not restated as results.** The functional rows above are unaffected:
they come from the surviving cold run and do not depend on the model reaching
every ticket.

Two supporting figures that *are* reproducible: classification accuracy over the
54 tickets that reached the model was **85.2%** (46 of 54, derived from
`technical.classification_accuracy` 0.575 across 80 with a 32.5% fallback rate),
and per-class accuracy is in the same file. That is consistent with the 87%±2 dev
figure, but it is a partial-run number and is reported as one.

**On latency.** The raw p95 of 9.99s is not a system measurement: **74% of total
per-ticket processing time in that run (217.6s of 294.3s) was the client asleep
waiting for the free tier's token allowance.** Net of that wait the mean is
**0.96s**. The harness now records provider wait per ticket and reports both
figures, so this is no longer a subtraction done by hand — but the p95 *net* of
waiting needs one run under the new instrumentation, and is pending with the rest.

### 7.3 Calibration — a failed condition, reported as one

The governance condition is stated confidence within five points of observed
accuracy. Across four cold runs of 100 tickets:

| Run | Accuracy | ECE | Within 5 points? |
|---|---|---|---|
| 1–4 | 89 / 86 / 87 / 90% | 3.2 / 6.0 / 5.2 / 2.5% | **2 pass, 2 fail** |

**Two of four runs fail.** The cause is specific: the model is systematically
overconfident by roughly four points in the 0.80–1.00 band, where 99 of 100
predictions land.

This failure is also the justification for the architecture. Confidence fails
calibration, which is precisely why routing thresholds on *margin* rather than
confidence, and why §5.1's conjunction leans on grounding and the deny-list.

### 7.4 Why one target is missed on purpose

Maximum defensible automation on development is 311 tickets labelled
`auto_respond` plus 15 labelled `escalate` that are neither deny-listed nor
ungrounded — **326/500 = 65.2%**, giving an escalation floor of **34.8%**. The
built system reaches 64.0% / 36.0% at the shipped margin of 0.85.

Reaching 30% would require moving 39 more tickets, and the only pools available
are 87 deny-listed tickets (a governance failure) or 87 ungrounded ones (blocked
by the system's own grounding guardrail).

There is a reading under which both targets are achievable: the targets sum to 90
rather than 100, and the Build Specification counts "blocked by guardrails"
separately from "escalated". Under that reading, 60% answered + 30% escalated +
10% blocked satisfies both. **That reading is rejected by design choice**: every
guardrail routes to block *and* escalate, because a blocked response still leaves
a customer without an answer and a human who must write one. Hitting 30% under
the three-outcome reading would require **at least 24 of 120 hidden tickets to
end with no answer and no human assigned**. Blocked counts are reported
separately regardless, so a reader can recompute under either taxonomy.

### 7.5 The limits of what was measured

**The figures above should be treated with caution because:**

- **The data is templated.** 57% of development ticket bodies duplicate another
  ticket. Any classifier scores implausibly well; a naive k-NN reaches 99.4%.
  These figures describe synthetic data.
- **Development and validation diverge on five measures and sometimes invert**, so
  a development figure may be optimistic on the hidden set.
- **Accuracy varies ±2 points run to run** because the provider is not
  deterministic at temperature 0.
- **Repeat contacts cannot be measured at all.** Same-customer, same-intent within
  seven days yields 2 pairs in 500 tickets. Reporting a number would be
  fabrication.
- **Satisfaction is not measured.** No live customers exist. Not estimated.
- **Response time is processing latency, not wall-clock human response.** The
  schema has no `replied_at` field, so the Evaluation Framework's own sample code
  cannot be run. Comparing a sub-second pipeline to an 8-hour human queue needs
  that caveat to be honest.
- **Hallucination rate has not been established** to the Framework's standard of
  fifty responses and two assessors.

---

## 8. Governance and risk

### 8.1 Decision logging

Every stage writes the Governance Framework's minimum record, including
`prompt_version` and `requirement_ids` — the two fields that answer *"was this
behaviour intended?"* after an incident. Reconciliation is by **identity in both
directions**, scoped to a run.

### 8.2 The safety gate, and a claim that was withdrawn

The design originally described "a deterministic deny-list that no confidence
score can override". **That was false and was retracted.** The deny-list keys on
the *predicted* intent, so a misclassified security incident never triggers it —
nothing is overridden, the rule simply does not fire. At the brief's own 85%
accuracy target that is roughly 3 tickets per 120, against a threshold of zero.

Three layers replaced it — predicted intent, an intent-agnostic lexical
pre-screen, and alternatives-aware abstention — plus a fourth, structural
protection: **56 of the 87 deny-listed development tickets cannot be grounded at
all**, so grounding protects them regardless of the classifier. Residual exposure
is confined to `security_incident` and `compliance_request` and is estimated at
~1 ticket in 120.

**Measured: zero deny-listed tickets auto-answered, at every threshold tested.**

### 8.3 Fairness

Measuring segments against each other would be wrong here. The **labels
themselves** already vary by more than the five-point condition:

| Segment | Dev label spread | Validation label spread |
|---|---|---|
| `customer_region` | **14.4pt** | **28.6pt** |
| `language_fluency` | 5.9pt | **23.5pt** |

Three of four segments exceed the condition before any system exists. The
ordering also inverts between splits. The audit therefore reports **system rate
minus the same split's label baseline**, pre-registered before results were
known. Segments below ten tickets carry a Wilson interval and are labelled as
unable to support inference — a caveat that, until review, printed only when no
outcomes were supplied, so it was suppressed on exactly the delta rows most
likely to be quoted (`enterprise`, n=8; `latin_america`, n=7). It is now
unconditional.

Sofia believed non-fluent English tickets were handled worse and that nobody had
noticed. She is right on validation and wrong on development — she identified a
real risk that the development data alone would have denied.

**The audit refuses to run on a degraded run.** Pointed at a degraded run it
returned eleven negative deltas — −42.9pt (asia_pacific) to −5.3pt (non_fluent) —
and the verdict `EXCEEDED — investigate`: a system apparently biased against every
customer group at once. That run had lost its provider partway, so every ticket
after that escalated regardless of content, pulling all segments down together.
The audit was measuring the outage. Uniformly negative numbers are superficially
plausible, and publishing them would have been the most damaging error in this
report.

The tool now reads the run's `metrics.json` and declines to produce per-segment
deltas when the run is marked degraded, printing only the label baselines, which
need no run and are always valid (D-44). It also refuses when *no* metrics file is
present, because copying `outcomes.json` into the dated-evidence layout used to
disable the guard silently. A cache replay is still accepted — replayed outcomes
are real routing decisions; only degradation invalidates them.

**The current figure is therefore the baselines alone.** A published per-segment
delta needs one non-degraded full-set run. Three attempts on 8 September were lost
to the free tier's daily token cap (D-45); the fourth is scheduled for the next
UTC window.

### 8.4 The kill switch

`touch storage/KILL`. Checked once per ticket **before any model call**, effective
on the next ticket, no deployment. Tickets in flight complete as escalations.
Two tests: every ticket escalates, and **zero model calls are made**. It was moved
earlier in the pipeline during the build after a test showed classification had
already spent a call before the switch was checked.

---

## 9. The requirements revision

Eight changes, each with a dated trigger. The largest:

**AS-02 failed.** PRD v1 assumed classifier confidence was calibrated enough to
threshold on. Measurement put **99 of 100 predictions in a single band** — there
is no curve to pick a point on. The routing basis moved to the *margin* between
the top intent and the best alternative, which has a real precision/coverage
curve. Confidence is now used only to report calibration.

**The safety gate claim was withdrawn** (§8.2), and the conjunction was
explicitly **ranked** rather than presented as four equals.

**The fairness baseline became split-dependent** after the orderings were found to
invert.

**What was deliberately not changed:** the escalation target was not chased; the
99.4% k-NN was not shipped; the higher-scoring derived vocabulary was not shipped;
and nothing was tuned against validation after the gate missed its target.

Full log with triggers and dates: Stage 5 workbook.

---

## 10. Conclusions

### 10.1 What was delivered

A system that clears the gate — 80 tickets, one command, unattended, zero
governance violations, a reconciling decision log, every ticket accounted for
even after the provider stopped answering at ticket 54.

Its **business** rates are not among the results, and that is the honest state of
this submission rather than a formatting choice: the runs that produced them were
lost to the free tier's daily token cap, and the reporter withholds rates from a
degraded run by design (§7.2, D-45). The functional and governance criteria are
measured and committed; the business figures need one clean run in a fresh UTC
token window. On the development set, where the budget stretched further, the
system reaches **64.0% first-contact resolution at its shipped margin of 0.85,
against a 65.2% day-zero prediction** (`2026-09-07-routing-200.txt`) — which is
what I would expect it to approach on validation, and I am deliberately not
presenting an expectation as a result.

### 10.2 What I would do next

1. **Renegotiate the escalation target before launch**, not after. It is
   unreachable without a governance breach and pretending otherwise sets up a
   failure that is nobody's fault.
2. **Measure the fluency gap on live tickets.** The two supplied splits disagree
   by 23.5 points and invert. Neither can be trusted as a baseline.
3. **A continuous human review sample in production.** The residual harm named in
   §8 — a correctly cited but misapplied passage — is invisible to every
   automated control in the system.
4. **Re-sort the queue by urgency.** High-urgency tickets currently have *worse*
   resolution (39.7% vs 48.4%) and longer handling, because the queue is sorted by
   age. This is a finding the system does not yet act on.

### 10.3 Reflection

*(To be rewritten in the author's own words. Draft follows.)*

Every revision in §9 replaced an assumption with a measurement, and in every case
the measurement was less flattering and more useful.

The three that mattered most were caught by independent review rather than by me:
a safety gate described as deterministic when it was not, a fairness result
generalised from one split to a population, and a calibration figure reported
from a cached run as though it were a cold measurement. Each was a plausible
reading of real data. All three would have been indefensible under questioning,
and all three were in writing before anyone challenged them.

The most uncomfortable finding concerned my own diagnosis. When the gate missed
its first-contact-resolution target, my first answer was that the data splits
diverge. That was true, and it was also deflection — two of my own safety markers
were costing eleven false escalations and catching nothing, and one of them was
the word `planned`. The lesson is not "measure things"; I was measuring plenty.
It is that the direction I chose to look first placed the fault outside my own
work.

What I would do differently is run the full chain end to end on day two rather
than day five, even against ten tickets. Every defect that cost real time was
invisible until the whole pipeline ran at volume. The Build Specification says
this in as many words. I read it, agreed with it, and still sequenced four days
of component-level confidence before the first full run.

---

## 11. Declaration of AI tool use

This project was developed with substantial AI assistance, used for writing and
debugging code, drafting and refining the prompts that run inside the system, and
structuring documentation.

**Where I overrode or corrected it:**

- Rejected a proposed marker vocabulary figure (94.3% recall / 0% false
  positives) as an in-sample upper bound, and re-measured it on a held-out split:
  **90.8% / 0.7%**.
- Rejected the reasoning that the FCR and escalation targets were *arithmetically*
  incompatible; they are incompatible by design choice, and the distinction
  matters because the Build Specification supports a three-outcome reading.
- Corrected an arithmetic error in a review (56 structurally-protected deny-list
  tickets, not 35).
- Overrode a recommendation to derive the routing threshold from margin *because
  confidence has no spread*, after measuring that margin's calibration is **worse**
  (ECE 6.9% vs 3.2%). Both are used, for different purposes.
- Declined to accept "the splits diverge" as an explanation for the missed FCR
  target, which led to finding two defective markers in my own vocabulary.

All figures were independently recomputed from the raw data before being
reported. Where a claim could not be verified it is labelled as unverified.

---

## Appendices

- **A** — Stage 1 Discovery Workbook
- **B** — Stage 2 PRD v1.0 and v1.1
- **C** — Stage 3 Prompt Library and traceability matrix
- **D** — Stage 4 Sprint Plan with estimates against actuals
- **E** — Stage 5 Revision Log
- **F** — Governance Framework (risk register, fairness audit, incident procedure)
- **G** — Decision record: 42 decisions with evidence (`docs/DECISIONS.md`)
- **H** — Evaluation artifacts (`evaluation/results/`), each with a provenance banner
- **I** — Validator charter and six review verdicts (`docs/VALIDATOR.md`)
