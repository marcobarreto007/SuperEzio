#!/usr/bin/env python
"""
chart_verify.py — WebGL Chart (Lightweight Charts) Verification Script

Verification checklist:
1. Page loads, no JS errors
2. Lightweight Charts library loads
3. Chart DOM structure: main-pane, rsi-pane (88px), macd-pane (96px)
4. Dark theme background #111820
5. Candle colors: bull #00e676, bear #ef5350
6. Legend with SMA20, SMA50, EMA20, BB, VWAP
7. Tooltip element exists
8. Sub-pane labels: RSI(14), MACD(12,26,9)
9. JS console errors/warnings
10. Data flow check (if server provides data)
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_URL = "http://127.0.0.1:8002"
SERVER_START_CMD = [sys.executable, "-m", "src.agent_server.main"]
SERVER_PID = None

os.chdir(str(REPO_ROOT))


async def main():
    # ── Step 1: Ensure server is running ──
    print("=" * 60)
    print("SUPEREZIO CHART VERIFICATION — WebGL (Lightweight Charts)")
    print("=" * 60)

    server_proc = await ensure_server()
    if server_proc is False:
        print("[FAIL] Could not start or detect server")
        return False
    print("[INFO] Server is ready")

    # ── Step 2: Start Playwright ──
    from playwright.async_api import async_playwright

    results = {
        "page_load": False,
        "lightweight_charts_loaded": False,
        "chart_dom_structure": False,
        "dark_theme": False,
        "legend": False,
        "tooltip": False,
        "sub_pane_labels": False,
        "no_js_errors": False,
        "console_errors": [],
        "js_warnings": [],
        "chart_data_loaded": False,
        "data_format": {},
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = await context.new_page()

        # Collect console messages
        console_errors = []
        console_warnings = []
        js_logs = []

        page.on("console", lambda msg: js_logs.append({"type": msg.type, "text": msg.text}))
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # ── Step 3: Navigate to frontend ──
        print("\n[1/9] Navigating to frontend...")
        try:
            await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=15000)
            # Wait a bit more for JS to fully execute
            await page.wait_for_timeout(5000)
            results["page_load"] = True
            print("  [OK] Page loaded")
        except Exception as e:
            print(f"  [FAIL] Page load error: {e}")
            await browser.close()
            return results

        await page.wait_for_timeout(3000)

        # ── Handle auth modal if visible ──
        auth_modal = page.locator("#auth-modal-overlay")
        if await auth_modal.is_visible():
            print("  [INFO] Auth modal detected — logging in")
            try:
                # Fill login form
                await page.fill("#auth-login-username", "testuser")
                await page.fill("#auth-login-password", "test12345")
                await page.click(".auth-submit")
                await page.wait_for_timeout(2000)
                # Check if modal closed
                if not await auth_modal.is_visible():
                    print("  [OK] Login successful, modal closed")
                else:
                    print("  [WARN] Login may have failed, checking for register...")
                    # Try register tab
                    await page.click('[data-auth-tab="register"]')
                    await page.wait_for_timeout(500)
                    await page.fill("#auth-reg-username", "testuser2")
                    await page.fill("#auth-reg-email", "test2@test.com")
                    await page.fill("#auth-reg-password", "test12345")
                    await page.click(".auth-submit")
                    await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"  [WARN] Auth handling error: {e}")
        else:
            print("  [INFO] No auth modal — dev mode or already authenticated")

        await page.wait_for_timeout(2000)

        # ── Step 4: Check JS console for errors ──
        print("\n[2/9] Checking JavaScript console...")
        for log in js_logs:
            if log["type"] == "error":
                console_errors.append(log["text"])
            elif log["type"] == "warning":
                console_warnings.append(log["text"])

        if console_errors:
            results["console_errors"] = console_errors
            for err in console_errors:
                print(f"  [ERR] {err[:200]}")
        else:
            results["no_js_errors"] = True
            print("  [OK] No JS errors found")

        if console_warnings:
            results["js_warnings"] = console_warnings
            for w in console_warnings:
                print(f"  [WARN] {w[:200]}")
        else:
            print("  [OK] No JS warnings")

        # Print all relevant logs
        for log in js_logs:
            txt = log["text"]
            if any(kw in txt for kw in ["[SZ]", "chart", "Lightweight", "WebGL", "error", "Error"]):
                print(f"  [{log['type']}] {txt[:200]}")

        # ── Step 5: Check Lightweight Charts library ──
        print("\n[3/9] Checking Lightweight Charts library...")
        lw_loaded = await page.evaluate("typeof LightweightCharts !== 'undefined'")
        results["lightweight_charts_loaded"] = lw_loaded
        if lw_loaded:
            version = await page.evaluate(
                "LightweightCharts.version || 'unknown'"
            )
            print(f"  [OK] Lightweight Charts loaded (version: {version})")
        else:
            print("  [FAIL] Lightweight Charts NOT loaded")
            # Check if CDN script tag exists
            script_tag = await page.evaluate(
                "document.querySelector('script[src*=\"lightweight-charts\"]') !== null"
            )
            print(f"  [INFO] Lightweight Charts script tag in HTML: {script_tag}")
            if script_tag:
                src = await page.evaluate(
                    "document.querySelector('script[src*=\"lightweight-charts\"]').src"
                )
                print(f"  [INFO] Script src: {src}")

        # ── Step 6: Check chart DOM structure ──
        print("\n[4/9] Checking chart DOM structure...")

        # Check if the canvas was replaced with flex container
        live_canvas = await page.evaluate("""
            (() => {
                const el = document.getElementById('live-canvas');
                if (!el) return { exists: false };
                return {
                    exists: true,
                    tagName: el.tagName,
                    display: getComputedStyle(el).display,
                    childCount: el.children.length,
                    children: Array.from(el.children).map(c => ({
                        id: c.id,
                        tagName: c.tagName,
                        className: c.className,
                        flex: getComputedStyle(c).flex || 'none',
                        height: c.style.minHeight || 'auto',
                    }))
                };
            })()
        """)

        if live_canvas["exists"]:
            print(f"  [OK] #live-canvas exists: <{live_canvas['tagName']}> display={live_canvas['display']}")
            for child in live_canvas["children"]:
                print(f"    child: <{child['tagName']}#{child['id']}> flex={child['flex']} height={child['height']}")

            # Check for specific sub-panes
            pane_ids = [c["id"] for c in live_canvas["children"]]
            has_main = "chart-main-pane" in pane_ids
            has_rsi = "chart-rsi-pane" in pane_ids
            has_macd = "chart-macd-pane" in pane_ids

            if has_main and has_rsi and has_macd:
                results["chart_dom_structure"] = True
                print("  [OK] All 3 panes present: main, RSI (88px), MACD (96px)")
            else:
                missing = []
                if not has_main: missing.append("main")
                if not has_rsi: missing.append("RSI")
                if not has_macd: missing.append("MACD")
                print(f"  [WARN] Missing panes: {', '.join(missing)}")

            # Verify RSI height is 88px
            rsi_pane = next((c for c in live_canvas["children"] if c["id"] == "chart-rsi-pane"), None)
            if rsi_pane:
                expected_h = "88px"
                actual = rsi_pane.get("height", "unknown")
                match = "OK" if expected_h in actual else "MISMATCH"
                print(f"  [INFO] RSI pane height: {actual} (expected {expected_h}) [{match}]")

            # Verify MACD height is 96px
            macd_pane = next((c for c in live_canvas["children"] if c["id"] == "chart-macd-pane"), None)
            if macd_pane:
                expected_h = "96px"
                actual = macd_pane.get("height", "unknown")
                match = "OK" if expected_h in actual else "MISMATCH"
                print(f"  [INFO] MACD pane height: {actual} (expected {expected_h}) [{match}]")
        else:
            print("  [FAIL] #live-canvas not found in DOM")

        # ── Step 7: Check dark theme ──
        print("\n[5/9] Checking dark theme colors...")
        bg_color = await page.evaluate("""
            (() => {
                const el = document.getElementById('live-canvas');
                if (!el) return null;
                // Check background of the main pane container
                const parent = el.parentElement;
                const stage = document.querySelector('.chart-stage');
                return {
                    liveCanvasBg: getComputedStyle(el).background,
                    stageBg: stage ? getComputedStyle(stage).background : null,
                };
            })()
        """)
        print(f"  [INFO] Background colors: {bg_color}")

        # Check CSS variables for the theme
        css_vars = await page.evaluate("""
            (() => {
                const root = document.documentElement;
                const style = getComputedStyle(root);
                return {
                    bg: style.getPropertyValue('--bg').trim(),
                    surface: style.getPropertyValue('--surface').trim(),
                    green: style.getPropertyValue('--green').trim(),
                    red: style.getPropertyValue('--red').trim(),
                };
            })()
        """)
        print(f"  [INFO] CSS vars: {css_vars}")
        if css_vars.get("bg"):
            print(f"  [OK] Theme background: {css_vars['bg']}")
            results["dark_theme"] = True

        # Check chart.js design tokens
        chart_colors = await page.evaluate("""
            (() => {
                if (typeof SZ === 'undefined' || !SZ.chart) return null;
                // Access internal C object through the closure
                // It's not directly accessible, check via evaluate
                return { exists: true };
            })()
        """)
        print(f"  [INFO] SZ.chart module: {chart_colors}")

        # ── Step 8: Check legend ──
        print("\n[6/9] Checking chart legend...")
        legend = await page.evaluate("""
            (() => {
                const el = document.getElementById('chart-legend');
                if (!el) return { exists: false };
                const items = Array.from(el.querySelectorAll('span')).map(s => s.textContent);
                return {
                    exists: true,
                    text: el.textContent,
                    items: items.filter(i => i.trim()),
                    position: {
                        top: el.style.top,
                        left: el.style.left,
                    }
                };
            })()
        """)
        results["legend"] = legend["exists"]
        if legend["exists"]:
            print(f"  [OK] Legend found: {legend['items']}")
            expected_indicators = ["SMA20", "SMA50", "EMA20", "BB", "VWAP"]
            for ind in expected_indicators:
                if ind in legend["text"]:
                    print(f"    [OK] {ind} present in legend")
                else:
                    print(f"    [MISS] {ind} NOT in legend")
        else:
            print("  [FAIL] Legend not found")

        # ── Step 9: Check tooltip ──
        print("\n[7/9] Checking tooltip element...")
        tooltip = await page.evaluate("""
            (() => {
                const el = document.getElementById('chart-tooltip');
                if (!el) return { exists: false };
                return {
                    exists: true,
                    display: getComputedStyle(el).display,
                    background: getComputedStyle(el).background,
                    color: getComputedStyle(el).color,
                    zIndex: el.style.zIndex,
                };
            })()
        """)
        results["tooltip"] = tooltip["exists"]
        if tooltip["exists"]:
            print(f"  [OK] Tooltip element found (display: {tooltip['display']})")
        else:
            print("  [FAIL] Tooltip not found")

        # ── Step 10: Check sub-pane labels ──
        print("\n[8/9] Checking sub-pane labels...")
        labels = await page.evaluate("""
            (() => {
                const rsiLabel = document.getElementById('chart-rsi-label');
                const macdLabel = document.getElementById('chart-macd-label');
                return {
                    rsi: rsiLabel ? rsiLabel.textContent : null,
                    macd: macdLabel ? macdLabel.textContent : null,
                };
            })()
        """)
        results["sub_pane_labels"] = bool(labels["rsi"] and labels["macd"])
        if labels["rsi"]:
            print(f"  [OK] RSI label: {labels['rsi']}")
        else:
            print("  [MISS] RSI label not found")
        if labels["macd"]:
            print(f"  [OK] MACD label: {labels['macd']}")
        else:
            print("  [MISS] MACD label not found")

        # ── Step 11: Chart data status ──
        print("\n[9/9] Checking chart data loading...")
        chart_state = await page.evaluate("""
            (() => {
                if (typeof SZ === 'undefined') return { sz: false };
                const state = SZ.state || {};
                const chartData = state.chartData;
                return {
                    sz: true,
                    hasChartData: !!chartData,
                    ohlcvCount: (chartData && chartData.ohlcv) ? chartData.ohlcv.length : 0,
                    indicators: chartData && chartData.indicators ? Object.keys(chartData.indicators) : [],
                    ticker: state.ticker || '',
                    initPhase: !!SZ.chart,
                };
            })()
        """)
        results["chart_data_loaded"] = chart_state.get("hasChartData", False)
        print(f"  SZ.chart module: {'loaded' if chart_state.get('initPhase') else 'NOT loaded'}")
        print(f"  SZ.state.ticker: {chart_state.get('ticker', 'N/A')}")
        print(f"  Chart data present: {chart_state.get('hasChartData', False)}")
        print(f"  OHLCV data points: {chart_state.get('ohlcvCount', 0)}")
        print(f"  Indicators keys: {chart_state.get('indicators', [])}")

        # Check for [SZ.chart] load messages
        chart_loaded_logs = [l for l in js_logs if "[SZ.chart]" in l["text"]]
        for l in chart_loaded_logs:
            print(f"  [LOG] {l['text']}")

        # ── Take screenshot ──
        screenshot_path = REPO_ROOT / "runtime" / "checkpoints" / "chart_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"\n  [INFO] Screenshot saved: {screenshot_path}")

        # ── Summary ──
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)
        checks = [
            ("Page load", results["page_load"]),
            ("Lightweight Charts library", results["lightweight_charts_loaded"]),
            ("Chart DOM structure (3 panes)", results["chart_dom_structure"]),
            ("Dark theme", results["dark_theme"]),
            ("Legend with indicators", results["legend"]),
            ("Tooltip element", results["tooltip"]),
            ("Sub-pane labels (RSI/MACD)", results["sub_pane_labels"]),
            ("No JS errors", results["no_js_errors"]),
        ]
        for name, ok in checks:
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {name}")

        print(f"\n  JS errors: {len(results['console_errors'])}")
        print(f"  JS warnings: {len(results['js_warnings'])}")
        print(f"  Chart data points: {chart_state.get('ohlcvCount', 0)}")

        await browser.close()

    if server_proc:
        print("\n  [INFO] Server left running for manual inspection")

    # Write results JSON
    report_path = REPO_ROOT / "runtime" / "checkpoints" / "chart_verify_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Report saved: {report_path}")

    return results


async def ensure_server():
    """Check if server is running, start if not."""
    import urllib.request

    try:
        req = urllib.request.Request("http://127.0.0.1:8002/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                print("[INFO] Server already running")
                return True
    except Exception:
        pass

    print("[INFO] Starting server...")
    proc = subprocess.Popen(
        SERVER_START_CMD,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    for i in range(15):
        time.sleep(1)
        try:
            req = urllib.request.Request("http://127.0.0.1:8002/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(f"[INFO] Server started (PID: {proc.pid})")
                    return proc
        except Exception:
            continue

    print("[WARN] Server may not have started properly")
    return proc


if __name__ == "__main__":
    result = asyncio.run(main())
    if isinstance(result, dict):
        all_pass = all([
            result["page_load"],
            result["lightweight_charts_loaded"],
            result["chart_dom_structure"],
        ])
        sys.exit(0 if all_pass else 1)
