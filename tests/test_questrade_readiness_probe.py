from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "questrade_readiness_probe.py"
    spec = importlib.util.spec_from_file_location("questrade_readiness_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_without_token_fails_closed(monkeypatch):
    module = _load_module()

    class Settings:
        questrade_refresh_token = None
        questrade_practice = True

    monkeypatch.setattr(module, "get_settings", lambda: Settings())

    payload = module.run_probe()

    assert payload["connected"] is False
    assert payload["can_submit_orders"] is False
    assert payload["error"].startswith("credentials_missing")
