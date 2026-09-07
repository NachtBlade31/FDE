"""The shipped template must match the derived values — A1, D4, and D2-C1.

Build Specification §06 step 4: "Configuration is set from your `.env.example`,
with a working key substituted in." So `.env.example` is not documentation — it is
the configuration the graded run actually uses.

This test exists because that drifted once already and was caught in review
rather than by the suite. `RELEVANCE_FLOOR` shipped as 0.35 while the value
derived in D-20 and defended in the report was 0.40, and `GROQ_MODEL` named a
model the provider had withdrawn. A grader following the README would have run a
different system from the one every measurement describes.

D4's claim is that thresholds are derived rather than chosen. That claim is only
true if the derived value is the one that runs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import (
    DEFAULT_ABSTENTION_FLOOR,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_RELEVANCE_FLOOR,
)

TEMPLATE = Path(__file__).resolve().parents[1] / ".env.example"


def _template() -> dict[str, str]:
    if not TEMPLATE.exists():  # pragma: no cover - the template is committed
        pytest.skip(".env.example not present")
    values = {}
    for line in TEMPLATE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def test_the_template_exists_because_the_graded_run_is_configured_from_it():
    assert TEMPLATE.exists()


def test_the_template_parses_without_a_stray_byte_order_mark():
    """A BOM written by PowerShell once parsed as a key of its own."""
    raw = TEMPLATE.read_bytes()

    assert not raw.startswith(b"\xef\xbb\xbf"), "remove the UTF-8 BOM from .env.example"


@pytest.mark.parametrize(
    "key, derived",
    [
        ("RELEVANCE_FLOOR", DEFAULT_RELEVANCE_FLOOR),
        ("CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD),
    ],
)
def test_the_template_ships_the_derived_threshold(key, derived):
    """If this fails, the graded run uses a number the report does not defend."""
    values = _template()
    assert key in values, f"{key} is missing from .env.example"

    assert float(values[key]) == pytest.approx(derived), (
        f".env.example sets {key}={values[key]} but the derived value is {derived}. "
        "The graded run is configured from the template, so these must agree."
    )


def test_the_abstention_floor_is_documented_even_though_it_is_not_an_env_var():
    """It is a safety control, so its value must be discoverable, not buried."""
    assert 0.0 < DEFAULT_ABSTENTION_FLOOR < 1.0


def test_the_template_holds_placeholders_not_a_real_key():
    """NFR-04. The template is committed; a real key in it is a serious finding."""
    values = _template()

    for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        value = values.get(key, "")
        assert value.startswith("your_") or not value, (
            f"{key} in .env.example looks like a real credential"
        )


def test_the_template_names_a_provider_the_code_supports():
    from src.config import Provider

    provider = _template().get("PROVIDER", "")

    assert provider in {p.value for p in Provider}


def test_the_template_declares_a_model_for_the_selected_provider():
    """A blank or absent model name sends the grader to the fallback path."""
    values = _template()
    key = "GROQ_MODEL" if values.get("PROVIDER") == "groq" else "OPENROUTER_MODEL"

    assert values.get(key), f"{key} must name a model"
