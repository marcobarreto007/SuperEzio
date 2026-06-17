"""Live end-user probe for chart endpoint plus 20 Bob paper-order commands.

The probe runs from a browser context with Playwright:
- opens the local cockpit
- calls the same /api/chart-data/{ticker} endpoint used by the UI
- sends sequential /task/submit paper-order commands to Bob
- checks /task/active and /cockpit/portfolio after every command
- saves an append-only report under output/playwright/

This is intentionally a live paper/demo validation script, not a unit test.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "playwright"

ORDER_TICKERS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "PLUG",
    "SNDL",
    "NOK",
    "QQQ",
    "SPY",
    "VOO",
    "AMZN",
    "GOOG",
    "META",
    "AMD",
    "INTC",
    "F",
    "SOFI",
    "ATER",
    "TOP",
    "TQQQ",
]


def _round_limit(price: float) -> float:
    if not math.isfinite(price) or price <= 0:
        return 1.0
    if price < 2:
        return round(max(0.01, price * 0.5), 2)
    return round(price * 0.5, 2)


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
            errors.append(f"bad_json:{line[:160]}")
            continue
        events.append(event)
        event_type = event.get("type")
        if event_type == "CHUNK":
            chunks.append(str(event.get("content", "")))
        elif event_type == "ERROR":
            errors.append(str(event.get("detail") or event.get("error") or event))
        elif event_type == "STREAM_END" and isinstance(event.get("trace"), dict):
            trace = event["trace"]

    content = "".join(chunks)
    event_types: dict[str, int] = {}
    registry_event_count = 0
    mri_event_count = 0
    paper_exec_count = 0
    auto_execute_completed = False
    submit_result: dict[str, Any] | None = None

    for event in events:
        event_type = str(event.get("type") or "")
        event_types[event_type] = event_types.get(event_type, 0) + 1
        if event_type == "SCAN_EVENT":
            registry_event_count += 1
        elif event_type == "DATA_COLLECTED":
            mri = event.get("mri_events")
            if isinstance(mri, dict):
                mri_event_count += int(mri.get("event_count") or 0)
        elif event_type == "PAPER_EXEC":
            paper_exec_count += 1
        elif event_type == "PIPELINE_STEP" and event.get("step") == "auto_execute_paper":
            if event.get("status") == "completed":
                auto_execute_completed = True
                result = event.get("result")
                if isinstance(result, dict):
                    submit_result = result

    return {
        "events": events,
        "event_types": event_types,
        "content": content,
        "content_length": len(content.strip()),
        "errors": errors,
        "trace": trace,
        "registry_event_count": registry_event_count,
        "mri_event_count": mri_event_count,
        "paper_exec_count": paper_exec_count,
        "auto_execute_completed": auto_execute_completed,
        "submit_result": submit_result,
    }


def _chart_summary(chart: dict[str, Any]) -> dict[str, Any]:
    ohlcv = chart.get("ohlcv") if isinstance(chart, dict) else None
    if not isinstance(ohlcv, list) or not ohlcv:
        return {"ok": False, "points": 0, "last": 0.0, "context": "No chart data."}
    last_bar = ohlcv[-1] if isinstance(ohlcv[-1], dict) else {}
    last = float(last_bar.get("close") or last_bar.get("c") or chart.get("price") or 0)
    first_bar = ohlcv[0] if isinstance(ohlcv[0], dict) else {}
    first = float(first_bar.get("close") or first_bar.get("c") or last or 0)
    change_pct = ((last - first) / first * 100.0) if first else 0.0
    ticker = str(chart.get("ticker") or "").upper()
    timeframe = str(chart.get("timeframe") or "6M")
    recent = []
    for bar in ohlcv[-5:]:
        if not isinstance(bar, dict):
            continue
        recent.append(
            {
                "t": bar.get("time") or bar.get("date") or bar.get("timestamp"),
                "o": bar.get("open") or bar.get("o"),
                "h": bar.get("high") or bar.get("h"),
                "l": bar.get("low") or bar.get("l"),
                "c": bar.get("close") or bar.get("c"),
                "v": bar.get("volume") or bar.get("v"),
            }
        )
    context = (
        f"UI chart endpoint context: ticker={ticker}; timeframe={timeframe}; "
        f"points={len(ohlcv)}; last={last:.2f}; change_from_first={change_pct:.2f}%; "
        f"recent_ohlcv={json.dumps(recent, ensure_ascii=False)}"
    )
    return {
        "ok": True,
        "ticker": ticker,
        "timeframe": timeframe,
        "points": len(ohlcv),
        "last": round(last, 4),
        "change_pct": round(change_pct, 4),
        "context": context,
    }


def _message(case_no: int, ticker: str, limit_price: float) -> str:
    return (
        f"Bob, TESTE #{case_no:02d}: ordem operacional de validacao. "
        f"Use o CASE completo e as ferramentas obrigatorias antes de decidir: "
        f"chart_context da UI, collect_data, MathHub, Genie, Deep, experts, "
        f"Trinity e guardrails. Se o comite permitir, envie PAPER_TICKET para BUY 1 {ticker} "
        f"LMT {limit_price:.2f}. Ambiente de treino simulado; nunca live money. "
        f"Depois responda curto com: decisao, risco, eventos vistos, resultado de envio ou bloqueio."
    )


def run_probe(base_url: str, limit: int, timeout_ms: int, headed: bool) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report_path = OUT_DIR / f"bob-order-probe-20-{stamp}.json"
    screenshot_path = OUT_DIR / f"bob-order-probe-20-{stamp}.png"
    session_id = f"bob_order_probe_20_{stamp}"

    results: list[dict[str, Any]] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_selector("#live-canvas", timeout=timeout_ms)
        page.wait_for_selector("#user-inp", timeout=timeout_ms)

        health = page.evaluate(
            """async () => {
              const r = await fetch('/health');
              return { ok: r.ok, status: r.status, body: await r.json() };
            }"""
        )
        portfolio_before = page.evaluate(
            """async () => {
              const r = await fetch('/cockpit/portfolio');
              return { ok: r.ok, status: r.status, body: await r.json() };
            }"""
        )
        active_before = page.evaluate(
            """async () => {
              const r = await fetch('/task/active');
              return { ok: r.ok, status: r.status, body: await r.json() };
            }"""
        )

        for idx, ticker in enumerate(ORDER_TICKERS[:limit], 1):
            chart_response = page.evaluate(
                """async ({ ticker }) => {
                  const r = await fetch(`/api/chart-data/${encodeURIComponent(ticker)}?timeframe=6M`);
                  let body = null;
                  try { body = await r.json(); } catch (_) { body = await r.text(); }
                  return { ok: r.ok, status: r.status, body };
                }""",
                {"ticker": ticker},
            )
            chart = chart_response.get("body") if chart_response.get("ok") else {}
            chart_info = _chart_summary(chart if isinstance(chart, dict) else {})
            limit_price = _round_limit(float(chart_info.get("last") or 0))
            command = _message(idx, ticker, limit_price)

            t0 = time.monotonic()
            raw = page.evaluate(
                """async ({ command, ticker, chartContext, sessionId, timeoutMs }) => {
                  const controller = new AbortController();
                  const timer = setTimeout(() => controller.abort(), timeoutMs);
                  try {
                    const portfolio = await fetch('/cockpit/portfolio').then(r => r.json()).catch(() => ({}));
                    const payload = {
                      version: 'a2a/1.0',
                      msg_id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
                      from: 'ui-end-user-probe',
                      to: 'bob',
                      type: 'TASK.SUBMIT',
                      payload: {
                        message: command,
                        ticker,
                        chart_context: chartContext,
                        chart_context_ready: true,
                        chart_context_source: 'ui_chart_endpoint_probe',
                        portfolio_context: JSON.stringify(portfolio).slice(0, 6000),
                        session_id: sessionId,
                        rigor: 'strict',
                        memory_mode: 'relevant_all'
                      }
                    };
                    const response = await fetch('/task/submit', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json', 'Accept': 'application/x-ndjson' },
                      body: JSON.stringify(payload),
                      signal: controller.signal
                    });
                    return { ok: response.ok, status: response.status, text: await response.text() };
                  } catch (error) {
                    return {
                      ok: false,
                      status: 0,
                      text: String(error && error.name ? error.name + ': ' + error.message : error)
                    };
                  } finally {
                    clearTimeout(timer);
                  }
                }""",
                {
                    "command": command,
                    "ticker": ticker,
                    "chartContext": chart_info["context"],
                    "sessionId": session_id,
                    "timeoutMs": timeout_ms,
                },
            )
            elapsed_s = round(time.monotonic() - t0, 2)
            parsed = _parse_stream(str(raw.get("text") or "")) if raw.get("ok") else {
                "events": [],
                "event_types": {},
                "content": "",
                "content_length": 0,
                "errors": [f"HTTP {raw.get('status')}: {str(raw.get('text') or '')[:500]}"],
                "trace": {},
                "registry_event_count": 0,
                "mri_event_count": 0,
                "paper_exec_count": 0,
                "auto_execute_completed": False,
                "submit_result": None,
            }
            active_after = page.evaluate(
                """async () => {
                  const r = await fetch('/task/active');
                  return { ok: r.ok, status: r.status, body: await r.json() };
                }"""
            )
            portfolio_after = page.evaluate(
                """async () => {
                  const r = await fetch('/cockpit/portfolio');
                  return { ok: r.ok, status: r.status, body: await r.json() };
                }"""
            )

            active_count = int(((active_after.get("body") or {}).get("count") or 0))
            if active_count:
                for task in (active_after.get("body") or {}).get("tasks") or []:
                    run_id = task.get("run_id")
                    if run_id:
                        page.evaluate(
                            """async ({ runId }) => fetch(`/task/cancel/${encodeURIComponent(runId)}`, { method: 'POST' })""",
                            {"runId": run_id},
                        )

            portfolio_body = portfolio_after.get("body") or {}
            trace = parsed.get("trace") or {}
            order_path_touched = (
                parsed["paper_exec_count"] > 0
                or parsed["auto_execute_completed"]
                or "PAPER_TICKET" in parsed["content"]
                or "PAPER_ORDER" in parsed["content"]
                or "submit_paper_order" in parsed["content"]
            )
            ok = (
                bool(raw.get("ok"))
                and parsed["content_length"] > 80
                and bool(trace)
                and not parsed["errors"]
                and active_count == 0
                and "Bob failed to produce a valid answer" not in parsed["content"]
                and order_path_touched
            )
            result = {
                "case_no": idx,
                "ticker": ticker,
                "limit_price": limit_price,
                "ok": ok,
                "elapsed_s": elapsed_s,
                "http_status": raw.get("status"),
                "chart": {
                    "ok": bool(chart_response.get("ok")) and chart_info["ok"],
                    "status": chart_response.get("status"),
                    "points": chart_info.get("points"),
                    "last": chart_info.get("last"),
                },
                "stream": {
                    "content_length": parsed["content_length"],
                    "event_types": parsed["event_types"],
                    "errors": parsed["errors"],
                    "route": trace.get("route_used") or trace.get("route") or "unknown",
                    "intent": trace.get("detected_intent") or trace.get("intent") or "unknown",
                    "scanner_invoked": bool(trace.get("scanner_invoked")),
                    "registry_event_count": parsed["registry_event_count"],
                    "mri_event_count": parsed["mri_event_count"],
                    "paper_exec_count": parsed["paper_exec_count"],
                    "auto_execute_completed": parsed["auto_execute_completed"],
                    "order_path_touched": order_path_touched,
                    "submit_result": parsed["submit_result"],
                },
                "active_after": active_after.get("body"),
                "portfolio_after": {
                    "connected": portfolio_body.get("connected"),
                    "mode": portfolio_body.get("mode"),
                    "equity": portfolio_body.get("equity"),
                    "orders_count": portfolio_body.get("orders_count"),
                    "broker_orders_count": portfolio_body.get("broker_orders_count"),
                    "positions_count": portfolio_body.get("positions_count"),
                    "selected_ticker": portfolio_body.get("selected_ticker"),
                },
                "preview": " ".join(parsed["content"].split())[:500],
            }
            results.append(result)
            status = "OK" if ok else "FAIL"
            print(
                f"{status:<4} #{idx:02d} {ticker:<5} chart={result['chart']['points']} "
                f"route={result['stream']['route']:<16} intent={result['stream']['intent']:<24} "
                f"paper_exec={result['stream']['paper_exec_count']} orders={result['portfolio_after']['orders_count']} "
                f"active={active_count} {elapsed_s}s",
                flush=True,
            )

        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    summary = {
        "ok": failed == 0,
        "base_url": base_url,
        "session_id": session_id,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "health": health,
        "active_before": active_before,
        "portfolio_before": portfolio_before,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "screenshot": str(screenshot_path),
        "report": str(report_path),
        "results": results,
    }
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"REPORT {report_path}")
    print(f"SCREENSHOT {screenshot_path}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout-ms", type=int, default=600_000)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    summary = run_probe(
        base_url=args.base_url.rstrip("/"),
        limit=max(0, min(args.limit, len(ORDER_TICKERS))),
        timeout_ms=args.timeout_ms,
        headed=args.headed,
    )
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
