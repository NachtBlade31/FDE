"""Retracted claims and superseded figures must not survive anywhere.

This project has now had **nine** instances of one defect: a figure is corrected,
or a claim retracted, and the change reaches some of the documents carrying it
but not all. Every one was caught by a human reading carefully. Every one would
have been caught by `grep`.

The shape is always the same — a number computed from a constant that has since
changed, or a sentence whose evidence was withdrawn, sitting in a second document
nobody re-read. Three of the four blocking findings in the sixth validator review
were this, including `well powered (n=21)` surviving in the conclusions after the
decision log had explicitly retracted it two hundred lines earlier.

So the check is mechanical and runs in the suite. Each entry names a string and
**why** it was retracted, because a bare blocklist rots into noise once nobody
remembers what the strings were for.

A retracted phrase may still appear — *provided it is retracted in place*. Saying
"I reported X, X was wrong, here is what replaced it" is more useful than deleting
X and leaving the reader to wonder what changed. What must never happen is the
phrase standing alone, asserted, somewhere else.

Adding to this list is the cost of retracting a claim. That is the point: it makes
a retraction a code change rather than an intention.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

DELIVERABLES = [
    REPO / "docs" / "report" / "Report.md",
    REPO / "docs" / "workbooks" / "Governance_Framework.md",
    REPO / "docs" / "workbooks" / "Stage_5_PRD_Revision_Log.md",
    REPO / "docs" / "workbooks" / "Stage_1_Discovery_Workbook.md",
    REPO / "docs" / "workbooks" / "Stage_3_Prompt_Library.md",
    REPO / "docs" / "workbooks" / "Stage_4_Sprint_Plan.md",
    REPO / "README.md",
    REPO / "docs" / "VIDEO_SCRIPT.md",
]

# The decision log and validator log deliberately preserve what was believed at
# the time. They are held to the same rule: the correction must be adjacent.
HISTORICAL = [REPO / "docs" / "DECISIONS.md", REPO / "docs" / "VALIDATOR.md"]

RETRACTED: list[tuple[str, str]] = [
    (
        "well powered (n=21)",
        "Retracted in review 9. asia_pacific's Wilson interval is 37 points wide "
        "and its Holm-adjusted p is 0.424. It is the largest gap at the largest n, "
        "not a well-powered result.",
    ),
    (
        "moved by up to 3 points",
        "False. Six of eleven segments are identical between the two runs and the "
        "largest movement is north_america at 7.4pt. This sentence was the entire "
        "basis for calling asia_pacific a lead.",
    ),
    (
        "0.8% pessimistic",
        "Computed with the retired 646 tokens/call constant. The live constant is "
        "652 and the margin is 1.8%.",
    ),
    (
        "84,755",
        "estimated_run_cost(80) under the retired 646 constant. It is now 85,542.",
    ),
    (
        "1.35 calls",
        "Taken from a degraded run's auto-respond rate, depressed by the 26 tickets "
        "that never reached the model. The shipped figure is 1.64.",
    ),
    (
        "65.5% / 34.5%",
        "The margin<=0.60 row of the sweep, i.e. the margin gate switched off. The "
        "shipped configuration is 64.0% / 36.0%.",
    ),
    (
        "48.8%",
        "From a validation run whose artifact was overwritten. No committed "
        "artifact supports it.",
    ),
    ("82.5%", "Same overwritten run as 48.8%."),
    (
        "0.84s",
        "Same overwritten run, and it conflated a classification-only run with a "
        "full pipeline run. The measured net p95 is 2.66s (run 2) / 3.08s (run 1).",
    ),
    (
        "contradicted by the one healthy run",
        "Sofia's hypothesis is not refuted, it is undetectable: non_fluent is "
        "+5.3pt on a 4/5 discordant split, p = 1.00 on 19 tickets.",
    ),
    (
        "163 tickets",
        "Assumed 1,225 tokens a ticket before any run was measured. Measured, the "
        "daily cap is about 187 tickets.",
    ),
]

RETRACTION_MARKERS = (
    "supersede", "Superseded", "retract", "Retract", "corrected", "correction",
    "was wrong", "too strong", "no longer", "not restated", "predates",
    "originally", "first wrote", "first published", "first reported",
    "artifact since overwritten", "is false", "withdrawn", "earlier draft",
    "An earlier version", "overstated", "cannot be checked",
)

WINDOW = 1400


def _bodies(paths):
    for path in paths:
        if path.exists():
            yield path, path.read_text(encoding="utf-8")


@pytest.mark.parametrize("phrase,reason", RETRACTED, ids=[p for p, _ in RETRACTED])
def test_a_retracted_claim_is_never_asserted_unretracted(phrase, reason):
    """Every occurrence, in every document, must sit beside its own correction."""
    offenders = []
    for path, body in _bodies(DELIVERABLES + HISTORICAL):
        for match in re.finditer(re.escape(phrase), body):
            window = body[max(0, match.start() - WINDOW) : match.end() + WINDOW]
            if not any(marker in window for marker in RETRACTION_MARKERS):
                line = body.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{line}")

    assert not offenders, (
        f"{phrase!r} is asserted without a retraction at {offenders}.\n"
        f"{reason}\n"
        "Either remove it, or retract it in place: state that it was reported, "
        "that it is wrong, and what replaced it."
    )


# --- the conclusions must agree with the results -----------------------------


def test_the_conclusions_quote_the_headline_run():
    """Run 2 is the headline run. Section 10.1 quoted run 1's 53.8% FCR and its
    6.25-point ceiling gap as the delivered result, under a run-2 report."""
    report = (REPO / "docs" / "report" / "Report.md").read_text(encoding="utf-8")
    conclusions = report[report.index("## 10. Conclusions") :]

    assert "6.25 points" not in conclusions, (
        "6.25pt is run 1's gap to the label ceiling. Run 2 is 3.75 points under it."
    )
    for stray in ("53.8%", "46.3%"):
        assert stray not in conclusions, (
            f"{stray} is a run-1 figure. The conclusions must quote run 2, or name "
            "the run explicitly."
        )


def test_the_summary_and_the_conclusions_count_targets_the_same_way():
    """They disagreed: three missed versus four, out of eight versus nine."""
    report = (REPO / "docs" / "report" / "Report.md").read_text(encoding="utf-8")

    assert "Three targets missed" in report
    assert "Four of nine targets are missed" not in report, (
        "The section 1 table has eight targets and three are missed."
    )


def test_the_latency_target_is_never_reported_as_settled():
    """It is met in run 2 (2.66s) and missed in run 1 (3.08s). Any document that
    states it either way is picking the answer."""
    for path, body in _bodies(DELIVERABLES):
        assert "is reported as missed" not in body, (
            f"{path.name} settles the latency target; it straddles the run-to-run "
            "band and both runs are committed."
        )


# --- the README's commands must exist ------------------------------------------
#
# The README documented `python -m src.api` "from Day 6". It was never built, so
# anyone following the instructions literally hit `No module named src.api` —
# and acceptance criterion A1 is judged by following the README literally. It
# survived twelve validator reviews because every one of them read the code and
# the claims, and none of them ran the setup instructions as written.

STDLIB_MODULES = {"venv", "pip"}


# The README gives Windows steps in PowerShell blocks and the rest in bash
# blocks; a check that read only one fence type would pass while the other rotted.
COMMAND_FENCES = ("```bash", "```powershell", "```sh")


def _documented_commands() -> list[str]:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    inside, commands = False, []
    for line in readme.splitlines():
        if line.strip().startswith("```"):
            inside = line.strip().startswith(COMMAND_FENCES)
            continue
        if inside and line.strip().startswith(("python ", "pytest ")):
            commands.append(line.strip())
    return commands


def test_the_readme_documents_commands_at_all():
    """Guards the two checks below: an empty list would make both pass vacuously."""
    commands = _documented_commands()
    assert any("evaluation.harness" in c for c in commands)
    assert any("scripts/demo.py" in c for c in commands)


def test_every_python_module_the_readme_documents_exists():
    missing = []
    for command in _documented_commands():
        parts = command.split()
        if "-m" not in parts:
            continue
        module = parts[parts.index("-m") + 1]
        if module in STDLIB_MODULES:
            continue
        path = REPO / Path(*module.split(".")).with_suffix(".py")
        package = REPO / Path(*module.split(".")) / "__main__.py"
        if not path.exists() and not package.exists():
            missing.append(f"{command!r} -> no {path.relative_to(REPO).as_posix()}")

    assert not missing, (
        "The README documents commands that cannot run:\n  " + "\n  ".join(missing)
    )


def test_every_script_the_readme_documents_exists():
    missing = []
    for command in _documented_commands():
        for token in command.split():
            if token.endswith(".py") and not (REPO / token).exists():
                missing.append(f"{command!r} -> no {token}")

    assert not missing, (
        "The README documents scripts that do not exist:\n  " + "\n  ".join(missing)
    )
