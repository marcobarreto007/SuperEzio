"""Browser regressions for truthful client portfolio and risk status."""

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


@pytest.mark.parametrize(
    ("portfolio", "expected", "connected"),
    [
        ({"connection": "disconnected"}, "Indisponível", False),
        ({"connected": True, "equity": 0}, "0.00", True),
        ({"connection": "connected", "equity": "1234.56"}, "1234.56", True),
        ({"connection": "offline", "equity": "invalid"}, "Indisponível", False),
    ],
)
def test_portfolio_does_not_invent_balance_or_connection(portfolio, expected, connected):
    script = Path(__file__).resolve().parents[1] / "frontend/js/bob-panel.js"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content('<div id="expert-panel-cards"></div>')
            page.evaluate("pf => window.SZ = {state: {bobPanel: {portfolio: pf}}}", portfolio)
            page.add_script_tag(path=str(script))
            page.evaluate("window.SZ.bobPanel.render()")
            text = page.locator("#bob-runtime").text_content()
            assert expected in text
            assert ("PAPER CONNECTED" in text) is connected
            assert "100000" not in text
            assert page.locator(".bob-guardrail-row.is-good").count() == 0
            assert "Sem evidência de validação" in text
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("ibkr", "label"),
    [
        ({"connection": "disconnected"}, "IBKR OFFLINE"),
        ({"connection": "connected", "paper_port": True}, "IBKR READ"),
        (
            {"connection": "connected", "paper_port": True, "can_submit_orders": True},
            "IBKR PAPER",
        ),
        ({"can_submit_orders": True, "paper_port": False}, "IBKR BLOCKED"),
    ],
)
def test_broker_chip_requires_explicit_order_permission(ibkr, label):
    script = Path(__file__).resolve().parents[1] / "frontend/js/init.js"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(
                '<button id="broker-status-btn"><span id="broker-status-label"></span></button>'
            )
            page.evaluate("""() => {
                window.SZ = {};
                Object.defineProperty(document, 'readyState', {get: () => 'loading'});
            }""")
            page.add_script_tag(path=str(script))
            page.evaluate("ibkr => SZ.updateBrokerStatus({mission: {broker: {ibkr}}})", ibkr)
            assert page.locator("#broker-status-label").text_content() == label
        finally:
            browser.close()
