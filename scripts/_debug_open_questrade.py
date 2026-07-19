"""Debug helper: opens Questrade login in a Playwright-controlled Chromium
window, lists every <input> and <button> found on the page (id, name, type,
placeholder, aria-label), and keeps the window open so the operator can log
in manually while we inspect further if needed. Does not fill or click
anything itself.
"""

from __future__ import annotations

import time

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://login.questrade.com/"


def describe_inputs(page) -> None:
    inputs = page.query_selector_all("input")
    print(f"\nFound {len(inputs)} <input> elements:")
    for i, el in enumerate(inputs):
        attrs = {
            "type": el.get_attribute("type"),
            "id": el.get_attribute("id"),
            "name": el.get_attribute("name"),
            "placeholder": el.get_attribute("placeholder"),
            "aria-label": el.get_attribute("aria-label"),
        }
        print(f"  [{i}] {attrs}")

    buttons = page.query_selector_all("button")
    print(f"\nFound {len(buttons)} <button> elements:")
    for i, el in enumerate(buttons):
        attrs = {
            "type": el.get_attribute("type"),
            "id": el.get_attribute("id"),
            "text": (el.inner_text() or "").strip()[:40],
        }
        print(f"  [{i}] {attrs}")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL)
        page.wait_for_timeout(4000)  # let the SPA render; site keeps network busy (chat/analytics)
        print(f"Opened {LOGIN_URL}")

        describe_inputs(page)

        print(
            "\nWindow will stay open. You can log in manually if you want. "
            "Press Enter in this terminal to re-scan the page (e.g. after a "
            "2FA screen appears), or Ctrl+C to close."
        )
        try:
            while True:
                input("Press Enter to re-scan current page... ")
                describe_inputs(page)
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
