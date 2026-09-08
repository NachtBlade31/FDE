"""Harness tests — A9, A10, and the gate.

A9: "The system processes the full evaluation set in a single unattended run...
Then re-run against a file you have never seen."
A10: "That run produces a metrics report without further manual work."

The Dataset Guide is blunt about the failure this prevents: "Your harness must
accept an input path... If it only works against a file path you hardcoded, it
cannot be run, and that is treated as a failure of acceptance criterion A9."

So the properties under test are: it takes paths as arguments, it finishes
whatever the input contains, it accounts for every input record, and it produces
the report by itself.

Two guards come from validator conditions rather than the pack:
  - a run whose predictions collapse onto one class is broken, and that is
    detectable without trusting the provider's own error bookkeeping (D3-C4)
  - a degraded run must not publish business rates as though they were valid,
    because a broken run and a very conservative one look identical in the
    output (D3-C5)
"""

from __future__ import annotations

import json

import pytest

from evaluation.harness import build_report, run


class StubClient:
    """Stands in for LLMClient. `from_cache` makes it report cache hits, which is
    how a warm rehearsal is simulated without running one."""

    def __init__(self, replies=None, ok=True, from_cache=False):
        from src.llm_client import CallStats

        self._replies = list(replies or [])
        self._ok = ok
        self._from_cache = from_cache
        self.stats = CallStats()

    def complete(self, system, user, max_tokens=512):
        from src.llm_client import CompletionResult

        if not self._ok:
            self.stats.degraded = True
            self.stats.attempted += 1
            return CompletionResult(ok=False, error="provider unavailable")
        text = self._replies.pop(0) if self._replies else _CLASSIFY
        if self._from_cache:
            self.stats.cache_hits += 1
            return CompletionResult(text=text, ok=True, from_cache=True)
        self.stats.attempted += 1
        self.stats.succeeded += 1
        return CompletionResult(text=text, ok=True)


_CLASSIFY = '{"intent": "rate_limit", "urgency": "medium", "confidence": 0.97, "alternatives": []}'
_ANSWER = "Rate limits apply per organisation rather than per key [1]."


def _tickets(n=6):
    return [
        {
            "ticket_id": f"DEV-{i:04d}",
            "channel": ["email", "chat", "docs_comment", "forum"][i % 4],
            "subject": "",
            "body": "We are getting 429 responses from your api and traffic has not changed",
            "received_at": "2026-03-14T09:22:00Z",
            "customer_id": f"CUST-{i}",
            "customer_tier": ["enterprise", "business", "standard"][i % 3],
            "customer_region": "europe",
            "language_fluency": "fluent" if i % 2 else "non_fluent",
            "labels": {
                "intent": "rate_limit",
                "urgency": "medium",
                "expected_route": "auto_respond",
                "answerable_from_docs": True,
                "expected_doc_ids": ["DOC-API-001"],
                "must_not_auto_respond": False,
            },
        }
        for i in range(n)
    ]


@pytest.fixture()
def paths(tmp_path):
    def _paths(tickets=None):
        source = tmp_path / "in.json"
        source.write_text(json.dumps(tickets if tickets is not None else _tickets()), "utf-8")
        return source, tmp_path / "out"

    return _paths


def _run(paths, tickets=None, client=None, **kw):
    source, out = paths(tickets)
    return run(
        input_path=source,
        output_path=out,
        client=client or StubClient([_CLASSIFY, _ANSWER] * 60),
        storage_path=out / "storage",
        **kw,
    )


# --- A9: paths are arguments, not constants ----------------------------------


def test_the_harness_takes_an_input_and_an_output_path(paths):
    source, out = paths()
    report = run(
        input_path=source,
        output_path=out,
        client=StubClient([_CLASSIFY, _ANSWER] * 60),
        storage_path=out / "storage",
    )

    assert report["volume"]["processed"] == 6


def test_it_runs_against_a_file_it_has_never_seen(paths):
    """The hidden set has the same schema and a name we do not know."""
    unseen = [dict(t, ticket_id=f"HID-{i:04d}") for i, t in enumerate(_tickets(3))]

    report = _run(paths, tickets=unseen)

    assert report["volume"]["processed"] == 3


def test_a_missing_input_file_fails_loudly_rather_than_silently(tmp_path):
    with pytest.raises(FileNotFoundError):
        run(
            input_path=tmp_path / "nope.json",
            output_path=tmp_path / "out",
            client=StubClient(),
            storage_path=tmp_path / "s",
        )


# --- A9: every input record is accounted for ---------------------------------


def test_every_ticket_produces_an_outcome(paths):
    report = _run(paths)

    volume = report["volume"]
    assert volume["answered_automatically"] + volume["escalated"] == volume["processed"]


def test_malformed_records_are_processed_not_dropped(paths):
    tickets = _tickets(3) + ["junk", {}, {"channel": "email"}]

    report = _run(paths, tickets=tickets)

    assert report["volume"]["processed"] == 6


def test_the_run_completes_when_the_provider_is_entirely_down(paths):
    """A11: 'including disconnecting the model provider entirely.'"""
    report = _run(paths, client=StubClient(ok=False))

    assert report["volume"]["processed"] == 6
    assert report["volume"]["answered_automatically"] == 0


# --- A8: the log reconciles against the run ----------------------------------


def test_the_report_states_that_the_log_reconciles(paths):
    report = _run(paths)

    assert report["governance"]["decision_log_reconciles"] is True
    assert report["governance"]["decisions_logged"] > 0


def test_every_processed_ticket_appears_in_the_log(paths):
    report = _run(paths)

    assert report["governance"]["tickets_in_log"] == report["volume"]["processed"]


# --- A10: the report contains what the Build Spec requires -------------------


def test_the_report_has_all_four_required_groups(paths):
    report = _run(paths)

    assert {"volume", "business", "technical", "governance"} <= set(report)


def test_the_volume_group_has_the_four_required_counts(paths):
    report = _run(paths)

    assert {
        "processed",
        "answered_automatically",
        "escalated",
        "blocked_by_guardrails",
    } <= set(report["volume"])


def test_blocked_is_reported_separately_but_counted_inside_escalated(paths):
    """Design 2.3: the taxonomy choice must be auditable from the numbers."""
    volume = _run(paths)["volume"]

    assert volume["blocked_by_guardrails"] <= volume["escalated"]


def test_the_report_is_written_to_the_output_path(paths):
    source, out = paths()
    run(
        input_path=source,
        output_path=out,
        client=StubClient([_CLASSIFY, _ANSWER] * 60),
        storage_path=out / "storage",
    )

    assert (out / "metrics.json").exists()
    assert (out / "report.md").exists()


def test_per_ticket_outcomes_are_written_for_audit(paths):
    source, out = paths()
    run(
        input_path=source,
        output_path=out,
        client=StubClient([_CLASSIFY, _ANSWER] * 60),
        storage_path=out / "storage",
    )
    rows = json.loads((out / "outcomes.json").read_text("utf-8"))

    assert len(rows) == 6
    assert all("terminal_state" in r for r in rows)


def test_the_report_records_when_it_was_run_and_against_what(paths):
    """The Brief requires the evaluation date and run provenance to be stated."""
    report = _run(paths)

    assert report["run"]["generated_at"]
    assert report["run"]["input_path"]
    assert report["run"]["ticket_count"] == 6


# --- D3-C5: a degraded run must not publish rates as though valid ------------


def test_a_degraded_run_is_flagged_prominently(paths):
    report = _run(paths, client=StubClient(ok=False))

    assert report["run"]["degraded"] is True


def test_a_degraded_run_suppresses_the_business_rates(paths):
    """A broken run and a very conservative one produce identical output.

    100% escalation against a 30% target reads as a catastrophic result rather
    than a broken provider, so the rates are withheld rather than published.
    """
    report = _run(paths, client=StubClient(ok=False))

    assert report["business"]["first_contact_resolution"] is None
    assert report["business"]["withheld_reason"]


def test_a_healthy_run_publishes_the_business_rates(paths):
    report = _run(paths)

    assert report["business"]["first_contact_resolution"] is not None


# --- D3-C4: distribution collapse, independent of error bookkeeping ----------


def test_a_run_whose_predictions_collapse_onto_one_class_is_flagged(paths):
    """Detectable without trusting the provider's own error reporting.

    The empty-completion bug returned HTTP 200 with no content, so failures were
    booked as successes. Under that condition every ticket becomes the fallback
    class, which is visible in the distribution alone.
    """
    report = _run(paths, client=StubClient(ok=False))

    assert report["run"]["distribution_collapsed"] is True


def test_a_healthy_spread_is_not_flagged_as_collapsed(paths):
    varied = [
        '{"intent": "rate_limit", "urgency": "low", "confidence": 0.9, "alternatives": []}',
        _ANSWER,
        '{"intent": "billing_query", "urgency": "low", "confidence": 0.9, "alternatives": []}',
        _ANSWER,
        '{"intent": "onboarding", "urgency": "low", "confidence": 0.9, "alternatives": []}',
        _ANSWER,
    ] * 4
    report = _run(paths, tickets=_tickets(6), client=StubClient(varied))

    assert report["run"]["distribution_collapsed"] is False


def test_the_fallback_rate_is_reported(paths):
    report = _run(paths, client=StubClient(ok=False))

    assert report["technical"]["classification_fallback_rate"] == pytest.approx(1.0)


# --- the governance condition -------------------------------------------------


def test_the_report_states_the_deny_list_violation_count(paths):
    report = _run(paths)

    assert report["governance"]["deny_list_violations"] == 0


def test_a_deny_listed_ticket_is_never_auto_answered(paths):
    tickets = _tickets(2)
    for ticket in tickets:
        ticket["labels"]["intent"] = "security_incident"
        ticket["labels"]["must_not_auto_respond"] = True
        ticket["labels"]["expected_route"] = "escalate"
    reply = '{"intent": "security_incident", "urgency": "high", "confidence": 0.99, "alternatives": []}'

    report = _run(paths, tickets=tickets, client=StubClient([reply] * 10))

    assert report["governance"]["deny_list_violations"] == 0
    assert report["volume"]["answered_automatically"] == 0


# --- the human-readable report ------------------------------------------------


def test_the_markdown_report_names_the_failed_conditions(paths):
    source, out = paths()
    run(
        input_path=source,
        output_path=out,
        client=StubClient(ok=False),
        storage_path=out / "storage",
    )
    text = (out / "report.md").read_text("utf-8")

    assert "DEGRADED" in text.upper()


def test_build_report_is_pure_and_needs_no_run(paths):
    """The report is derived from outcomes, so it can be rebuilt and diffed."""
    report = _run(paths)

    assert build_report(report["_outcomes"], report["run"])["volume"] == report["volume"]


# --- a report must not present a cache replay as a timing measurement --------


def test_the_report_flags_when_most_work_came_from_cache(paths, tmp_path):
    """The same class of error as D-30, in the file the grader actually runs.

    A cache hit replays a real completion, so the functional results stay valid.
    Latency and provider-call counts do not: they measure dictionary lookups. The
    hidden run has a cold cache by definition, so a warm rehearsal must not be
    reported as though it characterised it.
    """
    source, out = paths()
    shared = out / "storage"

    run(input_path=source, output_path=out, client=StubClient([_CLASSIFY, _ANSWER] * 60),
        storage_path=shared)
    second = run(
        input_path=source,
        output_path=out,
        client=StubClient([_CLASSIFY, _ANSWER] * 60, from_cache=True),
        storage_path=shared,
    )

    assert second["run"]["cache_replay"] is True
    assert second["technical"]["processing_latency_p95_seconds"] is None
    assert second["technical"]["latency_withheld_reason"]


def test_a_cold_run_reports_its_latency(paths):
    report = _run(paths)

    assert report["run"]["cache_replay"] is False
    assert report["technical"]["processing_latency_p95_seconds"] is not None


def test_the_markdown_says_so_when_latency_is_withheld(paths, tmp_path):
    source, out = paths()
    shared = out / "storage"
    run(input_path=source, output_path=out, client=StubClient([_CLASSIFY, _ANSWER] * 60),
        storage_path=shared)
    run(input_path=source, output_path=out,
        client=StubClient([_CLASSIFY, _ANSWER] * 60, from_cache=True), storage_path=shared)

    text = (out / "report.md").read_text("utf-8")
    assert "cache" in text.lower()
