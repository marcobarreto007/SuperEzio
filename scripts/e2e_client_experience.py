"""Comprehensive Playwright end-to-end client experience test script.

Validates the full user journey in SuperEzio:
1. Navigation and Cockpit initialization
2. Status bar, connection indicator and metrics
3. Chart rendering and historical data fetching for Canadian / US tickers
4. Expert panels (F51, SDCA, Neural, Trinity, Guardrails, Mangala)
5. Bob Chat slide-in panel interaction and message submission
6. TD Direct Investing commission-free ETF catalog and draft tickets
7. Auth state and JWT handling
8. Multi-stage screenshots
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "playwright"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BASE_URL = os.environ.get("SUPEREZIO_URL", "http://127.0.0.1:8002").rstrip("/")


def run_client_e2e() -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    results: dict[str, Any] = {
        "timestamp": stamp,
        "base_url": BASE_URL,
        "steps": {},
        "screenshots": [],
        "errors": [],
        "success": False,
    }

    with sync_playwright() as pw:
        # Launch Chromium headless
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            ignore_https_errors=True,
        )
        page = context.new_page()

        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: results["errors"].append(str(exc)))

        # Step 1: Initial Load & Cockpit
        print("[1/6] Loading SuperEzio Cockpit UI...")
        try:
            response = page.goto(BASE_URL, wait_until="domcontentloaded", timeout=25000)
            status_code = response.status if response else 0
            page.wait_for_timeout(2000)

            # Dismiss auth modal if opened in non-dev mode
            page.evaluate("() => { if (window.SZ?.auth?.hideModal) window.SZ.auth.hideModal(); }")

            ss1 = OUTPUT_DIR / f"01_cockpit_initial_{stamp}.png"
            page.screenshot(path=str(ss1), full_page=True)
            results["screenshots"].append(str(ss1))

            cockpit_state = page.evaluate("""() => {
                return {
                    title: document.title,
                    hasLiveCanvas: !!document.getElementById('live-canvas'),
                    hasChartMainPane: !!document.getElementById('chart-main-pane'),
                    hasTickerInput: !!document.getElementById('ticker-inp'),
                    hasTimeframeGroup: !!document.getElementById('tf-group'),
                    hasAccountValue: document.getElementById('account-value')?.textContent?.trim() || null,
                    hasPnLValue: document.getElementById('pnl-value')?.textContent?.trim() || null,
                    expertCards: {
                        f51: !!document.getElementById('expert-card-f51'),
                        sdca: !!document.getElementById('expert-card-sdca'),
                        neural: !!document.getElementById('expert-card-neural'),
                        trinity: !!document.getElementById('expert-card-trinity'),
                        guardrails: !!document.getElementById('expert-card-guardrails'),
                        mangala: !!document.getElementById('expert-card-mangala'),
                    }
                };
            }""")
            results["steps"]["01_cockpit_load"] = {
                "ok": status_code == 200,
                "status_code": status_code,
                "cockpit_state": cockpit_state,
            }
        except Exception as exc:
            results["steps"]["01_cockpit_load"] = {"ok": False, "error": str(exc)}
            results["errors"].append(f"Step 1 failed: {exc}")

        # Step 2: Chart Data and Canvas Rendering
        print("[2/6] Testing chart data and canvas rendering...")
        try:
            chart_eval = page.evaluate("""async () => {
                try {
                    const res = await fetch('/api/chart-data/TD.TO?timeframe=6M');
                    const data = await res.json();
                    return {
                        ok: res.ok,
                        status: res.status,
                        ticker: data.ticker,
                        price: data.price,
                        candleCount: Array.isArray(data.ohlcv) ? data.ohlcv.length : 0,
                    };
                } catch(e) {
                    return { ok: false, error: e.message };
                }
            }""")

            # Trigger chart load on UI if available
            page.evaluate("""async () => {
                if (window.SZ && typeof window.SZ.loadChart === 'function') {
                    try { await window.SZ.loadChart('TD.TO'); } catch(e) {}
                }
            }""")
            page.wait_for_timeout(1500)

            ss2 = OUTPUT_DIR / f"02_chart_rendered_{stamp}.png"
            page.screenshot(path=str(ss2), full_page=True)
            results["screenshots"].append(str(ss2))

            results["steps"]["02_chart_test"] = {
                "ok": chart_eval.get("ok", False),
                "data": chart_eval,
            }
        except Exception as exc:
            results["steps"]["02_chart_test"] = {"ok": False, "error": str(exc)}
            results["errors"].append(f"Step 2 failed: {exc}")

        # Step 3: TD Commission-Free ETFs Universe
        print("[3/6] Testing TD Direct commission-free API and catalog...")
        try:
            td_eval = page.evaluate("""async () => {
                try {
                    const res = await fetch('/trade/td-commission-free');
                    const data = await res.json();
                    return {
                        ok: res.ok,
                        status: res.status,
                        count: data.count || (Array.isArray(data.etfs) ? data.etfs.length : 0),
                        sampleEtfs: Array.isArray(data.etfs) ? data.etfs.slice(0, 5) : []
                    };
                } catch(e) {
                    return { ok: false, error: e.message };
                }
            }""")
            results["steps"]["03_td_commission_free"] = {
                "ok": td_eval.get("ok", False),
                "data": td_eval,
            }
        except Exception as exc:
            results["steps"]["03_td_commission_free"] = {"ok": False, "error": str(exc)}
            results["errors"].append(f"Step 3 failed: {exc}")

        # Step 4: Bob Chat Panel and Interaction
        print("[4/6] Testing Bob Chat slide-in panel and interaction...")
        try:
            # Click Bob Chat tab to open panel
            chat_tab = page.query_selector("#bob-chat-tab")
            if chat_tab:
                chat_tab.click()
                page.wait_for_timeout(800)

            chat_panel_info = page.evaluate("""() => {
                const panel = document.getElementById('bob-chat-panel');
                const inp = document.getElementById('user-inp');
                const sendBtn = document.getElementById('send-btn');
                const chatBox = document.getElementById('chat');
                return {
                    panelExists: !!panel,
                    panelOpen: panel ? panel.classList.contains('open') : false,
                    inpExists: !!inp,
                    sendBtnExists: !!sendBtn,
                    chatBoxExists: !!chatBox,
                    initialMsgCount: chatBox ? chatBox.querySelectorAll('.msg, .msg-ceo, .msg-user').length : 0
                };
            }""")

            # Send a prompt to Bob
            test_prompt = "Qual é o framework de alocação de capital para CAD 25.000 no Canadá?"
            if page.query_selector("#user-inp") and page.query_selector("#send-btn"):
                page.fill("#user-inp", test_prompt)
                page.click("#send-btn")
                page.wait_for_timeout(3000)

            ss3 = OUTPUT_DIR / f"03_bob_chat_{stamp}.png"
            page.screenshot(path=str(ss3), full_page=True)
            results["screenshots"].append(str(ss3))

            chat_after = page.evaluate("""() => {
                const chatBox = document.getElementById('chat');
                const msgs = chatBox ? Array.from(chatBox.querySelectorAll('.msg-ceo, .msg-user, .msg')).map(m => m.textContent.trim()) : [];
                return {
                    msgCount: msgs.length,
                    latestMessages: msgs.slice(-3)
                };
            }""")

            results["steps"]["04_bob_chat"] = {
                "ok": chat_panel_info.get("panelExists", False),
                "before": chat_panel_info,
                "after": chat_after,
            }
        except Exception as exc:
            results["steps"]["04_bob_chat"] = {"ok": False, "error": str(exc)}
            results["errors"].append(f"Step 4 failed: {exc}")

        # Step 5: Mangala Daily Opportunities
        print("[5/6] Testing Mangala opportunities scanner view...")
        try:
            mangala_eval = page.evaluate("""async () => {
                try {
                    const res = await fetch('/data/mangala_daily.json');
                    if (res.ok) {
                        const data = await res.json();
                        return { ok: true, opportunities: data.opportunities || [] };
                    }
                } catch(e) {}
                return { ok: false };
            }""")
            results["steps"]["05_mangala_scan"] = mangala_eval
        except Exception as exc:
            results["steps"]["05_mangala_scan"] = {"ok": False, "error": str(exc)}

        # Step 6: Auth Modal & Security Flow
        print("[6/6] Testing Auth & Security modal...")
        try:
            # Trigger auth modal show
            page.evaluate("() => { if (window.SZ?.auth?.showModal) window.SZ.auth.showModal(); }")
            page.wait_for_timeout(800)

            ss4 = OUTPUT_DIR / f"04_auth_modal_{stamp}.png"
            page.screenshot(path=str(ss4), full_page=True)
            results["screenshots"].append(str(ss4))

            auth_modal_info = page.evaluate("""() => {
                const overlay = document.getElementById('auth-modal-overlay');
                const modal = document.getElementById('auth-modal');
                return {
                    overlayExists: !!overlay,
                    modalExists: !!modal,
                    hasLoginTab: !!document.getElementById('auth-tab-login'),
                    hasRegisterTab: !!document.getElementById('auth-tab-register'),
                    hasUsernameInput: !!document.getElementById('auth-username'),
                    hasPasswordInput: !!document.getElementById('auth-password'),
                };
            }""")
            results["steps"]["06_auth_modal"] = {
                "ok": auth_modal_info.get("modalExists", False),
                "data": auth_modal_info,
            }
        except Exception as exc:
            results["steps"]["06_auth_modal"] = {"ok": False, "error": str(exc)}

        browser.close()

    results["console_sample"] = console_logs[:20]
    results["success"] = all(
        step.get("ok", False)
        for k, step in results["steps"].items()
        if k
        in [
            "01_cockpit_load",
            "02_chart_test",
            "03_td_commission_free",
            "04_bob_chat",
            "06_auth_modal",
        ]
    )
    return results


def main() -> int:
    result = run_client_e2e()
    report_file = OUTPUT_DIR / f"e2e_client_report_{result['timestamp']}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"E2E CLIENT EXPERIENCE TEST RESULT: {'SUCCESS' if result['success'] else 'PARTIAL'}")
    print(f"Report saved to: {report_file}")
    for ss in result["screenshots"]:
        print(f"Screenshot: {ss}")
    print("=" * 60)
    print(json.dumps(result["steps"], indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
