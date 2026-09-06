"""List the chat models the configured provider actually serves this account.

Model availability on free tiers changes. Run this before assuming a model name
from documentation is still valid.

Run:  python scripts/list_models.py
"""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

import httpx  # noqa: E402

from src.config import Provider, Settings  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    if not settings.has_model_access:
        print("no key configured")
        return 1

    url = (
        "https://api.groq.com/openai/v1/models"
        if settings.provider is Provider.GROQ
        else f"{settings.base_url.rstrip('/')}/models"
    )
    response = httpx.get(
        url, headers={"Authorization": f"Bearer {settings.api_key}"}, timeout=30
    )
    if response.status_code != 200:
        print(f"provider returned {response.status_code}")
        return 1

    names = sorted(m["id"] for m in response.json().get("data", []))
    print(f"{settings.provider.value}: {len(names)} models available")
    for name in names:
        marker = "  <- configured" if name == settings.model_name else ""
        print(f"  {name}{marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
