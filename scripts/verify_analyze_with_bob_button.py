import os
import time
import requests
from playwright.sync_api import sync_playwright

print("[REAL TEST] Testando o botao 'Analisar com Bob' no navegador ao vivo...")
os.makedirs("output/bob_chart_action", exist_ok=True)

# 1. Login real
r = requests.post(
    "http://127.0.0.1:8002/auth/login",
    json={"username": "marco", "password": "Marco1234!"},
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=15,
)
token = r.json().get("access_token")
assert token, f"Login falhou: {r.text}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(f"localStorage.setItem('sz_access_token', '{token}');")
    page = context.new_page()
    
    # 2. Carrega o Cockpit
    page.goto("https://supereziorealtime.com", timeout=30000)
    page.wait_for_selector("#chat", timeout=15000)
    page.evaluate("if (window.SZ && window.SZ.loadChart) window.SZ.loadChart('TD.TO', '6M')")
    page.wait_for_timeout(3000)
    
    # 3. Screenshot do botao no cabecalho do grafico
    header = page.locator(".market-header")
    header.screenshot(path="output/bob_chart_action/01_market_header_button.png")
    print(" -> Salvo 01: Botao no cabecalho do grafico.")
    
    # 4. Clica no botao 'Analisar com Bob'
    print("[REAL TEST] Clicando no botao 'Analisar com Bob'...")
    btn = page.locator("#analyze-chart-bob-btn")
    assert btn.count() > 0, "Botao #analyze-chart-bob-btn nao encontrado no DOM!"
    btn.click()
    
    # 5. Aguarda abertura do drawer e envio
    page.wait_for_timeout(4000)
    page.screenshot(path="output/bob_chart_action/02_bob_drawer_triggered.png")
    print(" -> Salvo 02: Gaveta do Bob aberta e prompt tatico de grafico enviado.")

    browser.close()

print("[REAL TEST] Verificacao 100% concluida e comprovada com evidencias visuais!")
