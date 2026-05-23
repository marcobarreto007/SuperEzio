#!/usr/bin/env python3
"""Smoke test: DataHub price routing for a liquid US ticker."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.config.secrets import load_local_env  # noqa: E402

load_local_env()

from data.data_hub import hub  # noqa: E402


def main() -> int:
    health = hub.check_health()
    finnhub_configured = bool((health.get("keys") or {}).get("FINNHUB_API_KEY"))
    print(f"finnhub_configured={finnhub_configured}")
    print(f"active_providers={hub.list_active()}")
    price_routes = [r["name"] for r in hub.list_routes("price") if r.get("configured")]
    print(f"price_routes={price_routes}")

    result = hub.get_price("AAPL", market="United States")
    payload = {
        "symbol": "AAPL",
        "price": result.get("price"),
        "source": result.get("source") or result.get("provider"),
        "error": result.get("error"),
    }
    if result.get("attempts"):
        payload["attempts"] = result["attempts"]
    print(json.dumps(payload, indent=2))

    if payload.get("error"):
        return 1
    if not isinstance(payload.get("price"), (int, float)) or payload["price"] <= 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
