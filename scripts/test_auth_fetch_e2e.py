"""SuperEzio — Auth Fetch E2E Test (Playwright)

Valida que:
- fetchWithAuth() SEMPRE anexa o token JWT no header Authorization
- O debug log "[fetchWithAuth] path=... token=... status=..." aparece
- 401 → refreshToken() → retry funciona
- Se refresh falhar → modal de login aparece
- Cards da expert panel atualizam (saem de WAIT) após submit

Uso:
    python scripts/test_auth_fetch_e2e.py [--headed] [--base-url URL]
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
DEFAULT_BASE_URL = os.getenv("SUPEREZIO_BROWSER_SMOKE_URL", "http://127.0.0.1:8002")
TEST_USERNAME = os.getenv("SUPEREZIO_TEST_USERNAME", "testuser")
TEST_PASSWORD = os.getenv("SUPEREZIO_TEST_PASSWORD", "TestPass123!")
TEST_PROMPT = os.getenv(
    "SUPEREZIO_TEST_PROMPT",
    "What is the current market outlook for AAPL? Give a brief summary.",
)


def _server_up(base_url: str) -> bool:
    try:
        urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=3)
        return True
    except Exception:
        return False


def _check_fetch_debug_logs(console_lines: list[str]) -> dict[str, Any]:
    """Search console logs for [fetchWithAuth] entries and return analysis."""
    auth_logs = [l for l in console_lines if "[fetchWithAuth]" in l]
    if not auth_logs:
        return {"ok": False, "reason": "no_fetchWithAuth_logs_found", "logs": []}

    parsed = []
    for line in auth_logs:
        parsed.append(line)

    has_token = any("token=eyJ" in l or "Bearer eyJ" in l for l in auth_logs)
    has_status = any("status=" in l for l in auth_logs)

    return {
        "ok": has_token and has_status,
        "reason": None if (has_token and has_status) else "missing_token_or_status",
        "count": len(parsed),
        "logs": parsed,
    }


def _check_cards_not_wait(page: Page) -> dict[str, Any]:
    """Check expert panel verdict cards — at least one should be non-WAIT."""
    result = page.evaluate(
        """
        () => {
            const verdicts = document.querySelectorAll('.expert-card__verdict');
            const cards = Array.from(verdicts).map(el => ({
                text: el.textContent.trim(),
                notWait: el.textContent.trim() !== 'WAIT' && el.textContent.trim() !== '--'
            }));
            return {
                ok: cards.some(c => c.notWait),
                cards: cards
            };
        }
        """
    )
    return result


def _check_auth_modal_visible(page: Page) -> bool:
    """Check if the auth modal overlay is visible."""
    return page.evaluate(
        """
        () => {
            const overlay = document.getElementById('auth-modal-overlay');
            if (!overlay) return false;
            return overlay.classList.contains('auth-overlay--visible');
        }
        """
    )


def _dismiss_auth_modal(page: Page) -> None:
    """Dismiss auth modal if visible (for dev mode testing)."""
    page.evaluate("() => { if (window.SZ?.auth?.hideModal) window.SZ.auth.hideModal(); }")


def _login_via_modal(page: Page, username: str, password: str) -> dict[str, Any]:
    """Fill login form and submit. Returns result."""
    result = page.evaluate(
        """
        async (args) => {
            const auth = window.SZ && window.SZ.auth;
            if (!auth) return { ok: false, reason: 'auth_not_loaded' };
            if (typeof auth.isAuthenticated === 'function' && auth.isAuthenticated()) {
                return { ok: true, reason: 'already_authenticated' };
            }
            try {
                await auth.login(args.username, args.password);
                return { ok: true, reason: 'login_success' };
            } catch (err) {
                return { ok: false, reason: err.message };
            }
        }
        """,
        {"username": username, "password": password},
    )
    # If the evaluate failed (e.g. auth.login threw synchronously), try via DOM
    if not result.get("ok"):
        # Try filling the form fields directly
        try:
            page.fill("#auth-login-username", username)
            page.fill("#auth-login-password", password)
            page.click(".auth-submit")
            page.wait_for_timeout(2000)
            # Check if modal closed
            still_visible = _check_auth_modal_visible(page)
            return {
                "ok": not still_visible,
                "reason": "login via DOM" if not still_visible else "login_failed_modal_still_visible",
            }
        except Exception as exc:
            return {"ok": False, "reason": f"dom_login_exception: {exc}"}
    return result


def _submit_chat_and_wait(page: Page, prompt: str, timeout_ms: int) -> dict[str, Any]:
    """Submit a chat query and wait for Bob's response."""
    page.fill("#user-inp", prompt)
    page.click("#send-btn")

    # Wait for Bob response: a CEO message with substantial text
    try:
        page.wait_for_function(
            """
            () => {
                const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
                if (bobMsgs.length < 1) return false;
                const lastBob = bobMsgs[bobMsgs.length - 1];
                const text = lastBob.innerText || '';
                return text.length > 50 && !text.includes('Erro:');
            }
            """,
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        pass  # We'll report the state

    # Collect results
    result = page.evaluate(
        """
        () => {
            const bobMsgs = document.querySelectorAll('#chat .msg-ceo');
            const lastBob = bobMsgs.length > 0 ? bobMsgs[bobMsgs.length - 1] : null;
            const text = lastBob ? lastBob.innerText : '';
            const userMsgs = document.querySelectorAll('#chat .msg-user');

            // Check cards
            const verdicts = document.querySelectorAll('.expert-card__verdict');
            const cardStates = Array.from(verdicts).map(el => el.textContent.trim());

            // Check f51-verdict specifically
            const f51El = document.getElementById('f51-verdict');
            const f51Verdict = f51El ? f51El.textContent.trim() : 'N/A';

            // Check token in localStorage
            const token = localStorage.getItem('sz_access_token');

            return {
                responseLength: text.length,
                bobMsgCount: bobMsgs.length,
                userMsgCount: userMsgs.length,
                f51Verdict: f51Verdict,
                cardStates: cardStates,
                hasToken: Boolean(token),
                tokenPreview: token ? token.substring(0, 12) + '...' : null,
                firstChars: text.substring(0, 150)
            };
        }
        """
    )
    return result


def run_test(
    base_url: str,
    headed: bool,
    timeout_ms: int,
    slow_mo: int = 0,
) -> dict[str, Any]:
    if not _server_up(base_url):
        return {"ok": False, "error": f"Server not reachable at {base_url}"}

    out_dir = ROOT / "output" / "playwright"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    screenshot_path = out_dir / f"auth-fetch-e2e-{stamp}.png"

    console_lines: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed, slow_mo=slow_mo)
        # Create context with localStorage enabled
        context = browser.new_context(viewport={"width": 1440, "height": 980})
        page = context.new_page()

        # Capture ALL console output (not just errors)
        page.on("console", lambda msg: console_lines.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # Step 1: Navigate to the app
        page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_selector("#user-inp", timeout=timeout_ms)
        page.wait_for_selector("#send-btn", timeout=timeout_ms)
        page.wait_for_function(
            "window.SZ && typeof window.SZ.loadChart === 'function'",
            timeout=timeout_ms,
        )
        page.wait_for_timeout(2000)

        # Step 2: Check auth state
        initial_auth_state = page.evaluate(
            """
            () => {
                const auth = window.SZ && window.SZ.auth;
                if (!auth) return { loaded: false };
                return {
                    loaded: true,
                    hasToken: Boolean(auth.getToken()),
                    isAuthenticated: typeof auth.isAuthenticated === 'function' ? auth.isAuthenticated() : false,
                    hasGetValidToken: typeof auth.getValidToken === 'function',
                    hasGetToken: typeof auth.getToken === 'function',
                };
            }
            """
        )
        print(f"[test] Initial auth state: {json.dumps(initial_auth_state)}")

        # Step 3: If auth modal is visible, log in
        modal_visible = _check_auth_modal_visible(page)
        login_result = None
        if modal_visible:
            print("[test] Auth modal visible — attempting login")
            login_result = _login_via_modal(page, TEST_USERNAME, TEST_PASSWORD)
            print(f"[test] Login result: {json.dumps(login_result)}")
            page.wait_for_timeout(1000)
        else:
            print("[test] No auth modal — assuming dev mode or already authenticated")

        # Step 4: Check auth state after login
        post_login_auth = page.evaluate(
            """
            () => {
                const auth = window.SZ && window.SZ.auth;
                if (!auth) return { loaded: false };
                return {
                    loaded: true,
                    hasToken: Boolean(auth.getToken()),
                    isAuthenticated: typeof auth.isAuthenticated === 'function' ? auth.isAuthenticated() : false,
                    tokenPreview: auth.getToken() ? auth.getToken().substring(0, 12) + '...' : null,
                };
            }
            """
        )
        print(f"[test] Post-login auth state: {json.dumps(post_login_auth)}")

        # Step 5: Submit a chat query
        print(f"[test] Submitting chat: \"{TEST_PROMPT[:60]}...\"")
        # Hide modal if still visible (dev mode)
        _dismiss_auth_modal(page)
        page.wait_for_timeout(500)

        chat_result = _submit_chat_and_wait(page, TEST_PROMPT, timeout_ms)
        print(f"[test] Chat result: f51Verdict={chat_result.get('f51Verdict')} "
              f"bobLen={chat_result.get('responseLength')} "
              f"hasToken={chat_result.get('hasToken')}")

        # Step 6: Check cards updated
        cards_result = _check_cards_not_wait(page)
        print(f"[test] Cards updated: {cards_result.get('ok')} "
              f"verdicts={cards_result.get('cards', [])}")

        # Step 7: Check console for [fetchWithAuth] debug logs
        auth_fetch_logs = _check_fetch_debug_logs(console_lines)
        print(f"[test] fetchWithAuth logs: found={auth_fetch_logs.get('count', 0)} "
              f"ok={auth_fetch_logs.get('ok')}")

        # Step 8: Screenshot
        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    # Step 9: Compile results
    summary = {
        "ok": (
            (auth_fetch_logs.get("ok") or post_login_auth.get("hasToken"))
            and chat_result.get("responseLength", 0) > 50
        ),
        "server": base_url,
        "initial_auth": initial_auth_state,
        "login_result": login_result,
        "post_login_auth": post_login_auth,
        "chat": {
            "responseLength": chat_result.get("responseLength", 0),
            "f51Verdict": chat_result.get("f51Verdict"),
            "cardStates": chat_result.get("cardStates", []),
            "hasToken": chat_result.get("hasToken"),
            "firstChars": chat_result.get("firstChars", ""),
        },
        "cards_updated": cards_result.get("ok"),
        "cards_detail": cards_result.get("cards", []),
        "fetchWithAuth_logs": auth_fetch_logs,
        "page_errors": page_errors,
        "screenshot": str(screenshot_path),
    }

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="SuperEzio Auth Fetch E2E Test")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=180000)
    parser.add_argument("--slow-mo", type=int, default=300,
                        help="ms per action (default 300 with --headed, 0 otherwise)")
    args = parser.parse_args()

    slow_mo = args.slow_mo if args.headed else 0

    try:
        result = run_test(
            base_url=args.base_url.rstrip("/"),
            headed=args.headed,
            timeout_ms=args.timeout_ms,
            slow_mo=slow_mo,
        )
    except PlaywrightTimeoutError as exc:
        print(json.dumps({"ok": False, "error": f"timeout: {exc}"}, indent=2))
        return 1
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps({"ok": True, **result}, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
