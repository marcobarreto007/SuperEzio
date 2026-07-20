import json,os,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ROOT = Path("C:/Users/marco/Desktop/SuperEzio")
BASE_URL = "http://127.0.0.1:8002"
OUT_DIR = ROOT / "output" / "playwright"
OUT_DIR.mkdir(parents=True, exist_ok=True)
STAMP = time.strftime("%Y%m%d-%H%M%S")
results = {"tasks": {}, "screenshots": [], "console_errors": [], "page_errors": []}
CE = []

def sp(page, name):
    path = OUT_DIR / f"etapa2_{name}_{STAMP}.png"
    page.screenshot(path=str(path), full_page=True)
    results["screenshots"].append(str(path))
    print(f"  ss: {path.name}")
    return str(path)

def t(name, ok, detail="", evidence=None):
    results["tasks"][name] = {"ok": ok, "detail": detail, "evidence": evidence}
    s = "PASS" if ok else "FAIL"
    print(f"  [{s}] {name}: {detail}")

# === MAIN TEST BLOCK ===
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, slow_mo=150)
    ctx = browser.new_context(viewport={'width': 1440, 'height': 980})
    page = ctx.new_page()
    page.on('console', lambda msg: CE.append(msg.text) if msg.type == 'error' else None)
    page.on('pageerror', lambda exc: results['page_errors'].append(str(exc)))
    try:
        print('=== LOAD PAGE ===')
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_selector('#chat', timeout=15000)
        page.wait_for_selector('#user-inp', timeout=10000)
        page.wait_for_timeout(3000)
        sp(page, '01_initial_load')

        print('T1: Pipeline dots')
        pd = page.query_selector('#pipeline-progress')
        if pd:
            html = pd.inner_html().strip()
            t('1_pipeline_progress_dots', len(html) > 0, f'len={len(html)}')
        else:
            t('1_pipeline_progress_dots', False, 'missing')

        print('T2: Trust badges')
        bars = page.query_selector_all('.trust-bar')
        lbls = page.query_selector_all('.trust-label')
        vis = [b for b in bars if b.is_visible()]
        t('2_trust_score_badge', len(vis) > 0, f'{len(vis)}v/{len(lbls)}l')

        print('T3: Mangala card')
        mc = page.query_selector('#expert-card-mangala')
        if mc:
            mv = page.query_selector('#mangala-verdict')
            mb = page.query_selector('#mangala-body')
            vt = mv.inner_text() if mv else ''
            bh = mb.inner_html() if mb else ''
            hd = ('Carregando' not in bh) and ('empty-state' not in bh.lower()) and (len(bh.strip()) > 20)
            t('3_mangala_has_data', hd or ('$' in vt), f'vt={vt} bl={len(bh.strip())} hd={hd}')
        else:
            t('3_mangala_has_data', False, 'missing')

        print('T4: Bob numbers')
        bt = page.query_selector('#bob-chat-tab')
        if bt and bt.is_visible():
            bt.click()
            page.wait_for_timeout(800)
        page.fill('#user-inp', 'Give me RSI, MACD, F51, SDCA numbers for AAPL')
        page.click('#send-btn')
        from playwright.sync_api import TimeoutError as PWTimeout
        wf = repr('() => { const m = document.querySelectorAll("#chat .msg-ceo"); if (!m.length) return false; const t = m[m.length-1].innerText||""; return t.length>50 && !t.includes("Erro:"); }')
        try:
            page.wait_for_function(eval(wf), timeout=35000)
        except PWTimeout:
            t('4_bob_pipeline_numbers', False, 'timeout')
        else:
            ef = repr('() => { const m = document.querySelectorAll("#chat .msg-ceo"); const l = m[m.length-1]; const t = l ? l.innerText : ""; return {len:t.length, rsi:t.includes("RSI"), macd:t.includes("MACD"), f51:t.includes("F51"), sdca:t.includes("SDCA"), nums:/\d/.test(t)}; }')
            bob = page.evaluate(eval(ef))
            hn = bob.get('rsi') or bob.get('macd') or bob.get('f51') or bob.get('sdca')
            t('4_bob_pipeline_numbers', hn, f"l={bob['len']} R={bob['rsi']} M={bob['macd']} F={bob['f51']} S={bob['sdca']} n={bob['nums']}")
        sp(page, '02_after_bob')

        print('T5: Trade button')
        tb = page.query_selector_all('.trade-btn, .btn--trade, button:has-text("Trade"), button:has-text("BUY")')
        t('5_trade_button', len(tb) > 0, f'n={len(tb)}')

        print('T6: Portfolio mirror')
        ol = page.query_selector('#orders-list')
        th = page.query_selector('#trade-history-list')
        if ol and th:
            ot = ol.inner_text()
            ht = th.inner_text()
            nl = 'Loading' not in ot and 'Loading' not in ht
            t('6_portfolio_mirror', nl, f'oe={len(ot.strip())<=10} he={len(ht.strip())<=10}')
        else:
            t('6_portfolio_mirror', False, 'missing')

        print('T7: Alerts')
        ab = page.query_selector('#alert-bell-btn')
        if ab and ab.is_visible():
            ab.click()
            page.wait_for_timeout(600)
            dd = page.query_selector('#alert-dropdown')
            dv = dd and dd.is_visible()
            t('7_alerts', True, f'dd_vis={dv}')
        else:
            t('7_alerts', False, 'bell missing')
        sp(page, '03_alerts')

        print('T8: Theme toggle')
        thm = page.query_selector('#theme-toggle-btn')
        if thm and thm.is_visible():
            thm.click()
            page.wait_for_timeout(500)
            hc = page.evaluate('() => document.documentElement.className')
            thm.click()
            t('8_theme_toggle', True, f'cls={hc}')
        else:
            t('8_theme_toggle', False, 'missing')

        print('T9: Ticker autocomplete')
        ti = page.query_selector('#ticker-inp')
        if ti:
            ti.click()
            ti.fill('AAPL')
            page.wait_for_timeout(1500)
            ac = page.query_selector('#ticker-autocomplete')
            acv = ac and ac.is_visible()
            ach = ac.inner_html() if ac else ''
            t('9_ticker_autocomplete', True, f'vis={acv} sl={len(ach.strip())}')
        else:
            t('9_ticker_autocomplete', False, 'missing')

        print('T10: Mobile drawer')
        db = page.query_selector('#mobile-drawer-btn')
        if db and db.is_visible():
            ep = page.query_selector('#expert-panel')
            db.click()
            page.wait_for_timeout(500)
            pc = ep.get_attribute('class') if ep else ''
            db.click()
            t('10_mobile_drawer', True, f'pc={pc}')
        else:
            t('10_mobile_drawer', False, 'missing')

        print('T11: Expert cards')
        ids = ['expert-card-f51','expert-card-sdca','expert-card-neural','expert-card-trinity','expert-card-guardrails','expert-card-mangala']
        found = 0
        for cid in ids:
            c = page.query_selector(f'#{cid}')
            if c and c.is_visible():
                found += 1
                ne = c.query_selector('.expert-card__name')
                ve = c.query_selector(f"#{cid.replace('expert-card-', '')}-verdict")
                print(f'    {cid}: {ne.inner_text() if ne else "?"} / {ve.inner_text() if ve else "?"}')
        t('11_cards_rendered', found == len(ids), f'{found}/{len(ids)}')

        print('T12: Console errors')
        t('12_console_errors', len(CE)==0, f'{len(CE)} errs: {CE[:3] if CE else "none"}', evidence=CE)
        sp(page, '99_final')

    except Exception as e:
        print(f'ERROR: {e}')
        import traceback; traceback.print_exc()
        sp(page, 'error')
        t('unexpected_error', False, str(e))
    finally:
        results['console_errors'] = CE
        browser.close()


print()
for n,d in sorted(results['tasks'].items()):
    print(f"  [{'PASS' if d['ok'] else 'FAIL'}] {n}: {d['detail']}")
js = OUT_DIR / f'etapa2_results_{STAMP}.json'
with open(js, 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f'Saved: {js}')