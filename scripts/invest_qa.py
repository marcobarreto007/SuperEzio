"""Ask investment questions to Bob and capture responses for analysis."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from investment_answer_quality import evaluate_answer_quality

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = os.getenv("SUPEREZIO_BROWSER_SMOKE_URL", "http://127.0.0.1:8002")

QUESTIONS = [
    (
        "fax_industry",
        "Research the fax industry as an investment theme. Should I look for fax stocks, "
        "or is there a better adjacent opportunity? Do not scan tickers unless needed.",
    ),
    (
        "cad50_risk_lab",
        "I like risking CAD 50 per week instead of buying lottery tickets. "
        "Can Bob treat that as a small risk lab and tell me the rules before any trade?",
    ),
    # 1 — Capital allocation
    (
        "capital_allocation",
        "I have $25,000 to invest. I am 35 years old, moderate risk tolerance. "
        "How should I allocate this capital? Give me a specific allocation with percentages and tickers.",
    ),
    # 2 — Dividend strategy
    (
        "dividend_strategy",
        "I want to build a passive income portfolio with dividend stocks. "
        "What are 5 solid dividend stocks or ETFs for a Canadian investor? "
        "Consider tax efficiency and withholding taxes.",
    ),
    # 3 — Market conditions
    (
        "market_conditions",
        "With current interest rates and market volatility in May 2026, "
        "should I dollar-cost average into the market or wait for a correction? "
        "Give me a data-driven recommendation.",
    ),
    # 4 — Risk assessment
    (
        "risk_assessment",
        "I hold a concentrated position in AAPL (40% of my portfolio). "
        "Is this too risky? How should I diversify without triggering a huge tax bill?",
    ),
    # 5 — ETF comparison
    (
        "etf_comparison",
        "Compare VOO, VTI, and SCHD for a long-term buy-and-hold investor. "
        "Which one would you recommend and why? Consider fees, diversification, and historical performance.",
    ),
    (
        "smallcap_scan",
        "Find one US or Canadian small-cap stock under CAD 5 with liquidity and a real catalyst. "
        "If no candidate passes, say REJECT_ALL.",
    ),
]


def ask_question(page, question: str, timeout_ms: int = 120_000) -> dict[str, Any]:
    # Wait for input to be enabled (previous response may still be streaming)
    page.wait_for_function(
        """
        () => {
          const inp = document.querySelector('#user-inp');
          return inp && !inp.disabled;
        }
        """,
        timeout=30_000,
    )
    page.wait_for_timeout(500)

    page.fill("#user-inp", "")
    page.fill("#user-inp", question)
    page.click("#send-btn")

    # Wait for response: chat has new content (BOB CEO marker) after our question
    # and input is re-enabled (streaming finished)
    page.wait_for_function(
        """
        () => {
          const inp = document.querySelector('#user-inp');
          const chat = document.querySelector('#chat');
          const text = chat ? chat.innerText : '';
          // Response is done when input is re-enabled and chat contains BOB CEO
          return inp && !inp.disabled && text.includes('BOB CEO');
        }
        """,
        timeout=timeout_ms,
    )

    return page.evaluate(
        """
        () => {
          const trace = window.SZ.state.trace || {};
          const chatText = document.querySelector('#chat')?.innerText || '';
          return {
            finalContentLength: trace.final_content_length || 0,
            routeUsed: trace.route_used || 'unknown',
            detectedIntent: trace.detected_intent || 'unknown',
            scannerInvoked: Boolean(trace.scanner_invoked),
            elapsedMs: trace.elapsed_ms || 0,
            chatText: chatText.substring(0, 3000)
          };
        }
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=300)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    results: dict[str, Any] = {"base_url": base, "questions": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, slow_mo=args.slow_mo)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(base, wait_until="networkidle")

        # Wait for app to load
        page.wait_for_selector("#chat", timeout=30_000)
        page.wait_for_selector("#user-inp", timeout=10_000)
        page.wait_for_selector("#send-btn", timeout=10_000)

        for tag, question in QUESTIONS:
            print(f"\n{'=' * 60}")
            print(f"Q [{tag}]: {question[:100]}...")
            t0 = time.time()
            try:
                result = ask_question(page, question, timeout_ms=120_000)
                quality = evaluate_answer_quality(
                    question, result.get("chatText", ""), min_chars=120
                )
                result["ok"] = bool(quality["ok"])
                result["quality_reasons"] = quality["reasons"]
                elapsed = time.time() - t0
                result["wall_seconds"] = round(elapsed, 1)
                results["questions"][tag] = result

                print(f"  Route: {result['routeUsed']}")
                print(f"  Intent: {result['detectedIntent']}")
                print(f"  Scanner invoked: {result['scannerInvoked']}")
                print(f"  Content length: {result['finalContentLength']}")
                print(f"  Wall time: {elapsed:.1f}s")
                print(f"  QA ok: {result['ok']} {result['quality_reasons']}")
                print("  Response (first 500 chars):")
                print(f"  {result['chatText'][:500]}")
            except Exception as exc:
                elapsed = time.time() - t0
                results["questions"][tag] = {"error": str(exc), "wall_seconds": round(elapsed, 1)}
                print(f"  ERROR after {elapsed:.1f}s: {exc}")

            # Brief pause between questions
            page.wait_for_timeout(2000)

        browser.close()

    out_dir = ROOT / "output" / "playwright"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"invest-qa-{stamp}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {out_path}")
    failed = [
        tag
        for tag, result in results["questions"].items()
        if result.get("error") or result.get("ok") is False
    ]
    if failed:
        print(f"FAILED CASES: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
