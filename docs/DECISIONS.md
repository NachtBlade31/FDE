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

## D-23 · The supplied data is templated, and we say so

**Tag:** `NUMBERS` · **Date:** 2026-09-07 · **Status:** Accepted · **Measured**

A spike returned a result too good to accept: a k-nearest-neighbour classifier
over ticket embeddings scored **99.4% leave-one-out** against a brief targeting
85%. A number that far above target is evidence about the data, not the model.

Measured (`evaluation/results/2026-09-07-data-regularity.txt`):

| | Development | Validation |
|---|---|---|
| distinct ticket bodies | 215 of 500 | 60 of 80 |
| tickets duplicating another | **57.0%** | 25.0% |
| token overlap, same intent vs different | **19×** | — |

`rate_limit` has 13 tickets and 4 distinct openings; "too many request error. we"
appears six times verbatim.

**Consequence, stated in the report rather than quietly enjoyed:** any classifier
scores implausibly well here. The hidden set comes from the same population, so
the figure will hold there too — and still will not generalise to real CloudServe
tickets. Reported precision describes performance on synthetic, templated data,
and any claim beyond that is labelled an extrapolation.

**Why we did not simply ship the kNN.** It would score ~99% and be memorising
templates. The LLM classifier is what would work on real tickets, so it is the
primary path; the finding is reported rather than exploited.

> **Video line:** "A nearest-neighbour matcher gets 99.4% on this data. That is
> not a good classifier, it is a warning: 57% of the ticket bodies are exact
> duplicates of another ticket. I am reporting 89% from something that actually
> reads the ticket, and telling you what that number does and does not mean."

---

## D-24 · Tokens per minute, not requests, is the binding constraint

**Tag:** `SYSTEM` · **Date:** 2026-09-07 · **Status:** Accepted · **Measured**

The first 100-ticket run scored **23% accuracy**. It was not a classifier problem:
**222 provider calls, 131 retries, 75 fallbacks, degraded=True.** Reading the
response headers gave the real limits:

```
x-ratelimit-limit-requests : 1000   (reset 1h39m)   931 remaining
x-ratelimit-limit-tokens   : 8000   (reset 35s)    3275 remaining
```

**Requests were never the constraint; tokens per minute were.** At ~556 tokens a
call that is roughly 14 calls per minute. Reacting only to 429s spends the
allowance on retries that were always going to fail.

The fix is proactive pacing: record the allowance from every response and wait
for the window to reset before a call it cannot cover. Also honour the provider's
`retry-after` hint over our own exponential schedule — it knows better than we do.

| | before | after |
|---|---|---|
| provider calls for 100 tickets | 222 | **90** |
| retries | 131 | **0** |
| fallbacks | 75 | **0** |
| accuracy | 23.0% | **89.0%** |
| degraded | True | **False** |

> **Video line:** "My first run scored 23%. The classifier was fine — I was being
> rate limited and retrying into the limit. The fix was to read the headers the
> provider was already sending me."

---

## D-25 · A reasoning model bills its thinking against your token budget

**Tag:** `SYSTEM` · **Date:** 2026-09-07 · **Status:** Accepted · **Found live**

`openai/gpt-oss-20b` returns a `reasoning` field alongside `content`, and the
reasoning is charged to `max_tokens`. With `max_tokens=200`, harder tickets spent
the entire budget thinking and returned **HTTP 200 with empty content**.

Two fixes:

1. **`reasoning_effort: "low"`** — reasoning tokens fall from 113 to 7 and total
   tokens from 650 to 556. Saves 14% of the allowance *and* removes the
   truncation. `max_tokens` raised to 500 for headroom.
2. **An empty completion is a failure, not a success.** It was previously cached,
   which turned one truncation into a permanent misclassification for that ticket.

This is only findable by running against the real provider. A mock returning
well-formed JSON would have passed every test.

> **Video line:** "The model was returning HTTP 200 and an empty answer, because
> it had spent its whole token budget thinking. My tests all passed — the mock
> was too polite."

---

## D-26 · Layer 3 of the safety gate earned its place immediately

**Tag:** `GOVERNANCE` · **Date:** 2026-09-07 · **Status:** Confirmed

Measured over 100 development tickets, deny-list recall by layer:

| Intent | Layer 1 (top-1) | + Layer 3 (alternatives) |
|---|---|---|
| `compliance_request` | 4/4 | 4/4 |
| `feature_request` | 3/3 | 3/3 |
| `security_incident` | 4/4 | 4/4 |
| `unclear_request` | **0/1** | **1/1** |

One ticket was missed entirely by the top-1 label and caught by alternatives-aware
abstention — the exact case layer 3 was added for. Deny-listed tickets missed by
both classifier layers: **0**. The lexical pre-screen (layer 2) is a further
independent control on top of that.

> **Video line:** "The third layer was the validator's suggestion and I nearly
> argued against it. On the first hundred tickets it caught one the main
> classifier missed outright."

---

## D-27 · The lexical pre-screen is curated, not derived (O-4, resolved)

**Tag:** `GOVERNANCE` · **Date:** 2026-09-07 · **Status:** Accepted · **Measured**

Layer 2 of the D-04 safety gate. Two candidate vocabularies were measured.

**Automatically derived** — tokens selected by frequency inside deny-list tickets
versus outside, with 5-fold cross-validation so the vocabulary is never scored on
the tickets that produced it:

| | recall | FP rate |
|---|---|---|
| held-out (5-fold) | **90.8%** | 0.7% |
| in-sample (derived and scored on all 500) | 95.4% | 0.0% |

The in-sample figure is an upper bound, not an estimate. Reporting it would have
overstated the control by 4.6 points. (An earlier suggested figure of 94.3%/0.0%
was of this in-sample kind, and was not adopted.)

**Hand-curated** — 58 terms chosen for what they *denote* rather than what they
correlate with:

| Intent | Curated recall |
|---|---|
| `security_incident` | **26/26 = 100%** |
| `compliance_request` | **26/26 = 100%** |
| `feature_request` | 12/20 = 60% |
| `unclear_request` | **0/15 = 0%** |
| overall | 73.6% (FP rate 4.8%) |

**We chose the curated vocabulary, despite its worse headline number.** Three
reasons:

1. **It is 100% on the only two intents where residual risk exists.** D-04
   establishes that `feature_request` and `unclear_request` can never ground
   (0/20 and 0/15 answerable from docs), so D2's grounding conjunction protects
   them structurally regardless of what layer 2 does. Layer 2's job is precisely
   the two groundable intents, and it catches all of them.
2. **The derived vocabulary is overfitted to templates.** It contains `another`,
   `call`, `going`, `look`, `only`, `once`, `per`, `nobody`. Those correlate with
   deny-list templates in this synthetic data (see D-23) and denote nothing. A
   safety control that fires on the word "only" is not a control anyone can
   defend, and it would not survive contact with real tickets.
3. **A false positive costs one unnecessary escalation; a false negative is a
   governance breach.** 4.8% — 20 tickets in 500 — is an acceptable price. That
   asymmetry is why the vocabulary is tuned for recall on the intents that matter
   rather than for overall accuracy.

**`unclear_request` at 0% is not a defect.** Being unclear is not a vocabulary
property. "Nothing is loading properly today. Can someone look into this?"
contains no marker because there is nothing to mark. It is caught by layer 1
(the classifier's own `unclear_request` prediction, which is the fallback class)
and by grounding, and it can never be answered from documentation anyway.

> **Video line:** "The automatic version scored higher — ninety-one per cent
> against seventy-four. I shipped the lower one, because its misses are in the
> two categories that physically cannot be auto-answered, and because I am not
> willing to defend a security control that fires on the word 'only'."

---

## D-28 · The provider is not deterministic at temperature 0 — the cache is what satisfies A5

**Tag:** `DEMO` · **Date:** 2026-09-07 · **Status:** Accepted · **Measured**

A5 requires: "Run the same ticket twice. The decision does not change." Tested
directly — 20 unique tickets, two passes, a fresh cache for each so nothing was
replayed:

| | differed |
|---|---|
| intent | **1 / 20** |
| confidence | **3 / 20** |

`temperature=0` is not determinism. Provider-side batching and hardware
non-determinism move the output. Three cold 100-ticket runs gave **89.0%, 86.0%,
87.0%** accuracy on identical input, and ECE of **3.2%, 6.0%, 5.2%**.

**Consequence: the content-addressed cache is not an optimisation, it is the
mechanism that satisfies A5.** D5 originally justified it on cost and
reproducibility; it is now load-bearing for an acceptance criterion, and the
report says so rather than implying the model is deterministic.

**A reassuring detail worth checking on the full run:** the one intent that
flipped went `compliance_request` → `feature_request`. Both are deny-listed, so
the *routing decision* was identical either way. Whether flips can cross the
deny-list boundary is a governance question, and it is now on the Day 5 checklist.

**Reporting consequence:** accuracy is quoted as **87% ± 2 across runs**, not as a
single figure. ECE straddles the 5-point condition, so calibration is reported as
*at the boundary, with run variance exceeding the margin* — not as a pass.

> **Video line:** "Temperature zero is not determinism. I measured it: one ticket
> in twenty changes its answer between runs. The acceptance criterion asks the
> same ticket to give the same decision twice — the cache is what makes that
> true, not the model."

---

## D-29 · Confidence calibrates; margin discriminates (O-3, resolved)

**Tag:** `NUMBERS` · **Date:** 2026-09-07 · **Status:** Accepted · **Measured**

D4 requires the routing threshold to be derived, which presupposes a variable
with spread to sweep. Self-reported confidence has none: **99 of 100** predictions
land in one band.

Two candidates, measured:

| | ECE | Precision/coverage curve |
|---|---|---|
| top-1 confidence | **3.2–6.0%** | flat — nothing to sweep |
| margin (top-1 − best alternative) | 6.9% | **real: 0.80 → coverage 94%, precision 92.6% vs 89.0% base** |

**They are good at different things, and the design uses each for what it is good
at.** Confidence is better *calibrated*, so it is what the governance calibration
table reports. Margin is better at *discriminating*, so it is what the routing
threshold is swept on. A variable can rank without being a probability, and
conflating the two would have produced a threshold that is an artifact of the
model's numeric habits rather than a measured trade-off.

**Both are weak, and the conjunction is ranked accordingly.** The margin curve is
flat below 0.70. So D2's four conjuncts are not equal: **grounding and the
deny-list carry the routing decision; confidence is the weakest leg.** That
ranking is documented rather than implied — 56 of 87 deny-list tickets are
protected by grounding alone, which is a stronger control than any threshold.

**This is the Stage 5 revision trigger.** PRD v1 assumed routing would rest on a
calibrated confidence threshold (AS-02). Measurement showed self-reported
confidence is non-discriminative on this data. The routing basis moved to margin
plus grounding plus the deny-list. That is a specific requirement, a specific
trigger and a specific change — exactly what the revision log asks for.

> **Video line:** "I planned to route on a confidence threshold. Then I measured
> it: ninety-nine of a hundred predictions sit in the same band. There is no
> curve to pick a point on. So the threshold moved to a variable that actually
> separates, and the routing leans on whether the answer is grounded instead."

---

## D-30 · A cache replay is not a measurement

**Tag:** `NEXT` · **Date:** 2026-09-07 · **Status:** Fixed · **Caught in review**

The committed throughput evidence for D-24 was a cache replay. The run that
produced the reported figures was real, but the artifact captured afterwards
re-ran the same script against a warm cache and recorded `0 provider calls, 100
cache hits, p95 0.01s`. Accuracy survived — a cache hit replays a real completion
— but latency and calls-per-ticket measured dictionary lookups.

**The systemic fix, not just the instance:** the reporter now refuses to emit a
throughput budget when no live calls were made, and when some tickets were served
from cache it says so and measures latency over live calls only. Within-run cache
hits are real and expected — the data is templated (D-23), so 10 of 100 tickets
duplicate an earlier one even on a cold run — but they flatter wall-clock and are
disclosed rather than absorbed.

This matters most on Day 5: the design already notes the hidden run has a cold
cache by definition, so a warm rehearsal would produce a beautiful latency profile
and validate nothing.

**Honest cold figures** (`evaluation/results/2026-09-07-classifier-100-cold.txt`):
90 live calls for 100 tickets, 0 retries, p95 **1.25s**, wall clock 205s,
projected **4.1 min** for 120 tickets of classification.

> **Video line:** "One of my own evidence files was measuring its cache instead of
> the system. The fix was not to re-run it — it was to make the report refuse to
> print a throughput number when it has nothing live to measure."

---

## D-31 · Layer 3 needed a floor; without one it escalated two thirds of everything

**Tag:** `GOVERNANCE` · **Date:** 2026-09-07 · **Status:** Fixed · **Found by measurement**

The alternatives-aware abstention control (D-04 layer 3) was specified as "escalate
if a deny-listed intent appears in the alternatives **above a low floor**". The
floor was omitted in implementation, so *any* deny-listed alternative escalated.

Measured over 200 development tickets, that single check caused **66% of all
escalations** and held first contact resolution at 51% against a 60% target.

| abstention floor | FCR | route acc | auto precision | layer-3 escalations |
|---|---|---|---|---|
| 0.00 (as built) | 51.0% | 68.5% | 76.5% | 65 |
| **0.05 (derived)** | **64.5%** | **78.0%** | **78.3%** | 21 |
| 0.10 | 69.0% | 76.5% | 75.4% | 6 |
| 0.15 and above | 69.0% | 76.5% | 75.4% | **0 — inert** |

**Why 0.05.** It maximises both routing accuracy and auto-respond precision, and
is the last floor at which layer 3 still does anything: from 0.15 upward it never
fires, which is indistinguishable from deleting the control.

**Why the bug mattered.** A model asked to name its alternatives will list a
deny-listed class at trivial confidence on most tickets. Treating a 2% alternative
as a safety signal is not caution — it is noise, and it cost 13 points of first
contact resolution while catching nothing the other layers missed. **Zero
governance violations at every floor tested, including 0.00**, which is the proof
that the escalations it added were not buying safety.

> **Video line:** "One of my safety checks was firing on two thirds of all
> tickets. It wasn't making the system safer — the violation count is zero with
> or without it — it was just refusing to answer things it could have answered."

---

## D-32 · The margin threshold, derived (O-3 closed)

**Tag:** `NUMBERS` · **Date:** 2026-09-07 · **Status:** Accepted · **Measured**

Swept over 200 development tickets at abstention floor 0.05.

> **Superseded by D-39.** The table below is the sweep against the *original*
> 56-term marker vocabulary. Two markers were removed later that day, which
> changed the curve, and `evaluation/results/2026-09-07-routing-200.txt` was
> regenerated — so the artifact no longer contains these figures. The decision
> (0.85, the last point before the cliff) survived the re-derivation; the numbers
> did not. **The shipped configuration's development FCR is 64.0% at 36.0%
> escalation**, per D-39 and the current artifact. This table is kept because it
> is what the choice was actually made on, and is marked rather than rewritten.

| margin | FCR | escalation | route acc | auto precision |
|---|---|---|---|---|
| ≤0.75 | 65.5% | 34.5% | 78.0% | 77.9% |
| 0.80 | 64.5% | 35.5% | 78.0% | 78.3% |
| **0.85** | **62.5%** | 37.5% | **79.0%** | **80.0%** |
| 0.90 | 8.0% | 92.0% | 48.5% | 93.8% ← cliff |

**0.85 chosen**: the last point before the cliff, best on both routing accuracy
and auto-respond precision, with FCR still clearing the 60% target. Marcus's
constraint — "I would rather it said nothing than said something wrong" — makes
precision the tie-breaker.

**What is not claimed:** 0.75 to 0.85 is a flat region, and the differences across
it are within the ±1.5 point run-to-run variance established in D-28. 0.85 is
defensible as the conservative end of a plateau, not as a measured optimum. This
is the same honesty applied to the relevance floor in D-20.

**The D-03 prediction held, and the margin is smaller than I first wrote.** §2.3
argued from the labels that maximum defensible automation was 65.2% FCR with an
escalation floor of 34.8%. At the **shipped** configuration (margin 0.85, current
vocabulary) the system reaches **64.0% FCR at 36.0% escalation** — within 1.2
points of the predicted ceiling.

I originally reported 65.5% / 34.5% here, "within 0.3 points". That is the
`≤0.60` row of the sweep — the configuration with the margin gate effectively
switched off, which is not what ships. Quoting the best row of a sweep as the
system's result is a way of being wrong that flatters the prediction, and it is
the more tempting error precisely because the agreement looks so good. The
ceiling analysis was still right; it was right by 1.2 points, not 0.3.

---

## D-33 · Config drift is now caught by the suite, not by review

**Tag:** `SYSTEM` · **Date:** 2026-09-07 · **Status:** Fixed

`.env.example` is not documentation. Build Spec §06 step 4 configures the graded
run from it, so it *is* the configuration that runs.

It drifted once and was caught in review: the template shipped `RELEVANCE_FLOOR=0.35`
while the derived, defended value was 0.40, and named a model the provider had
withdrawn. Deriving the margin threshold immediately produced a second instance —
the template said 0.80 against a derived 0.85.

`tests/test_env_template.py` now parses the template and asserts it matches every
derived constant, that no BOM is present, that credentials are placeholders, and
that the named model is non-empty. **The second drift was caught by the suite
within a minute of being created**, which is the difference between a guard and a
resolution.

> **Video line:** "The file the grader configures from had drifted from the values
> I'd derived. Twice. It's a test now, so it can't drift a third time."

---

## D-34 · Layer 3 is a precision control, not a safety layer

**Tag:** `GOVERNANCE` · **Date:** 2026-09-07 · **Status:** Reclassified · **Measured**

Over 200 development tickets the abstention control caught **zero** deny-listed
tickets that the other layers missed — the violation count is 0 at every floor
including `off`. So it buys no governance protection on this data. What it does
buy is measurable: **+1.5pt routing accuracy and +2.9pt auto-respond precision**.

**It therefore moves out of D-04's safety argument and into D2's conjunction**,
justified by Marcus's constraint — "I would rather it said nothing than said
something wrong" — which those precision numbers directly serve. D-04 honestly
has **two** classifier-independent safety layers plus grounding, not three.

**Why it stays.** The review argued layer 2's recall collapses on the less
templated split (77% dev → 50% validation) and that the 5-fold CV could not see
it, because every fold comes from the same templated corpus. That last point is
correct and important — it is D-23's warning applied to a safety control.

But the aggregate hides where the loss falls. Measured per intent:

| Intent | dev | validation |
|---|---|---|
| `security_incident` | 26/26 | **4/4** |
| `compliance_request` | 26/26 | **1/1** |
| `feature_request`, `unclear_request` | partial | poor |

**Layer 2 holds at 100% on both groundable intents on both splits.** The
aggregate drop is confined to the two intents that cannot ground and are
protected structurally regardless. Validation n is 4 and 1, so this is thin
evidence and is reported as such — but it does not support "layer 2 is weakened
where it matters".

> **Video line:** "One of my safety layers turned out not to be a safety layer.
> It caught nothing the others missed. It stays because it makes the system more
> precise, which is a different argument, and I made the different argument."

---

## D-35 · The margin threshold is a deliberate trade, not a plateau

**Tag:** `NUMBERS` · **Date:** 2026-09-07 · **Status:** Corrected

D-32 described 0.85 as "the conservative end of a plateau". That was wrong, and
in the opposite direction to the relevance floor error. The real shape:

| margin | FCR | route acc | auto precision | |
|---|---|---|---|---|
| 0.00–0.75 | 70.0% | 76.5% | 75.0% | **identical rows — margin never binds** |
| 0.80 | 69.0% | 76.5% | 75.4% | already descending |
| **0.85** | **64.5%** | 77.0% | **77.5%** | shipped |

> **Superseded by D-39**, like D-32's table: this sweep predates the removal of
> two markers, which changed the curve. The shipped configuration's development
> FCR is **64.0%** at 36.0% escalation. The choice of 0.85 survived the
> re-derivation; the figure did not.
| 0.90 | 8.0% | 48.5% | 93.8% | cliff |

The plateau is 0.00–0.75. **0.85 is mid-slope**, and the cost from 0.75 is **5.5
points of FCR** — well outside the ±1.5pt run variance, so "within noise" is true
of routing accuracy but false of first contact resolution, which is a business
target.

**The honest claim:** a deliberate trade of 5.5pt coverage for 2.5pt auto
precision, justified by Marcus's constraint, and affordable because FCR still
clears the 60% target with headroom. That survives "why not 0.80?"; "conservative
end of a plateau" does not, because the table plainly shows 0.80 is flatter and
cheaper.

---

## D-36 · Calibration sits on the governance boundary and sometimes fails

**Tag:** `NUMBERS` · **Date:** 2026-09-07 · **Status:** Reported as a failed condition

Four cold runs of 100 development tickets, identical inputs:

| run | accuracy | ECE | condition (≤5%) |
|---|---|---|---|
| 1 | 89.0% | 3.2% | passes |
| 2 | 86.0% | 6.0% | **fails** |
| 3 | 87.0% | 5.2% | **fails** |
| 4 | 90.0% | 2.5% | passes |

**Two of four runs fail the governance condition.** The cause is specific and
worth naming: the model is systematically overconfident by roughly 4 points in
the 0.80–1.00 band, where 99 of 100 predictions land.

**This is reported as a named failed condition with its cause, not a footnote.**
The Submission Guide is explicit that a report saying "this was worse than we
targeted, and here is what caused it" marks above one that omits the figure.

**It is also the justification for the architecture.** Confidence fails
calibration — which is precisely why D-29 routes on margin rather than
confidence, and why D2's conjunction leans on grounding and the deny-list. The
failed condition is the evidence for the design, not a defect in it.

I reported this as passing at 3.2% in a summary; that figure came from the
superseded cached run. The correction is D-30's lesson repeating.

---

## D-37 · Artifacts now carry their own provenance

**Tag:** `NEXT` · **Date:** 2026-09-07 · **Status:** Fixed

Three committed evidence files disagreed with what shipped: throughput measured
over a warm cache (D-30), routing swept around 0.80 after 0.85 was adopted, and a
marker-vocabulary file describing the 61-token derived list rather than the 56
curated terms that ship.

Build Spec §06 step 9 opens the metrics report and the decision log and
reconciles them against each other, so an assessor spot-checking an artifact
against the code must find them agreeing.

**Every evaluation script now prints a provenance banner** — timestamp, commit,
provider, model, and all three thresholds — so a stale artifact is obvious rather
than plausible. The rejected-vocabulary file is renamed to say so in its filename
and its first line.

**A near-miss worth recording.** Reverting `derive_markers.py` from git undid an
earlier fix, and re-running it **overwrote the shipped `src/markers.json` with the
vocabulary D-27 had rejected**. The swap is silent: the router still loads a
vocabulary and every other test still passes, but the safety control becomes the
one that fires on the word "only". Three tests now guard it — provenance in the
file, absence of the generic tokens, and presence of the security and compliance
terms.

**Separately, latency is now reported twice**, as design §5 committed. Processing
latency answers the p95 < 3s target; wall clock including token-allowance pacing
answers the gate's "reasonable time". They diverge sharply: **p95 0.84s
processing against 304s total wall clock, of which 250s is pacing** — measured on
the 100-ticket *classification-only* run
(`evaluation/results/2026-09-07-classifier-100-cold.txt`), not on a full pipeline
run. Reporting only the first hides the run duration; only the second fails a
target it was never measuring.

> **Later correction (D-45).** This separation was not as clean as it looks here.
> Pacing sleeps happen *inside* `process()`, so they were still landing in the
> per-ticket "processing" figure on full runs: the 8 Sep cold run reported a p95
> of 9.99s of which 74% was waiting. The harness now measures provider wait per
> ticket and reports the p95 both ways. The principle was right; the
> implementation only separated the two at the run level, not the ticket level.

---

## D-38 · The first gate run failed, and the cause was my own pacing

**Tag:** `DEMO` · **Date:** 2026-09-07 · **Status:** Fixed · **Found by running it**

The first unattended run over the 80-ticket validation set was killed at 90
minutes having processed **25 tickets** — 3.6 minutes each. That is an A9 failure,
and it is exactly the failure the Build Spec warns about: "Systems that work
beautifully on a ticket at a time frequently collapse on the fortieth consecutive
ticket."

**The cause was the rate-limit pacing I had added to fix the previous
rate-limit problem.** Measured directly against the provider:

```
classify  544 tokens   remaining 7231   reset  5.8s
generate  681 tokens   remaining 6703   reset  9.7s
...                    remaining 3853   reset 31.1s
```

`reset` is **time until the bucket is full**, and it grows as the bucket empties.
Deficit ÷ reset is constant at **0.0075 s/token = 133 tokens/second**, which is
the 8000-per-minute limit. The bucket refills *continuously*.

My pacing slept the **entire reset window** whenever the allowance fell below a
fixed floor — so it would sleep up to a minute to buy a few hundred tokens, then
clear its state, make one call, and sleep again.

**The fix is to wait for the shortfall, not for a full bucket:**

```
rate      = (limit − remaining) / reset        # derived, not assumed
shortfall = needed − remaining
wait      = shortfall / rate                   # capped at 65s
```

At ~1,225 tokens per ticket against 8000 TPM, the sustainable rate is **6.5
tickets a minute**, so 80 tickets should take about **12 minutes** rather than
the 4.8 hours the first attempt was on course for.

**A second pass was needed.** Proportional waiting took it from 3.6 minutes a
ticket to 40 seconds — better, still four times slower than theory. The remaining
cause was the estimate: reserving `prompt + max_tokens` budgets 1,200 tokens for
a classification call that costs **544**, so every wait was for roughly twice
what was required. The response carries `usage.total_tokens`, so the client now
paces against a moving average of what calls **actually** cost rather than
against a guess. Two guesses replaced by two measurements: the refill rate from
the headers, the call cost from the usage figures.

The rate is derived from the headers rather than hardcoded, so a changed limit
changes the pacing without a code change. The wait is capped because A9 forbids
any single response from being able to stall an unattended run.

**Why this only appeared at the gate.** Every earlier measurement ran 100 tickets
of *classification only* — about half the tokens per ticket, and enough headroom
that the bad path rarely triggered. Adding generation roughly doubled the token
cost per ticket and pushed the allowance below the floor on nearly every call.
The Build Spec's advice to run the full chain end to end early in week two is
precisely this: the defect is invisible until the whole pipeline runs at volume.

> **Video line:** "My first full run did twenty-five tickets in ninety minutes. The
> bug was in the fix I'd written for the previous rate-limit problem — I was
> sleeping until the token bucket was completely full when I only needed a few
> hundred tokens. It refills continuously, and the header tells you the rate if
> you do the arithmetic."

---

## D-39 · Two markers were costing coverage and buying no safety

**Tag:** `NUMBERS` · **Date:** 2026-09-07 · **Status:** Fixed · **Measured**

The gate run missed the first contact resolution target (48.8% against 60%), and
"the splits diverge" was too passive an answer. *(That 48.8% came from the
validation run whose artifact was later overwritten — see report §7.2. It is kept
here because it is what prompted this investigation, but it is no longer citable
as a result.)* Diagnosing it on the development
set found a real defect of my own.

Per-marker cost and benefit across all 500 development tickets:

| marker | deny-listed tickets caught | false escalations | groundable catches |
|---|---|---|---|
| `audit` | 22 | 0 | 22 |
| `retention` | 24 | 0 | 14 |
| `breach` | 10 | 0 | 10 |
| **`planned`** | **0** | **5** | 0 |
| **`request`** | 2 | **6** | **0** |

`planned` caught **nothing at all** while causing five false escalations.
`request` caught two — neither of them groundable, so both were already protected
structurally — while causing six. Both are generic English that happens to
correlate with deny-list templates, which is exactly the argument D-27 used to
reject `only`, `call` and `nobody` from the derived vocabulary. I let two through
under a curated label.

**Removing them saves 11 false escalations with no loss of safety whatsoever:**

| | before | after |
|---|---|---|
| false escalations (dev) | 25 | **14** |
| deny-list recall | 67/87 | **67/87 — unchanged** |
| `security_incident` | 26/26 | **26/26** |
| `compliance_request` | 26/26 | **26/26** |

Development FCR rises from 62.5% to **64.0%**, with governance violations still
zero at every threshold.

**A second finding: the parameters interact.** The margin sweep had to be re-run,
because the previous derivation was against the old vocabulary. The curve
changed shape:

| margin | FCR | route acc | auto precision |
|---|---|---|---|
| ≤0.60 | 65.5% | 78.0% | 77.9% |
| 0.70–0.75 | 64.5% | 78.0% | 78.3% |
| 0.80–0.85 | 64.0% | 77.5% | 78.1% |
| 0.90 | 8.0% | 46.5% | 81.2% (cliff) |

0.70 to 0.85 now spans 0.5 points on every measure — inside the ±1.5 point
run-to-run variance established in D-28. **So it is now genuinely a plateau, and
0.85 is the conservative end of it before the cliff at 0.90.** D-35 corrected me
for calling it a plateau when it was a slope; after this fix the description has
become accurate, which is a coincidence worth stating rather than quietly
enjoying.

**What this does not fix.** Development FCR of 64.0% is against a development
label ceiling of 62.2% auto-respond — so on that split we are effectively at the
ceiling. Validation's ceiling is 60%, and the gate measured 48.8% at the time
(artifact since overwritten; §7.2). The remaining
gap is on validation, and it will not be chased: the Project Brief forbids tuning
against it, and the hidden set is drawn from its population. Fixes are derived
from development evidence only, and validation is re-measured once at the end.

> **Video line:** "The system missed its resolution target, and my first instinct
> was to blame the data. Two of my own safety markers turned out to be costing
> eleven escalations and catching nothing. One of them was the word 'planned'."

---

## D-40 · There is a daily token budget, and the headers do not mention it

**Tag:** `SYSTEM` · **Date:** 2026-09-08 · **Status:** Fixed · **Found by running out of it**

The cold gate run stalled at 64 of 80 tickets. Instrumenting eight tickets showed
where the time went:

```
34 calls attempted, 2 succeeded, 10 failed, 22 retries
995 seconds of sleep, of which 0 seconds was pacing
```

The pacing was not firing — the allowance looked healthy at 7,484 of 8,000
tokens. All the sleep came from retry backoff, so calls were *failing*. Capturing
the response body gave the reason:

```
Rate limit reached ... on tokens per day (TPD): Limit 200000, Used 199919
retry-after: 204
x-ratelimit-remaining-tokens: 8000     <- the per-minute bucket, completely full
```

**There is a 200,000 tokens-per-day cap, and it appears only in the body of the
429.** Every rate-limit header describes the per-minute bucket, which was full.
The pacing logic was watching the right numbers for the wrong limit.

**Three consequences.**

**1. Retrying a daily cap is pointless and expensive.** The reset is hours away,
not seconds, so each retry slept three to five minutes and failed again. A daily
exhaustion is now terminal within a run: the first one marks the client
exhausted, every later call short-circuits without attempting, and the run
degrades to retrieval-only. The same eight tickets that took 995 seconds of sleep
now complete in **6.6 seconds**, with the report correctly flagged `DEGRADED` and
its business rates withheld.

**2. The budget is roughly 163 tickets a day, in total.** *(Superseded by D-45: measured at 652 tokens per call and 1.64 calls per ticket, the real figure is ~187 a day. The estimate below predates any measured run and is kept because it is what the day's decisions were made on.)* At ~1,225 tokens a
ticket, 200,000 tokens covers about 163 — across *all* runs that day, not per
run. The hidden 120-ticket run fits comfortably, but only if the day's budget has
not already been spent. I spent this day's on repeated gate runs while debugging
the pacing, which is worth stating rather than hiding: the constraint is real and
it shaped the schedule.

**3. The cache is now load-bearing three times over.** D-28 established it
provides A5's determinism, since the provider is not deterministic at temperature
zero. D-38 showed it is what makes repeat runs affordable. This adds that it is
what makes the daily budget survivable at all. It is not an optimisation.

**Documented for the grader**, because they will hit it too: a second full run in
the same day may exhaust the budget, and the system will then degrade to
retrieval-only rather than fail — which is the designed behaviour, and the report
will say so plainly.

> **Video line:** "The provider has a daily budget that none of its rate-limit
> headers mention. My system was watching the per-minute allowance, seeing it
> full, and retrying into a limit that resets tomorrow. Now it recognises it,
> stops, and finishes the run in retrieval-only mode in six seconds instead of
> stretching overnight."

---

## D-41 · The decision log is persistent, so reconciliation is scoped to a run

**Tag:** `GOVERNANCE` · **Date:** 2026-09-08 · **Status:** Fixed

Running the harness twice failed A8: the second run reported
`log reconciles: False`, naming the first run's tickets as "logged but not
processed".

Both halves of that are correct behaviour in tension. The log *should* accumulate
across runs — the Governance Framework wants decisions reconstructable months
later — and reconciliation *should* check identity in both directions, which is
what catches a log written only for the tickets that succeeded.

Every record now carries a `run_id`, and A8 reconciles within the run. Two
consecutive runs against the same file now both report `log reconciles: True`,
the history is preserved, and a second terminal state within one run is still
rejected.

Worth noting how this was found: not by a test, but by running the harness twice
in a row because the first run had exhausted the token budget. A grader may well
do the same thing.

---

## D-42 · The fairness baseline is not flat, and its ordering inverts between splits

**Tag:** `NUMBERS` · **Date:** 2026-09-08 · **Status:** Confirmed · **Measured**

The Governance Framework asks for variation across customer groups to stay under
five percentage points. The obvious reading is to measure the system's rate per
segment and check the spread. Measured against the *labels alone*, before any
system exists:

| segment | dev spread | validation spread |
|---|---|---|
| `customer_region` | **14.4pt** | **28.6pt** |
| `ticket_length` | 7.6pt | — |
| `language_fluency` | 5.9pt | **23.5pt** |
| `customer_tier` | 3.8pt | — |

**Three of four segments already exceed the governance condition in the labels
themselves.** A system that mirrored the labels perfectly would be reported as
biased. So measuring system output against an assumed-flat baseline does not
measure fairness — it measures the data's structure.

**Worse, the ordering inverts between splits:**

| | dev | validation |
|---|---|---|
| non-fluent vs fluent | 66.7% vs 60.8% — *better* | 42.1% vs 65.6% — 23.5pt *worse* |
| `asia_pacific` | 53.8%, the **lowest** region | 71.4%, the **highest** region |

There is no stable per-segment baseline in this data. A fairness claim measured
on development would be not merely imprecise on validation but **backwards**.

This is precisely why design section 2.4 pre-registered the method as *system
outcome minus the same split's label baseline*, fixed before any result was
known. That decision was made defensively after the validator caught me
generalising a dev-only result; this measurement shows it was necessary rather
than cautious.

**Consequence for the report:** the fairness audit reports a delta against the
split it was measured on, states the baseline alongside it, and does not
generalise across splits. Segments with fewer than ten tickets are reported with
their interval and labelled as unable to support inference — validation has seven
`latin_america` tickets, whose 95% interval spans 16% to 75% on the label baseline (and 3% to 51% on the system rate, which is the figure the audit now prints beside a delta — see D-46).

> **Video line:** "The framework asks whether some customers get worse answers,
> and says the gap should be under five points. In this data three of the four
> groupings are already further apart than that in the labels — before my system
> touches anything. And on the other split the ordering flips: the region that
> does worst on one is the region that does best on the other."

---

## D-43 · The clean-checkout rehearsal (A1) passes, with one Windows caveat

**Tag:** `DEMO` · **Date:** 2026-09-08 · **Status:** Verified

The Build Specification's test procedure was run against this repository, in
order, from a clone into an empty directory. Roughly half of submissions are said
to fail at step two.

| Step | Result |
|---|---|
| 1. Clone into an empty directory | ✅ |
| 2. Follow the README literally | ✅ |
| 3. Create the environment and install | ✅ **2m48s**, no torch |
| 4. Configure from `.env.example` | ✅ |
| 5. Run the tests | ✅ **355 passed, 14 skipped, no API key needed** |
| 6. Run the harness | ✅ 8/8 processed in 6.0s, all three output files written, log reconciles |

The 14 skips are the tests requiring the full development and validation sets,
which are deliberately not committed. They skip cleanly rather than failing, so
the suite stays meaningful on a checkout that has only the sample data.

**The one real finding: Windows `MAX_PATH`.** `onnxruntime` nests files about 120
characters deep, and Windows still enforces a 260-character limit by default. The
first rehearsal — at a checkout path of 113 characters — failed partway through
`pip install`:

```
OSError: [Errno 2] No such file or directory:
'...\onnxruntime	ools\ort_format_model\ort_flatbuffers_pybs\...'
```

Re-run at a 14-character path, the same install succeeded in 2m48s. This is
documented at the top of the README with both remedies, because a grader on
Windows could hit it and the error message does not obviously point at the cause.

**Worth noting what this rehearsal did *not* find**, because that is the point of
doing it: no missing step, no undocumented dependency, no path that existed only
on my machine, and no test that needed credentials. The suite passing without an
API key was a deliberate design choice on day one, and this is where it paid.

> **Video line:** "I cloned my own repository into an empty folder and followed
> my own README. It worked — except on Windows, where a deeply nested dependency
> hits the old 260-character path limit. That is in the README now, with the fix."

---

## D-44 · The fairness audit refuses to run on a degraded run

**Tag:** `GOVERNANCE` · **Date:** 2026-09-08 · **Status:** Implemented

I pointed the fairness audit at a degraded run's outcomes and every one of the
eleven segments came back negative: −42.9pt (asia_pacific), −37.5pt (enterprise),
−34.1pt (short tickets), down to −5.3pt (non_fluent). It closed with
`VERDICT: EXCEEDED — investigate`.

Read at face value that is a system biased against every customer group at once,
which is not a coherent claim; the uniform sign is the tell. The run had lost its
provider partway, so every ticket after that point escalated regardless of
content, which drags each segment's system rate down together. The audit was
measuring the outage, not fairness.

Verbatim output, under the new `--allow-degraded` flag, is committed at
[`evaluation/results/2026-09-08-fairness-degraded-run-INSPECTION-ONLY.txt`](../evaluation/results/2026-09-08-fairness-degraded-run-INSPECTION-ONLY.txt).
I originally paraphrased that table into this entry from memory and got its range
wrong — writing "−37 to −43" when the real spread was −5.3 to −42.9. The validator
caught it. Reconstructing a transcript inside a code fence is the same defect as
the one this entry is about, committed in the act of describing it, so the fence
is gone and the artifact is linked instead.

This is the same error class as D-30, where I committed a throughput figure that
turned out to be a cache replay. Both are cases of a number that is arithmetically
correct and evidentially worthless, and in both cases the defence is the same: the
tool that produces the number has to know when its input cannot support it.

`scripts/fairness_audit.py` now reads `metrics.json` alongside `outcomes.json` and
refuses to publish per-segment deltas when the run is marked `degraded` or
`distribution_collapsed`. It still prints the label baselines, which need no run
and are always valid. Four further holes closed during review:

| Hole | Why it mattered |
|---|---|
| No metrics file → guard silently skipped | Copying `outcomes.json` to the dated-evidence convention removed the guard. A guard `cp` can silence is not a guard; a missing metrics file is now itself a refusal, with `--no-metrics` to override. |
| `--allow-degraded` printed a clean-looking report | Redirected to a file it was indistinguishable from a real result. It now carries a `DEGRADED RUN — NOT A FAIRNESS RESULT` banner and emits **no verdict at all**. |
| Small-n caveat suppressed exactly when deltas showed | `enterprise` (n=8) printed `−37.5pt` with no interval — and that is the figure this entry quotes. The caveat is now unconditional. |
| Baseline and system rates could span different tickets | A partial run compared a 23-ticket system rate against a 30-ticket baseline and reported the gap between two populations as bias. The baseline now narrows to the covered tickets. |

A **cache replay is explicitly allowed** — the outcomes in a replay are real
routing decisions; what a replay cannot support is a *timing* claim (D-30), and
this audit makes none. That distinction is now pinned by a test rather than left
to a comment: `tests/test_fairness_audit.py`, 15 cases.

Recorded refusal: [`evaluation/results/2026-09-08-fairness-degraded-run-refused.txt`](../evaluation/results/2026-09-08-fairness-degraded-run-refused.txt).

The alternative was to fix it by hand — note the caveat in the report and move on.
That works exactly once, for the person who already knows. The guard works for
whoever runs it next.

> **Video line:** "My fairness audit told me the system was biased against every
> single customer group at once. That is not bias, that is an outage — the run
> had lost its provider halfway through and escalated everything after that. So
> the audit now refuses to report fairness numbers from a degraded run at all."

---

## D-45 · A successful preflight call does not mean a run will fit

**Tag:** `NUMBERS` · **Date:** 2026-09-08 · **Status:** Implemented

The third gate run died the same death as the second, and the cause was my own
reasoning rather than the provider.

`scripts/check_env.py` made a full-sized 700-token live call. It succeeded. I
read that as "the daily budget has reset" and started a cold 80-ticket run. It
stopped at **VAL-0054** — 54 of 80 — with `provider quota exhausted`, having
spent 47,774 tokens. The remaining 26 tickets escalated with no model call, the
run was correctly marked degraded, and its business rates were correctly
withheld. Every control behaved; the decision to start was wrong.

**The reasoning error is worth naming precisely.** A successful call proves that
*one call* fits. It says nothing about eighty. The provider publishes a
per-minute remaining figure in response headers and **no daily figure anywhere** —
the daily cap surfaces only in the body of a 429 (D-40). So "will this run fit?"
is a question the provider will not answer, and I answered it by analogy from a
single probe.

The compounding factor was the reset boundary. It is 00:00 **UTC**, which is
05:30 local. The degraded run at 12:35 UTC and the cold run at 18:00 UTC were the
*same allowance*, and it did not feel that way at 23:30 in the evening.

**What was built.** `src/token_budget.py` keeps a per-UTC-day ledger of measured
spend, summed from the provider's own `usage.total_tokens` — which the client was
already receiving and discarding. The harness records each run's cost; the
preflight reads it before spending anything, and now refuses to probe at all when
a run cannot fit:

```
  UTC day             : 2026-09-08 (resets at 00:00 UTC)
  recorded spend      : 47,774 of 200,000 tokens
  remaining (local)   : 0
  EXHAUSTED           : a run today was refused with 'quota exhausted'. Wait for 00:00 UTC.
  a 128,313-token run  : DOES NOT FIT
  This ledger counts only what this machine recorded. It can rule a run out; it cannot promise one will complete.
```

*(Verbatim, from `TokenLedger().view(day='2026-09-08').explain(128313)`. I first
printed an abbreviated version of this block here with a 104,490-token estimate —
120 × 1.35 × 645, the repudiated multiplier this very entry goes on to retract,
inside a reconstructed transcript, which is the defect D-44 was corrected for in
the same commit. Twice in two entries. The ledger itself lives in `storage/`,
which is gitignored because it is machine-local state, so it is quoted here
rather than committed.)*

Two design points matter more than the arithmetic:

1. **The ledger is asymmetric on purpose.** It may rule a run *out*; it may never
   promise one will complete. It cannot see spend from another machine, another
   key, or a run that died before recording, so its count is always a floor. The
   success message says "one call fits", not "you are good to go" — the exact
   sentence that caused this.
2. **A 429 outranks the ledger's own arithmetic.** The cold run recorded 47,774
   tokens — 24% of the cap — and was refused anyway, because earlier runs that
   day had spent the rest without recording it. When the provider says the day is
   over, that fact is stored and wins over the sum. `test_token_budget.py` pins
   this as its central case.

**The measured cost, at last.** A fully processed ticket costs one classification
plus, for every ticket that produces a draft, one generation — so **1 + FCR**
calls per ticket, 1.64 at the shipped configuration's 64.0%
(`2026-09-07-routing-200.txt`, margin 0.85). Per call, the two healthy runs of 10
September measured 648.2 and 651.5, so the constant is **652** — the more
expensive of them, rounded up. **120 tickets ≈ 128,000 tokens, about two thirds
of the daily cap.**

The first version of this used 646, taken from the *degraded* 8 September run.
By the time a healthy run existed that had become five tokens per call
**optimistic** — the wrong side for a number feeding a gate — and the test pinned
it there with an equality against the degraded artifact, so nothing would have
noticed. The test is now directional ( the maximum across healthy runs) and
refuses to derive the estimate from a run marked degraded at all.

I first published 1.35 calls per ticket, taken from the cold run's own
auto-respond rate of 33.75%. That was wrong in an instructive way: 26 of that
run's 80 tickets never reached the model, so the rate was depressed *by the very
failure the estimate is meant to prevent*. A degraded run made the next run look
cheap. The validator caught it; the multiplier now comes from a healthy artifact,
and `estimated_run_cost` documents that it returns the pessimistic end on purpose,
because an optimistic estimate makes the gate wave through exactly the run it
exists to stop.

The README previously stated 94,000–106,000 from an estimate, and D-40 implied
~147,000 from a different one; neither was measured, and they could not both be
right. Both inputs here remain floors — errored calls are billed but uncounted,
and generation calls are larger than classification ones.

> **Video line:** "My preflight check made a real API call, it succeeded, and I
> took that as permission to start. The run died two thirds of the way through:
> one call fitting tells you nothing about eighty fitting. So I stopped asking
> the provider a question it doesn't answer, and started keeping my own ledger."

---

## D-46 · The fairness condition fails, and the failure is specific

**Tag:** `GOVERNANCE` · **Date:** 2026-09-10 · **Status:** Reported, not fixed

The first validation run that did not degrade finally allowed the fairness audit
to produce a result. It fails the five-point condition, at −38.1 points.

Both healthy runs, so the stability is visible:

| Segment | n | Baseline | Run 1 | Run 2 | Discordant (run 2) | p | Holm |
|---|---|---|---|---|---|---|---|
| `asia_pacific` | 21 | 71.4% | −38.1pt | **−38.1pt** | 10 / 2 | 0.039 | 0.424 |
| `north_america` | 27 | 51.9% | +7.4pt | +14.8pt | 2 / 6 | 0.289 | 1.000 |
| `europe` | 25 | 64.0% | +12.0pt | +12.0pt | 2 / 5 | 0.453 | 1.000 |
| `short` tickets | 44 | 65.9% | −15.9pt | −11.4pt | 8 / 3 | 0.227 | 1.000 |
| `fluent` | 61 | 65.6% | −9.8pt | −6.6pt | 12 / 8 | 0.503 | 1.000 |
| `long` tickets | 36 | 52.8% | +5.6pt | +5.6pt | 8 / 10 | 0.815 | 1.000 |
| `non_fluent` | 19 | 42.1% | +5.3pt | +5.3pt | 4 / 5 | 1.000 | 1.000 |
| `standard` | 42 | 50.0% | −4.8pt | −4.8pt | 9 / 7 | 0.804 | 1.000 |
| `business` | 30 | 70.0% | +0.0pt | +3.3pt | 5 / 6 | 1.000 | 1.000 |

(`latin_america` n=7 and `enterprise` n=8 also exceed, are flagged by the tool as
too small to support an inference, and are excluded from the verdict.)

Evidence: `evaluation/results/2026-09-10-fairness-validation.txt`, which is **run
2** (`…gate-run-2/`). An earlier version of this entry printed run 1's figures
under that pointer — four of seven rows would not have reproduced for anyone who
followed it. The run each column comes from is now named.

**The mixed signs are the thing to notice.** Two days earlier the same tool,
pointed at a degraded run, produced eleven deltas that were *all* negative — the
signature of an outage, where everything escalates and every segment falls
together. D-44 built a refusal control on exactly that distinction. This is the
first time both patterns have been observed with the same code, and they do not
resemble each other: a real measurement has segments on both sides of their
baseline. The control was worth building.

**The substantive gap is regional, and it is not one I predicted.** `asia_pacific`
has the *highest* label baseline of any region on this split (71.4%) and receives
the *lowest* service (33.3%). Two hypotheses are worth separating on development
data: the corpus may cover that segment's intents less well, which per-segment
retrieval scores would show; or the classifier may be less accurate on its
phrasing, which per-segment accuracy would show. Both are measurable without
touching validation.

**A correction to how I first wrote this up.** The entry originally called
`asia_pacific` "well powered (n=21)" and presented `europe +12.0pt` as a
contrasting signal. The validator asked for a paired test, and it was right to.
The system's decision and the label are made on the same ticket, so the rates are
paired and only discordant tickets carry information; `asia_pacific` is 10 vs 2,
exact p = 0.039, and `europe` is 2 vs 5, p = 0.45. **Eleven segments were tested
at once, and after Holm correction nothing survives at 0.05** — `asia_pacific`
adjusts to 0.424. Quoting the smallest of eleven p-values as a finding is how a
table like this manufactures one, and I had done it.

The audit now computes and prints the discordant split, an exact paired p, and
the Holm-adjusted p for every segment, and states in its own output that the
verdict is on the *condition* — which is in percentage points and is missed as
measured — and not a claim about any individual segment.

**What survives the correction is a lead, and it is a real one.** The
`asia_pacific` gap is **identical in two independent cold runs**, −38.1 points
from the same 10/2 split each time.

I first wrote that this made it distinctive, "while other segments moved by up to
3 points". That is false, and the table above refutes it: **six of the eleven
segments are identical between the two runs**, `asia_pacific` among them, and the
largest movement is `north_america` at 7.4 points (`enterprise`, at n=8, moved
12.5). Stability is the norm here — both runs route the same 80 tickets and only a
handful of decisions differ — so reproducibility is much weaker evidence than I
made it sound.

What is left is the largest gap in the table, at the largest n of any exceeding
segment, stable across two runs, and not surviving correction. That is a **lead,
not a result**: a reason to go and measure properly where there are 500 tickets
rather than 21.

**Not fixed here, deliberately.** The Project Brief forbids tuning against
validation, and the hidden set is drawn from the same population — so a fix
derived from this table would be both a rule violation and self-defeating. It is
carried into report §10.2 as the first thing to investigate.

**And Sofia's hypothesis is not refuted — it is undetectable here.** She believed
non-fluent English tickets were being handled worse. `non_fluent` measures +5.3pt,
nominally *better* than its baseline, but on a 4 vs 5 discordant split: p = 1.00.
Nineteen tickets cannot answer her question in either direction.

I first wrote that the run "contradicted" her. It does not, and the difference
matters: a stakeholder who raises a fairness concern and is told the data refutes
it has been given a stronger answer than the data can support. The audit exists
partly because she raised this, and what it can honestly say is that the effect
she describes is not detectable at nineteen tickets — which is an argument for
measuring it on live traffic, not for closing the question.

> **Video line:** "The fairness audit ran on a healthy run and the condition
> failed — Asia-Pacific tickets get answered a third of the time where the labels
> say seventy percent are answerable. Then I tested it properly: eleven segments,
> paired test, Holm correction. Nothing survives. So what I have is a gap that
> reproduces exactly across two runs and still is not statistically established —
> which makes it a lead to go and measure, not a headline to publish."

---

## D-47 · Four blocked drafts were reported as zero blocks

**Tag:** `GOVERNANCE` · **Date:** 2026-09-10 · **Status:** Fixed · **Measured**

The 10 September gate run reported `blocked_by_guardrails: 0` and
`guardrail_activations: {}`. Four drafts had been generated and withheld.

**The mechanism.** `Generator` returns an answer with `is_answerable == False`
when no citation marker in the draft resolves to a retrieved passage.
`Pipeline._validate` checked that first and short-circuited to
`ESCALATED_DIRECT` with an empty `blocked_by`, **without ever calling the
validator**. But `Validator._grounding`'s first condition is `if not
answer.citations` — the identical case. So that branch was unreachable from the
pipeline: it fires only when `citations` is empty, and reaching it required
`is_answerable`, which requires `citations` non-empty. Mutually exclusive.

Two things were wrong with that, and the second is worse than the first:

1. A draft that was produced and then withheld was counted as a ticket that never
   got as far as a draft. Those are different events and the Build Specification
   asks for them separately.
2. **A governance control was silently doing nothing.** The grounding guardrail
   had a branch that no production path could reach, so its activation count was
   structurally zero rather than observed to be zero. `deny_list` and
   `tone_and_scope` were unaffected, and the deny-list condition held throughout —
   but "zero activations" and "cannot activate" look identical in a report.

**Why the tests missed it.** `test_a_guardrail_block_produces_escalated_after_block`
covered `tone_and_scope`, which fires on drafts that *do* carry citations, so it
exercised the path that worked. The uncovered path was the one where the two
conditions were mutually exclusive, which no single-guardrail test would show.

**The fix is a deletion.** Every draft now goes to the validator and the validator
decides. One code path, one place where blocking happens, and the guardrail
records its own activation. Corrected counts for the re-run: **45 auto-answered,
35 escalated, of which 4 blocked and 31 escalated before a draft existed** —
against the 43 / 37 / 0 first published. Four tests now pin it, including one
that a grounded draft is *not* blocked, since a control that blocks everything
would also pass the other three.

**A third case, found by the same question.** Reviewing the fix, the validator
asked what else `_grounding` passes that it should not, and drove `"[1]"` through
the pipeline. It was **released to the customer**: the marker resolves to a real
passage, so grounding passed, and pii, instruction integrity, tone and confidence
have nothing to object to. A bracket and a link, counted as a first-contact
resolution with a citation. Grounding asked whether the citations resolve and
never asked whether the draft said anything.

Fixed inside `_grounding` rather than as a sixth guardrail, because FR-15
specifies five and "is there a grounded answer here" is the question all three of
its branches now ask: the citations resolve, they were actually given, and there
are at least 20 characters of prose outside the markers. Four tests, one of which
is the negative control — a short real answer citing `[1]` must still pass, or a
control that blocks everything would look identical.

**And one in the opposite direction.** `generate.py` tested `if
INSUFFICIENT_CONTEXT in text` — a substring — so a draft that merely *mentioned*
the token ("the passages give INSUFFICIENT_CONTEXT on your refund question") was
discarded, its text thrown away, and reported as "no draft was produced at all".
Same understatement of guardrail activations, opposite cause. Now `==`, which is
what the prompt asks for.

This is the second defect of its shape in this project. D-32's markers were
"present but buying nothing"; this was "present but unreachable". Both were found
by asking what a number would look like if the thing it counts could never
happen — and both times the answer was: exactly like the number I had.

> **Video line:** "My report said zero drafts were blocked by guardrails. Four
> were. The grounding check had a branch the pipeline could never reach, so it
> wasn't returning zero — it was structurally incapable of returning anything
> else. A control that cannot fire and a control that never needed to fire look
> the same in a report, and only one of them is good news."

---

## Open decisions

| # | Question | Due |
|---|---|---|
| ~~O-1~~ | ~~Chunking strategy~~ — resolved, see D-19 | ✅ Day 2 |
| ~~O-2~~ | ~~Relevance floor~~ — resolved, see D-20 | ✅ Day 2 |
| ~~O-5~~ | ~~Throughput budget~~ — 8000 TPM binding; 6.1 min/120 tickets for classification, see D-24 | ✅ Day 3 |
| ~~O-3~~ | ~~Confidence threshold~~ — resolved, see D-29 (margin, not confidence) | ✅ Day 3 |
| ~~O-4~~ | ~~Marker vocabulary~~ — resolved, see D-27 | ✅ Day 3 |
| O-6 | Incident procedure, six steps with owner and duration | Day 8 |
