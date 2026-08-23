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
      const tg = document.querySelector('.topbar__ticker-group');
      const out = [];
      for (const el of tg.children) {
        const b = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        out.push({cls: el.className, id: el.id, top: Math.round(b.top), h: Math.round(b.height),
                  left: Math.round(b.left), w: Math.round(b.width), flex: cs.flex,
                  display: cs.display, order: cs.order});
      }
      const tg2 = tg.getBoundingClientRect();
      out.push({cls: 'ticker-group', top: Math.round(tg2.top), h: Math.round(tg2.height)});
      return out;
    }""")
    print(json.dumps(out, indent=1))
    browser.close()
