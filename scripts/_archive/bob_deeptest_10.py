"""Run a 10-prompt live Bob delivery test through the browser runtime.

This is a pre-delivery smoke/deeptest, not a unit test. It loads the local UI
with Playwright, then submits 10 different Bob prompts to /task/submit from the
browser context and validates nonempty streamed answers.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from investment_answer_quality import evaluate_answer_quality


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = os.getenv("SUPEREZIO_BROWSER_SMOKE_URL", "http://127.0.0.1:8002")

PROMPTS: list[dict[str, Any]] = [
    {
        "id": "identity_capabilities",
        "ticker": "",
        "message": "Se identifica em portugues e me diga exatamente o que voce consegue fazer hoje.",
        "min_chars": 120,
    },
    {
        "id": "cad25k_capital_allocation",
        "ticker": "",
        "message": (
            "I live in Canada and have CAD 25,000. Should I keep cash, pay debt, "
            "buy ETFs, invest in education, or try a short-term trade? Give one clear framework."
        ),
        "min_chars": 200,
        "expected_scanner_invoked": False,
    },
    {
        "id": "fax_industry_research",
        "ticker": "",
        "message": (
            "Research the fax industry as an investment theme. Should I look for fax stocks, "
            "or is there a better adjacent opportunity? Do not scan tickers unless needed."
        ),
        "min_chars": 180,
        "expected_scanner_invoked": False,
    },
    {
        "id": "cad50_risk_lab",
        "ticker": "",
        "message": (
            "I like risking CAD 50 per week instead of lottery tickets. Treat it as a risk lab. "
            "What are the rules before any trade?"
        ),
        "min_chars": 180,
        "expected_scanner_invoked": False,
    },
    {
        "id": "ticker_aapl_analysis",
        "ticker": "AAPL",
        "message": "Analyze AAPL for the next 2 weeks. Give risks, invalidation, and a clear stance.",
        "min_chars": 200,
        "expected_route": "ticker_analysis",
    },
    {
        "id": "decisive_trade_order",
        "ticker": "",
        "message": (
            "Find one US or Canadian liquid stock with a real 14-day catalyst. "
            "Do not scan China stocks. Return BUY_CANDIDATE, WAIT, or REJECT_ALL."
        ),
        "min_chars": 160,
        "expected_scanner_invoked": True,
    },
    {
        "id": "smallcap_under_5cad",
        "ticker": "",
        "message": (
            "Use opportunity criteria for smallcaps or penny stocks under CAD 5, "
            "US or Canada only, with liquidity and a real catalyst. Give one candidate or reject all."
        ),
        "min_chars": 160,
        "expected_scanner_invoked": True,
    },
    {
        "id": "risk_panic_cash",
        "ticker": "",
        "message": "Markets are falling. Should I sell everything and go to cash? Answer with risk gates.",
        "min_chars": 160,
    },
    {
        "id": "education_etf_vs_mutual",
        "ticker": "",
        "message": "Explain ETFs vs mutual funds for a Canadian beginner, with practical pros and cons.",
        "min_chars": 160,
    },
    {
        "id": "debt_vs_investing",
        "ticker": "",
        "message": "I have credit card debt at 19 percent and CAD 1000. Should I invest or pay debt?",
        "min_chars": 160,
    },
    {
        "id": "portfolio_diversification",
        "ticker": "",
        "message": "How should a Canadian family diversify CAD 50k across cash, ETFs, and risk assets?",
        "min_chars": 180,
    },
    {
        "id": "chart_context_aapl",
        "ticker": "AAPL",
        "message": "Using AAPL context only, tell me what would invalidate a bullish short-term thesis.",
        "min_chars": 160,
    },
]

FAILURE_TEXT = (
    "Bob failed to produce a valid answer",
    "could not produce a complete answer",
    "Traceback",
    "Unhandled",
)


def _parse_stream(raw_text: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    chunks: list[str] = []
    errors: list[str] = []
    trace: dict[str, Any] = {}

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"bad_json:{line[:120]}")
            continue
        events.append(event)
        event_type = event.get("type")
        if event_type == "CHUNK":
            chunks.append(str(event.get("content", "")))
        elif event_type == "ERROR":
            errors.append(str(event.get("detail") or event.get("error") or event))
        elif event_type == "STREAM_END":
            trace_value = event.get("trace")
            if isinstance(trace_value, dict):
                trace = trace_value

    content = "".join(chunks)
    return {
        "events": events,
        "event_count": len(events),
        "content": content,
        "content_length": len(content.strip()),
        "errors": errors,
        "trace": trace,
    }


def _evaluate_case(
    case: dict[str, Any], parsed: dict[str, Any], elapsed_s: float
) -> dict[str, Any]:
    content = parsed["content"]
    trace = parsed["trace"]
    min_chars = int(case["min_chars"])
    failure_hits = [text for text in FAILURE_TEXT if text.lower() in content.lower()]
    final_content_length = int(trace.get("final_content_length") or parsed["content_length"] or 0)
    route = trace.get("route_used") or trace.get("route") or "unknown"
    scanner_invoked = bool(trace.get("scanner_invoked"))
    quality = evaluate_answer_quality(case["message"], content, min_chars=min_chars)

    checks = {
        "no_http_or_stream_error": not parsed["errors"],
        "nonempty_answer": parsed["content_length"] >= min_chars,
        "stream_end_trace_present": bool(trace),
        "final_content_positive": final_content_length > 0,
        "no_failure_text": not failure_hits,
        "quality_contract": bool(quality["ok"]),
    }
    if case.get("expected_route"):
        checks["expected_route"] = route == case["expected_route"]
    if "expected_scanner_invoked" in case:
        checks["expected_scanner_invoked"] = scanner_invoked == bool(
            case["expected_scanner_invoked"]
        )
    ok = all(checks.values())
    return {
        "id": case["id"],
        "ok": ok,
        "elapsed_s": round(elapsed_s, 2),
        "content_length": parsed["content_length"],
        "final_content_length": final_content_length,
        "event_count": parsed["event_count"],
        "route": route,
        "intent": trace.get("detected_intent") or trace.get("intent") or "unknown",
        "scanner_invoked": scanner_invoked,
        "llm_calls_total": trace.get("llm_calls_total"),
        "checks": checks,
        "errors": parsed["errors"],
        "failure_hits": failure_hits,
        "quality_reasons": quality["reasons"],
        "preview": " ".join(content.split())[:280],
    }


def run_deeptest(base_url: str, headed: bool, timeout_ms: int) -> dict[str, Any]:
    out_dir = ROOT / "output" / "playwright"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    screenshot_path = out_dir / f"bob-deeptest-10-{stamp}.png"
    report_path = out_dir / f"bob-deeptest-10-{stamp}.json"

    console_errors: list[str] = []
    page_errors: list[str] = []
    results: list[dict[str, Any]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_selector("#chat", timeout=timeout_ms)
        page.wait_for_selector("#user-inp", timeout=timeout_ms)
        page.wait_for_selector("#send-btn", timeout=timeout_ms)
        page.wait_for_selector("#live-canvas", timeout=timeout_ms)
        page.get_by_text("Bob is online.").wait_for(timeout=timeout_ms)

        health = page.evaluate(
            """
            async () => {
              const response = await fetch('/health');
              return { ok: response.ok, status: response.status, body: await response.json() };
            }
            """
        )
        if not health.get("ok"):
            raise AssertionError(f"health failed from browser: {health}")

        for case in PROMPTS:
            started = time.monotonic()
            try:
                raw = page.evaluate(
                    """
                    async ({ caseData, timeoutMs }) => {
                      const controller = new AbortController();
                      const timer = setTimeout(() => controller.abort(), timeoutMs);
                      try {
                        const payload = {
                          from: 'bob_deeptest_10',
                          to: 'bob',
                          type: 'TASK.SUBMIT',
                          payload: {
                            message: caseData.message,
                            ticker: caseData.ticker || '',
                            session_id: 'bob_deeptest_10_' + caseData.id
                          }
                        };
                        const response = await fetch('/task/submit', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify(payload),
                          signal: controller.signal
                        });
                        return {
                          ok: response.ok,
                          status: response.status,
                          text: await response.text()
                        };
                      } catch (error) {
                        return {
                          ok: false,
                          status: 0,
                          text: String(error && error.name ? error.name + ': ' + error.message : error)
                        };
                      } finally {
                        clearTimeout(timer);
                      }
                    }
                    """,
                    {"caseData": case, "timeoutMs": timeout_ms},
                )
            except Exception as exc:
                raw = {"ok": False, "status": 0, "text": str(exc)}
            elapsed_s = time.monotonic() - started
            if not raw.get("ok"):
                parsed = {
                    "events": [],
                    "event_count": 0,
                    "content": "",
                    "content_length": 0,
                    "errors": [f"HTTP {raw.get('status')}: {raw.get('text', '')[:300]}"],
                    "trace": {},
                }
            else:
                parsed = _parse_stream(str(raw.get("text") or ""))
            result = _evaluate_case(case, parsed, elapsed_s)
            results.append(result)
            status = "OK" if result["ok"] else "FAIL"
            print(
                f"{status:<4} {result['id']:<26} len={result['content_length']:<5} "
                f"route={result['route']:<16} intent={result['intent']:<24} {result['elapsed_s']}s",
                flush=True,
            )

        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    summary = {
        "ok": failed == 0 and not page_errors,
        "base_url": base_url,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshot": str(screenshot_path),
        "report": str(report_path),
        "results": results,
    }
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    if page_errors:
        raise AssertionError(f"browser page errors: {page_errors}")
    if failed:
        failed_ids = [item["id"] for item in results if not item["ok"]]
        raise AssertionError(f"Bob deeptest failed {failed}/{len(results)} cases: {failed_ids}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 10 live Bob prompts before delivery.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=120_000)
    args = parser.parse_args()

    try:
        summary = run_deeptest(
            base_url=args.base_url.rstrip("/"),
            headed=args.headed,
            timeout_ms=args.timeout_ms,
        )
    except PlaywrightTimeoutError as exc:
        print(json.dumps({"ok": False, "error": f"timeout: {exc}"}, indent=2))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
