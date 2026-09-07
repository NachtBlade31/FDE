# CloudServe Intelligent Support System

A retrieval-grounded triage and drafting system for CloudServe Solutions' support
function.

**Written for someone who has never seen this project.** Every command below is
meant to be copied and run in order, from a clean checkout, without improvisation.

---

## What this is, in one paragraph

CloudServe asked for a chatbot. The evidence says they do not have an answer
shortage — 71.4% of their tickets are already answered in their own 29-article
knowledge base — they have a *delivery* failure: keyword search cannot connect a
customer's description of a symptom to the article that resolves it. This system
therefore retrieves the relevant documentation, drafts an answer grounded in it
with resolvable citations, and decides whether to send that answer or hand it to
a human **with the draft, the sources and a statement of what it was unsure
about attached**. Escalation is a designed output, not a failure branch.

Full reasoning: [`docs/superpowers/specs/2026-09-04-cloudserve-support-design.md`](docs/superpowers/specs/2026-09-04-cloudserve-support-design.md).
Requirements: [`docs/PRD-v1.md`](docs/PRD-v1.md).

---

## 1. Prerequisites

| You need | Check with | If missing |
|---|---|---|
| Python 3.10 or later | `python --version` | Install from python.org |
| Git | `git --version` | Install from git-scm.com |
| ~600 MB free disk | — | The install is deliberately small; see note below |

> **Note on install size.** This project does *not* depend on `torch` or
> `sentence-transformers`. `chromadb` ships `onnxruntime`, and its built-in
> embedding function is `all-MiniLM-L6-v2` — the model the brief specifies — so
> we get the required model without a ~2.5 GB dependency.

## 2. Create the environment

```bash
python -m venv .venv
```

Activate it. **On Windows:**

```bash
.venv\Scripts\activate
```

**On macOS or Linux:**

```bash
source .venv/bin/activate
```

Confirm you are inside it — the path should contain `.venv`:

```bash
python -c "import sys; print(sys.prefix)"
```

## 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> The pack's own `06_Configuration/requirements.txt` cannot be installed — it
> pins `langchain-openai==0.0.7` (which requires `openai>=1.10`) against
> `openai==1.0.0`, and pip returns `ResolutionImpossible`. The file in this
> repository is a verified replacement, resolved together in a clean virtual
> environment. The deviation is documented in the report.

## 4. Configure

```bash
cp .env.example .env
```

Then open `.env` and set **one** provider key. Both have free tiers that are
sufficient for this project; you do not need to pay for anything.

| Provider | Set | Get a free key from |
|---|---|---|
| Groq (default, faster) | `PROVIDER=groq` and `GROQ_API_KEY=...` | <https://console.groq.com/keys> |
| OpenRouter | `PROVIDER=openrouter` and `OPENROUTER_API_KEY=...` | <https://openrouter.ai/keys> |

`.env` is in `.gitignore` and must never be committed.

> **Without a key the system still runs.** It degrades to retrieval-only:
> it returns the relevant documentation and escalates every ticket to a human,
> rather than failing to start. That is acceptance criterion A11 in action.

## 5. Run the tests

```bash
pytest
```

This is the single documented test command (A12). It needs no API key — model
interactions in tests use recorded fixtures — so it passes on a clean checkout
before you have obtained credentials.

## 6. Run the evaluation harness

This is the single command that processes a whole ticket file end to end,
unattended, and writes the metrics report.

```bash
python -m evaluation.harness --input data/sample_tickets.json --output evaluation/results/my-run
```

It takes an **input path** and an **output path** as arguments and never a
hardcoded filename, because it is meant to be pointed at a file this repository
has never seen. Point it at any file using the pack's ticket schema:

```bash
python -m evaluation.harness --input /path/to/any_tickets.json --output results/
```

**What it writes** into the output directory:

| File | Contents |
|---|---|
| `report.md` | The human-readable report: volume, business, technical, governance |
| `metrics.json` | The same figures as data |
| `outcomes.json` | Per-ticket audit trail: terminal state, reason, citations, latency |

The decision log is written to `storage/decisions.db` and is reconciled against
the run before the report is produced — if any ticket is missing from it, the
report says so rather than quietly averaging over the gap.

**Expect it to pause.** The provider's free tier is limited by tokens per minute,
not requests, so the harness waits for the allowance window rather than retrying
into the limit. The report separates *processing latency* (what the sub-3-second
target measures) from *wall clock* (which includes those waits).

**If the model provider is unreachable**, the run still completes: every ticket
escalates with its retrieved context attached, and the report is marked
`DEGRADED` with the business rates withheld rather than published — a broken run
and a very conservative one otherwise look identical in the output.

## 7. Start the API

> Available from Day 6.

```bash
python -m src.api
```

---

## Repository layout

```
src/                  application code, one module per pipeline component
  models.py           domain types; every value crossing a boundary
  ingest.py           four-channel normalisation (A2)
  config.py           settings, dual provider, kill switch
  logging_store.py    the decision log (A8)
prompts/              the prompt library, versioned
tests/                the test suite; `pytest` runs all of it
evaluation/           the harness and dated results
docs/                 design specification, PRD, validator log
data/                 the documentation corpus and a small ticket sample
.github/workflows/    continuous integration
```

## The kill switch

The system can be stopped from answering automatically, immediately, without a
deployment:

```bash
# engage - every subsequent ticket escalates, with no model call
touch storage/KILL

# release
rm storage/KILL
```

`KILL_SWITCH=1` in the environment does the same. It is checked once per ticket,
so it takes effect on the next ticket, and tickets already in flight complete as
escalations rather than being dropped.

## Data

`data/documentation.json` is the 29-article corpus the retrieval layer searches;
the system cannot run without it, so it is committed. `data/sample_tickets.json`
is an 8-ticket sample covering all four channels and every deny-listed intent,
used by the tests and the demonstration.

The full 500-ticket development set and 80-ticket validation set are **not**
committed, per the Submission Guide's instruction to include small samples only.
Tests that need them skip cleanly when they are absent.

## Attribution

Development of this project was AI-assisted; the declaration of tool use, and
attribution for any code not written by the author, is in the project report.
