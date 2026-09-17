from pathlib import Path

from playwright.sync_api import sync_playwright


def test_research_card_labels_history_and_keeps_canadian_ticker():
    script = Path(__file__).resolve().parents[1] / "frontend/js/cockpit.js"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chrome")
        try:
            page = browser.new_page()
            page.set_content(
                '<div id="mangala-body"></div>'
                '<div id="mangala-trust-bar" class="is-good"><span></span></div>'
            )
            page.evaluate("""() => { window.SZ = {
                selectTicker: t => { window.selectedTicker = t; },
                __mangalaOpportunities: {
                    count: 1, opportunities: [{ticker: 'VFV.TO',
                        historical_close: 188.58, price: null,
                        price_as_of: '2026-09-11', friction: 'estimativa 0.1234%',
                        signal: 'PESQUISA', meta_labeling_p: null}]
                }
            }; }""")
            page.add_script_tag(path=str(script))
            page.evaluate("SZ.cockpit.renderMangalaCard({status: 'ok'})")
            text = page.locator("#mangala-body").inner_text()
            assert "Fech. ajustado $188.58 CAD" in text
            assert "2026-09-11 · Yahoo Finance · histórico" in text
            assert "estimativa 0.1234%" in text
            assert "TOP OPORTUNIDADES" not in text
            assert "P:" not in page.locator(".mangala-scan-row").inner_text()
            assert page.locator("#mangala-trust-bar.is-good").count() == 0
            page.locator(".mangala-scan-row").click()
            assert page.evaluate("window.selectedTicker") == "VFV.TO"
            page.evaluate("""() => {
                SZ.__mangalaOpportunities = {opportunities: [], message: 'Referências vencidas'};
                SZ.cockpit.renderMangalaCard({status: 'ok'});
            }""")
            assert "Referências vencidas" in page.locator("#mangala-body").inner_text()
            assert page.locator(".mangala-scan-row").count() == 0
        finally:
            browser.close()
