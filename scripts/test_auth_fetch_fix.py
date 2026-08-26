"""Validate that fetchWithAuth() correctly sends Authorization header."""

import json
import os
import sys
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
TEST_TICKER = os.environ.get("SUPEREZIO_TEST_TICKER", "TD.TO").strip().upper()


def main():
    # Login to get a real token
    login_payload = json.dumps({"username": "smoke_test_user", "password": "TestPass123!"}).encode()
    req = urllib.request.Request(
        f"{BASE}/auth/login",
        data=login_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        login_data = json.loads(resp.read())
        token = login_data["access_token"]
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Need to register first
            reg = json.dumps(
                {
                    "username": "smoke_test_user",
                    "email": "smoke@test.io",
                    "password": "TestPass123!",
                }
            ).encode()
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{BASE}/auth/register",
                    data=reg,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=10,
            )
            resp = urllib.request.urlopen(req, timeout=10)
            login_data = json.loads(resp.read())
            token = login_data["access_token"]
        else:
            print(f"Login failed: {e.code} {e.read().decode()[:200]}")
            return 1
    except Exception as e:
        print(f"Login error: {e}")
        return 1
    print(f"[OK] Login OK, token={token[:20]}...")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_function("window.SZ && window.SZ.api", timeout=15000)
        page.wait_for_timeout(500)

        # Inject token via function form (avoids ARG interpolation issues)
        page.evaluate("(t) => { localStorage.setItem('sz_access_token', t); }", token)
        stored = page.evaluate("() => localStorage.getItem('sz_access_token')")
        print(f"[OK] Token in localStorage: {stored[:20] if stored else 'NONE'}...")
        assert stored == token, "Token mismatch!"

        # TEST 1: fetchWithAuth sends Authorization header
        hdr = page.evaluate("""
            (t) => {
                const orig = window.fetch;
                let captured = null;
                window.fetch = function(url, opts) {
                    captured = {
                        url: url,
                        authHeader: (opts && opts.headers) ? (opts.headers['Authorization'] || opts.headers['authorization'] || null) : null
                    };
                    window.fetch = orig;
                    return Promise.resolve(new Response(null, {status: 200}));
                };
                return window.SZ.api.fetchWithAuth('/test-123').then(() => {
                    window.fetch = orig;
                    return captured;
                }).catch(() => {
                    window.fetch = orig;
                    return captured;
                });
            }
        """)
        if hdr and hdr.get("authHeader"):
            print("[PASS] TEST 1: Authorization header PRESENT")
            print(f"       Value: {hdr['authHeader'][:50]}...")
            print(f"       URL: {hdr.get('url', '')}")
        else:
            print("[FAIL] TEST 1: No Authorization header")
            print(f"       {json.dumps(hdr)}")
            page.screenshot(path="C:/Users/marco/Desktop/SuperEzio/output/playwright/t1_fail.png")
            browser.close()
            return 1

        # TEST 2: Real chart data
        chart = page.evaluate(
            """
            async (ticker) => {
                try {
                    const d = await window.SZ.api.fetchChartData(ticker, '1D');
                    return {ok: true, ticker: d.ticker, hasPrice: Boolean(d.price), candles: Array.isArray(d.ohlcv) ? d.ohlcv.length : 0};
                } catch(e) {
                    return {ok: false, error: e.message || String(e)};
                }
            }
        """,
            TEST_TICKER,
        )
        if chart.get("ok"):
            print(
                f"[PASS] TEST 2: fetchChartData OK (ticker={chart.get('ticker')}, candles={chart.get('candles')})"
            )
        else:
            print(f"[FAIL] TEST 2: {chart}")

        # TEST 3: Cockpit
        cockpit = page.evaluate("""
            async () => {
                try {
                    const d = await window.SZ.api.fetchCockpitSummary();
                    return {ok: true, status: d.status || 'ok'};
                } catch(e) {
                    return {ok: false, error: e.message || String(e)};
                }
            }
        """)
        if cockpit.get("ok"):
            print("[PASS] TEST 3: Cockpit OK")
        else:
            print(f"[INFO] TEST 3: {cockpit}")

        page.screenshot(
            path="C:/Users/marco/Desktop/SuperEzio/output/playwright/auth_fix_verified.png",
            full_page=True,
        )
        browser.close()

    all_ok = bool(hdr and hdr.get("authHeader")) and bool(chart.get("ok"))
    print(f"\n{'=' * 60}")
    print(f"VERDICT: {'PASS' if all_ok else 'FAIL'}")
    print(f"{'=' * 60}")
    return 0 if all_ok else 1


sys.exit(main())
