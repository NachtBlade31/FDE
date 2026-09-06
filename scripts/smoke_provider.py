"""One live call to the configured provider. Prints no secrets.

Run:  python scripts/smoke_provider.py
"""

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from src.config import Settings  # noqa: E402
from src.llm_client import LLMClient  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    print(f"provider : {settings.provider.value}")
    print(f"model    : {settings.model_name}")

    if not settings.has_model_access:
        print("no key configured — the system would run retrieval-only")
        return 1

    client = LLMClient(settings, cache_path=REPO / "storage" / "smoke-cache")

    start = time.perf_counter()
    result = client.complete("Reply with exactly one word.", "Say: ready")
    elapsed = time.perf_counter() - start

    print(f"ok       : {result.ok}")
    print(f"attempts : {result.attempts}")
    print(f"cached   : {result.from_cache}")
    print(f"latency  : {elapsed:.2f}s")
    print(f"reply    : {result.text.strip()[:80]!r}")
    if result.error:
        print(f"error    : {result.error[:200]}")

    print(f"\nstats    : {client.stats}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
