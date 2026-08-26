import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    p = ctx.new_page()
    p.goto("http://127.0.0.1:8002", wait_until="load", timeout=25000)
    p.wait_for_timeout(3000)
    out = p.evaluate("""() => {
      function lum(hex) {
        const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(hex);
        if (!m) return null;
        const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        const [r, g, bl] = [f(+m[1]), f(+m[2]), f(+m[3])];
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
      }
      function bgOf(el) {
        let cur = el;
        while (cur && cur !== document.documentElement) {
          const bg = getComputedStyle(cur).backgroundColor;
          if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') return bg;
          cur = cur.parentElement;
        }
        return 'rgb(17, 24, 32)';
      }
      function ratio(fg, bg) {
        const l1 = lum(fg), l2 = lum(bg);
        if (l1 == null || l2 == null) return null;
        const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
        return ((hi + 0.05) / (lo + 0.05)).toFixed(2);
      }
      const sels = ['.price-cell__label', '.price-cell__value', '.trust-label', '.expert-card__name', '.expert-card__verdict',
        '.topbar__metric-value', '#cockpit-connection', '.mangala-progress__label', '.mangala-growth__value',
        '#bob-welcome-body', '.bob-chat__tab-label', '#live-price', '.market-header__label', '.tf-btn'];
      const res = {};
      sels.forEach(sel => {
        const el = document.querySelector(sel);
        if (!el) return;
        const cs = getComputedStyle(el);
        res[sel] = {color: cs.color, bg: bgOf(el), ratio: ratio(cs.color, bgOf(el))};
      });
      const noLabel = [];
      document.querySelectorAll('input, textarea, select').forEach(el => {
        const hasAria = el.getAttribute('aria-label');
        const hasLab = el.id && document.querySelector('label[for="' + el.id + '"]');
        const hasPh = el.getAttribute('placeholder');
        if (!hasAria && !hasLab && !hasPh) noLabel.push(el.id || el.tagName + '.' + (el.className || ''));
      });
      return {contrast: res, inputsWithoutAnyLabel: noLabel};
    }""")
    print(json.dumps(out, indent=1))
    b.close()
