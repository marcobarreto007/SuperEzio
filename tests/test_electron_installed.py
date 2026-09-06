"""Opt-in installed Windows app acceptance; no real API credentials are used."""

import os
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


@pytest.mark.skipif(
    not os.getenv("SUPEREZIO_ELECTRON_EXE"), reason="requires installed Electron app"
)
def test_customer_onboarding_encrypts_key_and_opens_packaged_workspace():
    root = Path(__file__).resolve().parents[1]
    profile = root / "runtime" / ("desktop-onboarding-" + uuid.uuid4().hex[:8])
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    env = {
        **os.environ,
        "SUPEREZIO_DESKTOP_TEST_DATA": str(profile),
        "SUPEREZIO_ANS_SCAN": "0",
        "SUPEREZIO_MANGALA_SCAN": "0",
        "SUPEREZIO_CORPO_HEARTBEAT": "0",
    }
    process = subprocess.Popen(
        [os.environ["SUPEREZIO_ELECTRON_EXE"], f"--remote-debugging-port={port}"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    browser = None
    try:
        with sync_playwright() as pw:
            for _ in range(30):
                try:
                    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                    break
                except PlaywrightError:
                    time.sleep(0.5)
            assert browser is not None, "Installed application did not expose its test browser"
            context = browser.contexts[0]
            page = context.pages[0]
            page.locator("#setup").wait_for()
            assert page.title() == "Configurar SuperEzio"
            page.screenshot(path=str(root / "output" / "electron-customer-setup.png"))
            key = "synthetic-desktop-acceptance-key"
            page.locator('[name="SUPEREZIO_DEEPSEEK_API_KEY"]').fill(key)
            page.locator("#start").click()
            workspace = None
            for _ in range(120):
                workspace = next(
                    (p for p in context.pages if p.url.startswith("http://127.0.0.1:")), None
                )
                if workspace:
                    break
                time.sleep(0.5)
            assert workspace is not None, "API settings did not launch the workspace"
            workspace.locator("#chat").wait_for()
            assert workspace.evaluate("typeof require") == "undefined"
            encrypted = (profile / "api-settings.enc").read_bytes()
            assert key.encode() not in encrypted
            assert (profile / "workspace" / "runtime" / "auth.db").exists()
            workspace.screenshot(path=str(root / "output" / "electron-installed-workspace.png"))
            workspace.evaluate("window.close()")
            process.wait(timeout=15)
            assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
