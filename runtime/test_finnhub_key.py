#!/usr/bin/env python3
"""One-off Finnhub key check — never prints the API key."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.config.secrets import load_local_env  # noqa: E402

load_local_env()
key = (os.getenv("FINNHUB_API_KEY") or "").strip()
out: dict = {"key_present": bool(key), "key_length": len(key)}
if not key:
    out["status"] = "MISSING"
    print(json.dumps(out, indent=2))
    sys.exit(2)

import requests  # noqa: E402

for symbol in ("AAPL", "MSFT"):
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol, "token": key},
            timeout=15,
        )
        row = {"symbol": symbol, "http_status": r.status_code}
        if r.status_code == 200:
            data = r.json()
            row["price"] = data.get("c")
            row["ok"] = bool(data.get("c") and float(data["c"]) > 0)
        else:
            try:
                row["finnhub_error"] = r.json()
            except Exception:
                row["body_preview"] = (r.text or "")[:80]
        out[symbol] = row
    except Exception as exc:
        out[symbol] = {"error": str(exc)}

ok_any = any(
    isinstance(out.get(s), dict) and out[s].get("ok") for s in ("AAPL", "MSFT")
)
out["status"] = "OK" if ok_any else "FAILED"
print(json.dumps(out, indent=2))
sys.exit(0 if ok_any else 1)
