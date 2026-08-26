import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(".env.local")
load_dotenv(".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_server.auth import _create_access_token

print("=" * 70)
print("[CHROMIUM OPERATOR] Iniciando operacao automatizada com CHROMIUM...")
print("=" * 70)

token = _create_access_token(1, "marco")
print(" -> Token de acesso gerado com sucesso.")

os.makedirs("output/chromium_live_run", exist_ok=True)

with sync_playwright() as p:
    print(" -> Lancando Chromium oficial do Playwright na tela (headless=False)...")
    browser = p.chromium.launch(
        headless=False, slow_mo=1000, args=["--start-maximized", "--no-sandbox"]
    )
    context = browser.new_context(
        no_viewport=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    )
    context.add_init_script(f"localStorage.setItem('sz_access_token', '{token}');")

    page = context.new_page()

    print(" -> Navegando para https://supereziorealtime.com ...")
    page.goto("https://supereziorealtime.com", timeout=60000)
    page.wait_for_selector("#chat", timeout=30000)
    time.sleep(2)
    page.screenshot(path="output/chromium_live_run/01_chromium_home.png")
    print(" -> [1/4] Chromium abriu o Cockpit com sucesso.")

    # 1. Clicar no botão 'Analisar com Bob'
    print(" -> [2/4] Clicando no botao 'Analisar com Bob' no grafico...")
    analyze_btn = page.locator("#analyze-chart-bob-btn")
    if analyze_btn.count() > 0:
        analyze_btn.click()
        time.sleep(2)
        page.screenshot(path="output/chromium_live_run/02_chromium_bob_analysis.png")
        print(" -> Clique realizado em 'Analisar com Bob'.")

    # 2. Interagir com o chat do Bob
    print(" -> [3/4] Interagindo com o chat do Bob...")
    bob_tab = page.locator("#bob-chat-tab")
    if bob_tab.count() > 0:
        bob_tab.click()
    time.sleep(1)

    user_inp = page.locator("#user-inp")
    if user_inp.count() > 0:
        try:
            user_inp.click()
            user_inp.fill("bob tudo bem")
            page.click("#send-btn")
            print(" -> Mensagem 'bob tudo bem' enviada com sucesso no Chromium.")
        except Exception as e:  # noqa: BLE001 — operacao manual nao deve abortar por falha de interacao com o chat
            print(" -> Detalhe chat:", e)

    time.sleep(4)
    page.screenshot(path="output/chromium_live_run/03_chromium_bob_response.png")
    print(" -> [3/4] Resposta do Bob capturada no Chromium.")

    # 3. Clicar nos cards de trade/oportunidades
    print(" -> [4/4] Clicando nos cards de oportunidades do deck inferior...")
    cards = page.locator("#orders-list .order-row, #trade-history-list .trade-row")
    if cards.count() > 0:
        cards.first.click()
        time.sleep(2)
        page.screenshot(path="output/chromium_live_run/04_chromium_card_click.png")

    print(" -> Operacao Chromium concluida. Janela mantida aberta por 180s para voce interagir...")
    time.sleep(180)
    browser.close()
