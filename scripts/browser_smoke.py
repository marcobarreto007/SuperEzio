"""Browser smoke test for the local SuperEzio UI.

Validates:
- API health is reachable.
- The UI loads core chat/chart controls.
- Chart data endpoint is reachable from the browser.
- The chart canvas renders nonblank pixels.
- A real chat submission returns a nonempty Bob answer.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = os.getenv("SUPEREZIO_BROWSER_SMOKE_URL", "http://127.0.0.1:8002")
DEFAULT_PROMPT = (
    "I live in Canada, earn and spend in CAD, have a family, unstable work income, "
    "and have CAD 25,000 to allocate between emergency cash reserve, debt, ETFs, "
    "side-business equipment, and education. Give me a concise serious framework."
)


def _http_json(url: str, timeout_s: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise AssertionError(f"{url} did not return a JSON object")
    return data


def _assert_canvas_nonblank(page: Page) -> dict[str, Any]:
    result = page.evaluate(
        """
        () => {
          const canvas = document.querySelector('#live-canvas');
          if (!canvas) return { ok: false, reason: 'missing_canvas' };
          const width = canvas.width;
          const height = canvas.height;
          if (!width || !height) return { ok: false, reason: 'zero_sized_canvas', width, height };
          const ctx = canvas.getContext('2d');
          const data = ctx.getImageData(0, 0, width, height).data;
          let nonBlank = 0;
          for (let i = 3; i < data.length; i += 4) {
            if (data[i] !== 0) nonBlank++;
          }
          return { ok: nonBlank > 100, width, height, nonBlank };
        }
        """
    )
    if not result.get("ok"):
        raise AssertionError(f"chart canvas failed smoke: {result}")
    return result


def _browser_chart_fetch(page: Page) -> dict[str, Any]:
    result = page.evaluate(
        """
        async () => {
          const response = await fetch('/api/chart-data/AAPL?timeframe=6M');
          const data = await response.json();
          return {
            ok: response.ok,
            status: response.status,
            ticker: data.ticker || null,
            hasPrice: Boolean(data.price),
            candleCount: Array.isArray(data.candles) ? data.candles.length : 0
          };
        }
        """
    )
    if not result.get("ok"):
        raise AssertionError(f"browser chart fetch failed: {result}")
    return result


def _submit_chat(page: Page, prompt: str, timeout_ms: int) -> dict[str, Any]:
    page.fill("#user-inp", prompt)
    page.click("#send-btn")
    page.wait_for_function(
        """
        () => {
          const trace = window.SZ && window.SZ.state && window.SZ.state.trace;
          const chat = document.querySelector('#chat');
          const text = chat ? chat.innerText : '';
          return trace && trace.final_content_length > 0 &&
            !text.includes('Bob failed to produce a valid answer');
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
            fallbackUsed: Boolean(trace.fallback_used),
            containsFinalVerdict: chatText.includes('Final verdict:'),
            containsFailureBubble: chatText.includes('Bob failed to produce a valid answer')
          };
        }
        """
    )


def run_smoke(
    base_url: str,
    headed: bool,
    skip_chat: bool,
    timeout_ms: int,
    slow_mo: int = 0,
) -> dict[str, Any]:
    health = _http_json(f"{base_url.rstrip('/')}/health")
    out_dir = ROOT / "output" / "playwright"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    screenshot_path = out_dir / f"superezio-browser-smoke-{stamp}.png"

    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed, slow_mo=slow_mo)
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
        page.wait_for_timeout(1500)

        # Smoke check for System Operations Console
        page.wait_for_selector("#ops-console-btn", timeout=timeout_ms)
        page.click("#ops-console-btn")
        page.wait_for_selector("#ops-console.open", timeout=timeout_ms)
        page.wait_for_timeout(1000)
        page.wait_for_selector("#ops-health-status", timeout=timeout_ms)
        page.click("#ops-console-close")
        page.wait_for_timeout(500)

        chart_fetch = _browser_chart_fetch(page)
        canvas = _assert_canvas_nonblank(page)

        chat: dict[str, Any] | None = None
        if not skip_chat:
            chat = _submit_chat(page, DEFAULT_PROMPT, timeout_ms)
            if chat.get("containsFailureBubble"):
                raise AssertionError(f"chat failure bubble rendered: {chat}")
            if chat.get("finalContentLength", 0) <= 0:
                raise AssertionError(f"chat produced empty answer: {chat}")

        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    if page_errors:
        raise AssertionError(f"browser page errors: {page_errors}")

    return {
        "base_url": base_url,
        "health": health,
        "chart_fetch": chart_fetch,
        "canvas": canvas,
        "chat": chat,
        "console_errors": console_errors,
        "screenshot": str(screenshot_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SuperEzio browser smoke test.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--skip-chat", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=90000)
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=300,
        help="Milliseconds to slow down each action (only applies with --headed)",
    )
    args = parser.parse_args()

    slow_mo = args.slow_mo if args.headed else 0

    try:
        result = run_smoke(
            base_url=args.base_url.rstrip("/"),
            headed=args.headed,
            skip_chat=args.skip_chat,
            timeout_ms=args.timeout_ms,
            slow_mo=slow_mo,
        )
    except PlaywrightTimeoutError as exc:
        print(json.dumps({"ok": False, "error": f"timeout: {exc}"}, indent=2))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
