# Stage One: Discovery Workbook

**Kshitiz Bhargava — Forward Deployed AI Engineering Capstone**
**Client: CloudServe Solutions**

Every figure in this workbook was computed from `development_tickets.json`
(n=500) and `validation_tickets.json` (n=80) rather than taken from the pack's
summary tables. The scripts that produce them are in `scripts/`, and the saved
outputs are in `evaluation/results/`, so any number here can be re-derived.

---

## 1. What the interviews tell you

| Who | What they told you | What they appear not to know | What you want to verify in the data |
|---|---|---|---|
| **Marcus Adeyemi**, Head of Support | Volume above 500/week against six agents. First response 8–12h against a 2h agreement. FCR 42%, target 65%. Every escalation costs ~4× a resolved ticket. Cares most about FCR, reports response time. Two fears: a confidently wrong answer being screenshotted, and more agent work not less. Compliance review in the autumn, so decisions must be explainable. Admits: "If you asked me for a breakdown I would be guessing." | **What is inside his escalations.** He sees the escalation rate but not its composition. He does not know that roughly half of what reaches tier two is answerable from documentation he already owns. He also does not know enterprise customers currently get his *slowest* service. | The intent breakdown he says he has never done. Whether escalations are genuinely hard. Whether enterprise really is protected. |
| **Sofia Restrepo**, Tier One Agent | 40–70 tickets each morning, sorted by age. "Seven out of ten I could answer without looking anything up." The documentation is good but unsearchable, so she keeps a personal answer file. Escalates for three reasons: doesn't know, isn't confident enough, or it's a security matter. Not worried about her job — worried about apologising for a wrong answer she did not write. Non-fluent English tickets take longer and have the worst satisfaction, "and I do not think anyone has noticed." | **That her 7-in-10 estimate is almost exactly right**, and therefore how large the addressable share is. She frames it as her own coping strategy rather than as a systemic finding. | Her 70% claim. Whether non-fluent tickets really do worse. |
| **Daniel Okonkwo**, Tier Two Engineer | About half of what reaches him could have been resolved at tier one "if they had been confident, or if they had found the right page". Escalations arrive as bare forwarded tickets with no summary, so he re-reads the thread and re-asks questions the customer already answered — "that is where the customer frustration really comes from, more than the waiting." Wants context, not correctness: "I do not need it to be right. I need it to show its working." Warns that agents' private snippet files contain answers that were correct two years ago. | **That Marcus cannot see what he can.** He describes the escalation composition accurately but treats it as a known fact rather than as the central finding it is. | His "about half" claim, which is the load-bearing one. |
| **Ines Varga**, Technical Writer | 29 knowledge base articles, reviewed on a rotation, accurate within that cycle. Used externally, effectively unused internally. Diagnoses the mechanism precisely: internal search matches titles and exact terms, and "someone writes *my deployment keeps dying* and my article is called *resolving container health check failures*. There is no path between those two phrases in a keyword search." Wants to know which article an answer came from, so a wrong answer can be traced to either the article or the system. Notes what is *not* covered: feature requests, roadmap, genuinely novel incidents. | **That her diagnosis is the whole problem.** She offers it as an explanation for low internal usage; it is in fact the mechanism behind Marcus's headline numbers. | Whether the corpus really does cover the incoming volume. Which intents have no article at all. |
| **Ravi Menon**, Customer | "Slow but decent once you get there." Waiting costs vary enormously by urgency — a pagination question can wait, a failing deployment at 9am cannot. Searches the docs himself and finds the answer "maybe half the time", after which the eventual reply says the same thing. Would accept an automated first response *provided it is honest* and says where it came from. Wants to be told it was automated, because he calibrates his trust on it. Believes an enterprise-plan colleague gets answers in about an hour. | **That enterprise is not, in fact, faster.** His belief about the tier gap is wrong in the opposite direction to his fear. | Resolution time by customer tier. |

### Where the accounts disagree

| The disagreement | Who says what | How the data settles it | What follows from the answer |
|---|---|---|---|
| **How much of tier two's work is genuinely tier-two work** | Daniel: "about half of what reaches me is something tier one could have resolved". Marcus does not mention this at all and reports only the escalation rate. | Of 281 historically escalated tickets, **138 (49.1%)** are `answerable_from_docs`, and **92 (32.7%)** are labelled `expected_route = auto_respond`. Daniel is right, to within a point. | This is the project. The intervention is not "answer more tickets" but "stop escalating tickets that the documentation already answers." |
| **How much of the incoming volume is already answered** | Sofia: "seven out of ten I could answer without looking anything up." Marcus: "Broadly... I would be guessing." | **71.4%** of development tickets are `answerable_from_docs` (357/500). Sofia's estimate is accurate. | CloudServe does not have an answer shortage. Building new answers would address nothing. |
| **Whether enterprise customers get better service** | Ravi believes an enterprise colleague gets replies in about an hour and fears the gap will widen. Marcus fears enterprise "will notice immediately if they get worse service." | Median resolution: **enterprise 369 min, standard 266 min, business 141 min.** Enterprise is the *slowest* tier. FCR: enterprise 37.3% against business 48.2%. | Both are wrong, in opposite directions. Enterprise is already the worst-served tier, so the fairness risk is the reverse of the one Marcus is guarding against — and it is a renewal risk today, not a future one. |
| **Whether non-fluent English tickets are handled worse** | Sofia believes they are, and that nobody has noticed. | **Split-dependent, and this is a finding in itself.** On development: non-fluent FCR 45.8% vs fluent 43.2% — slightly *better*. On validation: 21.1% vs 54.1% — dramatically worse (Fisher p=0.017). | Sofia is right on one split and wrong on the other. No single baseline can be assumed; the fairness audit must compare against the same split it measures. |

### What nobody said

| What was never mentioned | Why you would have expected it | How you will check it |
|---|---|---|
| **That escalations consume almost all the agent time.** | Marcus prices an escalation at ~4× a resolved ticket but never states the aggregate. | Computed: escalated tickets are **56.2% of volume and 96.8% of all agent minutes**. |
| **That the tickets nobody can answer and the tickets nobody should answer are different sets.** | Ines lists what has no article; Daniel lists what is unsafe to automate. Neither connects them. | `feature_request` and `unclear_request` are 0% answerable *and* must never be auto-answered. `security_incident` and `compliance_request` must never be auto-answered but are 54–65% answerable — so they are the only real safety risk. |
| **What happens when the system is wrong.** | Marcus fears a wrong answer; nobody describes the recovery path. | No incident procedure exists. Recorded as a governance gap and written in Stage 5. |
| **Anything about cost.** | Marcus mentions headcount and outsourcing quotes but never a per-ticket cost. | Not derivable from the data. Recorded as an open assumption: the ~4× escalation multiplier is Marcus's figure, unverified. |
| **That the data itself is templated.** | Nobody could know this; it is an artefact of the sample. | 57% of development ticket bodies duplicate another ticket verbatim. Material for how much any accuracy figure can be trusted. |

---

## 2. What the ticket data shows

| What to measure | Figure | Where it came from | What surprised you |
|---|---|---|---|
| Total tickets in the sample | 500 dev, 80 validation, 29 articles, 200 reference answers | file counts | — |
| Split by channel | email 212 (42.4%), chat 155 (31.0%), docs_comment 78 (15.6%), forum 55 (11.0%) | `scripts/analyse_data_regularity.py` | Chat is nearly a third — and chat customers abandon fastest, so latency matters more than the aggregate suggests. |
| Split by intent | 22 classes, unevenly spread. Largest: `data_export` and `data_residency` (29 each). Smallest: `rate_limit` (13). | computed | No dominant class. A system good at two intents would help very little. |
| Split by urgency | medium 226, high 146, low 128 | computed | 29% are high urgency, which is a large share to be sitting in an age-sorted queue. |
| Proportion resolved on first contact | **43.8%** (219/500) | `history.first_contact_resolution` | Matches Marcus's 42% almost exactly. His headline number is sound. |
| Average satisfaction rating | **2.97 / 5** | `history.csat_rating` | *Lower* than the 3.2 Marcus reported. The situation is slightly worse than he is reporting upward. |
| Most frequent single question | Deployment/rollback themes together are the largest cluster; `data_export` and `data_residency` the largest single classes | computed | — |
| **Proportion answerable from existing documentation** | **71.4%** (357/500) | `labels.answerable_from_docs` | **The central finding.** Sofia's "seven out of ten" is right, and it means the problem is delivery, not knowledge. |
| Proportion non-fluent, and their outcomes | 120/500 (24%). Dev FCR 45.8% vs fluent 43.2%; validation 21.1% vs 54.1% | computed | The two splits disagree sharply. Any claim about a fluency gap must name its split. |
| Outcomes by customer tier | FCR: business 48.2%, standard 43.1%, enterprise 37.3%. Median minutes: business 141, standard 266, enterprise 369 | computed | Enterprise is worst on both. The opposite of what everyone assumed. |
| Proportion that are repeat contacts | 108/500 (21.6%), and **100% of them have `first_contact_resolution = false`** | computed | Repeat contact is fully determined by non-resolution, so it is not an independent measure. |
| Tickets with no supporting document | 143/500 (28.6%), `expected_doc_ids` empty | computed | Just over a quarter of tickets *cannot* be grounded. Returning nothing must be a supported outcome. |
| Tickets that must never be auto-answered | 87/500 (17.4%), exactly four intents, zero label violations | computed | Cleanly separable, so the safety rule can be deterministic rather than probabilistic. |

---

## 3. Where the time actually goes

Volume and effort are not the same distribution. Effort here is the share of
total `history.resolution_time_minutes` — 210,849 minutes, about 3,514 agent
hours across the 500-ticket sample.

| Ticket category | Share of volume | Share of effort | Ratio | Why the two differ | Evidence |
|---|---|---|---|---|---|
| `security_incident` | 5.2% | **9.7%** | 1.86× | Genuinely hard, always escalated, median 734 min | computed |
| `feature_request` | 4.0% | **6.9%** | 1.72× | No article exists; time spent establishing there is no answer | 0% answerable |
| `compliance_request` | 5.2% | **8.4%** | 1.61× | Contractual, needs a human, median 678 min | computed |
| `performance_degradation` | 4.6% | 5.9% | 1.29× | Diagnostic work | 74% answerable |
| `data_export` | 5.8% | 4.0% | 0.69× | Routine and documented | 93% answerable, median 40 min |
| `sso_configuration` | 5.2% | 2.4% | 0.45× | Documented and quick | 85% answerable, median 47 min |
| `rate_limit` | 2.6% | **0.8%** | 0.29× | The cheapest class in the queue | 92% answerable, median 35 min |

**The finding that matters is not in this table but across it:**

> Escalated tickets are **56.2% of volume** but consume **96.8% of all agent
> minutes**. Of those escalations, 49.1% were answerable from documentation.
> **46.2% of all agent time in the sample was spent on escalations the
> documentation already answered.**

That is the number the project exists to move. It also reframes the target:
the win is not shaving minutes off easy tickets, it is preventing answerable
tickets from entering the expensive path at all.

### The steps an agent takes on a typical ticket

Reconstructed from Sofia's account.

| Step | What the agent does | Roughly how long | Could this be automated? |
|---|---|---|---|
| 1 | Open the queue, sort by age, pick the oldest | seconds | **Yes, and it should be re-sorted.** Age-sorting is why high-urgency tickets do *worse* (FCR 39.7% vs 48.4% for low). |
| 2 | Read the ticket and work out what is actually being asked | 1–5 min; longer for non-fluent English, where she sometimes answers the wrong question | **Partly.** Classification does this, but it is also where the fluency risk lives. |
| 3 | Decide whether she already knows the answer | seconds | **This is the leverage point.** For 7 in 10 she does. |
| 4 | Find the wording — from memory, her personal file, or (rarely) the documentation | **the bulk of the time** | **Yes. This is the automatable step**, and it is the one Ines diagnosed: search cannot bridge symptom wording to article titles. |
| 5 | Write and send the reply | 2–5 min | Partly — drafting from a retrieved passage. |
| 6 | If unsure: escalate with the raw ticket forwarded | seconds to send, **hours of downstream cost** | **Not automatable, but improvable.** Attaching context is what Daniel asked for. |

Step 4 is where the time goes and step 3 is where the decision is made. A system
that helps at step 4 and supports the judgement at step 3 addresses the problem;
one that only drafts text at step 5 does not.

---

## 4. What the client counts as success

| Measure | Who watches it | Current value | What they would call success | Confidence in this |
|---|---|---|---|---|
| First contact resolution | Marcus, and it is what he actually cares about | **43.8%** (measured) | 60–65% | **High.** Measured directly and matches his stated 42%. |
| Time to first reply | Reported to the executive team; in the service agreement | 8–12 h (Marcus's figure) | Under 2 h contractually, under 5 min aspirationally | **Low.** Not derivable from the data — there is no `replied_at` field. Median `resolution_time_minutes` is 214 (3.6 h), which measures something different. |
| Customer satisfaction | Marcus; surfaces at renewal | **2.97 / 5** (measured) | 4.0+ | **High for the figure, low as a proxy.** It is *worse* than the 3.2 he reports. |
| Escalation rate | Marcus, as the mirror of FCR | 56.2% | ≤ 30% | **High** for the measurement, but the target is unreachable — see below. |
| Cost per escalation | Marcus, informally | ~4× a resolved ticket | Fewer escalations | **Low.** His figure, unverified, no cost data supplied. |
| Agent attrition | Marcus | "rising"; two seniors left last quarter citing workload | Stable | **None.** No data. Recorded as an open question. |
| Explainability | Marcus, for the autumn compliance review | Nothing exists | Every decision reconstructable | **High** as a requirement; it drove the decision-log schema on day one. |

### The sentence test

| Prompt | Answer |
|---|---|
| This project will have been worth doing if, within three months of launch, … | …the share of agent time spent on escalations that the documentation already answered has fallen from **46%** toward zero, first contact resolution has moved from **43.8%** toward **60%**, and every automated decision can be explained to the autumn compliance review. |
| We will know it did not work if we see … | …a single confidently wrong answer sent to a customer on a security, compliance or billing matter; or agents spending *more* time because they now check the system's drafts as well as writing their own. Both are Marcus's stated failure conditions and both are more important than the headline rate. |
| The measure the client will actually be judged on internally is … | …**time to first reply**, because it is in the service agreement and is what gets reported upward — even though Marcus says first contact resolution is what he actually cares about, and FCR is the one that moves the cost base. |

---

## 5. Data, constraints and risk

| Data source | What it contains | Quality and gaps | Access constraints | Private data present? |
|---|---|---|---|---|
| Support tickets | 500 dev + 80 validation, labelled with intent, urgency, expected route, groundability, expected documents, and a history block | **Templated.** 57% of dev bodies duplicate another ticket; same-intent vocabulary overlap is 19× cross-intent. Labels are internally consistent (zero violations across three invariants). | Dev free to use. **Validation must not be tuned against** (Project Brief §06 overrides the Dataset Guide's looser wording). | **Yes** — `customer_name`, `customer_id`. Never sent to the model; only subject and body are. |
| Documentation | 29 articles, 31,733 characters (~8k tokens), 10 categories | Accurate within Ines's review cycle. `last_reviewed_days_ago` is **0 for all 29**, so staleness is undetectable in this data. Coverage gaps are deliberate: feature requests, roadmap, novel incidents. | Free to use. | No. |
| Past resolutions | 200 senior-agent reference answers with `must_mention` and `must_not_claim` | Useful as a quality standard. Daniel's warning applies to agents' *private* files, which are not supplied — so the risk he names cannot be measured here. | Free to use. | No. |
| Customer records | Only what is on the ticket: id, name, tier, region, fluency | No separate customer database. Tier/region/fluency are the fairness segments. | — | **Yes.** Names and ids are fairness segments and PII simultaneously. |
| The hidden evaluation set | 120 tickets, same schema, not supplied | Unknown, but drawn from validation's population — which differs from dev on **five** measured dimensions. | Run once, after submission. | Presumed same. |

### Initial risk register

| What could go wrong | How likely | How bad | Who it affects | First thought on preventing it |
|---|---|---|---|---|
| The system answers confidently and incorrectly | **High** — 22 classes, imperfect classification, and confidence is self-reported | **Severe.** Marcus: customers are engineers who "will screenshot a confidently incorrect answer and put it on the internet within the hour" | The customer, then the agent who apologises for it | Never answer without a retrieved passage; construct citations from retrieval rather than letting the model write them; require several conditions to agree before answering |
| Private information appears in a reply | Medium | **Unacceptable at any rate** | Another customer entirely | Scan every outbound response; block rather than redact, since a redacted leak is still a leak that was nearly sent |
| A security or compliance ticket is auto-answered | Medium — 17.4% of tickets, and classification is imperfect | **Severe and non-recoverable** | The customer and CloudServe's compliance position | A rule keyed on intent is not enough, because intent is predicted. Needs a control that does not depend on the classifier being right |
| Some customers get consistently worse answers | **High** — Sofia already suspects it, and the splits disagree | Severe at renewal; enterprise is *already* worst-served | Non-fluent English writers; enterprise customers | Segment every measure by tier, region and fluency, and compare against the same split's own baseline rather than an assumed one |
| The documentation goes out of date | Medium | Moderate, and hard to detect | Everyone, silently | Surface article age beside every citation. Note that `last_reviewed_days_ago` is uniformly 0 here, so this cannot be tested with the supplied data |
| A customer's ticket is treated as an instruction | Medium — the customers are engineers | Severe | Everyone | Never concatenate ticket text into instructions; check the released response independently |
| The model provider becomes unavailable | **High** — it is a free tier | Moderate if handled, severe if not | Every waiting customer | Degrade to retrieval-only and keep going; a run that stops is worse than a run that escalates |
| Agents trust the system and stop checking | Medium | Severe, and slow to notice | Customers | Disclose that the reply was automated; state uncertainty explicitly on escalations |

---

## 6. The problem statement

| Element | Statement | Supporting evidence |
|---|---|---|
| **What the client asked for** | A chatbot to answer the easy tickets so the team can do the hard ones. | §1, Marcus |
| **What the evidence suggests they actually need** | A way to stop tickets that the documentation already answers from reaching a human at all — and, for those that must reach one, to arrive with the relevant article and a statement of what was uncertain. | §2 (71.4% answerable), §1 (Daniel 49.1%), §3 (46.2% of effort) |
| **The gap between those two** | A chatbot is a delivery mechanism. It says nothing about where answers come from, whether they are right, what happens when they are unknown, or who is accountable when they are wrong. The failure is not that answers do not exist — 71.4% of them do — but that nobody can find them. | §1 Ines (the search mechanism), §2 |
| **Who is affected and how** | Customers wait 8–12 hours for answers that already existed. Sofia re-answers the same questions and fears apologising for text she did not write. Daniel spends his time on questions a page would have answered. Marcus reports a red number and faces a compliance review. Enterprise customers — the ones Marcus most fears upsetting — are already the worst served. | §1, §4 |
| **What will change if this is solved** | The 46% of agent time spent on answerable escalations is released. First contact resolution moves toward 60%. Escalations that remain arrive with context, so tier two stops re-asking questions the customer already answered. | §3, §4 |
| **What is explicitly not in scope** | A conversational chatbot; learning from agents' unreviewed private snippet files; writing to the knowledge base (Ines owns editorial control); translation; and auto-answering security, compliance, feature-request or unclear tickets under any circumstances. | §1 Daniel and Ines, §5 |

### The one paragraph version

> CloudServe's support team is not short of answers — it is short of a way to
> find them. Seven out of every ten tickets that arrive are already answered
> somewhere in the twenty-nine articles the company has written, but the search
> only matches the words in an article's title, and customers describe their
> problems in their own words instead. So agents answer from memory, and when
> they are not sure enough to send an answer they pass the ticket on. Half of
> everything that reaches the senior engineers is a question the documentation
> already answered, and those passed-on tickets consume almost all of the team's
> time — nearly half of every hour worked is spent on questions that did not
> need a person at all. The customer waits most of a day for an answer that
> already existed, the senior engineer re-asks questions the customer already
> answered, and the numbers Marcus reports upward get worse every quarter. What
> CloudServe need is not something that talks to customers. It is something that
> finds the answer they already have, sends it when it can stand behind it, and
> when it cannot, hands the ticket to a person with the right page already
> attached and an honest note about what it was unsure of.

### Reading it back against the five transcripts

The workbook asks whether each of the five would recognise this.

- **Marcus** would recognise it and would be surprised by two things: that half
  his escalations were answerable, and that enterprise is his slowest tier.
- **Sofia** would recognise it completely; it is her account, quantified.
- **Daniel** would recognise it and would say he had told people already.
- **Ines** would recognise the mechanism as hers, and would want the point about
  citation provenance kept.
- **Ravi** would recognise the waiting and would **object to one thing**: he
  believes enterprise customers are better served, and the data says they are
  not. That objection is the finding — he is describing a perception, and the
  perception is wrong in the direction that matters for renewal conversations.

A statement all five simply agreed with would not have gone far enough. This one
contradicts two of them on points of fact, and both contradictions are settled by
the ticket data rather than by argument.
