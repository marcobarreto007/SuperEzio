"""Full E2E browser test covering the complete SuperEzio analysis flow.

Validates (per POLITICA F51 — Playwright obrigatorio):
1. Page loads and auth is handled (dev mode skip or manual login)
2. Chart loads with visible candles and indicators (RSI, MACD, SMA)
3. Chat submission works with "AAPL analise"
4. Pipeline completes with expert cards updated (>=2 of 5)
5. Bob responds with text containing "AAPL"
6. No 401 errors in browser console
7. No expert card shows "WAIT" after pipeline completes

Screenshots saved to: output/playwright/e2e/
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
BASE_URL = os.environ.get("SUPEREZIO_E2E_URL", "http://127.0.0.1:8002")
SCREENSHOT_DIR = ROOT / "output" / "playwright" / "e2e"

# ── Timeouts ──────────────────────────────────────────────────────────────────
HEALTH_TIMEOUT_S = 45
NAV_TIMEOUT_MS = 30_000
PIPELINE_TIMEOUT_MS = int(os.environ.get("SUPEREZIO_E2E_PIPELINE_TIMEOUT", "150_000"))

# ── Expert card definitions (verdict element IDs and initial states) ──────────
EXPERT_CARDS: dict[str, dict[str, str]] = {
    "f51": {"verdict_id": "f51-verdict", "initial": "WAIT"},
    "sdca": {"verdict_id": "sdca-verdict", "initial": "WAIT"},
    "neural": {"verdict_id": "neural-verdict", "initial": "WAIT"},
    "trinity": {"verdict_id": "trinity-verdict", "initial": "--"},
    "guardrails": {"verdict_id": "guardrails-summary", "initial": "--/30"},
}

WAIT_CARDS = ["f51", "sdca", "neural"]  # cards that initially show "WAIT"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _server_healthy(url: str, timeout_s: float = 5.0) -> bool:
    """Return True if the agent server /health returns 200."""
    import urllib.request

    try:
        resp = urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=timeout_s)
        return resp.status == 200
    except Exception:
        return False


def _start_server() -> subprocess.Popen:
    """Start agent_server.main as a subprocess.

    Sets PYTHONPATH so that ``import core.xxx`` resolves from ``src/``.
    Returns the Popen handle (caller must terminate).
    """
    env = {
        **os.environ,
        "PYTHONPATH": str(SRC),
        # Force dev mode so no JWT auth is required on the UI side
        "SUPEREZIO_JWT_SECRET": "",
        # Disable heavy background scans so Bob's pipeline gets a clean,
        # deterministic event loop. The ANS scans ~893 tickers every 60s and
        # mangala runs a parallel opportunity scan — both starve user requests
        # on a cold server. Tests must be deterministic (POLITICA F51).
        "SUPEREZIO_ANS_SCAN": "0",
        "SUPEREZIO_MANGALA_SCAN": "0",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "agent_server.main"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.time() + HEALTH_TIMEOUT_S
    while time.time() < deadline:
        if _server_healthy(BASE_URL):
            return proc
        time.sleep(1.0)

    proc.kill()
    raise RuntimeError(f"Server did not become healthy within {HEALTH_TIMEOUT_S}s at {BASE_URL}")


def _screenshot(page: Page, name: str) -> Path:
    """Take a full-page screenshot and return its path."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def _collect_state(page: Page) -> dict[str, Any]:
    """Extract all relevant UI state via a single evaluate call."""
    return page.evaluate(
        """
        () => {
            const st = window.SZ && window.SZ.state || {};
            const chartData = st.chartData || {};

            // Chat messages
            const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
            const userMsgs = document.querySelectorAll('#chat .msg-user');

            // Bob's answer text (concatenate all CEO messages)
            let bobText = '';
            bobMsgs.forEach(function (m) {
                const bubble = m.querySelector('.msg-bubble');
                if (bubble) {
                    // Exclude cards and pipeline-bar from text
                    const clone = bubble.cloneNode(true);
                    clone.querySelectorAll('.card, .pipeline-bar, .scanner-progress, .scan-summary, .feedback-bar, .thinking, .evidence-btn')
                        .forEach(function (n) { n.remove(); });
                    const t = (clone.textContent || '').trim();
                    if (t.length > bobText.length) bobText = t;
                }
            });

            // Expert card verdicts (side panel)
            const verdicts = {
                f51:        (document.getElementById('f51-verdict') || {}).textContent || 'MISSING',
                sdca:       (document.getElementById('sdca-verdict') || {}).textContent || 'MISSING',
                neural:     (document.getElementById('neural-verdict') || {}).textContent || 'MISSING',
                trinity:    (document.getElementById('trinity-verdict') || {}).textContent || 'MISSING',
                guardrails: (document.getElementById('guardrails-summary') || {}).textContent || 'MISSING',
            };

            // Chart data
            const ohlcv = Array.isArray(chartData.ohlcv) ? chartData.ohlcv : [];
            const ind = chartData.indicators || {};

            // Chart DOM (LightweightCharts or Canvas2D)
            const hasChartMainPane  = !!document.getElementById('chart-main-pane');
            const hasChartLegend    = !!document.getElementById('chart-legend');
            const hasRsiLabel       = !!document.getElementById('chart-rsi-label');
            const hasMacdLabel      = !!document.getElementById('chart-macd-label');
            const liveCanvas        = document.getElementById('live-canvas');

            // Canvas non-blank check (for Canvas2D fallback)
            let canvasNonBlank = 0;
            if (liveCanvas && liveCanvas.tagName === 'CANVAS') {
                try {
                    const ctx = liveCanvas.getContext('2d');
                    const imgData = ctx.getImageData(0, 0, liveCanvas.width, liveCanvas.height).data;
                    for (let i = 3; i < imgData.length; i += 4) {
                        if (imgData[i] !== 0) canvasNonBlank++;
                    }
                } catch (e) { /* cross-origin or tainted */ }
            }

            // Pipeline status (are there done pipeline bars?)
            const pipelineDoneSteps = document.querySelectorAll(
                '[data-sz-pipeline] .pipeline-step--done'
            ).length;
            const pipelineFailSteps = document.querySelectorAll(
                '[data-sz-pipeline] .pipeline-step--fail'
            ).length;

            // Send button disabled state (busy indicator)
            const sendBtn = document.getElementById('send-btn');
            const isBusy = sendBtn ? sendBtn.disabled : null;

            return {
                verdicts: verdicts,
                ohlcvCount: ohlcv.length,
                indicatorKeys: Object.keys(ind),
                hasRsiInData: Boolean(ind.rsi),
                hasMacdInData: Boolean(ind.macd),
                hasSmaInData: Boolean(ind.sma_20 || ind.sma20),
                hasChartMainPane: hasChartMainPane,
                hasChartLegend: hasChartLegend,
                hasRsiLabel: hasRsiLabel,
                hasMacdLabel: hasMacdLabel,
                canvasNonBlank: canvasNonBlank,
                bobMsgCount: bobMsgs.length,
                userMsgCount: userMsgs.length,
                bobResponseText: bobText.substring(0, 1000),
                bobResponseLength: bobText.length,
                pipelineDoneSteps: pipelineDoneSteps,
                pipelineFailSteps: pipelineFailSteps,
                isBusy: isBusy,
            };
        }
        """
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def server() -> subprocess.Popen | None:
    """Ensure the SuperEzio agent server is running.

    Starts it if ``/health`` does not respond within 3 seconds.
    Yields the Popen handle (or ``None`` if already running).
    """
    if _server_healthy(BASE_URL):
        yield None  # already running, nothing to clean up
        return

    proc = _start_server()
    yield proc
    # Teardown
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="module")
def browser():
    """Headless Chromium via Playwright (module-scoped)."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=os.environ.get("SUPEREZIO_E2E_HEADED") not in ("1", "true"),
            args=["--no-sandbox"],
        )
        yield browser
        browser.close()


# ── The Test ──────────────────────────────────────────────────────────────────


def test_full_browser_flow(server: subprocess.Popen | None, browser) -> None:
    """E2E smoke covering the complete user flow: auth, chart, chat, pipeline."""
    # ── Collect console/page errors ──────────────────────────────────────
    console_errors: list[str] = []
    page_errors: list[str] = []

    page = browser.new_page(viewport={"width": 1440, "height": 980})
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
    )
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    try:
        # ═════════════════════════════════════════════════════════════════
        # 1. NAVEGAR + AGUARDAR CARREGAMENTO
        # ═════════════════════════════════════════════════════════════════
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        page.wait_for_selector("#chat", timeout=NAV_TIMEOUT_MS)
        page.wait_for_selector("#user-inp", timeout=NAV_TIMEOUT_MS)
        page.wait_for_selector("#send-btn", timeout=NAV_TIMEOUT_MS)
        # Give the JS boot sequence time to initialise
        page.wait_for_timeout(2500)

        _screenshot(page, "step-01-initial")

        # ═════════════════════════════════════════════════════════════════
        # 2. AUTENTICACAO (dev mode ou login real)
        # ═════════════════════════════════════════════════════════════════
        try:
            auth_overlay = page.query_selector("#auth-modal-overlay")
            if auth_overlay:
                is_visible = page.evaluate(
                    """() => {
                        const el = document.getElementById('auth-modal-overlay');
                        return el && el.classList.contains('auth-overlay--visible');
                    }"""
                )
            else:
                is_visible = False

            if is_visible:
                # Fill in the login form and submit
                page.fill("#auth-login-username", "trader")
                page.fill("#auth-login-password", "Trade123!")
                page.click("#auth-form-login .auth-submit")

                # Wait for the modal to close
                page.wait_for_function(
                    """() => {
                        const el = document.getElementById('auth-modal-overlay');
                        return !el || !el.classList.contains('auth-overlay--visible');
                    }""",
                    timeout=15_000,
                )
                page.wait_for_timeout(1000)
                _screenshot(page, "step-02-login-complete")
        except Exception:
            pass  # Dev mode — no login needed

        # ═════════════════════════════════════════════════════════════════
        # 3. CHART INICIAL — esperar dados carregarem
        # ═════════════════════════════════════════════════════════════════
        try:
            page.wait_for_function(
                """() => window.SZ && window.SZ.state && window.SZ.state.chartData
                       && Array.isArray(window.SZ.state.chartData.ohlcv)
                       && window.SZ.state.chartData.ohlcv.length > 3""",
                timeout=20_000,
            )
        except PlaywrightTimeoutError:
            # Not fatal — chart may load after pipeline
            pass

        _screenshot(page, "step-03-chart-loaded")

        # ═════════════════════════════════════════════════════════════════
        # 4. ENVIAR MENSAGEM NO CHAT
        # ═════════════════════════════════════════════════════════════════
        # Open the Bob chat panel if it's collapsed
        live_panel = page.query_selector("#live-panel")
        if live_panel:
            has_open = page.evaluate(
                """() => document.getElementById('live-panel')
                              && document.getElementById('live-panel').classList.contains('is-open')"""
            )
            if not has_open:
                page.click("#bob-chat-tab")
                page.wait_for_timeout(600)

        # Remove welcome banner if present (avoids interference)
        page.evaluate(
            """() => {
                const w = document.querySelector('#chat .bob-welcome');
                if (w) w.remove();
            }"""
        )

        # Ensure input is enabled (not disabled by prior busy state)
        page.wait_for_selector("#user-inp:not([disabled])", timeout=5000)

        # Type the query and click Send
        page.fill("#user-inp", "AAPL analise")
        page.wait_for_timeout(400)

        _screenshot(page, "step-04-about-to-send")

        page.click("#send-btn")
        page.wait_for_timeout(500)  # Let the submit() call start

        _screenshot(page, "step-05-sent")

        # ═════════════════════════════════════════════════════════════════
        # 5. AGUARDAR FIM DO PIPELINE
        # ═════════════════════════════════════════════════════════════════
        # Strategy: poll until the Send button is re-enabled (busy=false)
        try:
            page.wait_for_function(
                """() => {
                    const btn = document.getElementById('send-btn');
                    return btn && !btn.disabled;
                }""",
                timeout=PIPELINE_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            # If the button never re-enables, collect state anyway for diagnostics
            pass

        # Give STREAM_END events time to finalise cards
        page.wait_for_timeout(3000)

        final_screenshot = _screenshot(page, "step-06-pipeline-complete")

        # ═════════════════════════════════════════════════════════════════
        # 6. EXTRAIR STATE + ASSERTIONS
        # ═════════════════════════════════════════════════════════════════
        state = _collect_state(page)

        errors: list[str] = []

        # ── 6a. Chart has visible candles ──
        ohlcv_count = state.get("ohlcvCount", 0)
        canvas_nb = state.get("canvasNonBlank", 0)
        has_pane = state.get("hasChartMainPane", False)

        if ohlcv_count < 3 and canvas_nb < 100 and not has_pane:
            errors.append(
                f"Chart has no visible data: ohlcv={ohlcv_count}, "
                f"canvasNonBlank={canvas_nb}, hasChartMainPane={has_pane}"
            )

        # ── 6b. Indicators present in chart data (RSI, MACD, SMA) ──
        missing_ind: list[str] = []
        if not state.get("hasRsiInData"):
            missing_ind.append("RSI")
        if not state.get("hasMacdInData"):
            missing_ind.append("MACD")
        if not state.get("hasSmaInData"):
            missing_ind.append("SMA")
        if missing_ind:
            errors.append(
                f"Indicators not found in chart data: {missing_ind}. "
                f"Available keys: {state.get('indicatorKeys', [])}"
            )

        # ── 6c. Bob answered with text containing "AAPL" ──
        bob_len = state.get("bobResponseLength", 0)
        bob_text = state.get("bobResponseText", "")
        if bob_len < 80:
            errors.append(
                f"Bob response too short: {bob_len} chars (expected >= 80). Text: {bob_text[:150]}"
            )
        elif "AAPL" not in bob_text.upper():
            errors.append(f"Bob answer does not mention AAPL. First 200 chars: {bob_text[:200]}")

        # ── 6d. At least 2 of 5 expert cards updated from initial state ──
        verdicts = state.get("verdicts", {})
        updated_count = 0
        updated_names: list[str] = []
        for name, info in EXPERT_CARDS.items():
            current = verdicts.get(name, "")
            if current != info["initial"]:
                updated_count += 1
                updated_names.append(name)

        if updated_count < 2:
            errors.append(
                f"Only {updated_count}/5 expert cards updated from initial "
                f"state: {updated_names}. "
                f"Full verdicts: {verdicts}"
            )

        # ── 6e. No 401 errors in console ──
        auth_errors = [e for e in console_errors if "401" in e or "401" in str(e)]
        if auth_errors:
            errors.append(
                f"Found {len(auth_errors)} 401 error(s) in browser console. "
                f"First 5: {auth_errors[:5]}"
            )

        # ── 6f. No WAIT on expert cards after pipeline complete ──
        stuck_cards = [c for c in WAIT_CARDS if verdicts.get(c, "") == "WAIT"]
        if stuck_cards:
            errors.append(
                f"Expert cards still showing WAIT after pipeline: {stuck_cards}. "
                f"All verdicts: {verdicts}"
            )

        # ── Page-level errors ──
        if page_errors:
            errors.append(f"Uncaught page errors: {page_errors[:5]}")

        # ── Report ──────────────────────────────────────────────────
        summary = {
            "ok": len(errors) == 0,
            "ohlcv_count": ohlcv_count,
            "indicator_keys": state.get("indicatorKeys", []),
            "has_rsi": state.get("hasRsiInData", False),
            "has_macd": state.get("hasMacdInData", False),
            "has_sma": state.get("hasSmaInData", False),
            "chart_rendered": has_pane or canvas_nb > 100,
            "bob_response_length": bob_len,
            "bob_mentions_aapl": "AAPL" in bob_text.upper(),
            "expert_cards_updated": updated_count,
            "expert_cards_updated_names": updated_names,
            "cards_stuck_on_wait": stuck_cards,
            "console_401_count": len(auth_errors),
            "page_errors_count": len(page_errors),
            "pipeline_done_steps": state.get("pipelineDoneSteps", 0),
            "pipeline_fail_steps": state.get("pipelineFailSteps", 0),
            "was_busy": state.get("isBusy"),
            "verdicts": verdicts,
            "screenshot": str(final_screenshot),
        }

        # Print summary as JSON for CI/checkpoint consumption
        print(json.dumps(summary, indent=2))

        if errors:
            pytest.fail("\n    ".join(errors))

    finally:
        page.close()
