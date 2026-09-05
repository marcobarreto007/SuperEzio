import os
import time

import requests
from playwright.sync_api import sync_playwright

print("[BROWSER REAL VISIVEL] Obtendo autenticacao e iniciando navegador visual...")

# 1. Login na API
password = os.environ.get("SUPEREZIO_ADMIN_PASSWORD")
if not password:
    raise SystemExit(
        "SUPEREZIO_ADMIN_PASSWORD nao definida: exporte a senha do admin antes de rodar "
        '(gere com: python -c "import secrets; print(secrets.token_hex(32))")'
    )

r = requests.post(
    "http://127.0.0.1:8002/auth/login",
    json={"username": "marco", "password": password},
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=15,
)
token = r.json().get("access_token")
assert token, f"Falha no login: {r.text}"
print(" -> Token autenticado com sucesso.")

with sync_playwright() as p:
    print(" -> Abrindo o navegador Chromium VISIVEL na tela...")
    # headless=False para ABRIR VISIVEL NA TELA DO USUARIO
    browser = p.chromium.launch(headless=False, args=["--start-maximized"])
    context = browser.new_context(
        no_viewport=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    context.add_init_script(f"localStorage.setItem('sz_access_token', '{token}');")

    page = context.new_page()

    print(" -> Navegando para https://supereziorealtime.com ...")
    page.goto("https://supereziorealtime.com", timeout=60000)

    # Aguarda carregar o Cockpit
    page.wait_for_selector("#chat", timeout=25000)
    print(" -> Cockpit carregado.")
    time.sleep(2)

    # Abre a aba do Bob
    print(" -> Abrindo painel do Bob Copilot...")
    try:
        page.click("#bob-chat-tab")
    except Exception:  # noqa: BLE001, S110 — clique best-effort deliberado: aba pode ja estar aberta; segue sem ruido
        pass
    time.sleep(1)

    # Digita 'bob tudo bem' no chat
    print(" -> Digitando 'bob tudo bem' no chat...")
    try:
        page.fill("#user-inp", "bob tudo bem")
        page.click("#send-btn")
        print(" -> Mensagem enviada para o Bob.")
    except Exception as e:  # noqa: BLE001 — erro de digitacao best-effort deliberado: mensagem visivel e o navegador permanece aberto
        print(" -> Erro ao digitar no chat:", e)

    print(" -> Navegador aberto e ativo na sua tela. Aguardando 120 segundos para interacao...")
    time.sleep(120)
    browser.close()
