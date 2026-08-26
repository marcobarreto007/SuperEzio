"""Questrade portfolio reader (Playwright, persistent session).
Primeiro uso: abre browser, você faz login, fecha.
Segundo uso: carrega sessão salva, lê carteira automaticamente.
NUNCA clica em submit/confirm/place-order.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(__file__).resolve().parent.parent / "runtime" / "questrade_profile"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "data" / "questrade_portfolio.json"
PORTFOLIO_URL = "https://myportal.questrade.com/investing/money-movement/"


def read_portfolio(page) -> dict:
    """Extract portfolio data from loaded Questrade page."""
    time.sleep(8)  # Wait for React to render
    text = page.inner_text("body")

    portfolio = {
        "provider": "questrade",
        "mode": "read_only_playwright",
        "connected": False,
        "can_submit_orders": False,
        "scraped_at": datetime.now(UTC).isoformat(),
        "equity": None,
        "cash": None,
        "positions": [],
        "page_url": page.url[:200],
        "page_text_len": len(text),
        "page_text_sample": text[:2000],
    }

    # Find dollar amounts
    amounts = re.findall(r"\$[\d,]+\.?\d*", text)
    if amounts:
        portfolio["connected"] = True
        nums = []
        for a in amounts:
            try:
                nums.append(float(a.replace("$", "").replace(",", "")))
            except ValueError:
                pass
        if nums:
            portfolio["equity"] = max(nums)
            portfolio["cash"] = nums[0]
        print(f"Valores: {amounts[:10]}")

    # Find ticker-like patterns near dollar amounts
    for line in text.split("\n"):
        tickers = re.findall(r"\b[A-Z]{1,5}\b", line)
        dollars = re.findall(r"\$[\d,]+\.?\d*", line)
        if tickers and dollars:
            portfolio["positions"].append(
                {
                    "ticker": tickers[0],
                    "value": dollars[0],
                    "raw": line.strip()[:200],
                }
            )

    print(
        f"Equity: ${portfolio['equity']} | Cash: ${portfolio['cash']} | Posições: {len(portfolio['positions'])}"
    )

    # Screenshot
    screenshot_dir = Path(__file__).resolve().parent.parent / "output" / "playwright"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot_dir / "questrade-portfolio.png"), full_page=True)

    return portfolio


def main():
    parser = argparse.ArgumentParser(description="Questrade portfolio reader (persistent session)")
    parser.add_argument(
        "--login", action="store_true", help="Abre browser para fazer login (primeiro uso)"
    )
    parser.add_argument("--headed", action="store_true", help="Mostra browser")
    parser.add_argument("--output", type=str, default=str(OUTPUT_FILE))
    args = parser.parse_args()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=not args.headed,
            viewport={"width": 1440, "height": 980},
            locale="en-CA",
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(PORTFOLIO_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            text = page.inner_text("body")

            if "User ID" in text or "Log in" in text:
                if args.headed:
                    print("=" * 60)
                    print("FAÇA LOGIN NO BROWSER AGORA")
                    print("1. Digite seu usuário e senha")
                    print("2. Resolva CAPTCHA/Turnstile")
                    print("3. Resolva MFA (código de verificação)")
                    print("4. Navegue até a página de investimentos")
                    print("=" * 60)
                    print("Aguardando 90 segundos...")
                    time.sleep(90)

                    # Reload page after login
                    page.goto(PORTFOLIO_URL, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(5)
                    text = page.inner_text("body")

                    if "User ID" in text or "Log in" in text:
                        print("Ainda na página de login. Tente novamente.")
                        context.close()
                        sys.exit(1)

                    print("Login detectado! Extraindo dados...")
                    portfolio = read_portfolio(page)
                else:
                    print("Sessão não autenticada. Use --headed --login para fazer login primeiro.")
                    context.close()
                    sys.exit(1)
            else:
                print("Sessão já autenticada! Extraindo dados...")
                portfolio = read_portfolio(page)

            # Save
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(portfolio, f, indent=2, ensure_ascii=False, default=str)

            print(f"\nSalvo em: {output_path}")
            print(
                f"Conectado: {portfolio['connected']} | Equity: ${portfolio['equity']} | Cash: ${portfolio['cash']}"
            )

        finally:
            context.close()


if __name__ == "__main__":
    main()
