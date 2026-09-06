# Decision Record

Every significant decision, why it was taken, and what evidence supports it.

**Purpose.** Three things depend on this file. The report needs the reasoning
(§5 Architecture asks for "the alternatives you considered, and why you chose as
you did"). The video needs it more sharply — the Project Instructions warn that
you may be "stopped mid-sentence and asked why you did it that way", and this is
where the answer lives. And the Governance Framework requires decisions to be
reconstructable months later by someone who was not there.

**Video column.** Each entry is tagged with the video section it belongs in, per
the Submission Guide's prescribed structure:

| Tag | Minutes | Section |
|---|---|---|
| `PROBLEM` | 0–2 | What the client asked for vs. what we found |
| `DISCOVERY` | 2–5 | The findings that changed the design |
| `SYSTEM` | 5–7 | Architecture, for a non-engineer |
| `DEMO` | 7–14 | Live run: success, escalation, guardrail, unattended |
| `NUMBERS` | 14–17 | Business, then technical, then governance |
| `GOVERNANCE` | 17–18 | What could go wrong, what stops it |
| `NEXT` | 18–20 | What we got wrong, what the PRD revision changed |

---

## D-01 · Build a triage and drafting system, not a chatbot

**Tag:** `PROBLEM` · **Date:** 2026-09-04 · **Status:** Accepted

CloudServe asked for a chatbot. The evidence says a chatbot addresses none of
their actual failure. 71.4% of tickets are already answered in their own 29
articles, so they do not lack answers — they cannot deliver them. Ines names the
mechanism exactly: keyword search cannot bridge "my deployment keeps dying" to an
article titled "Resolving container health check failures".

**Alternatives considered:** (a) the chatbot as asked; (b) improving internal
search only; (c) retrieval-grounded triage with drafted answers and
context-carrying escalation.

**Chosen (c),** because it addresses delivery *and* the confidence problem Sofia
describes. (b) would help agents but leave customers waiting. (a) answers the
request and fails the assignment.

**Evidence:** E-01 (71.4% answerable), E-02 (Ines on search), E-06 (Sofia
escalates when unsure), E-03 (49.1% of escalations were answerable).

> **Video line:** "They asked for a chatbot. A chatbot is a delivery mechanism —
> it says nothing about where the answer comes from or what happens when it isn't
> known. Their problem isn't that answers don't exist. It's that nobody can find
> them."

---

## D-02 · Escalation is a designed output, not a failure branch

**Tag:** `SYSTEM` · **Date:** 2026-09-04 · **Status:** Accepted

Every escalation carries the drafted answer, the retrieved sources with scores,
the predicted intent with alternatives, and an explicit statement of what the
system was unsure about.

**Why:** Daniel says escalations arrive as bare forwarded tickets, so he re-reads
the thread and re-asks the customer — "that is where the customer frustration
really comes from, more than the waiting". He explicitly does not need it to be
right: "I need it to show its working."

**Evidence:** E-04, E-03.

> **Video line:** "Students treat escalation as the losing branch. It isn't. An
> escalation that arrives with a draft, the relevant page, and a note saying what
> the system wasn't sure about is worth more to a tier-two engineer than a raw
> ticket."

---

## D-03 · Deliberately miss the escalation ≤30% target

**Tag:** `NUMBERS` · **Date:** 2026-09-04 · **Status:** Accepted · **Contestable**

Maximum *defensible* automation is 311 (`auto_respond`) + 15 (escalate-labelled,
not deny-listed, and groundable) = **326/500 = 65.2%**, so the escalation floor is
**34.8%**. FCR clears its 60% target with headroom; escalation misses 30% by ~5
points.

**The counter-argument, stated fairly:** the targets sum to 90, not 100, and Build
Spec §04 lists "blocked by guardrails" as a *separate* count from escalated. That
implies a legitimate third bucket, under which 60/30/10 satisfies both targets.

**Why we reject it:** every guardrail routes to block **and** escalate, because a
blocked response still leaves a customer with nothing and a human who must now
write the answer. Under the three-outcome reading, hitting 30% requires **≥24 of
120 hidden tickets to end with no answer and no human assigned**. That is worse
than a missed target, and invisible in every reported figure.

This is a **design choice, not arithmetic** — an earlier draft claimed the targets
were mathematically incompatible, which was wrong, and the validator caught it.
§5 reports `blocked_by_guardrails` separately anyway so a reader can recompute
under either taxonomy.

> **Video line:** "We miss one of the two targets on purpose. The only way under
> 30% runs through security and compliance tickets. I'd rather report 34.8% and
> explain it than hit 30% and not be able to."

---

## D-04 · The safety gate is three layers, and is *not* deterministic

**Tag:** `GOVERNANCE` · **Date:** 2026-09-04 · **Status:** Accepted · **Revised once**

Four intents must never be auto-answered: `security_incident`,
`compliance_request`, `feature_request`, `unclear_request` (87/500, zero label
violations).

**The error we corrected:** the first draft called this "a deterministic gate that
no confidence score can override". That was false. The deny-list keys on the
*predicted* intent, so a misclassified security incident never triggers it —
nothing is overridden, the rule simply never fires.

**Now three independent layers, any of which escalates:** (1) predicted top-1
intent; (2) an intent-agnostic lexical pre-screen over raw text; (3)
alternatives-aware abstention reading the whole distribution. They fail
independently: label, surface tokens, distribution.

**A fourth control is structural:** grounding. `feature_request` (0/20) and
`unclear_request` (0/15) can never ground, and with the ungrounded
`security_incident` and `compliance_request` tickets that is **56 of 87**
protected regardless of the classifier. Residual exposure ≈ **1 ticket in 120**,
confined to the two groundable intents. Reported as deny-list recall on those two
specifically, never as a diluted four-class aggregate.

> **Video line:** "The Governance Framework asks a good question: if the answer
> describes a property of the model rather than a control you built, you've
> described a hope. My first version was a hope. Here's what replaced it."

---

## D-05 · The fairness baseline is split-dependent

**Tag:** `NUMBERS` · **Date:** 2026-09-04 · **Status:** Accepted · **Revised once**

| Segment | Dev (500) | Validation (80) |
|---|---|---|
| non-fluent vs fluent FCR | +2.7pt | **−33.0pt** (p=0.017) |

**The error we corrected:** the first draft checked only dev, found no gap, and
concluded "any gap our system exhibits is one we introduced". Validation says the
opposite. Since the hidden set is drawn from the validation population, that
would have been an indefensible pre-commitment.

**Method, pre-registered before results are known:** report **system outcome minus
the label baseline of the same split**, per segment, never against an assumed-flat
baseline. Segments: tier, region, fluency, and short vs. long tickets.

> **Video line:** "The framework predicts you'll find non-fluent English does
> worse. On the development set it doesn't. On validation it's 33 points worse.
> Which means the honest thing to measure is my delta against whichever baseline
> the graded set actually has."

---

## D-06 · Thresholds are derived, never chosen

**Tag:** `NUMBERS` · **Date:** 2026-09-04 · **Status:** In progress

`CONFIDENCE_THRESHOLD` and `RELEVANCE_FLOOR` currently carry placeholder values,
explicitly marked `TODO(D4)` in `src/config.py`. Both are replaced from measured
curves — the relevance floor from Day 2's retrieval sweep, the confidence
threshold from Day 3's precision/coverage curve and calibration table.

**Why it matters:** the brief penalises "a threshold chosen because it looked
reasonable rather than because it was measured", and an uncalibrated confidence
score makes the whole routing conjunction meaningless.

---

## D-07 · Replace the pack's `requirements.txt`

**Tag:** `SYSTEM` · **Date:** 2026-09-04 · **Status:** Accepted

The pack's file cannot be installed: it pins `langchain-openai==0.0.7` (requiring
`openai>=1.10`) against `openai==1.0.0`, and pip returns `ResolutionImpossible`.
`sentence-transformers==2.2.2` also fails at import against modern
`huggingface_hub`. Following the Setup Guide literally fails A1 at step one.

Verified by running pip's resolver, not by inspection. Our replacement was
resolved together in a clean venv.

---

## D-08 · No torch — use Chroma's built-in ONNX MiniLM

**Tag:** `SYSTEM` · **Date:** 2026-09-04 · **Status:** Accepted

`chromadb` ships `onnxruntime`, and its default embedding function *is*
`all-MiniLM-L6-v2` — the exact model the Project Brief specifies. Using it removes
`torch` and `sentence-transformers` entirely: **~2.5 GB smaller install**, same
model, materially faster and less fragile clean checkout.

> **Video line:** "Same embedding model the brief asks for, two and a half
> gigabytes less to install. The gate is a clean checkout on someone else's
> machine, so install size is a correctness property, not a nicety."

---

## D-09 · Support both Groq and OpenRouter

**Tag:** `SYSTEM` · **Date:** 2026-09-04 · **Status:** Accepted

Build Spec §06 step 4 sets configuration from *our* `.env.example` with a key
substituted in — but the pack's Setup Guide uses `OPENROUTER_API_KEY` while we
default to Groq (faster free tier, which helps the p95 <3s target). A grader
holding the pack's default would otherwise land in the degraded fallback path and
see an all-escalation run. One hour of work removes a gate risk entirely.

---

## D-10 · A missing key degrades; a *broken* key must fail loudly

**Tag:** `GOVERNANCE` · **Date:** 2026-09-04 · **Status:** Partially implemented

A11 requires graceful degradation, so absent credentials must not stop the system
starting. But the dangerous case is a *misconfigured* graded run: a wrong key
produces 120 escalations, a clean exit, and a metrics report — indistinguishable
from a very conservative working system.

**Resolution:** degrade on mid-run provider failure; fail loudly at startup on a
key that is present but rejected; and flag `degraded_run: true` prominently in the
metrics report so an escalation rate is never reported without it. Preflight
implemented as `scripts/check_env.py`; the report flag lands with the harness.

---

## D-11 · Reconcile the decision log by identity, not by count

**Tag:** `GOVERNANCE` · **Date:** 2026-09-04 · **Status:** Accepted · **Revised once**

`decisions == tickets × stages` is wrong, because stage counts legitimately vary:
a deny-listed ticket terminates at routing, an ungrounded one escalates before
generation, a kill-switched one makes no model call. That assertion would fail on
a run that is entirely correct.

Instead: exact set identity in both directions, every ticket has ≥1 record, and
each stage sequence is a valid pipeline prefix.

---

## D-12 · One terminal state per ticket, enforced at write time

**Tag:** `GOVERNANCE` · **Date:** 2026-09-04 · **Status:** Accepted · **Bug found by review**

`volume_counts()` originally counted *records*, not tickets. Demonstrated: two
tickets plus one stray second terminal record reported `processed: 3`, counted one
ticket in two outcomes, and still passed reconciliation — which compared id sets
only.

**Build Spec §06 step 9 opens the metrics report and the decision log and
reconciles them against each other**, so this was the exact check the grader runs.
Terminal state is now unique per ticket, rejected at write time, and `processed`
derives from distinct terminated ids.

> **Video line:** "This one is worth showing. The metrics report and the decision
> log could disagree, and the reconciliation check passed anyway. That's the
> precise thing step nine of the test procedure looks for."

---

## D-13 · Fairness segments degrade to `UNKNOWN`, and degradation is recorded

**Tag:** `GOVERNANCE` · **Date:** 2026-09-04 · **Status:** Accepted · **Revised once**

`CustomerTier` and `LanguageFluency` originally fell back to `STANDARD` and
`FLUENT` — *aliases of real members*, so a defaulted ticket was indistinguishable
from a genuine one, and both defaults landed in the majority segment (50.6% and
76.0%) which is exactly where D-05's baseline is computed.

Both now fall back to a distinct `UNKNOWN`, matching what `Channel` and
`CustomerRegion` already did, and every coercion is recorded in
`NormalisedTicket.degraded_fields` so it stays auditable after ingest.

---

## D-14 · Citations are constructed from retrieved IDs, never emitted by the model

**Tag:** `DEMO` · **Date:** 2026-09-04 · **Status:** Accepted

`RetrievedPassage` carries `doc_id`, `chunk_id`, `score` and character offsets.
The validator re-resolves every citation against the store before release; an
unresolvable citation blocks the response.

This makes A6 **structurally** true rather than prompt-dependent. The type
immediately caught an existing test fixture with no `chunk_id` — i.e. a citation
that could not have been re-resolved.

---

## D-15 · Ingest is defensive everywhere except `ticket_id`

**Tag:** `SYSTEM` · **Date:** 2026-09-04 · **Status:** Accepted

Every field degrades to a documented fallback, because a run that stops on the
fortieth ticket fails A9. `ticket_id` is the single exception: identity is what
A8's reconciliation cannot synthesise, so a ticket without one is rejected rather
than given a fabricated id. `normalise_batch` returns rejections alongside
tickets so the harness accounts for every input record.

---

## D-16 · Repeat contacts are reported as unmeasurable

**Tag:** `NUMBERS` · **Date:** 2026-09-04 · **Status:** Accepted

It is a required Tier-1 target ("reduced by half"). Same-customer, same-intent
within 7 days yields **2 pairs across 500 dev tickets** and 1 across 80
validation. A single pass over independent tickets cannot produce it. Reported as
not measurable, with the evidence — claiming a number would be fabrication.

---

## D-17 · An independent validator gates every phase

**Tag:** `NEXT` · **Date:** 2026-09-04 · **Status:** Active

No phase proceeds without a recorded verdict. Across three reviews it has found
eight defects, four load-bearing — including D-04, D-05, and the D-12 bug. Its
charter, precedence order and full verdict history are in
[`VALIDATOR.md`](VALIDATOR.md).

It is a check, not an authority: I verify its numbers as it verifies mine, and
corrected one of its own figures (56 structurally-protected deny-list tickets,
not 35).

> **Video line:** "Two of the things I'm proudest of in this project are things I
> got wrong and fixed before they shipped."

---

## D-18 · Test-driven throughout

**Tag:** `NEXT` · **Date:** 2026-09-04 · **Status:** Active

Every test written and watched fail before the code that satisfies it. Governance
premises are frozen as tests against the real 500-ticket set, so if the data ever
contradicts the design's argument, CI says so in under two seconds.

Mid-Day-1 I caught myself having written four methods without failing tests
first, deleted them, and reimplemented the one that was needed.

---

## D-19 · Whole-document chunking (open decision O-1, resolved)

**Tag:** `SYSTEM` · **Date:** 2026-09-04 · **Status:** Accepted · **Measured**

Compared two strategies over the 500 development tickets. Evidence:
`evaluation/results/2026-09-04-retrieval-tuning.txt`.

| Strategy | Chunks | any-hit@3 | recall@3 |
|---|---|---|---|
| **whole document** | 29 | **95.2%** | **88.2%** |
| section (markdown headings) | 145 | 92.7% | 81.1% |

Whole-document wins on both metrics *and* is simpler. This matches the Dataset
Guide's warning that "splitting inside a resolution sequence tends to produce
passages that retrieve well but read as incomplete" — a resolution step separated
from its symptoms retrieves on the symptom words it no longer contains.

The articles are 860–1,336 characters, already smaller than the 800-character
chunk size the Setup Guide offers as a starting point, so splitting them was
always likely to hurt. The point is that we measured it rather than asserting it.

> **Video line:** "The setup guide suggests 800-character chunks. The articles
> are about a thousand characters. Splitting them cost two and a half points of
> hit rate, so we didn't."

---

## D-20 · Relevance floor 0.40 — and why not the argmax (O-2, resolved)

**Tag:** `NUMBERS` · **Date:** 2026-09-04 · **Status:** Accepted · **Measured**

| floor | any-hit@3 | ungroundable rejected |
|---|---|---|
| 0.35 | 93.6% | 12.6% |
| **0.40** | **92.7%** | **14.7%** |
| 0.45 | 85.4% | 21.0% |
| 0.50 | 73.4% | 35.0% ← argmax of the combined score |

**We chose 0.40 and deliberately rejected the naive optimum at 0.50.** Three
arguments, strongest first.

**1. The argmax is an artifact of the metric, not of the data.** The `combined`
column is an unweighted mean of any-hit (measured on 357 groundable tickets) and
rejection (measured on 143 ungroundable). That silently weights each ungroundable
ticket **2.5×** each groundable one. Weight by actual population instead:

| floor | unweighted combined | population-weighted | tickets correct |
|---|---|---|---|
| 0.30 | 53.3% | **70.8%** | 354.0 |
| 0.35 | 53.1% | 70.4% | 352.2 |
| **0.40** | 53.7% | **70.4%** | 352.0 |
| 0.45 | 53.2% | 67.0% | 334.9 |
| 0.50 | **54.2%** ← argmax | **62.4%** | 312.1 |

Population-weighted, 0.50 is **8 points worse** than 0.40 and gets **40 fewer
tickets right**. The argmax disappears entirely.

**2. There is a real knee, and 0.40 is the last floor before it.** Marginal
any-hit loss per 0.05 step: 0.5pt, 0.9pt, then **7.3pt** — an eight-fold
acceleration at 0.45.

**3. Division of labour.** Rejecting ungroundable tickets is not the floor's job.
Even at 0.60 only 70.6% are rejected, with any-hit down to 33.9% — retrieval
similarity is a weak signal for groundability, because an ungroundable ticket is
about the *same topic*, it simply has no article answering it. Groundability
belongs to the grounding guardrail. Under D2's conjunction a false accept is
caught downstream, while a miss is terminal — so the asymmetry favours coverage.

**What we do NOT claim.** 0.40 is not measurably better than 0.35: they are
identical population-weighted (70.4% both), and the move costs 3.2 groundable
tickets to buy 3.0 rejections. Anything in **0.30–0.40 is equivalent on this
evidence**. 0.40 is defensible as the conservative end of a flat region that
terminates in a cliff — not as an optimum.

> **Video line:** "The obvious move is to take the number that maximises your
> score. That was 0.50, and it would have been a mistake — the metric was
> weighting a hundred and forty tickets as if they were three hundred and fifty."


---

## D-21 · Retrieval validates the design's central premise

**Tag:** `DISCOVERY` · **Date:** 2026-09-04 · **Status:** Confirmed

Assumption AS-01 was that semantic retrieval bridges the symptom-to-title gap
Ines described. Measured: **95.2% any-hit@3, 88.2% recall@3** across the 357
groundable development tickets.

A test asserts the bridge directly — the query "my deployment keeps dying" must
retrieve a `DOC-DEPLOY` article — and a second asserts the hit rate does not fall
below 60%. If either breaks, the premise is wrong and the design needs revisiting
rather than patching.

> **Video line:** "Ines said there is no path between 'my deployment keeps dying'
> and 'resolving container health check failures' in a keyword search. There
> isn't. There is in an embedding, and it finds the right article 95% of the time."

---

## D-22 · The documented model no longer exists

**Tag:** `SYSTEM` · **Date:** 2026-09-04 · **Status:** Accepted · **Found live**

The Setup Guide's suggested `meta-llama/llama-3.1-8b-instruct`, and the whole
Llama family, are no longer served by Groq's free tier — the API returns 404. We
queried the models endpoint rather than trusting documentation, and chose
`openai/gpt-oss-20b` from what the account can actually reach. Verified live:
**1.03s** for a trivial completion, which is the first real datapoint against the
p95 < 3s target.

`scripts/list_models.py` exists so this can be re-checked rather than assumed
next time. The brief is explicit that "a well-built system running on a small free
model will out-score a thin one running on an expensive one", so a 20B model is a
deliberate choice.

**A bug this exposed:** the first 404 was retried three times with backoff, taking
4.0s to report a failure that was certain on the first attempt. A missing model or
a bad key is not transient. `ProviderConfigError` is now raised for 4xx other than
429 and is never retried — 1 attempt, 0.49s. Over a 120-ticket unattended run that
is the difference between a fast failure and a slow, expensive one.

> **Video line:** "The setup guide names a model that no longer exists. Worth
> checking what your provider actually serves rather than trusting a document
> written six months ago."

---

## Open decisions

| # | Question | Due |
|---|---|---|
| ~~O-1~~ | ~~Chunking strategy~~ — resolved, see D-19 | ✅ Day 2 |
| ~~O-2~~ | ~~Relevance floor~~ — resolved, see D-20 | ✅ Day 2 |
| O-3 | Confidence threshold, from the precision/coverage curve | Day 3 |
| O-4 | Marker-token vocabulary for D-04 layer 2, with measured recall | Day 3 |
| O-5 | Throughput budget: calls/ticket, rate limits, wall-clock for 120 | Before Day 5 |
| O-6 | Incident procedure, six steps with owner and duration | Day 8 |
