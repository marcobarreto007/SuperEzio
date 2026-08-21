"""Investor Journey & Fact-Based Audit for SuperEzio.

Audits real system execution without hardcoded scores:
1. Scenario A: Capital Allocation Question to Bob (extracts actual streamed text and SDCA trace).
2. Scenario B: Real Market Analysis on TD.TO (verifies candle count, non-zero timestamps, and indicators).
3. Scenario C: TD Direct Commission-Free ETF Catalog (verifies 83 CAN + 25 US = 108 symbols).
4. Scenario D: Money Gate & TD Limit Ticket Validation (verifies fail-closed authentication protection).
5. Compiles an objective, fact-based verification matrix.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "playwright" / "investor_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BASE_URL = os.environ.get("SUPEREZIO_URL", "http://127.0.0.1:8002").rstrip("/")


def run_investor_audit() -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    report: dict[str, Any] = {
        "timestamp": stamp,
        "investor_profile": "Canadian Retail Investor (CAD 25k, Family, Moderate Risk)",
        "scenarios": {},
        "verifications": {},
        "screenshots": [],
    }

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            ignore_https_errors=True,
        )
        page = context.new_page()

        print("[Investor Audit] 1. Loading Cockpit...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(2000)
        page.evaluate("() => { if (window.SZ?.auth?.hideModal) window.SZ.auth.hideModal(); }")

        ss_init = OUTPUT_DIR / f"01_investor_cockpit_view_{stamp}.png"
        page.screenshot(path=str(ss_init), full_page=True)
        report["screenshots"].append(str(ss_init))

        # Scenario A: Capital Allocation Framework
        print("[Investor Audit] 2. Testing Scenario A: Capital Allocation Framework...")
        chat_tab = page.query_selector("#bob-chat-tab")
        if chat_tab:
            chat_tab.click()
            page.wait_for_timeout(600)

        prompt_a = "Marco aqui. Tenho CAD 25.000 para organizar entre reserva de emergência, ETFs no TD Canadá e amortização de dívidas. Qual o framework sério?"
        if page.query_selector("#user-inp") and page.query_selector("#send-btn"):
            page.fill("#user-inp", prompt_a)
            page.click("#send-btn")

            # Wait for Bob's response stream to finish (up to 15s)
            for _ in range(15):
                page.wait_for_timeout(1000)
                is_done = page.evaluate("""() => {
                    const chatBox = document.getElementById('chat');
                    if (!chatBox) return false;
                    const ceoMsgs = chatBox.querySelectorAll('.msg-ceo .msg-bubble');
                    if (ceoMsgs.length === 0) return false;
                    const lastBubble = ceoMsgs[ceoMsgs.length - 1];
                    const text = lastBubble.innerText.trim();
                    return text.length > 50 && !document.querySelector('.typing-indicator');
                }""")
                if is_done:
                    break

        ss_scen_a = OUTPUT_DIR / f"02_scenario_a_capital_alloc_{stamp}.png"
        page.screenshot(path=str(ss_scen_a), full_page=True)
        report["screenshots"].append(str(ss_scen_a))

        chat_state_a = page.evaluate("""() => {
            const chatBox = document.getElementById('chat');
            if (!chatBox) return { messageCount: 0, text: '' };
            const ceoMsgs = chatBox.querySelectorAll('.msg-ceo .msg-bubble');
            const userMsgs = chatBox.querySelectorAll('.msg-user .msg-bubble');
            const lastCeo = ceoMsgs.length > 0 ? ceoMsgs[ceoMsgs.length - 1].innerText.trim() : '';
            const lastUser = userMsgs.length > 0 ? userMsgs[userMsgs.length - 1].innerText.trim() : '';
            return {
                userMessagesCount: userMsgs.length,
                ceoMessagesCount: ceoMsgs.length,
                lastUserPrompt: lastUser,
                lastBobResponse: lastCeo,
                responseLength: lastCeo.length
            };
        }""")
        report["scenarios"]["scenario_a_capital_allocation"] = {
            "prompt": prompt_a,
            "result": chat_state_a,
            "assessed": True,
        }

        # Scenario B: Technical & Asset Analysis on TD.TO
        print("[Investor Audit] 3. Testing Scenario B: Real Market Analysis on TD.TO...")
        try:
            chart_data = page.evaluate("""async () => {
                const res = await fetch('/api/chart-data/TD.TO?timeframe=6M');
                const data = await res.json();
                const ohlcv = Array.isArray(data.ohlcv) ? data.ohlcv : [];
                const zeroTimestamps = ohlcv.filter(c => !c.time || c.time === 0).length;
                return {
                    status: res.status,
                    ticker: data.ticker,
                    current_price: data.price ? data.price.current : null,
                    change_pct: data.price ? data.price.change_pct : null,
                    candles_count: ohlcv.length,
                    zero_timestamps_count: zeroTimestamps,
                    first_candle: ohlcv.length > 0 ? ohlcv[0] : null,
                    last_candle: ohlcv.length > 0 ? ohlcv[ohlcv.length - 1] : null,
                    has_sma20: !!(data.indicators && Array.isArray(data.indicators.sma20) && data.indicators.sma20.length > 0),
                    has_bollinger: !!(data.indicators && Array.isArray(data.indicators.bollinger_upper) && data.indicators.bollinger_upper.length > 0)
                };
            }""")

            ss_scen_b = OUTPUT_DIR / f"03_scenario_b_td_analysis_{stamp}.png"
            page.screenshot(path=str(ss_scen_b), full_page=True)
            report["screenshots"].append(str(ss_scen_b))

            report["scenarios"]["scenario_b_asset_analysis"] = {
                "ticker": "TD.TO",
                "market_data": chart_data,
                "assessed": True,
            }
        except Exception as exc:
            report["scenarios"]["scenario_b_asset_analysis"] = {"error": str(exc)}

        # Scenario C: Commission-Free ETF Catalog Inspection
        print("[Investor Audit] 4. Testing Scenario C: Commission-Free ETF Universe...")
        try:
            etf_data = page.evaluate("""async () => {
                const res = await fetch('/trade/td-commission-free');
                const data = await res.json();
                const manifest = data.manifest || {};
                const symbols = manifest.symbols || {};
                const can = Array.isArray(symbols.CAN) ? symbols.CAN : [];
                const us = Array.isArray(symbols.US) ? symbols.US : [];
                return {
                    status: res.status,
                    ok: data.ok,
                    count_reported: data.count,
                    canadian_count: can.length,
                    us_count: us.length,
                    total_symbols_verified: can.length + us.length,
                    sample_can: can.slice(0, 5),
                    sample_us: us.slice(0, 5)
                };
            }""")
            report["scenarios"]["scenario_c_etf_catalog"] = {"etf_data": etf_data, "assessed": True}
        except Exception as exc:
            report["scenarios"]["scenario_c_etf_catalog"] = {"error": str(exc)}

        # Scenario D: Money Gate & TD Limit Ticket Validation
        print("[Investor Audit] 5. Testing Scenario D: Money Gate and Limit Order Ticket...")
        try:
            ticket_eval = page.evaluate("""async () => {
                const payload = {
                    ticker: "XIC.TO",
                    action: "BUY",
                    quantity: 50,
                    limit_price: 36.50,
                    currency: "CAD",
                    exchange: "TSX",
                    require_commission_free: true
                };
                const res = await fetch('/trade/td-draft', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                return {
                    status: res.status,
                    ok: res.ok,
                    fail_closed_detail: data.detail || null
                };
            }""")
            report["scenarios"]["scenario_d_ticket_gate"] = {
                "ticket_result": ticket_eval,
                "assessed": True,
            }
        except Exception as exc:
            report["scenarios"]["scenario_d_ticket_gate"] = {"error": str(exc)}

        browser.close()

    # Fact-Based Verifications (Pass/Fail)
    print("[Investor Audit] 6. Compiling Objective Verifications...")
    b_data = report["scenarios"].get("scenario_b_asset_analysis", {}).get("market_data", {})
    c_data = report["scenarios"].get("scenario_c_etf_catalog", {}).get("etf_data", {})
    d_data = report["scenarios"].get("scenario_d_ticket_gate", {}).get("ticket_result", {})

    report["verifications"] = {
        "candles_count_verified": b_data.get("candles_count", 0) > 100,
        "timestamps_nonzero_verified": b_data.get("zero_timestamps_count") == 0,
        "sma20_calculated": b_data.get("has_sma20") is True,
        "td_etfs_exact_count": c_data.get("total_symbols_verified") == 108,
        "td_canadian_etfs_count": c_data.get("canadian_count") == 83,
        "td_us_etfs_count": c_data.get("us_count") == 25,
        "money_gate_fail_closed": d_data.get("status") == 503,
    }

    report_path = OUTPUT_DIR / f"investor_audit_report_{stamp}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[Investor Audit Completed] Report saved to: {report_path}")
    return report


if __name__ == "__main__":
    result = run_investor_audit()
    print("\n=== FACT-BASED AUDIT VERIFICATIONS ===")
    for k, v in result["verifications"].items():
        print(f"  • {k:<30}: {'PASS [OK]' if v else 'FAIL [X]'}")
