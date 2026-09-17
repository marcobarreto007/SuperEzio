"""The browser gate must prove a completed answer, not pipeline status cards."""

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from scripts.browser_smoke import _submit_chat


@pytest.mark.parametrize("scenario", ["cards_only", "unfinished", "finished"])
def test_smoke_requires_completed_answer_text(scenario):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel="chrome")
        try:
            page = browser.new_page()
            page.set_content("""
                <div id="chat"><div class="msg-ceo" data-done="1">
                  <div class="msg-bubble">An old completed answer must never count.</div>
                </div></div>
                <input id="user-inp"><button id="send-btn">Send</button>
            """)
            page.evaluate(
                """scenario => {
                document.querySelector('#send-btn').onclick = () => {
                    const message = document.createElement('div');
                    message.className = 'msg-ceo';
                    message.dataset.done = scenario === 'unfinished' ? '0' : '1';
                    message.innerHTML = '<div class="msg-bubble">'
                      + '<div class="card">SDCA Firewall: extensive pipeline status details.</div>'
                      + '<div class="feedback-bar">Helpful feedback controls</div></div>'
                      + '<div class="msg-meta">Bob Copilot metadata</div>';
                    if (scenario !== 'cards_only') {
                        message.querySelector('.msg-bubble').prepend(
                          document.createTextNode('Esta resposta final explica os riscos com clareza.'));
                    }
                    document.querySelector('#chat').append(message);
                };
            }""",
                scenario,
            )
            if scenario == "finished":
                result = _submit_chat(page, "Teste", 500)
                assert result["finished"] is True
                assert result["newMessageCount"] == 1
                assert result["firstChars"] == (
                    "Esta resposta final explica os riscos com clareza."
                )
            else:
                with pytest.raises(PlaywrightTimeoutError):
                    _submit_chat(page, "Teste", 500)
        finally:
            browser.close()
