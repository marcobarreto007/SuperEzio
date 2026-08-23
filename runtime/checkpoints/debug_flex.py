import json, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
payload = json.dumps({"username": "rapha", "password": "12345678"}).encode()
req = urllib.request.Request(f"{BASE}/auth/login", data=payload, headers={"Content-Type": "application/json"})
token = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())["access_token"]

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script(f"localStorage.setItem('sz_access_token', {json.dumps(token)});")
    page = ctx.new_page()
    page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    out = page.evaluate("""() => {
      const info = (sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const cs = getComputedStyle(el);
        const b = el.getBoundingClientRect();
        return {sel, w: Math.round(b.width), h: Math.round(b.height),
          flex: cs.flex, flexBasis: cs.flexBasis, flexGrow: cs.flexGrow, flexShrink: cs.flexShrink,
          flexWrap: cs.flexWrap, minWidth: cs.minWidth, width: cs.width,
          display: cs.display, alignSelf: cs.alignSelf};
      };
      return ['.topbar', '.topbar__left', '.topbar__search', '.topbar__ticker-group',
              '.ticker-wrap', '.topbar__tf-group', '#chart-btn', '.topbar__right',
              '.topbar__brand', '.topbar__hamburger'].map(info);
    }""")
    print(json.dumps(out, indent=1))
    browser.close()
