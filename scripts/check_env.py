"""Preflight check: confirm configuration resolves and a provider is reachable.

Prints booleans and lengths only — never the key itself. Run this after editing
.env and before a graded run:

    python scripts/check_env.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.config import Settings  # noqa: E402


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

    print("\nConfiguration resolves. Model access available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
