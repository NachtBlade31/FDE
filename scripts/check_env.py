"""Preflight check: confirm configuration resolves and a provider is reachable.

Prints booleans and lengths only for the credential — never the key itself. It
does make one real, billable provider call, for the reason below. Run it after
editing .env and before a graded run:

    python scripts/check_env.py

**What this script can and cannot tell you.** It can tell you the configuration
resolves, the key works, and that a full-sized call goes through right now. It
cannot tell you a whole run will fit in today's budget — the provider publishes
no daily-remaining figure, only a per-minute one. That gap is why the local
ledger exists (`src/token_budget.py`), and why a green probe here is reported as
"one call fits" rather than "you are good to go".
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.config import Settings  # noqa: E402
from src.token_budget import TokenLedger  # noqa: E402

# The largest call the pipeline makes. Classification reserves 500
# (src/classify.py) and generation reserves 700 (src/generate.py); a probe that
# only clears the smaller one does not show the larger one will go through.
PROBE_MAX_TOKENS = 700

# What a run costs, from artifacts rather than assumption — and rounded the
# pessimistic way, because this number feeds a gate whose contract is that it may
# rule a run out but must never wave one through.
#
# Cost per call: 47,774 tokens over 74 successful calls in
# `evaluation/results/2026-09-08-gate-run-cold/metrics.json` = 645.6, rounded UP to 646. That is a
# floor: calls that raised were billed but recorded nothing, and the blend is 73%
# cheap classifications (500 max_tokens) to 27% generations (700, plus retrieved
# passages in the prompt), so a healthier run's mix costs more per call.
#
# Calls per ticket: one classification always, plus one generation for each
# ticket that auto-responds — so 1 + FCR. The FCR to use is NOT the degraded cold
# run's 33.75%, which is depressed by 26 tickets that never reached the model;
# using it here would let a degraded run's failure make the next run look cheap.
# The shipped-configuration figure is 64.0% on 200 development tickets
# (`evaluation/results/2026-09-07-routing-200.txt`, margin 0.85), giving 1.64.
TOKENS_PER_PROVIDER_CALL = 646
CALLS_PER_TICKET = 1.64  # 1 classification + 0.64 generation, at the shipped 0.85


def estimated_run_cost(tickets: int) -> int:
    """Tokens a run of this size should be expected to need.

    Deliberately the pessimistic end. An optimistic estimate makes `fits()`
    return True when it should not, which is the exact failure D-45 exists to
    prevent — so where the evidence gives a range, this returns its top.
    """
    return int(tickets * CALLS_PER_TICKET * TOKENS_PER_PROVIDER_CALL)


def budget_report(tickets: int = 120) -> str:
    view = TokenLedger().view()
    return "Daily token budget (local ledger):\n" + view.explain(
        estimated_run_cost(tickets)
    )


def gate(view, tickets: int = 120) -> tuple[bool, str]:
    """May a run of this size be started? Returns (allowed, why not).

    Separated from `main()` so it can be tested without a provider. This is the
    control that is supposed to stop a fourth run being lost to the daily cap,
    and while it lived inside `main()` nothing exercised it end to end — the
    tests reached past it to `view.fits()` and asserted on that instead, which
    is not the same thing as asserting the script refuses.
    """
    cost = estimated_run_cost(tickets)
    if view.fits(cost):
        return True, ""
    if view.exhausted:
        return False, (
            f"  The provider already refused a run today with 'quota exhausted'.\n"
            f"  A {tickets}-ticket run needs about {cost:,} tokens and will not get\n"
            f"  them. Probing would spend tokens to learn nothing. Wait for 00:00 UTC."
        )
    if not view.complete:
        return False, (
            "  A run started today and never recorded what it spent, so the figure\n"
            "  above is a floor rather than a total. Refusing on incomplete records\n"
            "  rather than guessing downwards. Wait for 00:00 UTC, or clear the\n"
            "  stale entry in storage/token_ledger.json if you know the run died."
        )
    return False, (
        f"  A {tickets}-ticket run needs about {cost:,} tokens and only\n"
        f"  {view.remaining:,} remain on this UTC day. Probing would spend tokens\n"
        f"  to learn nothing. Wait for 00:00 UTC."
    )


def main() -> int:
    settings = Settings.from_env()

    print(f"provider             : {settings.provider.value}")
    print(f"model                : {settings.model_name}")
    print(f"has_model_access     : {settings.has_model_access}")
    print(f"key length plausible : {20 < len(settings.api_key) < 200}")
    print(f"repr hides the key   : {settings.api_key not in repr(settings)}")
    print(f"kill switch engaged  : {settings.kill_switch_engaged}")
    print(f"confidence threshold : {settings.confidence_threshold}")
    print(f"relevance floor      : {settings.relevance_floor}")

    if not settings.has_model_access:
        print("\nNo usable key found. The system will run retrieval-only and")
        print("escalate every ticket. Set a key in .env to enable generation.")
        return 1

    print("\nConfiguration resolves. Model access available.\n")
    print(budget_report())

    allowed, why_not = gate(TokenLedger().view(), 120)
    if not allowed:
        print()
        print(why_not)
        return 1

    # A representative probe, not a token one, and never a cached one.
    #
    # Two ways this check has lied. First, a five-token request succeeds against
    # a nearly-exhausted daily budget while a real classification call fails,
    # because the provider checks the requested size against what remains — so a
    # trivial probe reported health the actual workload did not have. Second,
    # `complete()` returns a cache hit before any network call, and the probe
    # text was fixed, so every run after the first printed a green result having
    # contacted nothing at all.
    #
    # Hence: the largest max_tokens the pipeline uses, and a unique probe string.
    print(f"\nProbing with a live {PROBE_MAX_TOKENS}-token request...")

    from src.classify import Classifier  # noqa: E402
    from src.llm_client import LLMClient  # noqa: E402

    client = LLMClient(
        settings,
        cache_path=Path(__file__).resolve().parents[1] / "storage" / "preflight-cache",
    )
    result = client.complete(
        Classifier.SYSTEM_PROMPT,
        f"We are seeing 429 errors from the api (preflight {uuid.uuid4().hex[:8]})",
        max_tokens=PROBE_MAX_TOKENS,
    )

    if result.from_cache:
        # Should be unreachable while the probe string is unique. If it ever
        # fires, the check proved nothing and must not report success.
        print("  CACHE HIT — this probe contacted nothing. Not a live check.")
        return 1

    if result.ok:
        TokenLedger().record(client.stats.total_tokens, closes_run=False)
        # NOT "the budget can support a run" — this script cannot support that
        # claim, and said it anyway on 8 Sep. The probe succeeded, I read it as
        # "the daily budget has reset", and the gate run stopped at ticket 54 of
        # 80 with `provider quota exhausted`. One call fitting says nothing
        # about eighty fitting.
        print("  One full-sized live call succeeds.")
        print("  That proves ONE call fits. It does not prove a RUN fits — the")
        print("  provider publishes no daily-remaining figure, so the ledger")
        print("  above is the only estimate available, and it undercounts.")
        return 0

    print(f"  A full-sized call FAILS: {(result.error or '')[:200]}")
    # Record unconditionally. A probe that burned tokens across retries and then
    # failed for some reason other than quota still spent real budget, and used
    # to write nothing — one more silent under-count in a ledger whose whole job
    # is to not under-count.
    TokenLedger().record(
        client.stats.total_tokens,
        exhausted=client.stats.quota_exhausted,
        closes_run=False,  # a probe is not a run; it opened no marker to close
    )
    if client.stats.quota_exhausted:
        print(
            "\n  The period budget is exhausted. A run started now would degrade to\n"
            "  retrieval-only and correctly withhold its business rates. Wait for the\n"
            "  reset at 00:00 UTC before the graded run."
        )
    print()
    print(budget_report())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
