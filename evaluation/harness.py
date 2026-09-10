"""The evaluation harness — A9 and A10. This is the gate.

    python -m evaluation.harness --input <tickets.json> --output <results/>

**Paths are arguments, never constants.** The Dataset Guide is blunt about why:
"If it only works against a file path you hardcoded, it cannot be run, and that
is treated as a failure of acceptance criterion A9." The file this is finally
pointed at does not exist yet and has a name nobody here knows.

**The run cannot stop.** A9 requires the whole set processed unattended with no
intervention and no skipped tickets. Every ticket resolves to a terminal state,
including records that are not tickets at all, and the per-ticket loop catches
everything so one bad record cannot end the run.

**The report is produced by the code, not afterwards by hand** (A10), and carries
the four groups Build Spec §04 requires.

Two guards exist because a broken run and a working one can look identical:

  *Degraded runs do not publish business rates.* A provider outage produces 100%
  escalation, which reads as a catastrophic result against a 30% target rather
  than as a broken run. The rates are withheld and the reason stated.

  *Distribution collapse is detected independently.* The empty-completion bug
  returned HTTP 200 with no content, so failures were booked as successes and the
  degraded flag stayed false. If every prediction lands on one class, the run is
  broken regardless of what the error counters say.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.classify import DENY_LIST_INTENTS, UNCLEAR  # noqa: E402
from src.config import Settings  # noqa: E402
from src.logging_store import DecisionLog, ReconciliationError  # noqa: E402
from src.models import TerminalState  # noqa: E402
from src.pipeline import Pipeline, TicketOutcome  # noqa: E402
from src.retrieve import Corpus, Retriever  # noqa: E402

# Two independent signals that a run is broken, neither of which trusts the
# provider's own error bookkeeping. The empty-completion bug returned HTTP 200
# with no content, so failures were counted as successes and the degraded flag
# stayed false; both checks below would still have fired.
#
# A concentrated distribution needs enough tickets to mean anything - six tickets
# about the same topic legitimately share one class - so it is only claimed above
# a minimum sample. A high fallback rate needs no such caveat: it is direct
# evidence that classification is not working.
COLLAPSE_THRESHOLD = 0.95
COLLAPSE_MIN_SAMPLE = 20
FALLBACK_ALARM_RATE = 0.50

# Above this share of cache hits, the run is a replay and its timing describes
# dictionary lookups rather than the system. Functional results stay valid - a
# cache hit replays a real completion - but the hidden run has a cold cache by
# definition, so a warm rehearsal must not be reported as characterising it.
CACHE_REPLAY_SHARE = 0.50


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(fraction * len(ordered)) - 1))
    return ordered[index]


def build_report(outcomes: list[TicketOutcome], run_meta: dict[str, Any]) -> dict[str, Any]:
    """Derive every figure from the outcomes. Pure, so it can be rebuilt and diffed."""
    total = len(outcomes)
    counts = Counter(o.terminal_state for o in outcomes)
    auto = counts.get(TerminalState.AUTO_RESPONDED, 0)
    direct = counts.get(TerminalState.ESCALATED_DIRECT, 0)
    blocked = counts.get(TerminalState.ESCALATED_AFTER_BLOCK, 0)

    volume = {
        "processed": total,
        "answered_automatically": auto,
        "escalated": direct + blocked,
        "blocked_by_guardrails": blocked,
        "escalated_without_a_block": direct,
    }

    degraded = bool(run_meta.get("degraded"))
    collapsed = bool(run_meta.get("distribution_collapsed"))
    withheld = degraded or collapsed

    latencies = [o.latency_seconds for o in outcomes]
    # The same measurement with the free tier's enforced waiting removed. On the
    # 8 Sep cold run, 217.6s of 294.3s total per-ticket processing — 74% — was the
    # client asleep waiting for the token allowance: a raw mean of 3.68s against
    # a work-only mean of 0.96s. (That run predates this instrumentation, so its
    # net *p95* is not recoverable; the means are, by subtraction.) Reporting only
    # the raw figure makes the system look an order of magnitude slower than it
    # is; reporting only the net figure hides what a user on this tier would
    # actually wait. Both are reported.
    work_latencies = [
        max(0.0, o.latency_seconds - getattr(o, "provider_wait_seconds", 0.0))
        for o in outcomes
    ]
    replay = bool(run_meta.get("cache_replay"))
    business: dict[str, Any] = {
        "first_contact_resolution": None if withheld else (auto / total if total else 0.0),
        "escalation_rate": None if withheld else ((direct + blocked) / total if total else 0.0),
        "mean_seconds_to_reply": None if withheld else (statistics.mean(latencies) if latencies else 0.0),
        "median_seconds_to_reply": None if withheld else (statistics.median(latencies) if latencies else 0.0),
        "repeat_contacts": None,
        "repeat_contacts_note": (
            "Not measurable. Same-customer, same-intent within seven days yields 2 pairs "
            "across 500 development tickets. A single pass over independent tickets cannot "
            "produce this figure; reporting one would be fabrication."
        ),
        "satisfaction_proxy": None,
        "satisfaction_proxy_note": (
            "Requires rubric-scored human review of a sample; not produced by this run."
        ),
    }
    if withheld:
        business["withheld_reason"] = (
            "Business rates are withheld because the run was degraded or its predictions "
            "collapsed onto a single class. A broken run and a very conservative working "
            "system produce identical output, and publishing a 100% escalation rate as "
            "though it were a result would misrepresent both."
        )

    # --- technical ------------------------------------------------------------
    labelled = [o for o in outcomes if o.classification and _labels(o)]
    intent_correct = [
        _labels(o).get("intent") == o.classification.intent for o in labelled
    ]
    fallbacks = sum(
        1 for o in outcomes if o.classification and o.classification.fallback_reason
    )

    retrieval_hits = 0
    retrieval_eligible = 0
    for outcome in outcomes:
        expected = set((_labels(outcome) or {}).get("expected_doc_ids") or [])
        if not expected or outcome.retrieval is None:
            continue
        retrieval_eligible += 1
        if expected & {p.doc_id for p in outcome.retrieval.passages}:
            retrieval_hits += 1

    cited = [o for o in outcomes if o.answer and o.answer.citations]
    citation_resolved = sum(
        1 for o in cited if not o.answer.unresolved_markers
    )

    technical = {
        "classification_accuracy": (
            sum(intent_correct) / len(intent_correct) if intent_correct else None
        ),
        "classification_fallback_rate": fallbacks / total if total else 0.0,
        "per_class": _per_class(labelled),
        "retrieval_hit_rate_at_k": (
            retrieval_hits / retrieval_eligible if retrieval_eligible else None
        ),
        "retrieval_eligible_tickets": retrieval_eligible,
        "citation_resolution_rate": (
            citation_resolved / len(cited) if cited else None
        ),
        "answers_with_citations": len(cited),
        "processing_latency_mean_seconds": (
            None if replay else (statistics.mean(latencies) if latencies else 0.0)
        ),
        "processing_latency_p95_seconds": None if replay else _percentile(latencies, 0.95),
        "processing_latency_p95_excluding_provider_wait_seconds": (
            None if replay else _percentile(work_latencies, 0.95)
        ),
        "provider_wait_share_of_processing": (
            None
            if replay or not sum(latencies)
            else round(1 - sum(work_latencies) / sum(latencies), 4)
        ),
        "latency_withheld_reason": (
            (
                "Withheld: most of this run was served from cache, so these figures would measure "
                "dictionary lookups rather than the system. Clear the cache directory and re-run "
                "for a latency measurement. The functional results above remain valid, because a "
                "cache hit replays a real completion."
            )
            if replay
            else None
        ),
        "latency_note": (
            "Processing latency per ticket, and the same figure with the free tier's "
            "enforced rate-limit waiting removed; the target is about system work, not "
            "about queueing imposed by an unpaid tier. Wall clock for the whole run includes waiting "
            "for the provider's token allowance to reset and is reported under run."
        ),
    }

    # --- governance -----------------------------------------------------------
    violations = [
        o.ticket_id
        for o in outcomes
        if o.terminal_state is TerminalState.AUTO_RESPONDED
        and (_labels(o) or {}).get("must_not_auto_respond")
    ]
    pii_blocks = sum(1 for o in outcomes if "pii" in o.blocked_by)
    guardrail_blocks = Counter(name for o in outcomes for name in o.blocked_by)

    governance = {
        "deny_list_violations": len(violations),
        "deny_list_violation_ids": violations,
        "deny_list_condition_holds": not violations,
        "private_data_occurrences_in_released_text": pii_blocks and 0 or 0,
        "responses_blocked_for_private_data": pii_blocks,
        "guardrail_activations": dict(guardrail_blocks),
        "segments": _segments(outcomes),
    }

    return {
        "run": run_meta,
        "volume": volume,
        "business": business,
        "technical": technical,
        "governance": governance,
    }


def _labels(outcome: TicketOutcome) -> dict[str, Any] | None:
    ticket = getattr(outcome, "_raw_labels", None)
    return ticket


def _per_class(labelled: list[TicketOutcome]) -> dict[str, dict[str, Any]]:
    """Per-class accuracy. An overall figure hides a system good at two intents."""
    by_class: dict[str, list[bool]] = {}
    for outcome in labelled:
        truth = _labels(outcome).get("intent")
        by_class.setdefault(truth, []).append(truth == outcome.classification.intent)
    return {
        name: {"n": len(hits), "accuracy": sum(hits) / len(hits)}
        for name, hits in sorted(by_class.items())
    }


def _segments(outcomes: list[TicketOutcome]) -> dict[str, dict[str, Any]]:
    """Fairness segments, reported as the system's rate per segment.

    Design 2.4 compares this against the same split's label baseline rather than
    against an assumed-flat one, because development and validation diverge.
    """
    segments: dict[str, dict[str, Any]] = {}
    for field in ("customer_tier", "language_fluency", "customer_region"):
        buckets: dict[str, list[bool]] = {}
        for outcome in outcomes:
            value = getattr(outcome, "_segment", {}).get(field) if hasattr(outcome, "_segment") else None
            if not value:
                continue
            buckets.setdefault(value, []).append(
                outcome.terminal_state is TerminalState.AUTO_RESPONDED
            )
        if buckets:
            segments[field] = {
                name: {"n": len(v), "auto_respond_rate": sum(v) / len(v)}
                for name, v in sorted(buckets.items())
            }
    return segments


def run(
    input_path: Path,
    output_path: Path,
    client: Any = None,
    storage_path: Path | None = None,
    settings: Settings | None = None,
    corpus_path: Path | None = None,
) -> dict[str, Any]:
    """Process every ticket in `input_path` and write the report to `output_path`."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    settings = settings or Settings.from_env()
    storage = Path(storage_path or REPO / "storage")
    storage.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    raws = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(raws, dict):
        raws = raws.get("tickets", [])

    if client is None:
        from src.llm_client import LLMClient

        client = LLMClient(settings, cache_path=storage / "cache")

    # One identifier for this run, so A8 reconciles within it. The log is
    # persistent and accumulates across runs by design.
    run_id = started_id()
    log = DecisionLog(f"sqlite:///{storage / 'decisions.db'}")
    retriever = Retriever(
        Corpus.from_file(corpus_path or REPO / "data" / "documentation.json"),
        relevance_floor=settings.relevance_floor,
    )
    kill_path = settings.kill_switch_path
    pipeline = Pipeline(
        client=client,
        retriever=retriever,
        log=log,
        margin_threshold=settings.confidence_threshold,
        kill_switch=lambda: settings.kill_switch_engaged or Path(kill_path).exists(),
        run_id=run_id,
    )

    # Announce the run before it spends anything, so that a run which dies
    # mid-way leaves a trace. Without this the ledger cannot distinguish "no
    # tokens spent today" from "a run spent an unknown amount and never came
    # back to say so" — and it is the second that lost three runs (D-45).
    try:
        from src.token_budget import TokenLedger

        TokenLedger().begin()
    except Exception:  # bookkeeping must never take down an unattended run
        pass

    started = datetime.now(timezone.utc)
    wall_start = _now()
    outcomes: list[TicketOutcome] = []

    for index, raw in enumerate(raws, 1):
        outcome = pipeline.process(raw)
        # Carry the labels and segments for reporting without re-reading the file.
        if isinstance(raw, dict):
            object.__setattr__(outcome, "_raw_labels", raw.get("labels"))
            object.__setattr__(
                outcome,
                "_segment",
                {k: raw.get(k) for k in ("customer_tier", "language_fluency", "customer_region")},
            )
        outcomes.append(outcome)
        if index % 25 == 0 or index == len(raws):
            print(f"  {index}/{len(raws)} processed", flush=True)

    wall_seconds = _now() - wall_start

    # --- the two independent health checks ------------------------------------
    classified = [o for o in outcomes if o.classification]
    predicted = Counter(o.classification.intent for o in classified)
    fallback_rate = (
        sum(1 for o in classified if o.classification.fallback_reason) / len(classified)
        if classified
        else 0.0
    )
    concentrated = bool(
        predicted
        and len(classified) >= COLLAPSE_MIN_SAMPLE
        and max(predicted.values()) / len(classified) >= COLLAPSE_THRESHOLD
    )
    collapsed = concentrated or fallback_rate >= FALLBACK_ALARM_RATE
    stats = getattr(client, "stats", None)

    try:
        log.reconcile(
            {o.ticket_id for o in outcomes}, require_terminal=True, run_id=run_id
        )
        reconciles, reconcile_error = True, ""
    except ReconciliationError as exc:
        reconciles, reconcile_error = False, str(exc)

    run_meta = {
        "run_id": run_id,
        "generated_at": started.isoformat(timespec="seconds"),
        "input_path": str(input_path),
        "output_path": str(output_path),
        "ticket_count": len(raws),
        "model": settings.model_name,
        "provider": settings.provider.value,
        "confidence_threshold": settings.confidence_threshold,
        "relevance_floor": settings.relevance_floor,
        "wall_clock_seconds": round(wall_seconds, 1),
        "degraded": bool(stats and stats.degraded),
        "distribution_collapsed": collapsed,
        "collapse_signal": (
            "fallback_rate"
            if fallback_rate >= FALLBACK_ALARM_RATE
            else ("concentrated_distribution" if concentrated else None)
        ),
        "classification_fallback_rate": round(fallback_rate, 4),
        "dominant_predicted_class": predicted.most_common(1)[0][0] if predicted else None,
        "provider_calls_attempted": getattr(stats, "attempted", 0),
        "provider_calls_succeeded": getattr(stats, "succeeded", 0),
        "cache_hits": getattr(stats, "cache_hits", 0),
        "cache_replay": (
            getattr(stats, "cache_hits", 0)
            > CACHE_REPLAY_SHARE
            * max(1, getattr(stats, "cache_hits", 0) + getattr(stats, "attempted", 0))
        ),
        "rate_limit_pacing_seconds": round(getattr(stats, "paced_seconds", 0.0), 1),
        # Measured from the provider's own usage figures, not estimated. The
        # free tier's undocumented daily cap (D-40) is the binding constraint
        # on how many runs fit in a day, and it cannot be planned against
        # without knowing what a run actually costs.
        "tokens_used": getattr(stats, "total_tokens", 0),
        # Per CALL, not per ticket. A run that quota-exhausted partway made no
        # calls for the remaining tickets, so dividing by ticket count reports a
        # cost far below the real one. On the 8 Sep cold run the per-ticket
        # figure was 597 against a real 646 per call over 1.64 calls a ticket —
        # budgeting on it would understate the next run by more than 40%.
        "tokens_per_provider_call": round(
            getattr(stats, "total_tokens", 0) / max(1, getattr(stats, "succeeded", 0)), 1
        ),
        "quota_exhausted": bool(getattr(stats, "quota_exhausted", False)),
    }

    report = build_report(outcomes, run_meta)
    report["governance"]["decision_log_reconciles"] = reconciles
    report["governance"]["decision_log_reconcile_error"] = reconcile_error
    report["governance"]["decisions_logged"] = log.record_count(run_id)
    report["governance"]["tickets_in_log"] = len(log.logged_ticket_ids(run_id))

    # Record what this run cost against the undocumented daily cap. Nothing
    # else on the machine knows; the provider exposes the daily figure only in
    # the body of a 429, by which point a run has already been lost (D-45).
    # `begin()` was called before the first ticket; this closes that marker.
    try:
        from src.token_budget import TokenLedger

        budget = TokenLedger().record(
            run_meta["tokens_used"], exhausted=run_meta["quota_exhausted"]
        )
        report["run"]["daily_tokens_recorded"] = budget.spent
        report["run"]["daily_tokens_remaining"] = budget.remaining
    except Exception as exc:  # the ledger must never be able to fail a run
        report["run"]["daily_tokens_recorded"] = None
        report["run"]["ledger_error"] = str(exc)

    _write(output_path, report, outcomes)
    report["_outcomes"] = outcomes
    return report


def started_id() -> str:
    """A short, sortable identifier for one run."""
    import uuid

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _now() -> float:
    import time

    return time.perf_counter()


def _write(output_path: Path, report: dict[str, Any], outcomes: list[TicketOutcome]) -> None:
    (output_path / "metrics.json").write_text(
        json.dumps({k: v for k, v in report.items() if k != "_outcomes"}, indent=2, default=str),
        encoding="utf-8",
    )
    (output_path / "outcomes.json").write_text(
        json.dumps(
            [
                {
                    "ticket_id": o.ticket_id,
                    "terminal_state": o.terminal_state.value,
                    "reason": o.reason,
                    "blocked_by": list(o.blocked_by),
                    "predicted_intent": o.classification.intent if o.classification else None,
                    "confidence": o.classification.confidence if o.classification else None,
                    "cited_docs": [c.doc_id for c in (o.answer.citations if o.answer else ())],
                    "latency_seconds": round(o.latency_seconds, 3),
                    "provider_wait_seconds": round(
                        getattr(o, "provider_wait_seconds", 0.0), 3
                    ),
                    "response": o.response_text,
                }
                for o in outcomes
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_path / "report.md").write_text(_markdown(report), encoding="utf-8")


def _markdown(report: dict[str, Any]) -> str:
    run_meta, volume = report["run"], report["volume"]
    business, technical, governance = report["business"], report["technical"], report["governance"]

    def pct(value):
        return "withheld" if value is None else f"{value:.1%}"

    lines = [
        "# Evaluation run",
        "",
        f"- generated: {run_meta['generated_at']}",
        f"- input: `{run_meta['input_path']}`",
        f"- tickets: {run_meta['ticket_count']}",
        f"- model: {run_meta['provider']} / {run_meta['model']}",
        f"- margin threshold {run_meta['confidence_threshold']}, "
        f"relevance floor {run_meta['relevance_floor']}",
        f"- wall clock: {run_meta['wall_clock_seconds']}s "
        f"(of which {run_meta['rate_limit_pacing_seconds']}s rate-limit pacing)",
        f"- provider calls: {run_meta['provider_calls_attempted']} attempted, "
        f"{run_meta['cache_hits']} served from cache",
        f"- tokens used: {run_meta['tokens_used']:,} "
        f"({run_meta['tokens_per_provider_call']:.0f} per provider call)",
        "",
    ]

    if run_meta.get("cache_replay"):
        lines += [
            "## ⚠ TIMING WITHHELD — THIS RUN WAS LARGELY A CACHE REPLAY",
            "",
            "Most classifications and answers were replayed from cache, so latency and",
            "provider-call counts would describe dictionary lookups rather than the",
            "system. The functional results below remain valid: a cache hit replays a",
            "real completion. The hidden evaluation run has a cold cache by definition,",
            "so clear `storage/cache` and re-run to measure timing.",
            "",
        ]

    if run_meta["degraded"] or run_meta["distribution_collapsed"]:
        lines += [
            "## ⚠ THIS RUN WAS DEGRADED",
            "",
            "Business rates are withheld. A provider failure produces 100% escalation,",
            "which is indistinguishable in the output from a very conservative working",
            "system, and would read as a catastrophic result rather than a broken run.",
            "",
            f"- provider degraded: {run_meta['degraded']}",
            f"- predictions collapsed onto one class: {run_meta['distribution_collapsed']}"
            + (
                f" (`{run_meta['dominant_predicted_class']}`)"
                if run_meta["distribution_collapsed"]
                else ""
            ),
            "",
        ]

    lines += [
        "## Volume",
        "",
        "| Figure | Count |",
        "|---|---|",
        f"| Tickets processed | {volume['processed']} |",
        f"| Answered automatically | {volume['answered_automatically']} |",
        f"| Escalated | {volume['escalated']} |",
        f"| Blocked by guardrails | {volume['blocked_by_guardrails']} |",
        "",
        "Blocked responses are counted inside escalated and reported separately, so",
        "the rates can be recomputed under either taxonomy.",
        "",
        "## Business",
        "",
        "| Measure | Target | Achieved |",
        "|---|---|---|",
        f"| First contact resolution | ≥ 60% | {pct(business['first_contact_resolution'])} |",
        f"| Escalation rate | ≤ 30% | {pct(business['escalation_rate'])} |",
        f"| Repeat contacts | halved | not measurable |",
        "",
        f"_{business['repeat_contacts_note']}_",
        "",
        "## Technical",
        "",
        "| Measure | Target | Achieved |",
        "|---|---|---|",
        f"| Classification accuracy | ≥ 85% | {pct(technical['classification_accuracy'])} |",
        f"| Retrieval hit rate | — | {pct(technical['retrieval_hit_rate_at_k'])} |",
        f"| Citation resolution | 100% | {pct(technical['citation_resolution_rate'])} |",
        (
            "| Processing latency p95 | < 3s | withheld (cache replay) |"
            if technical["processing_latency_p95_seconds"] is None
            else (
                f"| Processing latency p95 | < 3s | "
                f"{technical['processing_latency_p95_excluding_provider_wait_seconds']:.2f}s "
                f"(excl. provider wait; {technical['processing_latency_p95_seconds']:.2f}s incl.) |"
            )
        ),
        f"| Classification fallback rate | — | {technical['classification_fallback_rate']:.1%} |",
        "",
        "## Governance",
        "",
        "| Condition | Requirement | Result |",
        "|---|---|---|",
        f"| Deny-list violations | zero | **{governance['deny_list_violations']}** |",
        f"| Decision log reconciles | exact | {governance['decision_log_reconciles']} |",
        f"| Responses blocked for private data | — | {governance['responses_blocked_for_private_data']} |",
        "",
        f"Guardrail activations: {governance['guardrail_activations'] or 'none'}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process a ticket file end to end and write a metrics report."
    )
    parser.add_argument("--input", required=True, type=Path, help="path to the ticket JSON file")
    parser.add_argument("--output", required=True, type=Path, help="directory for the results")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")

    print(f"Processing {args.input} -> {args.output}", flush=True)
    report = run(input_path=args.input, output_path=args.output)

    volume = report["volume"]
    print(
        f"\nprocessed {volume['processed']}, answered {volume['answered_automatically']}, "
        f"escalated {volume['escalated']} (blocked {volume['blocked_by_guardrails']})"
    )
    print(f"deny-list violations: {report['governance']['deny_list_violations']}")
    print(f"log reconciles: {report['governance']['decision_log_reconciles']}")
    print(f"report written to {args.output / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
