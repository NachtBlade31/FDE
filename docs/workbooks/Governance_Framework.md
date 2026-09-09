# Governance Framework — completed

**Kshitiz Bhargava — CloudServe Solutions support system**

The Framework's own test of whether governance is real: *"Pick a plausible way
your system could harm a customer, and ask what in your design would stop it. If
the answer describes a property of the model rather than a control you built, you
have described a hope."*

Every control below names the file that implements it and the test that proves it
fires. Where a control is weaker than it first appears, that is stated rather than
smoothed over — one of them was rewritten mid-project for exactly that reason.

---

## 1. Decision logging

Implemented in `src/logging_store.py`. Every stage writes a record; the schema is
the Framework's minimum record in full.

| Field | Populated from | Why it matters here |
|---|---|---|
| `decision_id`, `created_at`, `ticket_id` | generated per record | identity |
| `stage` | one of ingest / classification / retrieval / routing / generation / validation | reconstructs the path a ticket took |
| `input_summary` | ticket subject and body | what was decided on |
| `model` name and version | resolved configuration | which model produced this |
| `prediction` value and confidence | classifier output | what it thought |
| **`alternatives`** | classifier top-k | what it *also* thought — read by the third safety layer |
| **`sources_used`** | retrieved passages with scores | what the answer stood on |
| `threshold_applied` | the routing margin in force | the decision rule at the time |
| `action_taken` | auto_respond / escalate / block | what happened |
| `reason` | generated sentence | **written for a support manager, not an engineer** |
| `guardrail_results` | all five checks, pass or fail | what was checked, not only what failed |
| **`prompt_version`** | e.g. `PR-01 v1.0` | answers "was this behaviour intended?" |
| **`requirement_ids`** | e.g. `["FR-08","FR-09"]` | traces a decision back to the requirement that asked for it |
| `run_id` | per harness run | see coverage below |

**Coverage check.** `DecisionLog.reconcile()` compares the set of logged ticket
ids against the set processed, **in both directions**, and asserts every ticket
reached exactly one terminal state.

Two things were learned building this.

*A count-based check is wrong.* An assertion of the form
`decisions == tickets × stages` fails on a correct run, because stage counts
legitimately vary — a deny-listed ticket terminates at routing and never reaches
generation. Reconciliation is by identity.

*The log outlives the run.* It accumulates across runs by design, which broke
reconciliation the first time the harness was run twice. Records now carry a
`run_id` and A8 reconciles within the run, so the history is preserved and the
check stays meaningful. A grader running it twice would have hit this.

---

## 2. Risk register

| ID | Risk | Likelihood | Impact | Mitigation **in the design** | Owner |
|---|---|---|---|---|---|
| **R-01** | The system answers confidently and incorrectly | High — 22 intent classes, and self-reported confidence proved non-discriminative | **Severe.** Marcus: customers are engineers who "will screenshot a confidently incorrect answer and put it on the internet within the hour" | Four conditions must *all* hold before any answer is sent: margin above threshold, intent not deny-listed, a retrieved passage above the relevance floor, and grounding validated. Citations are constructed from retrieved chunk ids, so the model cannot invent a reference. `src/route.py`, `src/generate.py` | Head of Support |
| **R-02** | Private data appears in an outbound response | Medium | **Unacceptable at any rate — the condition is zero** | The PII guardrail scans every response for emails, credential shapes and account numbers the customer did not themselves supply, and **blocks rather than redacts**: a redacted leak is a leak that was nearly sent. `src/guardrails.py` | Head of Support |
| **R-03** | A customer's input is treated as an instruction | Medium — the customers are engineers | Severe | Ticket text is never concatenated into the instructions; it travels as a separate message. The instruction-integrity guardrail independently checks both the input and the released text, and records the offending input for review. | Engineering |
| **R-04** | Some customer groups receive worse answers | High — and already true before the system existed | Severe at renewal | Every measure segmented by tier, region, fluency and ticket length, compared against **the same split's own label baseline**. See §3 — the baseline is not flat and its ordering inverts between splits. | Head of Support |
| **R-05** | The documentation the system relies on goes stale | Medium | Moderate, and silent | Answers cite the document they came from, so a wrong answer can be traced to either the article or the system — Ines's requirement. **Limitation stated:** `last_reviewed_days_ago` is 0 for all 29 articles, so staleness is undetectable in this data. The control is design-level (surface article age beside every citation), not measurable here. | Technical Writer |
| **R-06** | The model provider becomes unavailable | **High — it is a free tier, and it happened repeatedly during the build** | Moderate if handled | The run degrades to retrieval-only and completes: every ticket escalates with its retrieved context attached, which is still faster than today's 8–12 hour wait. The report is flagged `DEGRADED` and its business rates withheld. `src/pipeline.py`, `evaluation/harness.py` | Engineering |
| **R-07** | Latency degrades under load | Medium | Moderate — chat customers abandon | Processing latency and wall clock are reported separately, because token-allowance pacing makes them diverge sharply. On the 8 Sep cold run, 74% of measured per-ticket time (217.6s of 294.3s) was
the client asleep waiting for the free tier's token allowance: a raw mean of
3.68s against a work-only mean of 0.96s, both against a 3s target. The harness
now records provider wait per ticket and reports the figure both ways. | Engineering |
| **R-08** | Costs rise unexpectedly with volume | Low in money, **high in allowance** | Moderate | Free tier throughout. The binding constraint is 200,000 tokens/day ≈ 163 tickets — a limit that appears only in the error body, not the rate-limit headers. Exhaustion is detected and the run degrades rather than stalling. Cache hits and per-ticket call counts are reported. | Engineering |
| **R-09** | A security or compliance ticket is auto-answered | Medium — 17.4% of tickets and classification is imperfect | **Severe and non-recoverable** | Three independent layers plus grounding. **This one was rewritten mid-project** — see §4. | Head of Support |
| **R-10** | A broken run is mistaken for a conservative one | Medium | Severe — it corrupts the evaluation | A provider outage produces 100% escalation, which is indistinguishable in the output from a very cautious working system. Two independent detectors: the degraded flag, and distribution collapse measured from the predictions themselves. Business rates are withheld when either fires. | Engineering |
| **R-11** | Agents stop checking the system's drafts | Medium | Severe, and slow to notice | Every automated reply discloses that it was automated. Escalations state explicitly what the system was uncertain about rather than presenting a confident draft. | Head of Support |

---

## 3. Fairness audit

Implemented in `scripts/fairness_audit.py`. Method pre-registered before results
were known: **system auto-respond rate minus the same split's label baseline**,
per segment.

**Why not simply compare segments.** The labels are not flat, and a system that
mirrored them perfectly would be reported as biased:

| Segment | Dev label spread | Validation label spread |
|---|---|---|
| `customer_region` | **14.4pt** | **28.6pt** |
| `ticket_length` | 7.6pt | — |
| `language_fluency` | 5.9pt | **23.5pt** |
| `customer_tier` | 3.8pt | — |

Three of four segments already exceed the five-point condition **in the data
itself**, before any system exists.

**The ordering also inverts between splits:**

| | Development | Validation |
|---|---|---|
| non-fluent vs fluent | 66.7% vs 60.8% — *better* | 42.1% vs 65.6% — 23.5pt *worse* |
| `asia_pacific` | 53.8% — the **lowest** region | 71.4% — the **highest** region |

A fairness claim measured on one split would be **backwards** on the other. This
is the strongest argument for the pre-registered method, and it was found by
measurement rather than anticipated.

**Sample-size honesty.** Segments below ten tickets are reported with a 95%
Wilson interval and labelled as unable to support inference. Validation has seven
`latin_america` tickets, whose interval spans 16% to 75%. Until review this
caveat printed only when no run was supplied — so it was suppressed on precisely
the rows carrying a delta, including the `enterprise` figure (n=8) that a
decision entry went on to quote. It is now unconditional.

**The audit refuses to run on a run it cannot trust.** This is the control that
matters most in this section, and it exists because the audit got it wrong first.

Pointed at a run whose provider had failed partway, it returned eleven negative
deltas — −42.9pt (`asia_pacific`) through −5.3pt (`non_fluent`) — and the verdict
`EXCEEDED — investigate`. That reads as a system biased against every customer
group at once. It was not: a run that loses its provider escalates everything it
cannot classify, which pulls all segments down together. The audit was measuring
an outage and reporting it as discrimination — and because the numbers were
uniformly negative and individually plausible, nothing about the output looked
wrong.

`scripts/fairness_audit.py` therefore reads the run's `metrics.json` and:

| Condition | Behaviour |
|---|---|
| `degraded` or `distribution_collapsed` | **Refuses** to publish per-segment deltas |
| No `metrics.json` found beside the outcomes | **Refuses** — a guard a file copy can silence is not a guard. `--metrics PATH` or `--no-metrics` to override explicitly |
| `cache_replay` | **Proceeds.** Replayed outcomes are real routing decisions; only a *timing* claim needs live calls (D-30), and this audit makes none |
| `--allow-degraded` | Proceeds for inspection, under a `DEGRADED RUN — NOT A FAIRNESS RESULT` banner, and emits **no verdict** |

In every refusing case it still prints the label baselines, which need no run and
are always valid. The behaviour is pinned by `tests/test_fairness_audit.py`
(15 cases) rather than by convention, because it is a governance control whose
failure mode is a confident false finding about protected groups.

Full reasoning: **D-44**. Recorded refusal:
`evaluation/results/2026-09-08-fairness-degraded-run-refused.txt`.

**What Sofia said.** She believed non-fluent English tickets were handled worse
and that nobody had noticed. She is right on validation and wrong on development
— which means she identified a real risk that the development data would have
told us was not there.

---

## 4. Guardrails

Five checks run on **every** response, in production, and every one can block.
There is no flag that disables any of them — a test asserts the constructor
signature contains no such parameter, because Build Spec §08 names
"guardrails present in the code but disabled by a flag during the run" as a
failure.

| Guardrail | What it checks | What happens when it fires |
|---|---|---|
| **Private data** | Emails, credential shapes, account numbers not supplied by the customer themselves | Block and escalate. **Never redact and send.** Nothing at all is released |
| **Grounding** | Every citation resolves to a passage that was actually retrieved | Block and escalate, with the unresolvable reference named |
| **Instruction integrity** | The ticket has not redirected the system, and the response does not echo the instructions | Block, escalate, and **record the input for review** |
| **Tone and scope** | No commitment about refunds, credits, or dates | Block. Daniel: billing disputes "become contractual quickly and nothing automated should be making commitments about money" |
| **Confidence floor** | The routing threshold was actually applied | Block. *A missing confidence score is not a high one* |

### The safety gate, and how it changed

The design originally described a "deterministic deny-list that no confidence
score can override". **That claim was false and was retracted.** The deny-list
keys on the *predicted* intent, and prediction is the probabilistic step: a
misclassified security incident does not override the gate, it simply never
triggers it.

What replaced it:

| Layer | Reads | Independent of |
|---|---|---|
| 1 — deny-list | the predicted top-1 intent | — |
| 2 — lexical pre-screen | raw ticket text | the classifier entirely |
| 3 — abstention | the classifier's alternatives above a floor | the top-1 label |
| 4 — grounding *(structural)* | whether any passage can support an answer | all of the above |

Layer 4 does most of the work: **56 of the 87 deny-listed development tickets
cannot be grounded at all**, so they are protected regardless of what the
classifier does. Residual exposure is confined to `security_incident` and
`compliance_request` — the only two deny-listed intents that *can* ground — and
is estimated at roughly **1 ticket in 120**.

**Measured, not asserted.** Over 200 development tickets the governance condition
held at every threshold and every abstention floor tested: **zero deny-listed
tickets auto-answered**. Deny-list recall is reported for those two groundable
intents specifically, never as a four-class aggregate, because an aggregate is
diluted by the 56 structurally-safe tickets and would understate the risk exactly
where it is real.

**Layer 3 was also reclassified honestly.** It caught zero deny-listed tickets the
other layers missed — the violation count is zero with or without it. It stays
because it improves precision by 2.9 points, which is a different argument, and
it is now made as a different argument.

---

## 5. Incident response

Written so someone unfamiliar with the system could follow it at two in the
morning.

| Step | What to do | Who | How long |
|---|---|---|---|
| **1. Detect** | An incident is: a customer reports a wrong or harmful automated reply; a `pii` or `instruction_integrity` block appears in the metrics; the escalation rate jumps above 60% in a run; or a run reports `DEGRADED` unexpectedly. Check `storage/decisions.db` and the latest `report.md`. | On-call engineer | 15 min |
| **2. Contain** | `touch storage/KILL`. Every subsequent ticket escalates to a human with no model call. **No deployment, no restart, no code change.** Takes effect on the next ticket. Confirm with `python scripts/demo.py --only killswitch`. | Anyone with filesystem access | **under 1 minute** |
| **3. Assess** | Find the ticket: `SELECT * FROM decisions WHERE ticket_id = ?`. The records give the predicted intent and confidence, the alternatives considered, the passages retrieved with scores, the threshold in force, every guardrail result, and `prompt_version` — which answers whether the behaviour was intended or a regression. Count how many other tickets in that run shared the pattern. | Engineer + Head of Support | 1 hour |
| **4. Notify** | If a customer received a wrong answer: contact them directly, say a human is now handling it, and do not re-send an automated reply on that thread. If private data was disclosed: notify the affected customer **and** the data owner the same day, and treat it as a breach regardless of the recipient. If a security or compliance ticket was auto-answered: escalate to the Head of Support immediately — this is a governance failure, not a quality issue. | Head of Support | Same day; **immediately** for the last two |
| **5. Remediate** | Match the cause to the control. Wrong answer → check whether grounding passed and whether the cited passage supports the claim; the article may be wrong rather than the system. Deny-list miss → add the missing marker to `src/markers.json` and re-measure recall on both groundable intents. Guardrail gap → add a failing test first, then fix. Release the kill switch only once a test reproduces the incident and passes. | Engineer | Same day for the switch; within a week for the fix |
| **6. Review** | Record what happened, which control should have caught it and why it did not, and what changed. Add the incident to `docs/DECISIONS.md`. If the answer is "no control would have caught it", that is a design finding, not an operational one. | Head of Support | Within a week |

### The kill switch

| Question | Answer |
|---|---|
| **What is the mechanism?** | The presence of the file `storage/KILL`, or `KILL_SWITCH=1` in the environment. Checked once per ticket, **before any model call** |
| **Who is authorised to use it?** | Anyone with filesystem or environment access to the running host. Deliberately low-friction: a switch that needs approval is a switch that does not get used at 2am |
| **How long until it takes effect?** | The next ticket — under a second. No deployment or restart |
| **What happens to tickets in flight?** | They complete as escalations with their retrieved context attached. None are dropped, and all are logged |
| **How is it tested?** | Two tests: one asserts every ticket escalates when engaged, one asserts **zero model calls are made**. It is also a scenario in `scripts/demo.py`. It was moved earlier in the pipeline during the build after a test showed classification had already spent a call before the switch was checked |

---

## 6. The declaration

| Statement | Position |
|---|---|
| **This system must never …** | …send a customer an answer that is not supported by a retrieved CloudServe documentation passage, and must never auto-answer a security incident, compliance request, feature request or unclear ticket. |
| **The mechanism that enforces that is …** | Four controls, three of them independent of the classifier: the grounding guardrail blocks unsupported claims; citation re-resolution blocks references that do not resolve to real corpus text; the three-layer deny-list covers predicted intent, raw text and the alternative distribution; and D2's conjunction requires a retrievable passage before anything can be sent — which alone protects 56 of the 87 deny-listed tickets. **This is deliberately not described as deterministic**, because one layer keys on a predicted intent and prediction can fail. |
| **The most likely way it could still cause harm is …** | A **correctly cited but misapplied** passage: an article genuinely relevant to the symptom but wrong for that customer's configuration. Grounding checks cannot catch this by construction — the citation resolves and the claim is supported by the text; it is simply the wrong text for this customer. The secondary risk is a `security_incident` or `compliance_request` that is misclassified, uses none of the marker vocabulary, and happens to be groundable — roughly 1 ticket in 120. |
| **We would not deploy this without first …** | …a continuous human review sample in production, because the residual harm above is invisible to every automated control we have; a real measurement of the fluency gap on live tickets, since the two supplied splits disagree by 23.5 points and invert; and an agreed owner for the kill switch on every shift. I would also want the escalation-rate target renegotiated before launch rather than after, since it is unreachable without a governance breach and pretending otherwise sets up a failure that is nobody's fault. |
