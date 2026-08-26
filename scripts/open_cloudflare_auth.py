import time

from playwright.sync_api import sync_playwright

AUTH_URL = "https://dash.cloudflare.com/argotunnel?aud=&callback=https%3A%2F%2Flogin.cloudflareaccess.org%2FBJBUbawZ0Pytaflpq9bp55vbEYCLx-dISgLq7dBHpQk%3D"

print("[PLAYWRIGHT] Abrindo navegador visível para autenticação Cloudflare...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel="chrome")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.goto(AUTH_URL)
    print("[PLAYWRIGHT] Página carregada no navegador visível. Aguardando login do usuário...")

    # Mantém a janela aberta por 300 segundos ou até cert.pem existir
    import os

    cert_path = os.path.expanduser("~/.cloudflared/cert.pem")
    for _ in range(150):
        if os.path.exists(cert_path):
            print("[PLAYWRIGHT] cert.pem detectado com sucesso!")
            break
        time.sleep(2)

    browser.close()
