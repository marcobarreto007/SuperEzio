"""
SuperEzio — Pipeline End-to-End Test with AAPL.

Validates:
1. /task/submit accepts a ticker analysis request (AAPL).
2. The prompt is saved to runtime/prompts/{run_id}.txt.
3. The saved prompt contains real data: RSI, MACD, price, Sharpe.

Usage:
    python scripts/test_pipeline.py

Assumes the SuperEzio server is already running on SUPEREZIO_TEST_URL
(default http://127.0.0.1:8002).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "runtime" / "prompts"
DEFAULT_BASE_URL = os.getenv("SUPEREZIO_TEST_URL", "http://127.0.0.1:8002")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _http_json(url: str, timeout_s: float = 5.0) -> dict:

    with urllib.request.urlopen(url, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise AssertionError(f"{url} did not return a JSON object")
    return data


def _stream_ndjson(url: str, body: dict, timeout_s: float = 120.0) -> list[dict]:
    """POST *body* to *url*, read the NDJSON stream response, return parsed lines."""
    import http.client
    import urllib.error

    parsed = urllib.parse.urlparse(url)
    path_qs = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
    payload = json.dumps(body).encode("utf-8")

    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout_s)
    try:
        conn.request(
            "POST",
            path_qs,
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        if response.status != 200:
            detail = response.read().decode("utf-8", errors="replace")[:500]
            raise AssertionError(
                f"POST {url} returned {response.status}: {detail}"
            )

        lines: list[dict] = []
        while True:
            raw = response.readline()
            if not raw:
                break
            raw = raw.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                print(f"  [WARN] non-JSON line: {raw[:120]}", file=sys.stderr)
        return lines
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

_REQUIRED_TERMS = {"RSI", "MACD", "Sharpe", "price", "AAPL"}


def check_prompt_file(prompt_path: Path) -> int:
    """Validate the saved prompt file. Returns 0 on success, 1 on failure."""
    if not prompt_path.exists():
        print(f"\n  FAIL: prompt file not found at {prompt_path}")
        return 1

    text = prompt_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    print(f"\n  Prompt file: {prompt_path} ({len(lines)} lines, {len(text)} chars)")
    print("  First 100 lines:\n")
    for i, line in enumerate(lines[:100], start=1):
        print(f"    {i:>4d} | {line[:160]}")

    if len(lines) > 100:
        print(f"    ... ({len(lines) - 100} more lines)")

    missing = [t for t in _REQUIRED_TERMS if t not in text]
    if missing:
        print(f"\n  FAIL: missing terms in prompt: {missing}")
        return 1

    print(f"\n  PASS: all required terms found in prompt: {_REQUIRED_TERMS}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Test pipeline end-to-end with AAPL")
    parser.add_argument(
        "--url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    health_url = f"{base_url}/health"
    submit_url = f"{base_url}/task/submit"

    # Check server is reachable
    print(f"1. Checking server health at {health_url} ...")
    try:
        health = _http_json(health_url, timeout_s=5.0)
        print(f"   Health: {json.dumps(health, ensure_ascii=False)[:200]}")
    except Exception as e:
        print(f"   FAIL: cannot reach server — {e}")
        print("   Start the server with: python -m agent_server.main")
        return 1

    # Submit AAPL analysis
    print(f"\n2. Submitting AAPL analysis to {submit_url} ...")
    msg_id = str(uuid.uuid4())
    body = {
        "msg_id": msg_id,
        "from": "test_pipeline",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "Analyse AAPL. Give me price, RSI, MACD, and Sharpe ratio.",
        },
    }

    try:
        events = _stream_ndjson(submit_url, body, timeout_s=120.0)
    except Exception as e:
        print(f"   FAIL: request error — {e}")
        return 1

    print(f"   Received {len(events)} NDJSON events")

    # Extract run_id from events
    run_id = ""
    for ev in events:
        rid = ev.get("run_id", "")
        if rid:
            run_id = rid
            break

    if not run_id:
        print("   WARN: could not extract run_id from stream — scanning prompt dir")
        # Try the most recent prompt file
        prompt_files = sorted(PROMPTS_DIR.glob("*.txt"), key=os.path.getmtime, reverse=True)
        if prompt_files:
            latest = prompt_files[0]
            print(f"   Using most recent prompt file: {latest.name}")
            return check_prompt_file(latest)
        else:
            print(f"   FAIL: no prompt files found in {PROMPTS_DIR}")
            return 1

    print(f"   Run ID: {run_id}")

    # Check the saved prompt
    prompt_path = PROMPTS_DIR / f"{run_id}.txt"
    return check_prompt_file(prompt_path)


if __name__ == "__main__":
    sys.exit(main())
