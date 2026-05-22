"""
Bob Pipeline Stress Test — 20 investment prompts across all pipeline routes.

Tests the full pipeline: intent classification → routing → data collection → LLM generation.
Reports per-prompt: intent, route, content length, provider, errors.
"""

import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8002"

PROMPTS = [
    # ── Ticker Analysis (specific stock questions) ──
    {"msg": "What do you think about AAPL right now?", "ticker": "AAPL", "tag": "ticker_aapl"},
    {"msg": "Should I buy TSLA?", "ticker": "TSLA", "tag": "ticker_tsla_buy"},
    {"msg": "Analyze NVDA for me", "ticker": "NVDA", "tag": "ticker_nvda"},
    {"msg": "Is MSFT overvalued at this price?", "ticker": "MSFT", "tag": "ticker_msft_valuation"},
    {"msg": "Give me the bear case for AMZN", "ticker": "AMZN", "tag": "ticker_amzn_bear"},
    {"msg": "What's happening with META stock?", "ticker": "META", "tag": "ticker_meta"},
    {"msg": "Would you buy GOOGL at current levels?", "ticker": "GOOGL", "tag": "ticker_googl"},

    # ── Market Scan (broad market questions) ──
    {"msg": "What are the best tech stocks to buy right now?", "ticker": "", "tag": "scan_tech"},
    {"msg": "Show me undervalued stocks in the US market", "ticker": "", "tag": "scan_undervalued"},
    {"msg": "What Canadian stocks look interesting?", "ticker": "", "tag": "scan_canada"},
    {"msg": "Find me momentum stocks with catalysts", "ticker": "", "tag": "scan_momentum"},
    {"msg": "What healthcare stocks should I watch?", "ticker": "", "tag": "scan_healthcare"},

    # ── General / Educational ──
    {"msg": "How does dollar cost averaging work?", "ticker": "", "tag": "general_dca"},
    {"msg": "Explain the difference between ETFs and mutual funds", "ticker": "", "tag": "general_etf"},
    {"msg": "What is the VIX and how do I use it?", "ticker": "", "tag": "general_vix"},

    # ── Portfolio / Strategy ──
    {"msg": "How should I diversify a $50k portfolio?", "ticker": "", "tag": "strategy_diversify"},
    {"msg": "What's a good defensive strategy for a recession?", "ticker": "", "tag": "strategy_defensive"},

    # ── Edge Cases ──
    {"msg": "What's your top stock pick today?", "ticker": "", "tag": "edge_top_pick"},
    {"msg": "Should I sell everything and go to cash?", "ticker": "", "tag": "edge_panic_sell"},
    {"msg": "Give me a penny stock with 10x potential", "ticker": "", "tag": "edge_penny"},
]


def submit_task(prompt: str, ticker: str = "") -> dict:
    """Submit a task to Bob and collect all streamed events."""
    payload = {
        "message": prompt,
        "ticker": ticker,
        "session_id": "stress_test",
    }
    body = json.dumps({
        "from": "stress_test",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": payload,
    }).encode()

    req = urllib.request.Request(
        f"{BASE}/task/submit",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    events = []
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError:
                    events.append({"type": "RAW", "content": line[:200]})
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500]
        return {"error": f"HTTP {e.code}: {body_text}"}
    except Exception as e:
        return {"error": str(e)}

    return _parse_events(events)


def _parse_events(events: list[dict]) -> dict:
    """Extract trace info from NDJSON stream."""
    result = {
        "intent": "?",
        "route": "?",
        "scanner_invoked": False,
        "candidates": 0,
        "providers": [],
        "content_length": 0,
        "error": None,
        "trace": None,
    }
    full_content = []
    for ev in events:
        t = ev.get("type")
        if t == "INTENT_CLASSIFIED":
            result["intent"] = ev.get("intent", "?")
            result["route"] = ev.get("route", "?")
        elif t == "CHUNK":
            full_content.append(ev.get("content", ""))
        elif t == "DATA_COLLECTED":
            result["candidates"] = ev.get("candidates", 0)
            result["providers"] = list(set(ev.get("providers") or []))
            if ev.get("source_errors"):
                result["error"] = "; ".join(ev.get("source_errors", [])[:3])
        elif t == "ERROR":
            result["error"] = ev.get("detail", "unknown error")[:200]
        elif t == "STREAM_END":
            result["trace"] = ev.get("trace")

    result["content_length"] = sum(len(c) for c in full_content)
    result["content_preview"] = "".join(full_content)[:300]
    return result


def main():
    # Health check first
    try:
        req = urllib.request.Request(f"{BASE}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read())
            print(f"Server health: {health.get('status', 'unknown')}")
    except Exception as e:
        print(f"FAIL: Server not reachable at {BASE}: {e}")
        sys.exit(1)

    print(f"\n{'='*90}")
    print(f"{'#':>2} {'TAG':<22} {'INTENT':<20} {'ROUTE':<18} {'LEN':>5} {'CAND':>4} {'OK':>3} {'DETAIL'}")
    print(f"{'='*90}")

    results = []
    passed = 0
    failed = 0
    total_start = time.time()

    for i, p in enumerate(PROMPTS, 1):
        tag = p["tag"]
        msg = p["msg"]
        ticker = p.get("ticker", "")

        t0 = time.time()
        r = submit_task(msg, ticker)
        elapsed = time.time() - t0

        ok = r.get("error") is None and r.get("content_length", 0) > 50
        status = "OK" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        detail = ""
        if r.get("error"):
            detail = f"ERR: {r['error'][:60]}"
        elif r.get("content_length", 0) > 0:
            detail = f"content={r['content_length']} chars, {elapsed:.1f}s"
            if r.get("providers"):
                detail += f" providers={','.join(r['providers'])}"

        print(
            f"{i:>2} {tag:<22} {r.get('intent', '?'):<20} "
            f"{r.get('route', '?'):<18} {r.get('content_length', 0):>5} "
            f"{r.get('candidates', 0):>4} {status:>3} {detail}"
        )
        results.append({"tag": tag, "ok": ok, "elapsed": elapsed, **r})

    total_elapsed = time.time() - total_start

    # Summary
    print(f"\n{'='*90}")
    print(f"SUMMARY: {passed}/{len(PROMPTS)} passed, {failed} failed, {total_elapsed:.1f}s total")
    print(f"{'='*90}")

    # Route distribution
    routes = {}
    for r in results:
        rt = r.get("route", "?")
        routes[rt] = routes.get(rt, 0) + 1
    print(f"\nRoute distribution:")
    for rt, count in sorted(routes.items(), key=lambda x: -x[1]):
        print(f"  {rt}: {count}")

    # Intent distribution
    intents = {}
    for r in results:
        intent = r.get("intent", "?")
        intents[intent] = intents.get(intent, 0) + 1
    print(f"\nIntent distribution:")
    for intent, count in sorted(intents.items(), key=lambda x: -x[1]):
        print(f"  {intent}: {count}")

    # Failed details
    failures = [r for r in results if not r["ok"]]
    if failures:
        print(f"\nFAILED DETAILS:")
        for r in failures:
            print(f"  {r['tag']}: {r.get('error', 'no content')}")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
