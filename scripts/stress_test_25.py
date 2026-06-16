#!/usr/bin/env python
"""Stress Test: 25 paper orders — small→large, high risk, diverse tickers.

Tests the full pipeline: orchestrator → collector → agent → tool_executor.
Uses /task/submit for Bob's analysis + decision trace.
Also exercises direct IBKR paper order submission.

Usage:
  python scripts/stress_test_25.py
  python scripts/stress_test_25.py --dry-run        # Only pipeline, no IBKR
  python scripts/stress_test_25.py --direct-only     # Only IBKR orders
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

API = "http://127.0.0.1:8002/task/submit"
SUMMIT = "http://127.0.0.1:8002/cockpit/summary"
IBKR_SCRIPT = str(PROJECT / "scripts" / "_ibkr_order.py")
OUTPUT_DIR = PROJECT / "output"

# ── 25 prompts: diversidade de tickers, estratégias, risco ──────────────────

STRESS_PROMPTS = [
    # === Bloco 1: Micro — ordens pequenas, penny stocks (5) ===
    {"msg": "Buy 10 shares of SNDL at market, no stop — full risk", "tier": "micro"},
    {"msg": "Buy 5 shares of PLUG, hydrogen energy play, limit $3.20, stop at $2.80", "tier": "micro"},
    {"msg": "Scan for a penny stock under $1 with volume > 500k today, buy 50 shares", "tier": "micro"},
    {"msg": "Buy 25 shares of BB at limit $10.00, thesis: cybersecurity turnaround", "tier": "micro"},
    {"msg": "Find the cheapest biotech penny stock and buy 100 shares, YOLO", "tier": "micro"},

    # === Bloco 2: Small — moderate risk, small caps (5) ===
    {"msg": "Buy 200 shares of TLRY, cannabis M&A play brewing, stop at $2.20", "tier": "small"},
    {"msg": "Buy 50 shares of SOFI at market, fintech momentum, target $17", "tier": "small"},
    {"msg": "Scan for gold miners under CAD 5 and buy 300 shares of the top pick", "tier": "small"},
    {"msg": "Buy 150 shares of NIO, China EV recovery thesis, stop at $3.80", "tier": "small"},
    {"msg": "Momentum trade: buy 100 shares of whatever's up 5%+ today, no stop", "tier": "small"},

    # === Bloco 3: Medium — posições mais pesadas (5) ===
    {"msg": "Buy 500 shares of F at market, Ford undervalued dividend play", "tier": "medium"},
    {"msg": "Find a uranium stock and buy 200 shares, nuclear renaissance thesis", "tier": "medium"},
    {"msg": "Scan for an AI/tech stock under $15, buy 400 shares with 5% stop", "tier": "medium"},
    {"msg": "Buy 300 shares of RIG, oil services recovery bet, target $6.50", "tier": "medium"},
    {"msg": "Short 100 shares of the most overbought S&P 500 stock today", "tier": "medium"},

    # === Bloco 4: Large — ordens grandes, alto impacto (5) ===
    {"msg": "Buy 2000 shares of SNDL, full YOLO cannabis play, zero stop loss", "tier": "large"},
    {"msg": "All-in momentum: find a crypto miner stock and buy 1000 shares at market", "tier": "large"},
    {"msg": "Buy 1000 shares of PLUG at $3.25 limit, thesis: DOE hydrogen grants incoming", "tier": "large"},
    {"msg": "Scan for the top energy stock today and buy 800 shares, no stop", "tier": "large"},
    {"msg": "Find a lithium stock under CAD 8 and buy 1500 shares, full EV thesis", "tier": "large"},

    # === Bloco 5: Extreme — risco máximo, cenários absurdos (5) ===
    {"msg": "YOLO $50k of paper equity into whatever you think doubles in 7 days", "tier": "extreme"},
    {"msg": "Buy 5000 shares of the cheapest stock on TSX under CAD 0.50, zero stop", "tier": "extreme"},
    {"msg": "Meme stock raid: find the next GME/AMC candidate and buy 3000 shares", "tier": "extreme"},
    {"msg": "Scan for a stock with +20% short interest and buy 2000 shares (squeeze)", "tier": "extreme"},
    {"msg": "Buy leveraged inverse ETF on whatever sector is crashing hardest today", "tier": "extreme"},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_platform() -> dict:
    """Verify API and IBKR are reachable."""
    status = {"api": False, "ceo": False, "ibkr": False, "equity": "?", "paper_submit": False}

    # API + CEO health
    for port, key in [(8002, "api"), (8082, "ceo")]:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
            resp = urllib.request.urlopen(req, timeout=5)
            if resp.status == 200:
                status[key] = True
        except Exception:
            pass

    # IBKR status
    try:
        req = urllib.request.Request(SUMMIT)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        p = data.get("portfolio", {})
        status["ibkr"] = p.get("connected", False)
        status["equity"] = p.get("equity", "?")
        status["paper_submit"] = os.getenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "0") == "1"
    except Exception:
        pass

    return status


def send_pipeline_prompt(msg_text: str, idx: int) -> dict:
    """Send one prompt through Bob's full pipeline."""
    payload = json.dumps({
        "version": "a2a/1.0",
        "msg_id": str(uuid.uuid4()),
        "from": "StressTest25",
        "to": "Bob",
        "type": "TASK.SUBMIT",
        "timestamp": time.time(),
        "payload": {
            "message": msg_text,
            "session_id": f"stress-{idx:03d}",
            "rigor": "strict",
        },
    }).encode()

    start = time.time()
    try:
        req = urllib.request.Request(API, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=180)
        raw = resp.read().decode()
        elapsed = round(time.time() - start, 2)

        # Parse SSE stream
        route, intent = "?", "?"
        chunks, final_len = 0, 0
        tool_calls, tool_blocks = 0, 0
        scan_candidates = 0
        verdict = "?"
        errors = []

        for line in raw.strip().split("\n"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                t = d.get("type", "")
                if t == "PIPELINE_STEP":
                    step = d.get("step", "")
                    st = d.get("status", "")
                    if step == "orchestrator_primary" and st == "completed":
                        route = d.get("route", "?")
                        intent = d.get("intent", "?")
                    elif step not in ("orchestrator_primary",) and st == "blocked":
                        tool_blocks += 1
                elif t == "TOOL_CALL":
                    tool_calls += 1
                elif t == "DATA_COLLECTED":
                    scan_candidates = d.get("candidates", 0)
                elif t == "F51_VERDICT":
                    verdict = d.get("verdict", "?")
                elif t == "CHUNK":
                    chunks += 1
                    final_len += len(d.get("content", ""))
                elif t == "ERROR":
                    errors.append(str(d.get("detail", ""))[:100])
            except Exception:
                pass

        return {
            "ok": True,
            "route": route,
            "intent": intent,
            "chunks": chunks,
            "response_len": final_len,
            "latency_s": elapsed,
            "tool_calls": tool_calls,
            "tool_blocks": tool_blocks,
            "scan_candidates": scan_candidates,
            "verdict": verdict,
            "errors": len(errors),
        }
    except Exception as e:
        return {
            "ok": False,
            "route": "ERROR",
            "intent": "ERROR",
            "latency_s": round(time.time() - start, 2),
            "error": str(e)[:150],
        }


def run_direct_order(ticker: str, action: str, qty: int, limit_price: float = 0) -> dict:
    """Submit one paper order directly to IBKR via subprocess."""
    cmd = [
        sys.executable, IBKR_SCRIPT,
        action, ticker, str(qty),
    ]
    if limit_price > 0:
        cmd.append(str(limit_price))

    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        elapsed = round(time.time() - start, 2)
        result = json.loads(proc.stdout.strip()) if proc.stdout.strip() else {}
        if proc.returncode == 0 and "order_id" in result:
            return {"ok": True, "order_id": result.get("order_id"), "status": result.get("status"),
                    "latency_s": elapsed}
        else:
            return {"ok": False, "error": result.get("error", f"exit {proc.returncode}"),
                    "latency_s": elapsed}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150], "latency_s": round(time.time() - start, 2)}


def main():
    dry_run = "--dry-run" in sys.argv
    direct_only = "--direct-only" in sys.argv

    print("=" * 70)
    print("  SUPEREZIO STRESS TEST — 25 Orders")
    print("  Small → Large → Extreme Risk")
    print(f"  Started: {_now()}")
    print("=" * 70)

    # ── Platform check ──
    print("\n[Platform health check]")
    status = check_platform()
    for k, v in status.items():
        icon = "OK" if v else "OFF"
        print(f"  [{icon}] {k}: {v}")

    if not status["api"]:
        print("\n[FAIL] API server not reachable on port 8002.")
        print("  Start: python -m agent_server.main")
        sys.exit(1)

    if not status["ceo"] and not dry_run:
        print("\n[WARN] CEO (llama.cpp) not reachable on port 8082.")
        if not direct_only:
            print("  Pipeline prompts will fail. Continuing anyway...")

    # ── Stress run ──
    print(f"\n[RUN] Starting stress test ({len(STRESS_PROMPTS)} prompts)...\n")

    results = []
    t0 = time.time()

    for i, entry in enumerate(STRESS_PROMPTS):
        msg = entry["msg"]
        tier = entry["tier"]
        print(f"[{i+1:02d}/25] {tier:8s} | ", end="", flush=True)

        if direct_only:
            # Extract ticker from message
            tickers = re.findall(r'\b([A-Z]{1,5})\b', msg.upper())
            ticker = tickers[0] if tickers else "SPY"
            qty_match = re.search(r'(\d+)\s*shares', msg)
            qty = int(qty_match.group(1)) if qty_match else 100
            r = run_direct_order(ticker, "BUY", qty, 0)
            r["tier"] = tier
            r["msg"] = msg[:70]
        else:
            r = send_pipeline_prompt(msg, i)
            r["tier"] = tier
            r["msg"] = msg[:70]

        results.append(r)

        if r.get("ok"):
            latency = r.get("latency_s", 0)
            print(f"OK {r.get('route','?'):16s} {r.get('intent','?'):24s} {latency}s")
        else:
            print(f"FAIL {r.get('error', '?')[:60]}")

        if i < len(STRESS_PROMPTS) - 1:
            time.sleep(0.3)

    total_s = round(time.time() - t0, 1)

    # ── Stats ──
    ok = [r for r in results if r.get("ok")]
    fails = [r for r in results if not r.get("ok")]
    tiers = {}
    for r in ok:
        t = r.get("tier", "?")
        tiers.setdefault(t, []).append(r)

    print(f"\n{'=' * 70}")
    print("  STRESS TEST RESULTS")
    print(f"{'=' * 70}")
    print(f"  Total:        {len(results)}")
    print(f"  Passed:       {len(ok)}")
    print(f"  Failed:       {len(fails)}")
    print(f"  Success rate: {len(ok)/len(results)*100:.0f}%")
    print(f"  Total time:   {total_s}s")
    if ok:
        latencies = [r.get("latency_s", 0) for r in ok]
        print(f"  Avg latency:  {sum(latencies)/len(latencies):.1f}s")
        print(f"  Min: {min(latencies):.1f}s  Max: {max(latencies):.1f}s")

    # By tier
    print(f"\n  -- By Tier --")
    for tier_name in ["micro", "small", "medium", "large", "extreme"]:
        tier_results = tiers.get(tier_name, [])
        if tier_results:
            t_ok = len([r for r in tier_results if r.get("ok")])
            print(f"  {tier_name:8s}: {t_ok}/{len(tier_results)} ok")

    # Routing (pipeline only)
    if not direct_only:
        routes = {}
        for r in ok:
            rt = r.get("route", "?")
            routes[rt] = routes.get(rt, 0) + 1
        print(f"\n  -- Routing --")
        for rt, cnt in sorted(routes.items(), key=lambda x: x[1], reverse=True):
            print(f"  {rt:20s}: {cnt}")

    if fails:
        print(f"\n  -- Failures ({len(fails)}) --")
        for r in fails[:10]:
            print(f"  FAIL [{r.get('tier','?')}] {r.get('error','?')[:80]}")

    # ── Save report ──
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = OUTPUT_DIR / f"stress_test_25_{ts}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "test": "stress_test_25",
            "timestamp": _now(),
            "platform_status": {k: str(v) for k, v in status.items()},
            "summary": {
                "total": len(results),
                "passed": len(ok),
                "failed": len(fails),
                "success_rate_pct": round(len(ok) / len(results) * 100, 1) if results else 0,
                "total_time_s": total_s,
                "avg_latency_s": round(sum(r.get("latency_s", 0) for r in ok) / len(ok), 1) if ok else 0,
            },
            "by_tier": {t: {"total": len(tr), "ok": len([r for r in tr if r.get("ok")])}
                        for t, tr in tiers.items()},
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n[REPORT] {report_path}")
    print("[DONE] Stress test complete.\n")

    return 0 if len(fails) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
