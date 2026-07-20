"""Questrade portfolio reader (Playwright).
Lê posições, saldo e ordens da interface web do Questrade.
NUNCA clica em submit/confirm/place-order.
Salva em data/questrade_portfolio.json para o cockpit ler.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

LOGIN_URL = "https://login.questrade.com/"
PORTFOLIO_URL = "https://my.questrade.com/trading/"
ACCOUNTS_URL = "https://my.questrade.com/accounts/"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "data" / "questrade_portfolio.json"

SELECTORS = {
    "cookie_accept": "#onetrust-accept-btn-handler",
    "username_input": "input#userId",
    "password_input": "input#password",
    "login_submit": "button#btnLogin",
    # Portfolio — best-effort, may need updating
    "positions_table": "table.positions-table, div.positions-list, .holdings-container",
    "position_row": "tr.position-row, .holding-item, [data-testid='position-row']",
    "account_value": ".account-value, .total-equity, [data-testid='total-value']",
    "cash_balance": ".cash-balance, .buying-power, [data-testid='cash']",
}


def _safe_text(page: Page, selector: str, timeout: int = 5000) -> str:
    try:
        el = page.wait_for_selector(selector, timeout=timeout)
        return el.inner_text().strip() if el else ""
    except PWTimeout:
        return ""


def _safe_text_all(page: Page, selector: str, timeout: int = 5000) -> list[str]:
    try:
        page.wait_for_selector(selector, timeout=timeout)
        els = page.query_selector_all(selector)
        return [e.inner_text().strip() for e in els]
    except PWTimeout:
        return []


def login_questrade(page: Page, username: str, password: str) -> bool:
    """Log into Questrade. Returns True if login succeeded."""
    print(f"Navegando para {LOGIN_URL}...")
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)

    # Accept cookies
    try:
        page.click(SELECTORS["cookie_accept"], timeout=3000)
        print("Cookies aceitos.")
    except PWTimeout:
        pass

    # Fill credentials
    print("Preenchendo login...")
    page.fill(SELECTORS["username_input"], username)
    page.fill(SELECTORS["password_input"], password)
    page.click(SELECTORS["login_submit"])

    # Wait for navigation after login
    time.sleep(3)
    page.wait_for_load_state("networkidle", timeout=15000)

    # Check if still on login page (failed)
    if "login" in page.url.lower():
        print("ERRO: Login falhou — ainda na página de login.")
        return False

    print(f"Login OK. URL atual: {page.url}")
    return True


def read_portfolio(page: Page) -> dict:
    """Scrape portfolio data from Questrade web interface."""
    print("Navegando para página de portfolio...")

    portfolio = {
        "provider": "questrade",
        "mode": "read_only_playwright",
        "connected": False,
        "can_submit_orders": False,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "equity": None,
        "cash": None,
        "buying_power": None,
        "positions": [],
        "orders": [],
        "raw_text": "",
    }

    # Try portfolio page
    for url in [PORTFOLIO_URL, ACCOUNTS_URL]:
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            time.sleep(2)
            print(f"Página carregada: {page.url[:80]}")
            break
        except Exception as e:
            print(f"Falha ao carregar {url}: {e}")
            continue

    # Try to extract account value
    value_text = _safe_text(page, SELECTORS["account_value"])
    cash_text = _safe_text(page, SELECTORS["cash_balance"])

    if value_text:
        portfolio["connected"] = True
        portfolio["raw_text"] = value_text
        print(f"Valor da conta: {value_text}")
        # Try to parse "$123,456.78"
        import re
        nums = re.findall(r'[\d,]+\.?\d*', value_text.replace(',', ''))
        if nums:
            try:
                portfolio["equity"] = float(nums[0])
            except ValueError:
                pass

    if cash_text:
        import re
        nums = re.findall(r'[\d,]+\.?\d*', cash_text.replace(',', ''))
        if nums:
            try:
                portfolio["cash"] = float(nums[0])
            except ValueError:
                pass

    # Try to scrape positions
    try:
        rows = page.query_selector_all(SELECTORS["position_row"])
        for row in rows:
            text = row.inner_text().strip()
            if text and len(text) > 5:
                portfolio["positions"].append({"raw": text})
        print(f"Posições encontradas: {len(portfolio['positions'])}")
    except Exception as e:
        print(f"Erro ao ler posições: {e}")

    # Screenshot for debugging
    screenshot_path = Path(__file__).resolve().parent.parent / "output" / "playwright" / "questrade-portfolio.png"
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"Screenshot salvo: {screenshot_path}")

    return portfolio


def main():
    parser = argparse.ArgumentParser(description="Questrade portfolio reader (Playwright, read-only)")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--output", type=str, default=str(OUTPUT_FILE), help="Output JSON file")
    args = parser.parse_args()

    username = os.getenv("QUESTRADE_USERNAME", "")
    password = os.getenv("QUESTRADE_PASSWORD", "")

    if not username or not password:
        print("ERRO: QUESTRADE_USERNAME e QUESTRADE_PASSWORD não configurados no .env.local")
        sys.exit(1)

    print(f"=== Questrade Portfolio Reader ===")
    print(f"Usuário: {username}")
    print(f"Output:  {args.output}")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            viewport={"width": 1440, "height": 980},
            locale="en-CA",
        )
        page = context.new_page()

        try:
            if not login_questrade(page, username, password):
                print("Abortando — login falhou.")
                browser.close()
                sys.exit(1)

            # Pause for 2FA if needed
            print()
            print(">>> Se aparecer tela de verificação (2FA), resolva no browser.")
            print(">>> Depois pressione Enter aqui para continuar...")
            if args.headed:
                input()

            portfolio = read_portfolio(page)

            # Save
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(portfolio, f, indent=2, ensure_ascii=False, default=str)

            print()
            print(f"=== RESULTADO ===")
            print(f"Conectado: {portfolio['connected']}")
            print(f"Equity:    ${portfolio.get('equity', 'N/A')}")
            print(f"Cash:      ${portfolio.get('cash', 'N/A')}")
            print(f"Posições:  {len(portfolio['positions'])}")
            print(f"Salvo em:  {output_path}")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
