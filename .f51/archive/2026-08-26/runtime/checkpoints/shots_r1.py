import json
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
payload = json.dumps({"username": "rapha", "password": "12345678"}).encode()
req = urllib.request.Request(
    f"{BASE}/auth/login", data=payload, headers={"Content-Type": "application/json"}
)
token = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())["access_token"]
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    # mobile shots
    for vw, vh in [(390, 844), (320, 844)]:
        ctx = browser.new_context(
            viewport={"width": vw, "height": vh},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
        ctx.add_init_script(f"localStorage.setItem('sz_access_token', {json.dumps(token)});")
        page = ctx.new_page()
        page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3500)
        page.screenshot(path=f"runtime/checkpoints/r1_{vw}x{vh}_top.png")
        # scroll to the expert panel for a second shot
        page.evaluate("document.querySelector('.expert-panel').scrollIntoView()")
        page.wait_for_timeout(600)
        page.screenshot(path=f"runtime/checkpoints/r1_{vw}x{vh}_panel.png")
        ctx.close()
    # desktop sanity
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(f"localStorage.setItem('sz_access_token', {json.dumps(token)});")
    page = ctx.new_page()
    errs = []
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3500)
    desk = page.evaluate(
        """() => {
      const r = (sel) => { const el = document.querySelector(sel); if (!el) return null;
        const b = el.getBoundingClientRect(); return {w: Math.round(b.width), h: Math.round(b.height), top: Math.round(b.top)}; };
      return {topbar: r('.topbar'), tfGroup: r('.topbar__tf-group'),
              appMain: r('.app-main'), expertPanel: r('.expert-panel'),
              pricePane: r('#chart-main-pane'), overflowX: document.body.scrollWidth > window.innerWidth + 1,
              appMainCols: getComputedStyle(document.querySelector('.app-main')).gridTemplateColumns,
              errors: """
        + str(len("x"))
        + """};
    }"""
    )
    # redo errors properly
    desk["errors"] = len(errs)
    print("DESKTOP 1440x900:", json.dumps(desk))
    page.screenshot(path="runtime/checkpoints/r1_desktop.png")
    browser.close()
