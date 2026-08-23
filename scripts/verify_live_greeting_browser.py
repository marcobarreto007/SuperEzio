import os
import requests
from playwright.sync_api import sync_playwright

r = requests.post(
    "http://127.0.0.1:8002/auth/login",
    json={"username": "marco", "password": "Marco1234!"},
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=15,
)
token = r.json().get("access_token")
assert token, f"Login failed: {r.text}"

os.makedirs("output/bob_greetings_fix", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(f"localStorage.setItem('sz_access_token', '{token}');")
    page = context.new_page()
    page.goto("https://supereziorealtime.com", timeout=30000)
    page.wait_for_selector("#chat", timeout=15000)
    page.wait_for_timeout(2000)

    # Open Bob chat tab
    page.click("#bob-chat-tab")
    page.wait_for_timeout(1000)

    # Type 'bob tudo bem'
    page.fill("#user-inp", "bob tudo bem")
    page.click("#send-btn")

    # Wait for response
    page.wait_for_timeout(4000)
    page.screenshot(path="output/bob_greetings_fix/01_bob_greeting_clean.png")
    print("Screenshot salvo em output/bob_greetings_fix/01_bob_greeting_clean.png")
    browser.close()
