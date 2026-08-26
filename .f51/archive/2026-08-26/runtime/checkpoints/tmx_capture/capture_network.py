import json

from playwright.sync_api import sync_playwright

urls = {}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    page = ctx.new_page()
    seen = []

    def on_response(resp):
        ct = resp.headers.get("content-type", "")
        if "json" in ct or "graphql" in resp.url or "api" in resp.url.lower():
            try:
                body = resp.text()
            except Exception:  # noqa: BLE001 — leitura do corpo pode falhar (rede/timeout); fallback deliberado para body=None
                body = None
            seen.append({"url": resp.url, "status": resp.status, "ct": ct, "body": body[:2000]})

    page.on("response", on_response)
    page.goto("https://money.tmx.com/en/quote/TD.TO", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)
    print(json.dumps(seen, indent=1)[:6000])
    browser.close()
