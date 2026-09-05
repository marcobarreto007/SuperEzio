import os

import requests
from playwright.sync_api import sync_playwright

print("[LIVE PROBE] Solicitando token de autenticação...")
password = os.environ.get("SUPEREZIO_ADMIN_PASSWORD")
if not password:
    raise SystemExit(
        "SUPEREZIO_ADMIN_PASSWORD nao definida: exporte a senha do admin antes de rodar "
        '(gere com: python -c "import secrets; print(secrets.token_hex(32))")'
    )

r = requests.post(
    "https://supereziorealtime.com/auth/login",
    json={"username": "marco", "password": password},
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=10,
)
token = r.json().get("access_token")
assert token, f"Falha ao obter token: {r.text}"
print("[LIVE PROBE] Token obtido com sucesso.")

os.makedirs("output/live_deploy", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(f"localStorage.setItem('sz_access_token', '{token}');")
    page = context.new_page()

    print("[LIVE PROBE] Navegando para https://supereziorealtime.com...")
    page.goto("https://supereziorealtime.com", timeout=30000)
    page.wait_for_selector("#chat", timeout=15000)
    page.wait_for_timeout(3000)

    page.screenshot(path="output/live_deploy/01_live_cockpit.png")
    print("[LIVE PROBE] Screenshot salvo: output/live_deploy/01_live_cockpit.png")

    print("[LIVE PROBE] Carregando gráfico TD.TO (6M)...")
    page.evaluate("if (window.SZ && window.SZ.loadChart) window.SZ.loadChart('TD.TO', '6M')")
    page.wait_for_timeout(4000)

    page.screenshot(path="output/live_deploy/02_live_chart_td_to.png")
    print("[LIVE PROBE] Screenshot salvo: output/live_deploy/02_live_chart_td_to.png")

    print("[LIVE PROBE] Abrindo o painel do Bob e enviando mensagem de teste...")
    page.locator("#bob-chat-tab").click()
    page.wait_for_timeout(1000)
    page.locator("#user-inp").fill("olá bob, qual o status do mercado hoje?")
    page.locator("#send-btn").click()
    print("[LIVE PROBE] Mensagem enviada. Aguardando processamento...")
    page.wait_for_timeout(8000)

    page.screenshot(path="output/live_deploy/03_bob_live_response.png")
    print("[LIVE PROBE] Screenshot salvo: output/live_deploy/03_bob_live_response.png")

    browser.close()
print("[LIVE PROBE] Auditoria do navegador completa com sucesso!")
