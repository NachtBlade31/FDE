"""The secret scanner's allowlist must stay honest.

CI fails the build if any credential-shaped string appears in the source or the
history (NFR-04). Two exact values are permitted, because you cannot test a
secret detector without a string shaped like a secret, and both are already in
the committed history.

An allowlist is the dangerous half of a security control. It is where a real
credential eventually hides, and it rots quietly: someone adds a third fixture,
widens a pattern to cover it, and the rule stops meaning what its name says.

So these tests hold it in place from the other side. The allowlist must contain
exactly the fixtures the tests actually use — no more, so nothing is excused that
is not needed, and no fewer, so the build does not break on a fixture that is.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CI = REPO / ".github" / "workflows" / "ci.yml"
GUARDRAIL_TESTS = REPO / "tests" / "test_guardrails.py"

# The scanner's own pattern, kept in step with ci.yml by the test below.
CREDENTIAL_SHAPES = re.compile(
    r"(gsk_[A-Za-z0-9]{20,}|sk-or-v1-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{32,}"
    r"|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36})"
)


def _ci() -> str:
    return CI.read_text(encoding="utf-8")


def _allowlisted() -> set[str]:
    match = re.search(r"^\s*ALLOWED='\((.+?)\)'", _ci(), re.MULTILINE)
    assert match, "ci.yml no longer defines an ALLOWED list in the expected form"
    return set(match.group(1).split("|"))


def _fixtures_in_tests() -> set[str]:
    """Credential-shaped strings the test suite actually uses."""
    found: set[str] = set()
    for path in (REPO / "tests").glob("*.py"):
        if path.name == "test_ci_allowlist.py":
            continue  # this file quotes them by construction
        found |= set(CREDENTIAL_SHAPES.findall(path.read_text(encoding="utf-8")))
    return found


def test_the_allowlist_covers_every_fixture_the_tests_use():
    """Otherwise the build breaks on a fixture that is doing its job."""
    missing = _fixtures_in_tests() - _allowlisted()

    assert not missing, (
        f"{missing} are used as test fixtures but are not in ci.yml's ALLOWED "
        "list, so the secret scan will fail the build."
    )


def test_the_allowlist_excuses_nothing_the_tests_do_not_use():
    """The direction that matters. An entry no test needs is an entry nobody is
    watching, and that is where a real credential goes to live."""
    unused = _allowlisted() - _fixtures_in_tests()

    assert not unused, (
        f"{unused} are allowlisted in ci.yml but appear in no test. Remove them: "
        "an allowlist entry that nothing needs is a hole, not an exception."
    )


def test_the_allowlist_is_exact_values_not_a_pattern():
    """`gsk_.*` would excuse every Groq key ever committed."""
    for entry in _allowlisted():
        assert not set(entry) & set(".*+?[]{}^$\\"), (
            f"{entry!r} contains regex metacharacters. The allowlist must be "
            "literal values; a pattern here would excuse real credentials."
        )
        assert CREDENTIAL_SHAPES.fullmatch(entry), (
            f"{entry!r} is allowlisted but is not credential-shaped, so it does "
            "not need to be — it would never have tripped the scanner."
        )


def test_the_allowlist_is_small():
    """Not a rule, a smell. Two fixtures is a test suite; ten is a habit."""
    assert len(_allowlisted()) <= 3, (
        "More than three allowlisted credential shapes. Ask whether the tests "
        "really need distinct fixtures, or whether the list has started "
        "absorbing accidents."
    )


def test_the_scanner_pattern_here_matches_the_one_in_ci():
    """If ci.yml's pattern changes, these tests must be testing the new one."""
    match = re.search(r"^\s*PATTERN='\((.+?)\)'", _ci(), re.MULTILINE)
    assert match, "ci.yml no longer defines PATTERN in the expected form"

    ci_pattern = match.group(1)
    here = CREDENTIAL_SHAPES.pattern.strip("()")
    assert ci_pattern.replace(" ", "") == here.replace(" ", "").replace("\n", ""), (
        "ci.yml's credential pattern and this file's have drifted apart:\n"
        f"  ci.yml: {ci_pattern}\n"
        f"  tests : {here}"
    )


def test_the_permitted_fixtures_are_recognisably_fake():
    """A fixture that could be mistaken for a real key is a bad fixture."""
    import base64

    allowed = _allowlisted()

    assert "gsk_ZmFrZWtleWZha2VrZXlmYWtla2V5" in allowed
    decoded = base64.b64decode("ZmFrZWtleWZha2VrZXlmYWtla2V5").decode()
    assert decoded == "fakekeyfakekeyfakekey", "the fixture should decode to a disclaimer"

    assert "ghp_" + "a" * 36 in allowed, "the other fixture should be a single repeated character"


def test_the_guardrail_fixtures_still_reach_the_guardrail():
    """The allowlist exists to let these run. If they stopped being used, the
    allowlist should go too — and this is what would notice."""
    body = GUARDRAIL_TESTS.read_text(encoding="utf-8")

    assert "test_private_data_blocks_the_response" in body
    for fixture in _allowlisted():
        assert fixture in body, (
            f"{fixture} is allowlisted for the private-data guardrail tests but "
            "no longer appears in them."
        )
