#!/usr/bin/env python3
"""Smoke test: Twelve Data price + DataHub fallback order (no secrets in output)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.config.secrets import load_local_env  # noqa: E402

load_local_env()

OUT = ROOT / "runtime" / "smoke_twelve_data_result.json"


def main() -> int:
    key_set = bool((os.getenv("TWELVE_DATA_API_KEY") or "").strip())
    report: dict = {"twelve_data_key_set": key_set}

    if key_set:
        from data.twelve_data import TwelveDataProvider  # noqa: E402

        provider = TwelveDataProvider()
        direct = provider.get_price("AAPL")
        report["direct_aapl"] = {
            "price": direct.get("price"),
            "source": direct.get("source"),
            "error": direct.get("error"),
        }

    from data.data_hub import hub  # noqa: E402

    health = hub.check_health()
    report["finnhub_key_set"] = bool((health.get("keys") or {}).get("FINNHUB_API_KEY"))
    report["active_providers"] = hub.list_active()
    report["price_routes"] = [
        r["name"] for r in hub.list_routes("price") if r.get("configured")
    ]

    hub_result = hub.get_price("AAPL", market="United States")
    report["hub_aapl"] = {
        "price": hub_result.get("price"),
        "source": hub_result.get("source") or hub_result.get("provider"),
        "error": hub_result.get("error"),
        "attempts": hub_result.get("attempts"),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    ok = (
        report.get("direct_aapl", {}).get("price") is not None
        or report.get("hub_aapl", {}).get("price") is not None
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
