import os
import time

import requests
from playwright.sync_api import sync_playwright

print("[LIVE CHROME OPERATOR] Iniciando operacao visual do Google Chrome...")

# 1. Login
r = requests.post(
    "http://127.0.0.1:8002/auth/login",
    json={"username": "marco", "password": "Marco1234!"},
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=15,
)
token = r.json().get("access_token")
assert token, f"Falha no login: {r.text}"
print(" -> Token autenticado.")

chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
assert os.path.exists(chrome_exe), f"Chrome nao encontrado em {chrome_exe}"

os.makedirs("output/live_chrome_run", exist_ok=True)

with sync_playwright() as p:
    print(" -> Lancando Google Chrome oficial visivel na tela com slow_mo=1200ms...")
    browser = p.chromium.launch(
        executable_path=chrome_exe,
        headless=False,
        slow_mo=1200,  # 1.2 segundos por acao para o usuario ver claramente cada clique
        args=["--start-maximized", "--no-first-run", "--no-default-browser-check"],
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
    page.screenshot(path="output/live_chrome_run/01_cockpit_ready.png")
    print(" -> [1/5] Cockpit carregado.")

    # 1. Clicar no botão 'Analisar com Bob'
    print(" -> [2/5] Clicando no botao 'Analisar com Bob' no grafico...")
    analyze_btn = page.locator("#analyze-chart-bob-btn")
    if analyze_btn.count() > 0:
        analyze_btn.click()
        page.screenshot(path="output/live_chrome_run/02_clicked_bob_analysis.png")
        print(" -> Clique realizado em Analisar com Bob.")
    time.sleep(3)

    # 2. Clicar no chat do Bob e digitar saudação
    print(" -> [3/5] Focando no chat do Bob e digitando 'bob tudo bem'...")
    user_inp = page.locator("#user-inp")
    if user_inp.count() > 0:
        try:
            # Garante que a aba do chat esteja aberta
            bob_tab = page.locator("#bob-chat-tab")
            if bob_tab.count() > 0:
                bob_tab.click()
            time.sleep(1)
            user_inp.click()
            user_inp.fill("bob tudo bem")
            page.screenshot(path="output/live_chrome_run/03_typed_greeting.png")
            page.click("#send-btn")
            print(" -> Mensagem 'bob tudo bem' enviada.")
        except Exception as e:  # noqa: BLE001 — operacao manual nao deve abortar por falha de interacao com o chat
            print(" -> Aviso ao interagir com chat:", e)

    time.sleep(4)
    page.screenshot(path="output/live_chrome_run/04_bob_replied.png")

    # 3. Interagir com os cards de oportunidades do deck inferior
    print(" -> [4/5] Interagindo com os cards do deck inferior...")
    cards = page.locator("#orders-list .order-row, #trade-history-list .trade-row")
    if cards.count() > 0:
        print(f" -> Encontrados {cards.count()} cards no deck. Clicando no primeiro card...")
        cards.first.click()
        time.sleep(2)
        page.screenshot(path="output/live_chrome_run/05_card_clicked.png")

    print(
        " -> [5/5] Operacao completa realizada. Mantendo a janela aberta por 180 segundos para voce usar..."
    )
    time.sleep(180)
    browser.close()
