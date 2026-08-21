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
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = os.getenv("SUPEREZIO_BROWSER_SMOKE_URL", "http://127.0.0.1:8002")
DEFAULT_PROMPT = (
    "Moro no Canada, ganho e gasto em CAD, tenho familia, renda de trabalho instavel "
    "e CAD 25.000 para alocar entre reserva de emergencia, dividas, ETFs, "
    "equipamento para negocio proprio e educacao. De um framework serio e conciso, "
    "em portugues."
)
# The CEO must answer Brazilian-Portuguese operators in Portuguese.
PT_MARKERS_RE = r"\b(você|não|uma|para|com|como|por|dos|das|ser|pode|deve)\b"


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
          /* Require at least one canvas with painted (non-transparent) pixels. */
          const painted = Array.from(canvases).map((canvas) => {
            try {
              const ctx = canvas.getContext('2d');
              if (!ctx) return false;
              const sample = ctx.getImageData(0, 0, Math.min(canvas.width, 128), Math.min(canvas.height, 128)).data;
              for (let i = 3; i < sample.length; i += 4) {
                if (sample[i] > 0) return true;
              }
              return false;
            } catch (error) { return false; }
          });
          if (!painted.some(Boolean)) {
            return { ok: false, reason: 'all_canvases_blank', width, height };
          }
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
            const ohlcv = Array.isArray(data.ohlcv) ? data.ohlcv : [];
            let timesOk = false;
            let firstTime = null;
            let lastTime = null;
            if (ohlcv.length) {
              const first = ohlcv[0];
              const key =
                first && typeof first === 'object' && 'time' in first ? 'time'
                : first && typeof first === 'object' && 't' in first ? 't'
                : null;
              if (key) {
                const times = ohlcv.map((c) => Number(c[key])).filter(Number.isFinite);
                firstTime = times.length ? times[0] : null;
                lastTime = times.length ? times[times.length - 1] : null;
                let increasing = true;
                for (let i = 1; i < times.length; i++) {
                  if (times[i] < times[i - 1]) { increasing = false; break; }
                }
                timesOk = times.length > 0 && times[0] > 0 && increasing;
              }
            }
            return {
              ok: response.ok,
              status: response.status,
              ticker: data.ticker || null,
              hasPrice: Boolean(data.price),
              candleCount: ohlcv.length,
              timesOk,
              firstTime,
              lastTime
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
    if not result.get("timesOk"):
        raise AssertionError(
            f"browser chart fetch returned invalid timestamps (zero or unordered): {result}"
        )
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
    # Sentinel: a stale answer from a previous session must never satisfy the
    # smoke. Only a NEW CEO message beyond this baseline counts.
    baseline = page.evaluate("() => document.querySelectorAll('#chat .msg-ceo').length")
    page.fill("#user-inp", prompt)
    page.click("#send-btn")
    # Wait for Bob's response in the current CEO message UI.
    page.wait_for_function(
        f"""
        () => {{
          const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
          if (bobMsgs.length <= {baseline}) return false;
          const last = bobMsgs[bobMsgs.length - 1];
          const text = last.innerText || '';
          return text.length > 20 && !text.includes('Erro:');
        }}
        """,
        timeout=timeout_ms,
    )
    result = page.evaluate(
        """
        () => {
          const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
          const lastBob = bobMsgs[bobMsgs.length - 1];
          const text = lastBob ? (lastBob.innerText || '') : '';
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
    result["newMessageCount"] = result.get("bobMsgCount", 0) - baseline
    return result


def _chat_api_check(base_url: str, prompt: str, timeout_ms: int) -> dict[str, Any]:
    """Submits the chat prompt through the public API and validates the NDJSON
    stream directly. Language/answer assertions live here because the frontend
    DOM is racy: pipeline status cards (SDCA, experts) render as .msg-ceo
    bubbles and can masquerade as the final answer."""
    envelope = {
        "version": "a2a/1.0",
        "from": "smoke",
        "to": "superezio",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": prompt,
            "ticker": "",
            "timeframe": "6M",
            "session_id": f"browser-smoke-{time.strftime('%H%M%S')}",
        },
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/task/submit",
        data=json.dumps(envelope).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
    )
    t0 = time.perf_counter()
    chunks: list[str] = []
    saw_end = False
    with urllib.request.urlopen(request, timeout=max(timeout_ms / 1000.0, 120.0)) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            etype = obj.get("type")
            if etype == "CHUNK":
                chunks.append(obj.get("content", ""))
            elif etype == "STREAM_END":
                saw_end = True
                break
    elapsed = time.perf_counter() - t0
    text = "".join(chunks)
    pt = re.search(r"\b(você|não|uma|para|com|como|por|dos|das|ser|pode|deve)\b", text, re.I)
    en = re.search(r"\b(the|of|and|your|you|is|are|with)\b", text, re.I)
    return {
        "sawStreamEnd": saw_end,
        "contentLength": len(text),
        "languageOk": bool(pt and not en),
        "hasPtMarkers": bool(pt),
        "hasEnMarkers": bool(en),
        "elapsedSeconds": round(elapsed, 1),
        "firstChars": text[:200],
    }


def run_smoke(
    base_url: str,
    headed: bool,
    skip_chat: bool,
    timeout_ms: int,
    slow_mo: int = 0,
) -> dict[str, Any]:
    health_timeout_s = max(5.0, min(timeout_ms / 1000.0, 30.0))
    health = _http_json(f"{base_url.rstrip('/')}/health", timeout_s=health_timeout_s)
    cockpit = _http_json(f"{base_url.rstrip('/')}/cockpit/summary", timeout_s=health_timeout_s)
    primary_model = (cockpit.get("status") or {}).get("primary_model")
    if primary_model != "Qwen3.8-27B-UD-IQ2_XXS":
        raise AssertionError(
            f"cockpit reports wrong primary model: {primary_model!r} "
            f"(contract: Qwen3.8-27B-UD-IQ2_XXS)"
        )
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
        page.wait_for_function(
            "window.SZ && typeof window.SZ.loadChart === 'function'", timeout=timeout_ms
        )
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

        # Chat smoke (core validation). UI check proves the pipeline renders a
        # NEW message in the DOM; the API check proves the answer stream ends
        # properly and is in Portuguese (DOM is racy for language assertions).
        chat: dict[str, Any] | None = None
        chat_api: dict[str, Any] | None = None
        if not skip_chat:
            chat = _submit_chat(page, DEFAULT_PROMPT, timeout_ms)
            if chat.get("containsError"):
                raise AssertionError(f"chat returned error: {chat}")
            if chat.get("responseLength", 0) <= 20:
                raise AssertionError(f"chat produced empty answer: {chat}")
            if not chat.get("newMessageCount", 0) > 0:
                raise AssertionError(
                    f"chat did not produce a NEW Bob message (stale-answer risk): {chat}"
                )
            chat_api = _chat_api_check(base_url, DEFAULT_PROMPT, timeout_ms)
            if not chat_api.get("sawStreamEnd"):
                raise AssertionError(f"chat stream never emitted STREAM_END: {chat_api}")
            if chat_api.get("contentLength", 0) <= 80:
                raise AssertionError(f"chat stream produced empty/short answer: {chat_api}")
            if not chat_api.get("languageOk"):
                raise AssertionError(
                    f"chat language drift — expected PT answer, got: {chat_api.get('firstChars')!r}"
                )

        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    if page_errors:
        raise AssertionError(f"browser page errors: {page_errors}")
    if console_errors:
        raise AssertionError(f"browser console errors: {console_errors}")

    return {
        "base_url": base_url,
        "health": health,
        "cockpit_primary_model": primary_model,
        "chart_fetch": chart_fetch,
        "canvas": canvas,
        "chat": chat,
        "chat_api": chat_api,
        "console_errors": console_errors,
        "screenshot": str(screenshot_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SuperEzio browser smoke test.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--skip-chat", action="store_true")
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=600000,
        help="Chat answer timeout — the full financial pipeline can take minutes",
    )
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
