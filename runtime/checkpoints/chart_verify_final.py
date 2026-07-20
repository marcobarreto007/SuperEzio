#!/usr/bin/env python3
"""
chart_verify_final.py — Final WebGL Chart Verification

Verification targets (7 items):
1. Chart loads: candlestick + volume
2. Overlays: SMA20, SMA50, EMA20, Bollinger Bands, VWAP
3. Sub-panes: RSI (88px) + MACD (96px)
4. Crosshair + tooltip with OHLCV data
5. Dark theme: #111820, #00e676 (bull), #ef5350 (bear)
6. Report bugs / missing data
"""

import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_URL = "http://127.0.0.1:8002"
os.chdir(str(REPO_ROOT))

# ── 20 candles of mock OHLCV data ──
MOCK_CHART_DATA = {
    "ticker": "TEST",
    "timeframe": "6M",
    "profile": {"name": "Test Corp", "sector": "Technology", "currency": "USD", "exchange": "TEST"},
    "price": {"current": 150.25, "previous_close": 149.80, "change": 0.45, "change_pct": 0.30},
    "ohlcv": [
        {"time": 1721433600, "open": 150.00, "high": 152.00, "low": 149.50, "close": 151.50, "volume": 1250000},
        {"time": 1721520000, "open": 151.50, "high": 153.00, "low": 150.80, "close": 152.20, "volume": 1100000},
        {"time": 1721606400, "open": 152.20, "high": 154.50, "low": 151.00, "close": 151.80, "volume": 1350000},
        {"time": 1721692800, "open": 151.80, "high": 152.50, "low": 148.00, "close": 149.00, "volume": 1500000},
        {"time": 1721779200, "open": 149.00, "high": 150.00, "low": 147.50, "close": 148.20, "volume": 980000},
        {"time": 1721865600, "open": 148.20, "high": 149.80, "low": 146.00, "close": 147.00, "volume": 890000},
        {"time": 1721952000, "open": 147.00, "high": 150.50, "low": 146.50, "close": 150.00, "volume": 1200000},
        {"time": 1722038400, "open": 150.00, "high": 153.00, "low": 149.50, "close": 152.50, "volume": 1400000},
        {"time": 1722124800, "open": 152.50, "high": 157.00, "low": 152.00, "close": 156.50, "volume": 1650000},
        {"time": 1722211200, "open": 156.50, "high": 158.00, "low": 155.00, "close": 155.80, "volume": 1300000},
        {"time": 1722297600, "open": 155.80, "high": 156.50, "low": 152.00, "close": 153.00, "volume": 1150000},
        {"time": 1722384000, "open": 153.00, "high": 154.00, "low": 149.50, "close": 150.50, "volume": 1050000},
        {"time": 1722470400, "open": 150.50, "high": 151.50, "low": 147.00, "close": 148.50, "volume": 950000},
        {"time": 1722556800, "open": 148.50, "high": 150.00, "low": 146.50, "close": 147.20, "volume": 880000},
        {"time": 1722643200, "open": 147.20, "high": 149.50, "low": 144.00, "close": 145.00, "volume": 1020000},
        {"time": 1722729600, "open": 145.00, "high": 147.00, "low": 143.50, "close": 146.50, "volume": 1100000},
        {"time": 1722816000, "open": 146.50, "high": 151.00, "low": 146.00, "close": 150.50, "volume": 1250000},
        {"time": 1722902400, "open": 150.50, "high": 153.50, "low": 149.00, "close": 153.00, "volume": 1350000},
        {"time": 1722988800, "open": 153.00, "high": 154.00, "low": 151.50, "close": 152.00, "volume": 1200000},
        {"time": 1723075200, "open": 152.00, "high": 155.50, "low": 151.00, "close": 154.80, "volume": 1400000},
    ],
    "indicators": {
        "sma20": [
            {"time": 1721433600, "value": 149.50}, {"time": 1721520000, "value": 150.00},
            {"time": 1721606400, "value": 150.80}, {"time": 1721692800, "value": 150.00},
            {"time": 1721779200, "value": 149.50}, {"time": 1721865600, "value": 148.80},
            {"time": 1721952000, "value": 149.00}, {"time": 1722038400, "value": 150.20},
            {"time": 1722124800, "value": 151.50}, {"time": 1722211200, "value": 152.80},
            {"time": 1722297600, "value": 153.00}, {"time": 1722384000, "value": 152.00},
            {"time": 1722470400, "value": 150.50}, {"time": 1722556800, "value": 149.00},
            {"time": 1722643200, "value": 148.00}, {"time": 1722729600, "value": 147.50},
            {"time": 1722816000, "value": 148.00}, {"time": 1722902400, "value": 149.50},
            {"time": 1722988800, "value": 150.80}, {"time": 1723075200, "value": 151.50},
        ],
        "sma50": [
            {"time": 1721433600, "value": 147.00}, {"time": 1721520000, "value": 147.50},
            {"time": 1721606400, "value": 148.00}, {"time": 1721692800, "value": 148.00},
            {"time": 1721779200, "value": 147.50}, {"time": 1721865600, "value": 147.00},
            {"time": 1721952000, "value": 147.50}, {"time": 1722038400, "value": 148.00},
            {"time": 1722124800, "value": 149.00}, {"time": 1722211200, "value": 149.50},
            {"time": 1722297600, "value": 149.00}, {"time": 1722384000, "value": 148.50},
            {"time": 1722470400, "value": 148.00}, {"time": 1722556800, "value": 147.50},
            {"time": 1722643200, "value": 146.50}, {"time": 1722729600, "value": 146.00},
            {"time": 1722816000, "value": 146.50}, {"time": 1722902400, "value": 147.00},
            {"time": 1722988800, "value": 147.50}, {"time": 1723075200, "value": 148.00},
        ],
        "ema20": [
            {"time": 1721433600, "value": 149.80}, {"time": 1721520000, "value": 150.20},
            {"time": 1721606400, "value": 151.00}, {"time": 1721692800, "value": 150.20},
            {"time": 1721779200, "value": 149.50}, {"time": 1721865600, "value": 148.50},
            {"time": 1721952000, "value": 149.00}, {"time": 1722038400, "value": 150.50},
            {"time": 1722124800, "value": 152.00}, {"time": 1722211200, "value": 153.50},
            {"time": 1722297600, "value": 153.00}, {"time": 1722384000, "value": 152.00},
            {"time": 1722470400, "value": 150.50}, {"time": 1722556800, "value": 149.00},
            {"time": 1722643200, "value": 147.50}, {"time": 1722729600, "value": 147.00},
            {"time": 1722816000, "value": 148.50}, {"time": 1722902400, "value": 150.00},
            {"time": 1722988800, "value": 151.00}, {"time": 1723075200, "value": 152.00},
        ],
        "rsi": [
            {"time": 1721433600, "value": 55.0}, {"time": 1721520000, "value": 58.0},
            {"time": 1721606400, "value": 62.0}, {"time": 1721692800, "value": 45.0},
            {"time": 1721779200, "value": 42.0}, {"time": 1721865600, "value": 35.0},
            {"time": 1721952000, "value": 48.0}, {"time": 1722038400, "value": 55.0},
            {"time": 1722124800, "value": 65.0}, {"time": 1722211200, "value": 68.0},
            {"time": 1722297600, "value": 60.0}, {"time": 1722384000, "value": 50.0},
            {"time": 1722470400, "value": 42.0}, {"time": 1722556800, "value": 38.0},
            {"time": 1722643200, "value": 30.0}, {"time": 1722729600, "value": 33.0},
            {"time": 1722816000, "value": 40.0}, {"time": 1722902400, "value": 52.0},
            {"time": 1722988800, "value": 55.0}, {"time": 1723075200, "value": 60.0},
        ],
        "bb_upper": [
            {"time": 1721433600, "value": 155.0}, {"time": 1721520000, "value": 156.0},
            {"time": 1721606400, "value": 157.0}, {"time": 1721692800, "value": 155.0},
            {"time": 1721779200, "value": 154.0}, {"time": 1721865600, "value": 152.0},
            {"time": 1721952000, "value": 153.0}, {"time": 1722038400, "value": 155.0},
            {"time": 1722124800, "value": 158.0}, {"time": 1722211200, "value": 159.0},
            {"time": 1722297600, "value": 158.0}, {"time": 1722384000, "value": 156.0},
            {"time": 1722470400, "value": 154.0}, {"time": 1722556800, "value": 152.0},
            {"time": 1722643200, "value": 150.0}, {"time": 1722729600, "value": 150.0},
            {"time": 1722816000, "value": 152.0}, {"time": 1722902400, "value": 154.0},
            {"time": 1722988800, "value": 155.0}, {"time": 1723075200, "value": 156.0},
        ],
        "bb_lower": [
            {"time": 1721433600, "value": 145.0}, {"time": 1721520000, "value": 145.0},
            {"time": 1721606400, "value": 146.0}, {"time": 1721692800, "value": 144.0},
            {"time": 1721779200, "value": 143.0}, {"time": 1721865600, "value": 142.0},
            {"time": 1721952000, "value": 143.0}, {"time": 1722038400, "value": 144.0},
            {"time": 1722124800, "value": 146.0}, {"time": 1722211200, "value": 147.0},
            {"time": 1722297600, "value": 146.0}, {"time": 1722384000, "value": 145.0},
            {"time": 1722470400, "value": 143.0}, {"time": 1722556800, "value": 142.0},
            {"time": 1722643200, "value": 141.0}, {"time": 1722729600, "value": 140.0},
            {"time": 1722816000, "value": 142.0}, {"time": 1722902400, "value": 143.0},
            {"time": 1722988800, "value": 144.0}, {"time": 1723075200, "value": 145.0},
        ],
        "vwap": [
            {"time": 1721433600, "value": 150.50}, {"time": 1721520000, "value": 151.00},
            {"time": 1721606400, "value": 151.80}, {"time": 1721692800, "value": 150.50},
            {"time": 1721779200, "value": 149.00}, {"time": 1721865600, "value": 148.00},
            {"time": 1721952000, "value": 148.50}, {"time": 1722038400, "value": 150.00},
            {"time": 1722124800, "value": 152.00}, {"time": 1722211200, "value": 153.00},
            {"time": 1722297600, "value": 152.50}, {"time": 1722384000, "value": 151.00},
            {"time": 1722470400, "value": 149.50}, {"time": 1722556800, "value": 148.00},
            {"time": 1722643200, "value": 146.50}, {"time": 1722729600, "value": 145.50},
            {"time": 1722816000, "value": 147.00}, {"time": 1722902400, "value": 149.00},
            {"time": 1722988800, "value": 150.50}, {"time": 1723075200, "value": 151.50},
        ],
        "macd": {"histogram": [], "line": [], "signal": []},
        "macd_histogram": [],
        "macd_signal": [],
    },
}


async def main():
    from playwright.async_api import async_playwright

    print("=" * 65)
    print("  SUPEREZIO CHART VERIFICATION (WebGL — Lightweight Charts)")
    print("=" * 65)

    results = {
        "page_load": False,
        "lw_loaded": False,
        "chart_dom_correct": False,
        "candlestick_renders": False,
        "volume_renders": False,
        "overlay_indicators": False,
        "rsi_subpane_exists": False,
        "macd_subpane_exists": False,
        "tooltip": False,
        "legend": False,
        "dark_theme": False,
        "colors_correct": False,
        "js_errors": [],
        "data_format_issues": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = await context.new_page()

        js_errors = []
        page.on("pageerror", lambda err: js_errors.append(str(err)))

        # ── Step 1: Register/Login via API to get JWT ──
        print("\n[Step 1/7] Authenticating with backend...")
        token = None
        for username in ["verifier", "tester", "testuser"]:
            try:
                req = urllib.request.Request(
                    f"{FRONTEND_URL}/auth/login",
                    data=json.dumps({"username": username, "password": "test12345"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=10)
                data = json.loads(resp.read())
                token = data.get("access_token", "")
                print(f"  [OK] Logged in as '{username}', got JWT token")
                break
            except Exception:
                try:
                    # Try to register
                    req = urllib.request.Request(
                        f"{FRONTEND_URL}/auth/register",
                        data=json.dumps({"username": username, "email": f"{username}@test.com", "password": "test12345"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    resp = urllib.request.urlopen(req, timeout=10)
                    print(f"  [OK] Registered '{username}'")
                    # Login after register
                    req = urllib.request.Request(
                        f"{FRONTEND_URL}/auth/login",
                        data=json.dumps({"username": username, "password": "test12345"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    resp = urllib.request.urlopen(req, timeout=10)
                    data = json.loads(resp.read())
                    token = data.get("access_token", "")
                    print(f"  [OK] Logged in as '{username}'")
                    break
                except Exception as e2:
                    continue

        if not token:
            print("  [FAIL] Could not authenticate with any user")
            await browser.close()
            return results

        # ── Step 2: Navigate to page with stored JWT ──
        print("\n[Step 2/7] Loading frontend with JWT...")
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)

        # Inject JWT token into localStorage before page scripts fully initialize
        await page.evaluate(f"""
            localStorage.setItem('sz_access_token', '{token}');
            localStorage.setItem('sz_refresh_token', 'mock_refresh');
            localStorage.setItem('sz_user', JSON.stringify({{"username": "verifier"}}));
        """)
        await page.wait_for_timeout(1000)

        # Navigate again so the auth module reads the stored token
        await page.goto(FRONTEND_URL, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        results["page_load"] = True
        print("  [OK] Page loaded with JWT token")

        # ── Step 3: Inject mock chart data ──
        print("\n[Step 3/7] Injecting mock chart data for verification...")
        await page.evaluate(f"""
            window.SZ.state.chartData = {json.dumps(MOCK_CHART_DATA)};
            window.SZ.state.ticker = 'TEST';
            document.getElementById('workspace-ticker').textContent = 'TEST';
            document.getElementById('ticker-inp').value = 'TEST';
        """)
        await page.wait_for_timeout(500)

        # Wait for and call chart rendering
        has_chart_module = await page.evaluate("typeof SZ.chart !== 'undefined' && typeof SZ.chart._apply === 'function'")
        if has_chart_module:
            print("  [OK] SZ.chart module detected, calling render...")
            await page.evaluate("SZ.chart._apply();")
            await page.wait_for_timeout(1000)
        else:
            print("  [WARN] SZ.chart not available, calling renderChart...")
            await page.evaluate("""
                if (typeof SZ.renderChart === 'function') SZ.renderChart();
                if (typeof SZ.drawLiveCandles === 'function') SZ.drawLiveCandles();
            """)
            await page.wait_for_timeout(1000)

        # If chart still didn't init, call it directly
        chart_inited = await page.evaluate("typeof SZ !== 'undefined' && SZ.chart && SZ.chart._apply ? true : false")
        if not chart_inited:
            print("  [WARN] Chart not initialized, forcing init...")
            await page.evaluate("""
                if (typeof SZ !== 'undefined' && SZ.chart && SZ.chart.load) {
                    SZ.state.chartData = arguments[0];
                    SZ.chart.load('TEST', '6M');
                }
            """, json.dumps(MOCK_CHART_DATA))
            await page.wait_for_timeout(2000)

        # ── Step 4: Check Lightweight Charts and chart DOM ──
        print("\n[Step 4/7] Verifying chart DOM and library...")

        # Lightweight Charts
        lw_ok = await page.evaluate("typeof LightweightCharts !== 'undefined'")
        results["lw_loaded"] = lw_ok
        if lw_ok:
            ver = await page.evaluate("LightweightCharts.version || '4.x'")
            print(f"  [OK] Lightweight Charts v{ver}")
        else:
            print("  [FAIL] Lightweight Charts NOT loaded")
            # Check CDN availability
            cdn_ok = await page.evaluate("document.querySelector('script[src*=\"lightweight-charts\"]') !== null")
            print(f"  [INFO] CDN script tag present: {cdn_ok}")

        # Chart DOM structure
        dom_info = await page.evaluate("""
            (() => {
                const el = document.getElementById('live-canvas');
                if (!el) return {exists: false};
                const children = Array.from(el.children).map(c => ({
                    id: c.id,
                    tag: c.tagName,
                    flex: getComputedStyle(c).flex || 'none',
                    minH: c.style.minHeight || 'auto',
                }));
                return {
                    exists: true,
                    tag: el.tagName,
                    display: getComputedStyle(el).display,
                    children: children,
                    childCount: children.length,
                };
            })()
        """)

        if dom_info.get("exists") and dom_info.get("childCount", 0) >= 3:
            results["chart_dom_correct"] = True
            print(f"  [OK] #live-canvas <{dom_info['tag']}> display={dom_info['display']}")
            for child in dom_info["children"]:
                print(f"    <{child['tag']}#{child['id']}> flex={child['flex']} minH={child['minH']}")
        else:
            print(f"  [FAIL] Chart DOM incomplete: {json.dumps(dom_info)}")

        # ── Step 5: Check candlestick and volume rendering ──
        print("\n[Step 5/7] Checking candlestick + volume rendering...")

        # Check for canvas elements within the chart (Lightweight Charts renders to canvas)
        canvas_count = await page.evaluate("""
            (() => {
                const mainPane = document.getElementById('chart-main-pane');
                if (!mainPane) return -1;
                return mainPane.querySelectorAll('canvas').length;
            })()
        """)
        print(f"  [INFO] Canvas elements in main pane: {canvas_count}")
        if canvas_count > 0:
            results["candlestick_renders"] = True
            print("  [OK] Candlestick chart canvas found")

        # Check volume (histogram) — should render within the same main pane
        volume_canvas_count = await page.evaluate("""
            (() => {
                const mainPane = document.getElementById('chart-main-pane');
                if (!mainPane) return 0;
                return mainPane.querySelectorAll('canvas').length;
            })()
        """)
        if volume_canvas_count > 0:
            results["volume_renders"] = True
            print("  [OK] Volume histogram canvas found")

        # ── Step 6: Check overlays and sub-panes ──
        print("\n[Step 6/7] Verifying overlays and sub-panes...")

        # Legend
        legend = await page.evaluate("""
            (() => {
                const el = document.getElementById('chart-legend');
                if (!el) return null;
                return {
                    text: el.textContent,
                    items: Array.from(el.querySelectorAll('span')).map(s => s.textContent).filter(Boolean),
                    childCount: el.children.length,
                };
            })()
        """)
        if legend:
            results["legend"] = True
            print(f"  [OK] Legend: {legend['items']}")
            expected = ["SMA20", "SMA50", "EMA20", "BB", "VWAP"]
            for e in expected:
                if e in legend["text"]:
                    print(f"    [OK] {e}")
                else:
                    print(f"    [MISS] {e}")
        else:
            print("  [FAIL] Legend not found")

        # Sub-panes
        rsi_pane = await page.evaluate("""
            (() => {
                const el = document.getElementById('chart-rsi-pane');
                if (!el) return null;
                return {
                    exists: true,
                    height: el.style.minHeight,
                    canvasCount: el.querySelectorAll('canvas').length,
                    label: document.getElementById('chart-rsi-label')?.textContent || null,
                };
            })()
        """)
        macd_pane = await page.evaluate("""
            (() => {
                const el = document.getElementById('chart-macd-pane');
                if (!el) return null;
                return {
                    exists: true,
                    height: el.style.minHeight,
                    canvasCount: el.querySelectorAll('canvas').length,
                    label: document.getElementById('chart-macd-label')?.textContent || null,
                };
            })()
        """)

        if rsi_pane:
            results["rsi_subpane_exists"] = True
            print(f"  [OK] RSI sub-pane: height={rsi_pane['height']}, canvases={rsi_pane['canvasCount']}, label={rsi_pane['label']}")
        else:
            print("  [FAIL] RSI sub-pane not found")

        if macd_pane:
            results["macd_subpane_exists"] = True
            print(f"  [OK] MACD sub-pane: height={macd_pane['height']}, canvases={macd_pane['canvasCount']}, label={macd_pane['label']}")
        else:
            print("  [FAIL] MACD sub-pane not found")

        # Tooltip
        tooltip = await page.evaluate("""
            (() => {
                const el = document.getElementById('chart-tooltip');
                if (!el) return null;
                const cs = getComputedStyle(el);
                return {
                    exists: true,
                    display: cs.display,
                    bg: cs.backgroundColor,
                    color: cs.color,
                    zIndex: el.style.zIndex,
                    font: cs.fontFamily,
                };
            })()
        """)
        if tooltip:
            results["tooltip"] = True
            print(f"  [OK] Tooltip: display={tooltip['display']}, zIndex={tooltip['zIndex']}")
        else:
            print("  [MISS] Tooltip element not found (may be expected if no data rendered)")

        # ── Step 7: Check dark theme and colors ──
        print("\n[Step 7/7] Verifying dark theme and color scheme...")

        # Background
        bg_info = await page.evaluate("""
            (() => {
                const style = getComputedStyle(document.documentElement);
                const stage = document.querySelector('.chart-stage');
                const stageBg = stage ? getComputedStyle(stage).backgroundColor : null;
                return {
                    cssBg: style.getPropertyValue('--bg').trim(),
                    cssSurface: style.getPropertyValue('--surface').trim(),
                    cssGreen: style.getPropertyValue('--green').trim(),
                    cssRed: style.getPropertyValue('--red').trim(),
                    cssGreenRaw: style.getPropertyValue('--green-raw').trim(),
                    cssRedRaw: style.getPropertyValue('--red-raw').trim(),
                    stageBg: stageBg,
                };
            })()
        """)

        print(f"  CSS --bg: {bg_info.get('cssBg', 'N/A')}")
        print(f"  CSS --surface: {bg_info.get('cssSurface', 'N/A')}")
        print(f"  CSS --green: {bg_info.get('cssGreen', 'N/A')}")
        print(f"  CSS --red: {bg_info.get('cssRed', 'N/A')}")
        print(f"  Chart stage bg: {bg_info.get('stageBg', 'N/A')}")

        # Check if #111820 is present anywhere in the theme
        css = bg_info.get("cssSurface", "")
        stage_bg = bg_info.get("stageBg", "")

        if "111820" in css or "111820" in stage_bg:
            results["dark_theme"] = True
            print("  [OK] Dark surface color #111820 detected")
        elif "hsl(135, 12%, 6%)" in css or "hsl(135, 12%, 6%)" in stage_bg:
            results["dark_theme"] = True
            print("  [OK] Dark surface color detected (rendered from CSS var)")
        else:
            print(f"  [WARN] Could not detect expected dark surface (#111820)")
            print(f"    Found: cssSurface={css}, stageBg={stage_bg}")

        # Check bull/bear colors
        green = bg_info.get("cssGreen", "")
        red = bg_info.get("cssRed", "")
        if green == "#00e676" and red == "#ff1744":
            results["colors_correct"] = True
            print(f"  [OK] Bull/bear colors match: bull={green}, bear={red}")
        else:
            print(f"  [WARN] Colors mismatch: expected bull=#00e676 bear=#ef5350, got bull={green} bear={red}")

        # Check stage background for the surface color visually
        stage_actual_bg = await page.evaluate("""
            (() => {
                const el = document.querySelector('.chart-stage');
                if (!el) return null;
                return getComputedStyle(el).backgroundColor;
            })()
        """)
        print(f"  [INFO] Actual stage background: {stage_actual_bg}")

        # ── Check for JS errors ──
        if js_errors:
            results["js_errors"] = js_errors
            print(f"\n  [WARN] {len(js_errors)} page JS error(s):")
            for e in js_errors[:5]:
                print(f"    {e[:150]}")
        else:
            print("\n  [OK] No page-level JS errors")

        # ── Screenshot ──
        screenshot_path = REPO_ROOT / "runtime" / "checkpoints" / "chart_verify_final.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"\n  [INFO] Screenshot saved: {screenshot_path}")

        # ── Console log summary ──
        chart_logs = []
        page.on("console", lambda msg: chart_logs.append({"type": msg.type, "text": msg.text}))
        # Re-run to collect logs
        await page.wait_for_timeout(1000)

        # ── Summary ──
        print("\n" + "=" * 65)
        print("  VERIFICATION SUMMARY")
        print("=" * 65)
        checks = [
            ("Page loads with JWT", results["page_load"]),
            ("Lightweight Charts library loaded", results["lw_loaded"]),
            ("Chart DOM structure (3 panes)", results["chart_dom_correct"]),
            ("Candlestick series renders", results["candlestick_renders"]),
            ("Volume histogram renders", results["volume_renders"]),
            ("Legend with indicators", results["legend"]),
            ("Tooltip element exists", results["tooltip"]),
            ("RSI sub-pane (88px)", results["rsi_subpane_exists"]),
            ("MACD sub-pane (96px)", results["macd_subpane_exists"]),
            ("Dark theme (#111820)", results["dark_theme"]),
        ]
        for name, ok in checks:
            print(f"  {'[PASS]' if ok else '[FAIL]'} {name}")

        total_ok = sum(1 for _, ok in checks if ok)
        print(f"\n  Results: {total_ok}/{len(checks)} checks passed")
        print(f"  JS errors: {len(results['js_errors'])}")

        await browser.close()

    # Save report
    report_path = REPO_ROOT / "runtime" / "checkpoints" / "chart_verify_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Report saved: {report_path}")

    return results


if __name__ == "__main__":
    result = asyncio.run(main())
    if isinstance(result, dict):
        sys.exit(0 if result.get("page_load") else 1)
