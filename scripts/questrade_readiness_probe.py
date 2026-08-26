"""Verify Questrade OAuth read-only access without placing or changing orders.

Run after adding ``QUESTRADE_REFRESH_TOKEN`` to the local ``.env`` file:

    python scripts/questrade_readiness_probe.py

The default uses the practice OAuth endpoint. ``--live`` only reads account
metadata from the live account and still cannot submit, replace, or cancel an
order because the underlying client has no such methods.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapters.broker.questrade_readonly import (
    QuestradeReadOnlyClient,
    QuestradeReadOnlyError,
)
from core.config.settings import get_settings


def run_probe(*, practice: bool | None = None) -> dict[str, Any]:
    """Run the OAuth/account-list diagnostic while never exposing credential material."""
    settings = get_settings()
    token = settings.questrade_refresh_token
    configured_practice = settings.questrade_practice if practice is None else practice
    if token is None or not token.get_secret_value().strip():
        return {
            "provider": "questrade",
            "mode": "read_only",
            "connected": False,
            "practice": configured_practice,
            "can_submit_orders": False,
            "error": "credentials_missing: set QUESTRADE_REFRESH_TOKEN",
        }
    try:
        with QuestradeReadOnlyClient(
            token.get_secret_value(), practice=configured_practice
        ) as client:
            return client.readiness()
    except QuestradeReadOnlyError as exc:
        return {
            "provider": "questrade",
            "mode": "read_only",
            "connected": False,
            "practice": configured_practice,
            "can_submit_orders": False,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Read only from the live OAuth endpoint."
    )
    args = parser.parse_args()
    payload = run_probe(practice=False if args.live else None)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["connected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
