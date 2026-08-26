import json

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    p = ctx.new_page()
    p.goto("http://127.0.0.1:8002", wait_until="load", timeout=25000)
    p.wait_for_timeout(3000)
    out = p.evaluate(r"""() => {
      const r = (sel) => { const el = document.querySelector(sel); if (!el) return null; const x = el.getBoundingClientRect(); return {l: Math.round(x.left), r: Math.round(x.right), t: Math.round(x.top), b: Math.round(x.bottom), w: Math.round(x.width), h: Math.round(x.height)}; };
      const hit = (x, y) => { const el = document.elementFromPoint(x, y); if (!el) return 'NONE'; const id = el.id || ''; const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0,2).join('.') : ''; return el.tagName + (id ? '#' + id : '') + (cls ? '.' + cls : ''); };
      const kids = {};
      document.querySelectorAll('.topbar > div, .topbar > button, .topbar__left > * , .topbar__right > * , .topbar__ticker-group > *').forEach(el => {
        const x = el.getBoundingClientRect();
        kids[(el.id ? '#' + el.id : (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/)[0] : el.tagName))] = {l: Math.round(x.left), r: Math.round(x.right), t: Math.round(x.top), b: Math.round(x.bottom), w: Math.round(x.width), h: Math.round(x.height)};
      });
      const points = {};
      [[50,20],[120,20],[180,20],[270,20],[340,20],[370,20],[150,40],[30,20]].forEach(pt => {
        points[pt.join(',')] = hit(pt[0], pt[1]);
      });
      return {kids, points};
    }""")
    print(json.dumps(out, indent=1))
    b.close()
