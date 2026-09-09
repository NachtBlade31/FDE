"""Suite-wide safety nets.

The one here is not a convenience. `TokenLedger` defaults to a real file in
`storage/`, and a single test that constructed one without redirecting it wrote
10,000 fictional tokens into the project's live token ledger on every suite run —
ten runs deep before anyone looked. The file that the daily-budget control reads,
and that decision record D-45 quotes, had become mostly test data.

A test must not be able to reach it by forgetting something. So the redirect is
automatic and applies to every test, whether or not it knows the ledger exists.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_token_ledger(tmp_path, monkeypatch):
    """Point every test's TokenLedger at its own throwaway file."""
    monkeypatch.setenv("TOKEN_LEDGER_PATH", str(tmp_path / "token_ledger.json"))
