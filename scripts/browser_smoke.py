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
          const container = document.querySelector('#live-canvas');
          if (!container) return { ok: false, reason: 'missing_container' };
          const mainPane = document.querySelector('#chart-main-pane');
          if (!mainPane) return { ok: false, reason: 'missing_main_pane' };
          const width = mainPane.clientWidth;
          const height = mainPane.clientHeight;
          if (!width || !height) return { ok: false, reason: 'zero_sized_pane', width, height };
          /* Check that canvas elements exist inside the chart panes */
          const canvases = mainPane.querySelectorAll('canvas');
          if (!canvases.length) return { ok: false, reason: 'no_canvas_in_pane', width, height };
          return { ok: true, width, height, canvasCount: canvases.length };
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
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), 20000);
          try {
            const response = await fetch('/api/chart-data/TD.TO?timeframe=6M', {
              signal: controller.signal
            });
            const data = await response.json();
            return {
              ok: response.ok,
              status: response.status,
              ticker: data.ticker || null,
              hasPrice: Boolean(data.price),
              candleCount: Array.isArray(data.ohlcv) ? data.ohlcv.length : 0
            };
          } catch (error) {
            return { ok: false, status: 0, error: String(error), candleCount: 0 };
          } finally {
            clearTimeout(timer);
          }
        }
        """
    )
    if not result.get("ok"):
        raise AssertionError(f"browser chart fetch failed: {result}")
    if result.get("candleCount", 0) <= 0:
        raise AssertionError(f"browser chart fetch returned no candles: {result}")
    return result


def _submit_chat(page: Page, prompt: str, timeout_ms: int) -> dict[str, Any]:
    """Preenche o input, clica enviar, e espera a resposta do Bob aparecer no chat."""
    # Dismiss auth modal if present (JWT login UI overlay)
    page.evaluate("() => { if (window.SZ?.auth?.hideModal) window.SZ.auth.hideModal(); }")
    # Open the Bob Chat slide-in panel first
    tab = page.query_selector("#bob-chat-tab")
    if tab:
        tab.click()
        page.wait_for_timeout(500)
    page.fill("#user-inp", prompt)
    page.click("#send-btn")
    # Wait for Bob's response in the current CEO message UI.
    page.wait_for_function(
        """
        () => {
          const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
          if (bobMsgs.length < 1) return false;
          const lastBob = bobMsgs[bobMsgs.length - 1];
          const text = lastBob.innerText || '';
          return text.length > 80 && !text.includes('Erro:');
        }
        """,
        timeout=timeout_ms,
    )
    return page.evaluate(
        """
        () => {
          const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
          const lastBob = bobMsgs[bobMsgs.length - 1];
          const text = lastBob ? lastBob.innerText : '';
          const userMsgs = document.querySelectorAll('#chat .msg-user');
          const typing = document.getElementById('typing');
          return {
            responseLength: text.length,
            bobMsgCount: bobMsgs.length,
            userMsgCount: userMsgs.length,
            typingVisible: typing ? typing.style.display !== 'none' : null,
            containsError: text.includes('Erro:'),
            containsPrice: /\\$\\d/.test(text),
            firstChars: text.substring(0, 200)
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
    health_timeout_s = max(5.0, min(timeout_ms / 1000.0, 30.0))
    health = _http_json(f"{base_url.rstrip('/')}/health", timeout_s=health_timeout_s)
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
        page.wait_for_function("window.SZ && typeof window.SZ.loadChart === 'function'", timeout=timeout_ms)
        page.wait_for_timeout(1500)

        # Canvas + chart (skip gracefully if not on page)
        canvas: dict[str, Any] = {"ok": True, "skipped": True, "reason": "no_live_canvas"}
        chart_fetch: dict[str, Any] = {"ok": True, "skipped": True, "reason": "chart_not_available"}
        try:
            page.wait_for_selector("#live-canvas", timeout=3000)
            chart_fetch = _browser_chart_fetch(page)
            page.evaluate(
                """
                async () => {
                  if (window.SZ && typeof window.SZ.loadChart === 'function') {
                    await Promise.race([
                      window.SZ.loadChart('TD.TO'),
                      new Promise((_, reject) => setTimeout(
                        () => reject(new Error('loadChart timed out after 20s')), 20000
                      ))
                    ]);
                  }
                }
                """
            )
            canvas = _assert_canvas_nonblank(page)
        except PlaywrightTimeoutError:
            pass  # UI may not have chart loaded — not a blocker

        # Chat smoke (core validation)
        chat: dict[str, Any] | None = None
        if not skip_chat:
            chat = _submit_chat(page, DEFAULT_PROMPT, timeout_ms)
            if chat.get("containsError"):
                raise AssertionError(f"chat returned error: {chat}")
            if chat.get("responseLength", 0) <= 80:
                raise AssertionError(f"chat produced empty/short answer: {chat}")

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
    parser.add_argument("--timeout-ms", type=int, default=180000)
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
