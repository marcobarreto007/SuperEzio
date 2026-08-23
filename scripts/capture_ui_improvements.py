import os
import time
import requests
from playwright.sync_api import sync_playwright

print("[UI TEST] Capturando novas telas com as melhorias dos 3 subagentes...")
os.makedirs("output/ui_improvements", exist_ok=True)

r = requests.post(
    "http://127.0.0.1:8002/auth/login",
    json={"username": "marco", "password": "Marco1234!"},
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=15,
)
token = r.json().get("access_token")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(f"localStorage.setItem('sz_access_token', '{token}');")
    page = context.new_page()
    
    page.goto("https://supereziorealtime.com", timeout=30000)
    page.wait_for_selector("#chat", timeout=15000)
    page.evaluate("if (window.SZ && window.SZ.loadChart) window.SZ.loadChart('TD.TO', '6M')")
    page.wait_for_timeout(3500)
    
    # 1. Visão geral do Cockpit com Status Limpo e Novo Deck Inferior
    page.screenshot(path="output/ui_improvements/01_cockpit_status_clean.png")
    print(" -> Salvo 01: output/ui_improvements/01_cockpit_status_clean.png")

    # 2. Zoom na área inferior do deck
    deck = page.locator("#orders-mirror")
    if deck.count() > 0:
        deck.screenshot(path="output/ui_improvements/02_orders_deck_zoom.png")
        print(" -> Salvo 02: output/ui_improvements/02_orders_deck_zoom.png")

    browser.close()

print("[UI TEST] Concluído com sucesso!")
