import json

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(
        viewport={"width": 768, "height": 1024},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    p = ctx.new_page()
    p.goto("http://127.0.0.1:8002", wait_until="load", timeout=25000)
    p.wait_for_timeout(3000)
    out = p.evaluate(r"""() => {
      const r = (sel) => { const el = document.querySelector(sel); if (!el) return null; const x = el.getBoundingClientRect(); return {l: Math.round(x.left), r: Math.round(x.right), w: Math.round(x.width)}; };
      const hit = (x, y) => { const el = document.elementFromPoint(x, y); if (!el) return 'NONE'; const id = el.id || ''; const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0,2).join('.') : ''; return el.tagName + (id ? '#' + id : '') + (cls ? '.' + cls : ''); };
      return {tfGroup: r('#tf-group'), chartBtn: r('#chart-btn'), right: r('.topbar__right'), left: r('.topbar__left'),
        hits: {tf1: hit(300, 20), tf2: hit(360, 20), tf3: hit(420, 20), chartBtn: hit(490, 20), bell: hit(700, 20)}};
    }""")
    print(json.dumps(out, indent=1))
    b.close()
