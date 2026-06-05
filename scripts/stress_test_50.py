#!/usr/bin/env python
"""Stress test: 50 aggressive paper trades against Bob's pipeline.
Measures routing, tool usage, latency, and failure rate.
"""

import json
import time
import urllib.request
import uuid
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

API = "http://127.0.0.1:8002/task/submit"

# 50 prompts malucos — variados em estilo, ticker, estratégia
PROMPTS = [
    "Buy 100 shares of SNDL right now, market order, no stop loss, YOLO",
    "Short 500 shares of MARA, Bitcoin is crashing, stop at 12.50",
    "Find me the most volatile stock under $3 and buy 1000 shares",
    "All in on PLUG, 5000 shares market buy, hydrogen is the future",
    "Day trade RIG with 2000 shares, buy the dip, sell the rip",
    "Find a penny stock about to explode and give me entry/exit",
    "Buy 50 shares of NIO, China EV gonna moon, no stop",
    "Short TSLA 10 shares, Elon just tweeted something dumb",
    "Scan for uranium stocks under $10, pick the best, buy 500",
    "YOLO 100% of my paper account into whatever you find",
    "I want to make $500 in the next 30 minutes, find me a trade",
    "Buy 200 BB, BlackBerry comeback story, stop loss 9.00",
    "Find a small-cap gold miner under CAD 5, buy 1000 shares",
    "Short 100 shares of CLSK, Bitcoin miners are doomed today",
    "Find the most oversold stock on NASDAQ and buy 300 shares",
    "All in on crypto miners, pick 3, split 10k equally",
    "Buy 50 shares of SOFI, fintech is the future, target 17.00",
    "Scan for biotech penny stocks with upcoming catalysts, buy 2000",
    "Sell everything and buy GLD, market crash coming",
    "Find a stock that doubled last month and short it",
    "Buy 1000 shares of the cheapest stock on the TSX",
    "Momentum trade: find a stock up 5% today, buy 500 shares",
    "Reversal play: find a stock down 10% today, buy the dip 300 shares",
    "Buy 25 shares of RKT, mortgage rates dropping, free money",
    "Scan for AI stocks under $15, buy 200 shares of the best one",
    "YOLO 2000 shares of whatever is moving the most right now",
    "Find a lithium stock under CAD 10, buy 800 shares, EV boom",
    "Short the most overbought stock in the S&P, 50 shares",
    "Buy 150 shares of F, Ford is undervalued, dividend play",
    "Day trade: find a stock with high relative volume, buy 500 shares",
    "Swing trade: find a stock at support with upside, buy 400 shares",
    "Find the best cannabis stock under $2, buy 5000 shares",
    "Buy 300 shares of whatever Cathie Wood is buying",
    "Scan for energy stocks with momentum, buy 200 shares of the top pick",
    "Pattern day trade: find a breakout stock, buy 400 shares now",
    "Buy 100 shares of NXE, nuclear renaissance, no stop, full send",
    "Find a software stock with insider buying, buy 150 shares",
    "Short 200 shares of the most overvalued fintech stock",
    "Buy whatever you think will double in the next 7 days",
    "Meme stock scanner: find the next GME, buy 500 shares",
    "Find a dividend stock under $20 yielding over 5%, buy 300",
    "Buy 1000 shares of BITF.TO, Bitcoin miner at CAD 2.76, steal",
    "Scan for a stock with unusual options activity, buy 200 shares",
    "Buy 50 shares of ACB, cannabis legalization play, no stop",
    "Find a tech stock that missed earnings and tanked, buy the dip",
    "Short the VIX (whatever tracks it), market is too calm",
    "Buy 400 shares of TLRY, cannabis M&A play, target 6.00",
    "Scan for the most shorted stock and buy 1000 shares (squeeze play)",
    "YOLO everything into 0DTE SPY calls (or closest stock equivalent)",
    "I'm bored, find me something fun and risky to trade right now",
]

def send_prompt(msg_text: str, idx: int) -> dict:
    msg = {
        "version": "a2a/1.0",
        "msg_id": str(uuid.uuid4()),
        "from": "StressTest",
        "to": "Bob",
        "type": "TASK.SUBMIT",
        "timestamp": time.time(),
        "payload": {
            "message": msg_text,
            "session_id": f"stress-{idx:03d}",
            "rigor": "strict",
        },
    }
    data = json.dumps(msg).encode()
    start = time.time()
    try:
        req = urllib.request.Request(API, data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=120)
        content = resp.read().decode()
        elapsed = round(time.time() - start, 2)

        route = "?"
        intent = "?"
        chunks = 0
        final_length = 0
        for line in content.strip().split("\n"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                t = d.get("type", "")
                if t == "PIPELINE_STEP" and d.get("step") == "orchestrator_primary" and d.get("status") == "completed":
                    route = d.get("route", "?")
                    intent = d.get("intent", "?")
                elif t == "CHUNK":
                    chunks += 1
                    final_length += len(d.get("content", ""))
            except Exception:
                pass

        return {
            "msg": msg_text[:80],
            "route": route,
            "intent": intent,
            "chunks": chunks,
            "response_len": final_length,
            "latency_s": elapsed,
            "ok": True,
        }
    except Exception as e:
        return {
            "msg": msg_text[:80],
            "route": "ERROR",
            "intent": "ERROR",
            "chunks": 0,
            "response_len": 0,
            "latency_s": round(time.time() - start, 2),
            "ok": False,
            "error": str(e)[:100],
        }


def main():
    print(f"=== STRESS TEST: 50 trades ===\n")
    results = []
    start_total = time.time()

    for i, prompt in enumerate(PROMPTS):
        sys.stdout.write(f"[{i+1:02d}/50] ")
        sys.stdout.flush()
        r = send_prompt(prompt, i)
        status = "OK" if r["ok"] else "FAIL"
        print(f"{status} route={r['route']} intent={r['intent']} chunks={r['chunks']} len={r['response_len']} {r['latency_s']}s")
        results.append(r)

        if i < len(PROMPTS) - 1:
            time.sleep(0.5)  # Don't overwhelm the server

    total_s = round(time.time() - start_total, 1)

    # ── Stats ──
    ok = [r for r in results if r["ok"]]
    fails = [r for r in results if not r["ok"]]
    market_scans = [r for r in ok if r["route"] == "market_scan"]
    general = [r for r in ok if r["route"] == "general"]
    ticker_analysis = [r for r in ok if r["route"] == "ticker_analysis"]
    with_tools = [r for r in ok if r["chunks"] > 0]

    print(f"\n{'='*60}")
    print(f"STRESS TEST RESULTS")
    print(f"{'='*60}")
    print(f"Total:        {len(results)}")
    print(f"Passed:       {len(ok)}")
    print(f"Failed:       {len(fails)}")
    print(f"Success rate: {len(ok)/len(results)*100:.0f}%")
    print(f"Total time:   {total_s}s")
    print(f"Avg latency:  {sum(r['latency_s'] for r in ok)/len(ok):.1f}s" if ok else "N/A")
    print(f"")
    print(f"Routing:")
    print(f"  market_scan:     {len(market_scans)} ({len(market_scans)/len(ok)*100:.0f}%)" if ok else "  N/A")
    print(f"  ticker_analysis: {len(ticker_analysis)} ({len(ticker_analysis)/len(ok)*100:.0f}%)" if ok else "  N/A")
    print(f"  general:         {len(general)} ({len(general)/len(ok)*100:.0f}%)" if ok else "  N/A")
    print(f"")
    print(f"Tool usage:")
    print(f"  With response:   {len(with_tools)} ({len(with_tools)/len(ok)*100:.0f}%)" if ok else "  N/A")
    print(f"")

    if fails:
        print(f"FAILURES:")
        for r in fails:
            print(f"  [{r['route']}] {r.get('error','?')} — {r['msg']}")

    # Save report
    report_path = PROJECT / "output" / f"stress_test_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": len(results), "passed": len(ok), "failed": len(fails),
                "success_rate_pct": round(len(ok)/len(results)*100, 1),
                "total_time_s": total_s,
                "avg_latency_s": round(sum(r['latency_s'] for r in ok)/len(ok), 1) if ok else 0,
                "market_scan_pct": round(len(market_scans)/len(ok)*100, 1) if ok else 0,
                "ticker_analysis_pct": round(len(ticker_analysis)/len(ok)*100, 1) if ok else 0,
                "general_pct": round(len(general)/len(ok)*100, 1) if ok else 0,
            },
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
