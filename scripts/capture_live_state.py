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

chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
os.makedirs("output/live_chrome_run", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=chrome_exe, headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 950})
    context.add_init_script(f"localStorage.setItem('sz_access_token', '{token}');")
    page = context.new_page()
    page.goto("https://supereziorealtime.com", timeout=60000)
    page.wait_for_selector("#chat", timeout=30000)
    page.click("#bob-chat-tab")
    page.wait_for_timeout(3000)
    page.screenshot(path="output/live_chrome_run/06_current_live_state.png")
    print("Screenshot atual salvo em output/live_chrome_run/06_current_live_state.png")
    browser.close()
