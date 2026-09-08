# Stage Four: Sprint Plan

**Kshitiz Bhargava — CloudServe Solutions support system**

> **This plan covers nine days, not three weeks.** Work began on 4 September
> against a 13 September deadline. The pack assumes a three-week shape with three
> days of discovery before any code, and that shape was not available. The plan
> below is what was actually done, dated against the commit history, and the
> consequences of the compression are stated rather than hidden. Backdating
> commits to imply three weeks would have been trivial and dishonest; the history
> shows nine days because it was nine days.

---

## 1. Capacity

| Period | Hours realistically available | Other commitments | Days not worked |
|---|---|---|---|
| **Days 1–2** (4–5 Sep) | ~10 | — | **5 Sep lost entirely** |
| **Days 3–4** (6–7 Sep) | ~16 | — | — |
| **Days 5–6** (7–8 Sep) | ~14 | — | — |
| **Days 7–9** (9–13 Sep) | ~20 planned | — | — |

**The rule for working alone.** Nobody notices when you have been stuck for six
hours. The rule adopted was: anything blocking for more than an hour gets written
down and either escalated or worked around. Three things hit that rule and all
three are in `docs/DECISIONS.md` — the unresolvable dependency pins (D-07), the
withdrawn model (D-22), and the undocumented daily token cap (D-40). The last one
consumed most of a day, and it was caught because it had been written down rather
than wrestled with.

**A second mechanism replaced the missing colleague.** An independent validator
reviewed every phase before it was accepted, against the pack documents rather
than against my reasoning. It returned `BLOCKED` once and `CLEARED WITH
CONDITIONS` five times, and found eight defects — four of them load-bearing. That
is the coordination overhead a team pays for, bought back deliberately.

---

## 2. The backlog

Estimates were made on day one. Actuals come from the effort log and commit
history.

| ID | Item | Est. | Actual | Priority | Depends on | Definition of done |
|---|---|---|---|---|---|---|
| **B-01** | Environment and dependency setup | 1h | **2h** | Must | — | A clean venv installs from `requirements.txt`; the pack's own file was found unresolvable and replaced |
| **B-02** | Data loading and normalisation | 2h | 2h | Must | B-01 | All four channels normalise; 500 dev + 80 validation tickets parse with zero rejections |
| **B-03** | Chunking and embedding | 2h | **1h** | Must | B-02 | Two strategies compared on hit rate, not assumed |
| **B-04** | Vector store and retrieval | 3h | 3h | Must | B-03 | Citations resolve to real passages; nothing returned below the floor |
| **B-05** | Evaluation harness | 4h | **6h** | Must | B-02 | Takes `--input`/`--output`; produces the report unaided |
| **B-06** | Intent and urgency classifier | 3h | **6h** | Must | B-02 | Every ticket carries a class and confidence; a defined fallback on failure |
| **B-07** | Routing logic and thresholds | 3h | **5h** | Must | B-06 | Deterministic; thresholds swept from data; zero deny-list violations |
| **B-08** | Answer generation with citations | 3h | 3h | Must | B-04 | Every citation resolves to a retrieved passage |
| **B-09** | Guardrails and validation | 3h | 3h | Must | B-08 | Five checks, all blocking, none disableable |
| **B-10** | Decision logging | 2h | **4h** | Must | B-07 | Reconciles by identity, scoped to a run |
| **B-11** | **The gate — full unattended run** | 2h | **9h** | **Must** | B-05, B-09 | 80 tickets, one command, no intervention |
| **B-12** | Monitoring and dashboards | 3h | **0h** | Could | B-10 | **Cut. See §5** |
| **B-13** | Continuous integration | 1h | 1h | Should | B-11 | Tests and a secret scan run on every push |
| **B-14** | Fairness audit | 2h | 2h | Must | B-11 | Segmented against the same split's baseline |
| **B-15** | Report, video and packaging | 12h | *in progress* | Must | all | Four folders, correctly named |
| **B-16** | *(unplanned)* Rate-limit and quota handling | 0h | **7h** | Must | B-11 | Two pacing defects and an undocumented daily cap |
| **B-17** | *(unplanned)* Validator remediation | 0h | **6h** | Must | — | Six review rounds |

**The estimate that was most wrong is B-11, at 2 hours estimated against 9
actual.** That is the item the Build Specification warns about in as many words,
and I still under-estimated it by more than four times.

---

## 3. Days 1–5 in detail (the build)

| Day | Finished by end of day | Hours | Risk to this |
|---|---|---|---|
| **1** (4 Sep) | Design spec, validator charter, pinned env, models, four-channel ingest, decision log, PRD v1, effort log opened | 10 | Validator returned **BLOCKED** on the design; remediated same day |
| **2** (6 Sep) | Retrieval with resolvable citations; chunking and relevance floor derived by sweep | 6 | 5 Sep lost entirely — a full day of the nine |
| **3** (7 Sep) | Classifier, model client with pacing, router, both thresholds swept | 10 | Model named in the Setup Guide no longer exists; first rate-limit defect found |
| **4** (7 Sep) | Generation with resolved citations; five blocking guardrails | 5 | — |
| **5** (7–8 Sep) | Pipeline, harness, **the gate** | 9 | **The gate failed twice.** Three pacing/quota defects, each invisible until the full chain ran at volume |

## 4. Days 6–9 in detail

| Day | Finished by end of day | Hours | Risk to this |
|---|---|---|---|
| **6** (8 Sep) | A11 failure injection; per-node containment; daily-quota handling; run-scoped reconciliation | 7 | Daily token budget exhausted — no further full runs possible that day |
| **7** (8 Sep) | Discovery workbook, fairness audit, governance framework, revision log, prompt library, this plan | 8 | Deliberately chosen as work needing no model calls, because the budget was gone |
| **8** (9–11 Sep) | Cold gate run once the budget resets; report draft; **video take one** | 12 | **The largest remaining risk.** Video cannot be rushed and the pack says so three times |
| **9** (12–13 Sep) | Video take two; report final; clean-checkout rehearsal; packaging | 10 | A1 rehearsal must not be left to the final afternoon |

---

## 5. What gets dropped if time runs out

Decided on day one, and one item has already been cut.

| Item | Cut order | Consequence | What the report says |
|---|---|---|---|
| **Prometheus / Grafana monitoring** | **1st — already cut** | None to the assessment. Monitoring is not among the twelve acceptance criteria | Cut deliberately. The metrics it would surface — volume by outcome, latency percentiles, guardrail activations, confidence distribution — are all produced by the harness report instead, which is what A10 actually requires. A dashboard would have been a second view of numbers already computed |
| **FastAPI service surface** | 2nd | None to the criteria. A2 concerns ingest, which is complete and tested | Would be cut with the same reasoning. The demonstration runs through `scripts/demo.py` and the harness, both of which show more than an HTTP endpoint would |
| **LLM-judge hallucination cross-check** | 3rd | Weakens the hallucination measure to one assessor | One assessor plus a stated deviation already satisfies the honesty requirement; the cross-check is polish |
| **The chunking comparison** | 4th | Would have made the chunking decision asserted rather than measured | **Not cut** — it took an hour and produced a defensible decision |
| **Intent classes beyond the deny-list four** | Last resort, never reached | A3 requires every ticket to carry a class | Would have mapped cut classes to the fallback rather than skipping tickets, and the four deny-list intents could never be cut |

**Never cut**, in order of protection: the unattended run, the five guardrails,
the decision log, the deny-list layers, the video.

---

## 6. Daily check-in record

| Date | Finished since yesterday | Doing today | Blocked by |
|---|---|---|---|
| 4 Sep | — | Read the pack; analyse all four datasets; design spec; validator review; day-1 build | Pack's `requirements.txt` unresolvable — replaced and documented |
| 5 Sep | — | **Nothing. Day lost.** | — |
| 6 Sep | Day-1 remediation | Retrieval, chunking comparison, relevance floor sweep | — |
| 7 Sep | Retrieval complete | Classifier, model client, router, generation, guardrails, pipeline, harness | Setup Guide's model withdrawn by the provider; found by querying the models endpoint |
| 8 Sep (am) | Gate cleared functionally | Diagnose why the cold run takes 3.6 min/ticket | **Two pacing defects, then an undocumented 200k tokens/day cap.** ~7h |
| 8 Sep (pm) | Quota handling; A11 suite; run-scoped logging | Workbooks and governance — chosen because they need no model calls | Daily token budget exhausted; no full runs possible until reset |

---

## 7. What the plan got wrong

Three things, worth recording because the estimating is the point of this stage.

**The gate was under-estimated by 4.5×** (2h against 9h). Every defect that cost
real time was invisible until the whole pipeline ran at volume: the reasoning
model returning empty completions, two pacing bugs, the undocumented daily cap,
and the graph aborting on a raised exception. The Build Specification says to run
the full chain end to end early in week two. I read that, agreed with it, and
still sequenced five days of component work before the first full run.

**Two entire workstreams were unplanned** — 13 hours across rate-limit handling
and validator remediation, against a backlog that allowed for neither. Both were
predictable in kind if not in detail: free tiers throttle, and reviews find
things.

**The compression removed the recovery margin, not the work.** Losing 5 September
cost a ninth of the schedule with nothing to absorb it. The response was to
protect the gate and cut monitoring, which was the right call — but it was made
under pressure rather than from the cut list, and the cut list existed precisely
so it would not have to be.
