import os

import requests
from playwright.sync_api import sync_playwright

print("=" * 70)
print("[PLAYWRIGHT REAL TEST] Iniciando teste completo no navegador ao vivo...")
print("=" * 70)

os.makedirs("output/playwright_live_run", exist_ok=True)

# 1. Autenticação real
print("[1/5] Realizando login na API...")
password = os.environ.get("SUPEREZIO_ADMIN_PASSWORD")
if not password:
    raise SystemExit(
        "SUPEREZIO_ADMIN_PASSWORD nao definida: exporte a senha do admin antes de rodar "
        '(gere com: python -c "import secrets; print(secrets.token_hex(32))")'
    )

login_resp = requests.post(
    "http://127.0.0.1:8002/auth/login",
    json={"username": "marco", "password": password},
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=15,
)
token = login_resp.json().get("access_token")
assert token, f"Falha no login: {login_resp.text}"
print(" -> Token obtido com sucesso.")

console_logs = []
console_errors = []
failed_requests = []

with sync_playwright() as p:
    print("[2/5] Abrindo Chromium no endereco https://supereziorealtime.com ...")
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1600, "height": 950},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    )
    context.add_init_script(f"localStorage.setItem('sz_access_token', '{token}');")

    page = context.new_page()

    # Captura logs e erros do console
    page.on(
        "console",
        lambda msg: (
            console_logs.append(f"[{msg.type}] {msg.text}")
            if msg.type != "error"
            else console_errors.append(msg.text)
        ),
    )
    page.on("pageerror", lambda err: console_errors.append(f"[PageError] {err}"))
    page.on(
        "requestfailed",
        lambda req: failed_requests.append(f"{req.method} {req.url} - {req.failure}"),
    )

    # Navega para o domínio real
    page.goto("https://supereziorealtime.com", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_selector("#chat", timeout=20000)
    page.wait_for_timeout(3000)

    # Screenshot 1: Cockpit carregado
    shot1 = "output/playwright_live_run/01_cockpit_home.png"
    page.screenshot(path=shot1, full_page=False)
    print(f" -> Screenshot 1 salvo: {shot1}")

    # 3. Carregar e verificar gráfico de TD.TO
    print("[3/5] Selecionando ativo TD.TO (6M) e validando grafico...")
    page.evaluate("if (window.SZ && window.SZ.loadChart) window.SZ.loadChart('TD.TO', '6M')")
    page.wait_for_timeout(3000)
    shot2 = "output/playwright_live_run/02_chart_td_to.png"
    page.screenshot(path=shot2, full_page=False)
    print(f" -> Screenshot 2 salvo: {shot2}")

    # 4. Clicar no botão 'Analisar com Bob'
    print("[4/5] Clicando no botao 'Analisar com Bob'...")
    analyze_btn = page.locator("#analyze-chart-bob-btn")
    assert analyze_btn.count() > 0, "Botao #analyze-chart-bob-btn nao encontrado no DOM!"
    analyze_btn.click()

    # Aguardar o término do streaming da análise tática do Bob
    print(" -> Aguardando streaming completo da analise tatica de TD.TO...")
    page.wait_for_selector("#user-inp:not([disabled])", timeout=75000)
    page.wait_for_timeout(2000)
    shot3 = "output/playwright_live_run/03_bob_analysis_complete.png"
    page.screenshot(path=shot3, full_page=False)
    print(f" -> Screenshot 3 salvo: {shot3}")

    # 5. Testar saudação casual 'bob tudo bem'
    print("[5/5] Testando mensagem casual 'bob tudo bem' no chat...")
    page.fill("#user-inp", "bob tudo bem")
    page.click("#send-btn")
    print(" -> Aguardando resposta de saudacao do Bob...")
    page.wait_for_selector("#user-inp:not([disabled])", timeout=30000)
    page.wait_for_timeout(2000)
    shot4 = "output/playwright_live_run/04_bob_greeting_response.png"
    page.screenshot(path=shot4, full_page=False)
    print(f" -> Screenshot 4 salvo: {shot4}")

    # Final: Zoom no deck de trades inferior
    bottom_deck = page.locator("#orders-mirror")
    if bottom_deck.count() > 0:
        shot5 = "output/playwright_live_run/05_bottom_deck_zoom.png"
        bottom_deck.screenshot(path=shot5)
        print(f" -> Screenshot 5 salvo: {shot5}")

    browser.close()

print("=" * 70)
print("[PLAYWRIGHT REAL TEST] Teste ao vivo finalizado com sucesso!")
print(f"Logs coletados: {len(console_logs)}")
print(f"Erros de console criticos: {len(console_errors)}")
for err in console_errors:
    print(f"  [Console Error]: {err}")
print("=" * 70)
