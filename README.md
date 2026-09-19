# CloudServe Intelligent Support System

Reads support tickets, finds the answer in CloudServe's own documentation, and
either sends a cited answer or hands the ticket to a person with the answer
attached. Security and compliance tickets always go to a person.

Run every command below **in order**, from the folder that contains this README.

---

## 1. Before you start

- **Python 3.10 or later.** Check with `python --version`.
- **Windows: keep the folder path short**, e.g. `C:\dev\cloudserve`. A long path
  makes the install fail with `OSError ... onnxruntime ... Long Path support`.
  See [Troubleshooting](#troubleshooting).
- **One free API key**, from Groq (<https://console.groq.com/keys>) or
  OpenRouter (<https://openrouter.ai/keys>). You don't need to pay for anything.
  Without a key the system still runs, but it escalates every ticket.

## 2. Set up (once)

Open a terminal **in this folder**, the one with `README.md` and
`requirements.txt` in it.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

**macOS / Linux:**

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Then open `.env` and set **one** provider:

| Provider | Put this in `.env` |
|---|---|
| Groq (default) | `PROVIDER=groq` and `GROQ_API_KEY=<your key>` |
| OpenRouter | `PROVIDER=openrouter` and `OPENROUTER_API_KEY=<your key>` |

`.env` is git-ignored. Never commit it.

**Every later session:** open a terminal in this folder and activate the
environment again (`.venv\Scripts\Activate.ps1`, or `source .venv/bin/activate`).
Your prompt should start with `(.venv)`.

## 3. Check the setup

```bash
python scripts/check_env.py
```

This confirms the key works and that today's token allowance has room. Fix
anything it reports before going further.

## 4. Run the tests

```bash
pytest
```

All 516 tests, no API key needed. **It takes about 15 minutes.** It hasn't hung:
the retrieval tests build a real search index. For a one-minute check of the
safety controls:

```bash
pytest tests/test_route.py tests/test_guardrails.py tests/test_token_budget.py
```

## 5. See it work: the demo

```bash
python scripts/demo.py
```

This runs six scenarios in order against the real model: a ticket answered, a
ticket escalated, a question the documentation doesn't cover, a prompt-injection
attempt, a draft that a guardrail blocked, and the kill switch. To run just one:

```bash
python scripts/demo.py --only success
python scripts/demo.py --only escalation
python scripts/demo.py --only blocked
python scripts/demo.py --only killswitch
```

`blocked` needs the dataset pack next to this folder (see [Data](#data)). If the
pack isn't there, the demo says so and skips that scenario.

## 6. Process a ticket file

One command, unattended: a ticket file in, results out.

**The 8-ticket sample (about 2 minutes):**

```bash
python -m evaluation.harness --input data/sample_tickets.json --output evaluation/results/sample-run
```

**The 80-ticket validation set (about 8 minutes):**

```bash
python -m evaluation.harness --input ../FDE_Capstone_Complete-20260821T084330Z-1-001/FDE_Capstone_Complete/Capstone_Pack/05_Datasets/validation_tickets.json --output evaluation/results/validation-run
```

**Any other file** that uses the pack's ticket format, including a hidden test
set:

```bash
python -m evaluation.harness --input path/to/tickets.json --output evaluation/results/my-run
```

What gets written to the output folder:

| File | What's in it |
|---|---|
| `report.md` | Readable results: volume, business, technical, governance |
| `metrics.json` | The same figures as data |
| `outcomes.json` | One row per ticket: decision, reason, citations, timing |

Every decision is also logged to `storage/decisions.db`. The run checks that log
against its own tickets before it writes the report.

**Pauses during a run are normal.** The free tier limits tokens per minute, so
the harness waits for its allowance instead of failing.

**Watch the daily limit.** The free tier also caps usage at **200,000 tokens a
day**, and it resets at **00:00 UTC**, not at your local midnight. An 80-ticket
run uses about 85,000 tokens, so run `python scripts/check_env.py` before any
full run. Re-running a file you've already processed costs nothing, because the
results are cached.

## 7. Analyse a run

```bash
python scripts/fairness_audit.py --outcomes evaluation/results/validation-run/outcomes.json --tickets ../FDE_Capstone_Complete-20260821T084330Z-1-001/FDE_Capstone_Complete/Capstone_Pack/05_Datasets/validation_tickets.json
python scripts/list_runs.py
python scripts/analyse_agent_time.py
```

- `fairness_audit.py` compares outcomes across customer tier, region and
  language fluency. It won't run on a degraded run, because that result would
  be meaningless.
- `list_runs.py` lists every run recorded in the decision log.
- `analyse_agent_time.py` recomputes the discovery finding on where agent time
  goes, and redraws Figure 1 of the report.

## 8. The kill switch

This stops all automatic answers straight away, with no redeploy. Every ticket
after that goes to a person, and no model calls are made.

**Windows (PowerShell):**

```powershell
New-Item storage/KILL -ItemType File -Force    # stop answering
Remove-Item storage/KILL                        # resume
```

**macOS / Linux:**

```bash
mkdir -p storage && touch storage/KILL          # stop answering
rm storage/KILL                                 # resume
```

Setting `KILL_SWITCH=1` in the environment works the same way. The switch is
checked on every ticket. Run these from this folder, because the system looks
for `storage/KILL` relative to where it's started.

---

## Troubleshooting

| You see | Cause | Fix |
|---|---|---|
| `Could not open requirements file` | You're in the wrong folder | `cd` into the folder that contains `README.md` |
| `OSError ... onnxruntime ... Long Path support` | The Windows folder path is too long | Move the folder to a short path such as `C:\dev\cloudserve`, or enable long paths as administrator: `Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1`, then restart |
| `Activate.ps1 cannot be loaded ... running scripts is disabled` | PowerShell's execution policy | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once |
| `No module named ...` | The environment isn't active | Activate `.venv` (step 2) |
| Every ticket escalates; the report says `DEGRADED` | No key, a bad key, or the provider can't be reached | Run `python scripts/check_env.py` |
| A run stops with a 429 mentioning tokens per day | The daily cap is used up | Wait until 00:00 UTC |
| `--only blocked` says *Skipped* | The dataset pack isn't next to this folder | See [Data](#data) |
| A few `test_retrieve.py` tests fail with empty results (`assert []`, hit rate 0.0%) | An intermittent failure, seen once in four full runs; the cause is not yet known | Run `pytest tests/test_retrieve.py`. It passed every time it was run on its own |

## Data

- `data/documentation.json`: the 29 articles the system searches. Required, and
  committed.
- `data/sample_tickets.json`: 8 sample tickets covering all four channels.
- **The full development and validation sets are not committed.** They come
  from the Capstone Pack. Put the pack folder
  `FDE_Capstone_Complete-20260821T084330Z-1-001` **next to** this folder, not
  inside it. Tests that need the full sets skip if the pack isn't there.

## Where things are

| Path | What |
|---|---|
| `src/` | The pipeline: ingest, classify, retrieve, route, generate, validate |
| `evaluation/` | The harness, plus committed results from every gate run |
| `scripts/` | The demo, the environment check and the analysis tools |
| `tests/` | The test suite |
| `prompts/` | The prompt library, versioned |
| `docs/report/Report.md` | The project report: results, governance, decisions |
| `docs/DECISIONS.md` | Every design decision and the reasons for it |
| `docs/PRD-v1.md` | Requirements |

There is no web server or HTTP API, by design. The brief asks for one command
that takes a file in and writes results out (section 6).

Development was AI-assisted. The declaration is in the project report, §11.
