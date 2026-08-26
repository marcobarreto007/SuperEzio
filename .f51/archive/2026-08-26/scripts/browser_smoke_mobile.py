"""Mobile browser smoke for SuperEzio — touch viewports.

Validates what the desktop smoke cannot: self-hit of every topbar control
(taps must land on the element itself, not a covering layer), zero
horizontal overflow, a readable price pane, and zero console errors.

Runs at 390x844 and 320x844 with deviceScaleFactor=2, isMobile, hasTouch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from playwright.sync_api import sync_playwright

try:  # load .env.local so public-mode credentials resolve (same as the API)
    from core.config.secrets import load_local_env

    load_local_env()
except ImportError:  # PYTHONPATH=src not set — credentials must come from the OS env
    pass

DEFAULT_BASE_URL = "http://127.0.0.1:8002"


def _auth_bootstrap(base_url: str) -> str | None:
    """Return a Bearer access token when the server runs in public mode."""
    base = base_url.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/auth/me", timeout=5) as resp:
            return None  # dev mode — anonymous allowed
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise RuntimeError(f"/auth/me returned {exc.code} during smoke auth bootstrap")

    username = os.getenv("SUPEREZIO_SMOKE_USER", "admin")
    password = os.getenv("SUPEREZIO_SMOKE_PASSWORD") or os.getenv("SUPEREZIO_ADMIN_PASSWORD", "")
    if not password:
        raise RuntimeError(
            "Public mode active: set SUPEREZIO_SMOKE_PASSWORD (or "
            "SUPEREZIO_ADMIN_PASSWORD in .env.local) to run the smoke"
        )
    payload = json.dumps({"username": username, "password": password}).encode()
    request = urllib.request.Request(
        f"{base}/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"/auth/login returned {exc.code} — check smoke credentials") from exc
    token = body.get("access_token")
    if not token:
        raise RuntimeError("/auth/login returned no access_token")
    return token


VIEWPORTS = [(390, 844), (320, 844)]
TARGET_SELECTORS = (
    ".topbar__tf-group .tf-btn",
    "#chart-btn",
    "#ops-console-btn",
    "#ticker-inp",
    "#bob-chat-tab",
)
MIN_PRICE_PANE_HEIGHT = 180  # R4 baseline was 133px — illegible
MIN_TOUCH_SIZE = 40  # iOS 44pt / Android 48dp recommended; 40 is the floor


def _http_ok(base_url: str, timeout_s: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=timeout_s) as r:
            return r.status == 200
    except Exception:
        return False


def _check_viewport(page, vw: int, vh: int) -> dict[str, Any]:
    result = page.evaluate(
        """
        (args) => {
          const out = {fails: [], smallTargets: [], overflowX: false,
                       pricePaneH: null, consoleErrors: 0};
          out.overflowX = document.body.scrollWidth > window.innerWidth + 1;
          const price = document.querySelector('#chart-main-pane');
          if (price) out.pricePaneH = Math.round(price.getBoundingClientRect().height);
          for (const sel of args.selectors) {
            const els = Array.from(document.querySelectorAll(sel));
            for (const el of els) {
              const b = el.getBoundingClientRect();
              if (b.width === 0 || b.height === 0) {
                out.fails.push((el.id || el.getAttribute('data-tf') || sel) + ' HIDDEN');
                continue;
              }
              const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
              const ok = hit === el || (el.contains && el.contains(hit));
              if (!ok) out.fails.push((el.id || el.getAttribute('data-tf') || sel) + ' COVERED');
              if (el.id !== 'bob-chat-tab' && (b.width < args.minTouch || b.height < args.minTouch)) {
                out.smallTargets.push((el.id || el.getAttribute('data-tf') || sel)
                    + '=' + Math.round(b.width) + 'x' + Math.round(b.height));
              }
            }
          }
          return out;
        }
        """,
        {"selectors": list(TARGET_SELECTORS), "minTouch": MIN_TOUCH_SIZE},
    )
    return {"viewport": f"{vw}x{vh}", **result}


def run_mobile_smoke(base_url: str, timeout_ms: int) -> dict[str, Any]:
    if not _http_ok(base_url):
        raise RuntimeError(f"API unreachable at {base_url}")

    token = _auth_bootstrap(base_url)
    results: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for vw, vh in VIEWPORTS:
            context = browser.new_context(
                viewport={"width": vw, "height": vh},
                device_scale_factor=2,
                is_mobile=True,
                has_touch=True,
            )
            if token:
                # Public mode: the token must exist BEFORE the first fetch —
                # otherwise the initial load logs 401 console errors.
                context.add_init_script(
                    f"localStorage.setItem('sz_access_token', {json.dumps(token)});"
                )
            page = context.new_page()
            console_errors: list[str] = []
            page.on(
                "console",
                lambda m, console_errors=console_errors: console_errors.append(m.text)
                if m.type == "error"
                else None,
            )
            page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(3000)
            check = _check_viewport(page, vw, vh)
            check["consoleErrors"] = len(console_errors)
            check["consoleErrorText"] = console_errors[:5]
            results.append(check)
            context.close()
        browser.close()
    return {"base_url": base_url, "viewports": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="SuperEzio mobile browser smoke.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args()

    try:
        result = run_mobile_smoke(args.base_url, args.timeout_ms)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    problems = []
    for vp in result["viewports"]:
        if vp["overflowX"]:
            problems.append(f"{vp['viewport']}: horizontal overflow")
        if vp["fails"]:
            problems.append(f"{vp['viewport']}: covered/hidden controls {vp['fails']}")
        if vp["pricePaneH"] is not None and vp["pricePaneH"] < MIN_PRICE_PANE_HEIGHT:
            problems.append(
                f"{vp['viewport']}: price pane {vp['pricePaneH']}px < {MIN_PRICE_PANE_HEIGHT}px"
            )
        if vp["consoleErrors"]:
            problems.append(f"{vp['viewport']}: {vp['consoleErrors']} console errors")

    if problems:
        print(json.dumps({"ok": False, "problems": problems, **result}, indent=2))
        return 1
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
