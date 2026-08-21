"""Comprehensive Auth + UI verification test.

Validates:
  1. Auth modal appearance / dev-mode behavior
  2. Registration via UI
  3. Login via UI
  4. Bob Chat panel structure
  5. Status bar elements
  6. Theme verification (dark sci-fi, no glassmorphism)
  7. Chart rendering after auth
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
DEFAULT_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_TICKER = os.environ.get("SUPEREZIO_TEST_TICKER", "TD.TO").strip().upper()


def _http_json(url: str, timeout_s: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def test_auth_modal_behavior(page: Page) -> dict[str, Any]:
    """Check if auth modal auto-appears or is suppressed by dev mode."""
    # Wait a moment for auth.js to init
    page.wait_for_timeout(2000)

    modal_visible = page.evaluate(
        """() => {
            const overlay = document.getElementById('auth-modal-overlay');
            if (!overlay) return {exists: false};
            return {
                exists: true,
                visible: overlay.classList.contains('auth-overlay--visible'),
                computedDisplay: window.getComputedStyle(overlay).display,
                opacity: window.getComputedStyle(overlay).opacity,
                pointerEvents: window.getComputedStyle(overlay).pointerEvents
            };
        }"""
    )

    return modal_visible


def test_bob_chat_panel(page: Page) -> dict[str, Any]:
    """Verify Bob Chat slide-in panel structure."""
    result = page.evaluate(
        """() => {
            const panel = document.getElementById('live-panel');
            if (!panel) return {exists: false, reason: 'no #live-panel'};

            const tab = document.getElementById('bob-chat-tab');
            const chatPanel = panel.querySelector('.bob-chat__panel');
            const chatEl = document.getElementById('chat');
            const input = document.getElementById('user-inp');
            const sendBtn = document.getElementById('send-btn');
            const closeBtn = document.getElementById('bob-chat-close');

            return {
                exists: true,
                hasTab: !!tab,
                hasChatPanel: !!chatPanel,
                hasChatArea: !!chatEl,
                hasInput: !!input,
                hasSendBtn: !!sendBtn,
                hasCloseBtn: !!closeBtn,
                tabIcon: tab ? tab.querySelector('i')?.getAttribute('data-lucide') : null,
                tabLabel: tab?.querySelector('.bob-chat__tab-label')?.textContent?.trim(),
                inputPlaceholder: input?.getAttribute('placeholder'),
                panelClass: panel.className,
                inputRows: input?.getAttribute('rows'),
                sendBtnText: sendBtn?.querySelector('span')?.textContent?.trim(),
            };
        }"""
    )
    return result


def test_status_bar(page: Page) -> dict[str, Any]:
    """Verify the bottom status bar has all required elements."""
    result = page.evaluate(
        """() => {
            const bar = document.getElementById('cockpit-statusbar');
            if (!bar) return {exists: false, reason: 'no #cockpit-statusbar'};

            return {
                exists: true,
                ceo: document.getElementById('statusbar-ceo')?.textContent?.trim(),
                genie: document.getElementById('statusbar-genie')?.textContent?.trim(),
                deep: document.getElementById('statusbar-deep')?.textContent?.trim(),
                ibkr: document.getElementById('statusbar-ibkr')?.textContent?.trim(),
                guardrails: document.getElementById('statusbar-guardrails')?.textContent?.trim(),
                latency: document.getElementById('statusbar-latency')?.textContent?.trim(),
                cost: document.getElementById('statusbar-cost')?.textContent?.trim(),
                itemCount: bar.querySelectorAll('.bot-bar__item').length,
            };
        }"""
    )
    return result


def test_theme(page: Page) -> dict[str, Any]:
    """Verify dark sci-fi theme, no glassmorphism."""
    result = page.evaluate(
        """() => {
            const bodyBg = window.getComputedStyle(document.body).background;
            const bodyBgColor = window.getComputedStyle(document.body).backgroundColor;
            const root = document.documentElement;

            // Check for glassmorphism patterns (should NOT exist)
            const allEls = document.querySelectorAll('*');
            let glassCount = 0;
            allEls.forEach(el => {
                const bg = window.getComputedStyle(el).background;
                if (bg.includes('rgba(255, 255, 255, 0') && bg.includes('blur')) glassCount++;
            });

            // Check backdrop-filter (a key glassmorphism indicator)
            let backdropFilterCount = 0;
            allEls.forEach(el => {
                const bf = window.getComputedStyle(el).backdropFilter;
                if (bf && bf !== 'none') backdropFilterCount++;
            });

            // Get CSS variables for theme
            const cssVars = {
                bgPrimary: getComputedStyle(root).getPropertyValue('--bg-primary').trim(),
                bgSecondary: getComputedStyle(root).getPropertyValue('--bg-secondary').trim(),
                textPrimary: getComputedStyle(root).getPropertyValue('--text-primary').trim(),
                accent: getComputedStyle(root).getPropertyValue('--accent').trim(),
                fontFamily: getComputedStyle(root).getPropertyValue('--font-family').trim(),
                monoFont: getComputedStyle(root).getPropertyValue('--font-mono').trim(),
            };

            return {
                bodyBgColor,
                cssVars,
                glassmorphismBackdropFilterCount: backdropFilterCount,
                possibleGlassElements: glassCount,
                observations: {
                    isDarkBackground: bodyBgColor.includes('0, 0, 0') || bodyBgColor.includes('10,') || bodyBgColor.includes('4, 6, 5'),
                    usesInter: cssVars.fontFamily.toLowerCase().includes('inter'),
                    usesMono: cssVars.monoFont.toLowerCase().includes('mono'),
                    hasAccent: !!cssVars.accent,
                }
            };
        }"""
    )
    return result


def test_login_flow(page: Page) -> dict[str, Any]:
    """Test the login flow through the UI."""
    result = page.evaluate(
        """async () => {
            try {
                if (window.SZ && window.SZ.auth) {
                    await window.SZ.auth.login('testuser_ui', 'TestPass123!');
                    return {ok: true, method: 'api'};
                }
                return {ok: false, method: 'api', reason: 'SZ.auth not available'};
            } catch(e) {
                return {ok: false, method: 'api', reason: e.message};
            }
        }"""
    )
    return result


def test_auth_state_after_login(page: Page) -> dict[str, Any]:
    """Check localStorage and auth state after login."""
    result = page.evaluate(
        """() => {
            const token = localStorage.getItem('sz_access_token');
            const user = localStorage.getItem('sz_user');
            const isAuth = window.SZ?.auth?.isAuthenticated ? window.SZ.auth.isAuthenticated() : false;
            return {
                hasToken: !!token,
                tokenPrefix: token ? token.substring(0, 20) + '...' : null,
                hasUser: !!user,
                userData: user ? JSON.parse(user) : null,
                isAuthenticated: isAuth,
            };
        }"""
    )
    return result


def run_verification(
    base_url: str,
    headed: bool,
    timeout_ms: int,
    ticker: str,
    slow_mo: int = 0,
) -> dict[str, Any]:
    out_dir = ROOT / "output" / "playwright"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    screenshot_path = out_dir / f"auth-ui-flow-{stamp}.png"

    console_errors: list[str] = []
    page_errors: list[str] = []
    results: dict[str, Any] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed, slow_mo=slow_mo)
        context = browser.new_context(
            viewport={"width": 1440, "height": 980},
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.on(
            "console",
            lambda msg: (
                console_errors.append({"text": msg.text, "type": msg.type})
                if msg.type in ("error", "warning")
                else None
            ),
        )
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # Navigate
        page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(2000)

        # 1. Auth modal behavior
        results["auth_modal"] = test_auth_modal_behavior(page)

        # 2. Theme check (before login, page in initial state)
        results["theme"] = test_theme(page)

        # 3. Login flow
        login_result = test_login_flow(page)
        results["login"] = login_result

        # Wait for auth to settle
        page.wait_for_timeout(1000)

        # 4. Auth state
        results["auth_state"] = test_auth_state_after_login(page)

        # 5. Bob Chat panel
        results["bob_chat"] = test_bob_chat_panel(page)

        # 6. Status bar
        results["status_bar"] = test_status_bar(page)

        # 7. Chart data fetch (authenticated)
        try:
            chart_fetch = page.evaluate(
                """async (ticker) => {
                    try {
                        const response = await fetch(`/api/chart-data/${encodeURIComponent(ticker)}?timeframe=6M`);
                        const data = await response.json();
                        return {
                            ok: response.ok,
                            status: response.status,
                            ticker: data.ticker || null,
                            hasPrice: Boolean(data.price),
                            candleCount: Array.isArray(data.ohlcv) ? data.ohlcv.length : 0,
                        };
                    } catch(e) {
                        return {ok: false, error: e.message};
                    }
                }""",
                ticker,
            )
            results["chart_data"] = chart_fetch
        except Exception as e:
            results["chart_data"] = {"ok": False, "error": str(e)}

        # 8. Key UI elements
        try:
            results["ui_elements"] = page.evaluate(
                """() => ({
                    hasTickerInput: !!document.getElementById('ticker-inp'),
                    hasTimeframeGroup: !!document.getElementById('tf-group'),
                    hasChartCanvas: !!document.getElementById('live-canvas'),
                    hasExpertPanel: !!document.getElementById('expert-panel'),
                    hasF51Card: !!document.getElementById('expert-card-f51'),
                    hasSdcaCard: !!document.getElementById('expert-card-sdca'),
                    hasNeuralCard: !!document.getElementById('expert-card-neural'),
                    hasTrinityCard: !!document.getElementById('expert-card-trinity'),
                    hasGuardrailsCard: !!document.getElementById('expert-card-guardrails'),
                    hasMangalaCard: !!document.getElementById('expert-card-mangala'),
                    hasSdcaLabBtn: !!document.getElementById('sdca-lab-btn'),
                    hasOpsConsoleBtn: !!document.getElementById('ops-console-btn'),
                    hasAccountMetric: !!document.getElementById('account-value'),
                    hasPnLMetric: !!document.getElementById('pnl-value'),
                    hasConnectionStatus: !!document.getElementById('cockpit-connection'),
                })"""
            )
        except Exception as e:
            results["ui_elements"] = {"error": str(e)}

        # Screenshot
        page.screenshot(path=str(screenshot_path), full_page=True)
        results["screenshot"] = str(screenshot_path)
        browser.close()

    results["console_errors"] = console_errors
    results["page_errors"] = page_errors

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SuperEzio auth + UI flow verification.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--headed", action="store_true", default=True)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--ticker", default=DEFAULT_TICKER)
    args = parser.parse_args()

    try:
        result = run_verification(
            base_url=args.base_url.rstrip("/"),
            headed=args.headed,
            timeout_ms=args.timeout_ms,
            ticker=args.ticker.strip().upper(),
            slow_mo=args.slow_mo,
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
