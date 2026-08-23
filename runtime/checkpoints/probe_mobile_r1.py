"""Probe: measure mobile layout geometry at 390x844 and 320x844 (authenticated)."""
import json, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"

def login():
    import urllib.request
    payload = json.dumps({"username": "rapha", "password": "12345678"}).encode()
    req = urllib.request.Request(f"{BASE}/auth/login", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())["access_token"]

def probe(page):
    return page.evaluate("""() => {
      const out = {};
      const r = (sel) => { const el = document.querySelector(sel);
        if (!el) return null; const b = el.getBoundingClientRect();
        return {top: Math.round(b.top), left: Math.round(b.left),
                width: Math.round(b.width), height: Math.round(b.height),
                bottom: Math.round(b.bottom), right: Math.round(b.right)}; };
      out.topbar = r('.topbar');
      out.tfGroup = r('.topbar__tf-group');
      out.tfBtns = Array.from(document.querySelectorAll('.topbar__tf-group .tf-btn')).map(el => {
        const b = el.getBoundingClientRect();
        return {tf: el.dataset.tf, top: Math.round(b.top), left: Math.round(b.left),
                w: Math.round(b.width), h: Math.round(b.height)}; });
      out.topbarLeft = r('.topbar__left');
      out.topbarRight = r('.topbar__right');
      out.tickerWrap = r('.ticker-wrap');
      out.tickerGroup = r('.topbar__ticker-group');
      out.search = r('.topbar__search');
      out.appMain = r('.app-main');
      out.chartZone = r('.chart-zone');
      out.expertPanel = r('.expert-panel');
      out.chartStage = r('.chart-stage');
      out.stageCanvas = r('.chart-stage__canvas');
      out.pricePane = r('#chart-main-pane');
      out.ordersMirror = r('.orders-mirror');
      out.bodyScrollW = document.body.scrollWidth;
      out.innerW = window.innerWidth;
      out.overflowX = document.body.scrollWidth > window.innerWidth + 1;
      const cs = (sel, prop) => { const el = document.querySelector(sel);
        return el ? getComputedStyle(el)[prop] : null; };
      out.topbarWrap = cs('.topbar', 'flexWrap');
      out.tfGroupWrap = cs('.topbar__tf-group', 'flexWrap');
      out.tfGroupFlex = cs('.topbar__tf-group', 'flex');
      out.tfGroupDisplay = cs('.topbar__tf-group', 'display');
      out.tfBtnH = cs('.tf-btn', 'height');
      out.tfBtnMinW = cs('.tf-btn', 'minWidth');
      out.appMainCols = cs('.app-main', 'gridTemplateColumns');
      out.appMainRows = cs('.app-main', 'gridTemplateRows');
      out.expertPos = cs('.expert-panel', 'position');
      out.expertRight = cs('.expert-panel', 'right');
      out.expertW = cs('.expert-panel', 'width');
      out.bodyMinW = cs('body', 'minWidth');
      out.bodyOverflow = cs('body', 'overflow');
      out.bodyH = cs('body', 'height');
      return out;
    }""")


token = login()
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    for vw, vh in [(390, 844), (320, 844)]:
        ctx = browser.new_context(viewport={"width": vw, "height": vh},
                                  device_scale_factor=2, is_mobile=True, has_touch=True)
        ctx.add_init_script(f"localStorage.setItem('sz_access_token', {json.dumps(token)});")
        page = ctx.new_page()
        errs = []
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3500)
        data = probe(page)
        data["consoleErrors"] = errs[:8]
        data["consoleErrorCount"] = len(errs)
        print(f"===== {vw}x{vh} =====")
        print(json.dumps(data, indent=1))
        page.screenshot(path=f"runtime/checkpoints/probe_{vw}x{vh}_before.png", full_page=False)
        ctx.close()
    browser.close()
