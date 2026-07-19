"""Questrade order-ticket assist (Playwright).

Fills the Questrade Edge Web order ticket (ticker, side, quantity, LIMIT
price) so the operator does not have to type it by hand. It NEVER clicks
submit/confirm/place-order — that click is the one action Questrade
reserves for the human account holder, and this script does not perform it
under any flag, mode, or argument.

Usage (manual, one order at a time):

    python scripts/questrade_order_assist.py --ticker SHOP --side buy \\
        --quantity 10 --limit-price 85.30

First run: Questrade will likely show a 2FA/verification-code screen. The
script pauses (input()) at that point — enter the code in the real browser
window yourself, then press Enter in this terminal to let the script
continue.

Selectors below are best-effort placeholders for Questrade Edge Web as of
2026-07. Questrade can change its DOM at any time without notice; if a
selector no longer matches, the script fails loudly (raises) rather than
guessing or clicking something else. Update the SELECTORS dict below after
inspecting the live page (F12 dev tools) if that happens.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

LOGIN_URL = "https://login.questrade.com/"
ORDER_ENTRY_URL = "https://my.questrade.com/trading/"

# Best-effort selectors — VERIFY against the live DOM before relying on this.
# Keeping them centralized here means a DOM change only needs one edit.
SELECTORS = {
    "username_input": "input#username, input[name='username']",
    "password_input": "input#password, input[name='password']",
    "login_submit": "button[type='submit']",
    "symbol_search": "input[placeholder*='symbol' i], input[aria-label*='symbol' i]",
    "buy_tab": "button:has-text('Buy'), [role='tab']:has-text('Buy')",
    "sell_tab": "button:has-text('Sell'), [role='tab']:has-text('Sell')",
    "order_type_dropdown": "select[name*='orderType' i], [aria-label*='order type' i]",
    "quantity_input": "input[name*='quantity' i], input[aria-label*='quantity' i]",
    "limit_price_input": "input[name*='limitPrice' i], input[aria-label*='price' i]",
    # Intentionally NOT included: any submit/confirm/place-order selector.
    # This script has no code path that can click such a button.
}

SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "runtime" / "questrade_tickets"


def _pause_for_human(message: str) -> None:
    print(f"\n[PAUSED] {message}")
    input("Press Enter here once you've done that in the browser window... ")


def login(page: Page) -> None:
    username = os.getenv("QUESTRADE_USERNAME", "")
    password = os.getenv("QUESTRADE_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "QUESTRADE_USERNAME / QUESTRADE_PASSWORD not set. "
            "Set them in .env (never commit real values)."
        )

    page.goto(LOGIN_URL)
    page.fill(SELECTORS["username_input"], username)
    page.fill(SELECTORS["password_input"], password)
    page.click(SELECTORS["login_submit"])

    # Questrade will very likely show a 2FA / one-time-code screen here.
    # We cannot and do not try to bypass it — it's designed to require you.
    try:
        page.wait_for_url("**/trading/**", timeout=8000)
    except PWTimeout:
        _pause_for_human(
            "Looks like a 2FA/verification step. Complete it in the browser, "
            "then wait for the trading dashboard to load."
        )


def fill_order_ticket(
    page: Page,
    *,
    ticker: str,
    side: str,
    quantity: int,
    limit_price: float,
) -> None:
    if side not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")

    page.goto(ORDER_ENTRY_URL)
    page.wait_for_load_state("networkidle")

    page.fill(SELECTORS["symbol_search"], ticker)
    page.wait_for_timeout(1000)  # let the symbol autocomplete/lookup resolve
    page.keyboard.press("Enter")

    side_selector = SELECTORS["buy_tab"] if side == "buy" else SELECTORS["sell_tab"]
    page.click(side_selector)

    page.fill(SELECTORS["quantity_input"], str(quantity))
    page.fill(SELECTORS["limit_price_input"], f"{limit_price:.2f}")

    print(
        f"\nOrder ticket filled: {side.upper()} {quantity} {ticker} "
        f"@ LIMIT {limit_price:.2f}"
    )
    print(
        "Nothing has been submitted. Review every field on screen yourself, "
        "then click the confirm/submit button in the browser window if — and "
        "only if — it's correct."
    )


def screenshot_ticket(page: Page, ticker: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{ticker}_{int(time.time())}.png"
    page.screenshot(path=str(path))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--side", required=True, choices=["buy", "sell"])
    parser.add_argument("--quantity", required=True, type=int)
    parser.add_argument("--limit-price", required=True, type=float)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless. NOT recommended: you need to see the browser "
        "to complete 2FA and to click confirm yourself.",
    )
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context()
        page = context.new_page()

        try:
            login(page)
            fill_order_ticket(
                page,
                ticker=args.ticker.upper(),
                side=args.side,
                quantity=args.quantity,
                limit_price=args.limit_price,
            )
            shot = screenshot_ticket(page, args.ticker.upper())
            print(f"Screenshot of the filled ticket saved to: {shot}")
            _pause_for_human(
                "Review the order ticket in the browser. This script will "
                "close the browser once you press Enter — it will NOT click "
                "confirm/submit for you."
            )
        finally:
            context.close()
            browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
