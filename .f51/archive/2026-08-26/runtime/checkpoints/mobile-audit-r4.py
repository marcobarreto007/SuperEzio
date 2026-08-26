import json

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
OUT = "runtime/checkpoints"

MEASURE_JS = r"""
() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const bodySW = document.body.scrollWidth;
  const docSW = document.documentElement.scrollWidth;
  const offenders = [];
  document.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && (r.right > vw + 1 || r.left < -1)) {
      const cls = (typeof el.className === 'string') ? el.className.trim().split(/\s+/).slice(0,3).join('.') : '';
      offenders.push({t: el.tagName, id: el.id || '', c: cls, l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width)});
    }
  });
  offenders.sort((a,b) => (b.r - vw) - (a.r - vw));
  const smallFonts = [];
  document.querySelectorAll('*').forEach(el => {
    const fs = parseFloat(getComputedStyle(el).fontSize);
    if (fs > 0 && fs <= 10) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && !el.closest('script,style')) {
        const cls = (typeof el.className === 'string') ? el.className.trim().split(/\s+/).slice(0,2).join('.') : '';
        smallFonts.push({t: el.tagName, id: el.id || '', c: cls, fs: fs, txt: (el.textContent||'').trim().slice(0,18)});
      }
    }
  });
  smallFonts.sort((a,b) => a.fs - b.fs);
  const smallTargets = [];
  document.querySelectorAll('button, [role="tab"], a, input, select, textarea').forEach(el => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    if (r.width > 0 && (r.width < 40 || r.height < 40)) {
      const cls = (typeof el.className === 'string') ? el.className.trim().split(/\s+/).slice(0,2).join('.') : '';
      smallTargets.push({t: el.tagName, id: el.id || '', c: cls, w: Math.round(r.width), h: Math.round(r.height)});
    }
  });
  const chartPane = document.getElementById('chart-main-pane');
  const cr = chartPane ? chartPane.getBoundingClientRect() : null;
  const topbar = document.querySelector('.topbar');
  const tr = topbar ? topbar.getBoundingClientRect() : null;
  const canvasCount = document.querySelectorAll('canvas').length;
  return {vw: vw, vh: vh, bodySW: bodySW, docSW: docSW, overflow: bodySW - vw,
    topbarH: tr ? Math.round(tr.height) : null,
    chartPane: cr ? {w: Math.round(cr.width), h: Math.round(cr.height)} : null,
    canvasCount: canvasCount,
    offenders: offenders.slice(0, 20),
    smallFonts: smallFonts.slice(0, 20), smallFontCount: smallFonts.length,
    smallTargets: smallTargets.slice(0, 25), smallTargetCount: smallTargets.length};
}
"""


def shot(page, name):
    page.screenshot(path=OUT + "/" + name + ".png", full_page=True)


def run_case(pw, name, vw, vh, dpr, is_mobile, has_touch):
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={"width": vw, "height": vh},
        device_scale_factor=dpr,
        is_mobile=is_mobile,
        has_touch=has_touch,
    )
    page = ctx.new_page()
    console_errs, page_errs = [], []
    page.on("console", lambda m: console_errs.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page_errs.append(str(e)))
    try:
        page.goto(BASE, wait_until="load", timeout=25000)
        try:
            page.wait_for_function(
                "() => document.getElementById('live-canvas') && document.getElementById('live-canvas').children.length > 0",
                timeout=15000,
            )
        except Exception:
            pass
        page.wait_for_timeout(2500)
        data = {
            "name": name,
            "measure": page.evaluate(MEASURE_JS),
            "console_errors": console_errs[:10],
            "page_errors": page_errs[:5],
        }
        shot(page, "r4-" + name + "-initial")

        if is_mobile:
            try:
                page.tap("#mobile-drawer-btn")
                page.wait_for_timeout(600)
                data["drawer"] = page.evaluate("""() => {
                  const p = document.getElementById('expert-panel');
                  const r = p.getBoundingClientRect();
                  return {open: p.classList.contains('is-open'), l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width), top: Math.round(r.top), bottom: Math.round(r.bottom), vw: window.innerWidth, vh: window.innerHeight};
                }""")
                shot(page, "r4-" + name + "-drawer")
                page.tap("#expert-panel-backdrop")
                page.wait_for_timeout(400)
            except Exception as e:
                data["drawer"] = {"error": str(e)}
            try:
                page.tap("#bob-chat-tab")
                page.wait_for_timeout(600)
                data["bob_chat"] = page.evaluate("""() => {
                  const p = document.querySelector('.bob-chat');
                  const r = p.getBoundingClientRect();
                  return {open: p.classList.contains('is-open'), l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width), vw: window.innerWidth};
                }""")
                shot(page, "r4-" + name + "-chat")
                page.tap("#bob-chat-close")
                page.wait_for_timeout(400)
            except Exception as e:
                data["bob_chat"] = {"error": str(e)}
            try:
                page.tap("#ticker-inp")
                page.fill("#ticker-inp", "A")
                page.wait_for_timeout(400)
                data["autocomplete"] = page.evaluate("""() => {
                  const d = document.getElementById('ticker-autocomplete');
                  const r = d.getBoundingClientRect();
                  return {visible: d.classList.contains('is-visible'), l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width), vw: window.innerWidth};
                }""")
                shot(page, "r4-" + name + "-autocomplete")
                page.fill("#ticker-inp", "")
            except Exception as e:
                data["autocomplete"] = {"error": str(e)}
            try:
                page.tap("#alert-bell-btn")
                page.wait_for_timeout(500)
                data["alerts"] = page.evaluate("""() => {
                  const d = document.getElementById('alert-dropdown');
                  const r = d.getBoundingClientRect();
                  return {l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width), vw: window.innerWidth, visible: r.width > 0 && getComputedStyle(d).display !== 'none'};
                }""")
                shot(page, "r4-" + name + "-alerts")
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
            except Exception as e:
                data["alerts"] = {"error": str(e)}
            try:
                page.tap("#sdca-lab-btn")
                page.wait_for_timeout(500)
                data["sdca_lab"] = page.evaluate("""() => {
                  const d = document.getElementById('sdca-lab');
                  const r = d.getBoundingClientRect();
                  return {l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width), vw: window.innerWidth, open: r.width > 0 && getComputedStyle(d).display !== 'none'};
                }""")
                shot(page, "r4-" + name + "-sdca")
                page.tap("#sdca-lab-close")
                page.wait_for_timeout(300)
            except Exception as e:
                data["sdca_lab"] = {"error": str(e)}
    finally:
        browser.close()
    return data


with sync_playwright() as pw:
    results = [
        run_case(pw, "mobile-390", 390, 844, 2, True, True),
        run_case(pw, "tablet-768", 768, 1024, 2, True, True),
        run_case(pw, "desktop-1440", 1440, 900, 1, False, False),
    ]
print(json.dumps(results, indent=1))
