import json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
OUT = "runtime/checkpoints"

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    p = ctx.new_page()
    errs = []
    p.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    p.goto(BASE, wait_until="load", timeout=25000)
    p.wait_for_timeout(3000)
    p.screenshot(path=OUT + "/r4-probe-topbar.jpg", type="jpeg", quality=55, full_page=True)
    info = p.evaluate("""() => {
      const r = (sel) => { const el = document.querySelector(sel); if (!el) return null; const x = el.getBoundingClientRect(); return {l: Math.round(x.left), r: Math.round(x.right), t: Math.round(x.top), b: Math.round(x.bottom), w: Math.round(x.width), h: Math.round(x.height)}; };
      const tb = document.querySelector('.topbar');
      const mh = document.querySelector('.market-header');
      const oz = document.querySelector('.chart-zone');
      const om = document.querySelector('.orders-mirror');
      const st = document.querySelector('.chart-stage');
      return {
        iw: window.innerWidth, dpr: window.devicePixelRatio,
        vvpW: window.visualViewport ? window.visualViewport.width : null,
        topbar: r('.topbar'), topbarLeft: r('.topbar__left'), topbarRight: r('.topbar__right'),
        tickerGroup: r('.topbar__ticker-group'), tfGroup: r('#tf-group'),
        tbScrollH: tb ? tb.scrollHeight : null, tbClientH: tb ? tb.clientHeight : null,
        marketHeader: r('.market-header'), chartZone: r('.chart-zone'), chartStage: r('.chart-stage'), ordersMirror: r('.orders-mirror'),
        ordersList: r('#orders-list'), tradeHistory: r('#trade-history-list'),
        appMain: r('.app-main')
      };
    }""")
    # bell only, no prior interactions
    p.tap("#alert-bell-btn"); p.wait_for_timeout(500)
    info["alerts"] = p.evaluate("""() => {
      const d = document.getElementById('alert-dropdown');
      const x = d.getBoundingClientRect();
      return {l: Math.round(x.left), r: Math.round(x.right), w: Math.round(x.width), t: Math.round(x.top), b: Math.round(x.bottom), iw: window.innerWidth, bodySW: document.body.scrollWidth, vvpW: window.visualViewport ? window.visualViewport.width : null, scale: window.visualViewport ? window.visualViewport.scale : null, open: d.classList.contains('alert-dropdown--open')};
    }""")
    p.screenshot(path=OUT + "/r4-probe-alerts.jpg", type="jpeg", quality=55)
    print(json.dumps(info, indent=1))
    b.close()
