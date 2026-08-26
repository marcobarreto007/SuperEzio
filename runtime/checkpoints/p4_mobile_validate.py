import json
import os
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("P4_BASE_URL", "http://127.0.0.1:8002")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "p4")

try:
    from core.config.secrets import load_local_env

    load_local_env()
except ImportError:
    pass


def auth_bootstrap(base_url):
    base = base_url.rstrip("/")
    try:
        with urllib.request.urlopen(base + "/auth/me", timeout=5) as r:
            return None
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise RuntimeError("auth/me returned {}".format(exc.code))
    password = os.getenv("SUPEREZIO_SMOKE_PASSWORD") or os.getenv("SUPEREZIO_ADMIN_PASSWORD", "")
    if not password:
        raise RuntimeError("SUPEREZIO_ADMIN_PASSWORD missing")
    payload = json.dumps(
        {"username": os.getenv("SUPEREZIO_SMOKE_USER", "admin"), "password": password}
    ).encode()
    req = urllib.request.Request(
        base + "/auth/login", data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())["access_token"]


BACKEND_KEYS = [
    "missing_ticker",
    "missing_ticker_provenance",
    "missing_exchange",
    "missing_price",
    "missing_price_provenance",
    "missing_liquidity",
    "missing_liquidity_provenance",
    "liquidity_below_minimum",
    "dollar_volume_below_minimum",
    "missing_catalyst",
    "missing_catalyst_provenance",
    "missing_short_term_thesis",
    "missing_risk",
    "missing_risk_provenance",
    "missing_invalidation",
    "missing_invalidation_provenance",
    "provider_error",
    "currency_market_mismatch",
    "penny_filtered",
    "otc_filtered",
    "microcap_filtered",
    "price_above_requested_max",
    "quality_gate_failed",
    "excluded_previous_recommendation",
    "unknown",
]

JS_COCKPIT = (
    "() => ({ sz: !!window.SZ, topbar: !!document.querySelector(`.topbar`),"
    " uinpVisible: (() => { const e = document.querySelector(`#user-inp`);"
    " if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })() })"
)

JS_READABLE = (
    "() => { const els = document.querySelectorAll(`.msg.msg-ceo`);"
    " if (!els.length) return null; const b = els[els.length-1].querySelector(`.msg-bubble`);"
    " if (!b) return null; const cs = getComputedStyle(b); const r = b.getBoundingClientRect();"
    " return { fontSize: cs.fontSize, height: Math.round(r.height), text: b.textContent.trim().slice(0, 200) }; }"
)

JS_INPUT_VISIBLE = (
    "() => { const e = document.querySelector(`#user-inp`);"
    " if (!e) return false; const r = e.getBoundingClientRect();"
    " return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight; }"
)

JS_WAIT_RESP = (
    "() => document.querySelectorAll(`.msg.msg-ceo`).length > %d &&"
    " (() => { const els = document.querySelectorAll(`.msg.msg-ceo`);"
    " const b = els[els.length-1].querySelector(`.msg-bubble`);"
    " return b && b.textContent.trim().length > 10; })()"
)

JS_SYNTH = (
    "(keys) => { const summary = {}; keys.forEach((k, i) => { summary[k] = i + 1; });"
    " SZ.state.lastScan = { rejection_summary: summary, source_errors: [`provider_x`],"
    " quality: `partial`, candidates: 0, rejected_count: keys.length, scanProgress: { elapsedMs: 98765 } };"
    " SZ.chat.finishCEOMessage();"
    " SZ.handleEvent({ type: `DATA_COLLECTED`, capability: `market_scan`,"
    " rejection_summary: summary, source_errors: [`provider_x`], quality: `partial`,"
    " candidates: 0, rejected_count: keys.length, providers: [`scanner_a`, `scanner_b`] });"
    " const el = document.querySelector(`.scan-summary`); const text = el ? el.textContent : ``;"
    " const raw = keys.filter(k => text.includes(k + ` (`)); const body = document.body;"
    " const chat = document.getElementById(`chat`);"
    " return { summaryText: text.slice(0, 400), rawKeysRendered: raw,"
    " bodyOverflowX: body.scrollWidth > window.innerWidth + 1,"
    " chatOverflowX: chat && chat.scrollWidth > chat.clientWidth + 1 }; }"
)

JS_OVERFLOW = (
    "() => ({ bodyOverflowX: document.body.scrollWidth > window.innerWidth + 1,"
    " innerWidth: window.innerWidth, scrollWidth: document.body.scrollWidth })"
)


def main():
    try:
        _run()
    except Exception as exc:
        print(json.dumps({"fatal": str(exc)}, ensure_ascii=False))
        sys.exit(2)


def _run():
    token = auth_bootstrap(BASE)
    report = {"base_url": BASE, "steps": {}, "console_errors": [], "page_errors": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
        if token:
            context.add_init_script(
                "localStorage.setItem(`sz_access_token`, {});".format(json.dumps(token))
            )
        page = context.new_page()
        page.on(
            "console",
            lambda m: report["console_errors"].append(m.text) if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: report["page_errors"].append(str(e)))

        # (a) token login -> cockpit renders
        page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#chat", timeout=30000)
        page.wait_for_selector("#user-inp", timeout=30000)
        page.wait_for_selector("#send-btn", timeout=30000)
        page.wait_for_function("window.SZ && !!SZ.handleEvent", timeout=30000)
        page.wait_for_timeout(2000)
        cockpit = page.evaluate(JS_COCKPIT)
        report["steps"]["a_cockpit"] = cockpit
        page.screenshot(path=os.path.join(OUT, "01-cockpit.png"))

        # (b) chat open + greeting
        chat_open = page.evaluate(JS_INPUT_VISIBLE)
        if not chat_open:
            page.click("#bob-chat-tab", timeout=10000)
            page.wait_for_function(
                "() => { const bc = document.querySelector(`.bob-chat`);"
                " return bc && bc.classList.contains(`is-open`); }",
                timeout=10000,
            )
        page.wait_for_function(
            "() => { const e = document.querySelector(`#user-inp`); return !e.disabled; }",
            timeout=30000,
        )
        before = page.locator(".msg.msg-ceo").count()
        t0 = time.time()
        page.fill("#user-inp", "Oi Bob")
        page.click("#send-btn")
        response_ms = None
        try:
            page.wait_for_function(JS_WAIT_RESP % before, timeout=45000)
            response_ms = int((time.time() - t0) * 1000)
        except Exception as exc:
            report["steps"]["b_chat_error"] = str(exc)
        readable = page.evaluate(JS_READABLE)
        report["steps"]["b_greeting"] = {"response_ms": response_ms, "readable": readable}
        page.screenshot(path=os.path.join(OUT, "02-chat-greeting.png"))

        # (c1) real short scan (best effort, bounded)
        page.wait_for_function(
            "() => { const e = document.querySelector(`#user-inp`); return !e.disabled; }",
            timeout=120000,
        )
        t1 = time.time()
        page.fill("#user-inp", "scaneie o mercado")
        page.click("#send-btn")
        scan_real = {"triggered": False, "elapsed_ms": 0}
        try:
            page.wait_for_selector(".scan-summary", timeout=150000)
            scan_real = {
                "triggered": True,
                "elapsed_ms": int((time.time() - t1) * 1000),
                "text": page.locator(".scan-summary").inner_text()[:300],
            }
        except Exception:
            scan_real["elapsed_ms"] = int((time.time() - t1) * 1000)
        report["steps"]["c1_scan_real"] = scan_real

        # (c2) deterministic full-key dispatch through the real handler
        synth = page.evaluate(JS_SYNTH, BACKEND_KEYS)
        report["steps"]["c2_scan_summary_synthetic"] = synth
        page.screenshot(path=os.path.join(OUT, "03-scan-summary.png"))

        final = page.evaluate(JS_OVERFLOW)
        report["steps"]["d_e_overflow"] = final
        context.close()
        browser.close()

    report["console_errors"] = report["console_errors"][:10]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = (
        cockpit.get("uinpVisible")
        and report["steps"]["b_greeting"].get("response_ms") is not None
        and not synth["rawKeysRendered"]
        and not synth["bodyOverflowX"]
        and not synth["chatOverflowX"]
        and not final["bodyOverflowX"]
        and not report["console_errors"]
        and not report["page_errors"]
    )
    print("P4_MOBILE_OK" if ok else "P4_MOBILE_FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
