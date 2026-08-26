from playwright.sync_api import sync_playwright

results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    page = ctx.new_page()

    def on_request(req):
        if "app-money.tmx.com/graphql" in req.url:
            body = None
            try:
                body = req.post_data
            except Exception:  # noqa: S110, BLE001 - best-effort: falha em post_data é aceita.
                pass
            results.append({"kind": "REQ", "url": req.url, "post": body})

    def on_response(resp):
        if "app-money.tmx.com/graphql" in resp.url:
            try:
                body = resp.text()
            except Exception:  # noqa: BLE001 - best-effort: falha vira corpo vazio (None).
                body = None
            results.append(
                {
                    "kind": "RESP",
                    "url": resp.url,
                    "status": resp.status,
                    "body": (body or "")[:3000],
                }
            )

    page.on("request", on_request)
    page.on("response", on_response)
    page.goto("https://money.tmx.com/en/quote/TD.TO", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(5000)
    browser.close()

out = []
for r in results:
    if r["kind"] == "REQ":
        out.append("\n===== REQUEST =====")
        out.append(r["post"] or "")
    else:
        out.append("\n===== RESPONSE {} =====".format(r["status"]))
        out.append((r["body"] or "")[:3000])
print("\n".join(out)[:12000])
