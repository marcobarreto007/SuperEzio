from __future__ import annotations

import importlib.util
import json
import socket
from argparse import Namespace
from pathlib import Path


def _load_probe_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "broker_readiness_probe.py"
    spec = importlib.util.spec_from_file_location("broker_readiness_probe", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _closed_local_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_env_state_does_not_expose_secret_values(monkeypatch):
    module = _load_probe_module()
    monkeypatch.setenv("ALPACA_API_KEY", "secret-key-value")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-secret-value")

    payload = module._env_state(["ALPACA_API_KEY", "ALPACA_SECRET_KEY"])

    serialized = json.dumps(payload)
    assert "secret-key-value" not in serialized
    assert "secret-secret-value" not in serialized
    assert payload["ALPACA_API_KEY"]["present"] is True
    assert payload["ALPACA_SECRET_KEY"]["present"] is True


def test_ibkr_probe_closed_port_does_not_connect():
    module = _load_probe_module()
    result = module.probe_ibkr(port=_closed_local_port(), timeout=0.1)

    assert result["provider"] == "ibkr"
    assert result["mode"] == "read_only"
    assert result["connected"] is False
    assert result["port_open"] is False


def test_alpaca_probe_without_credentials_skips_network(monkeypatch):
    module = _load_probe_module()
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    result = module.probe_alpaca_paper(timeout=0.1)

    assert result["provider"] == "alpaca"
    assert result["mode"] == "paper_read_only"
    assert result["connected"] is False
    assert result["credentials_present"] is False
    assert result["error"].startswith("credentials_missing")


def test_run_probe_reports_no_orders_safe_mode():
    module = _load_probe_module()
    args = Namespace(
        provider="ibkr",
        ibkr_host="127.0.0.1",
        ibkr_port=_closed_local_port(),
        ibkr_client_id=91,
        timeout=0.1,
    )

    payload = module.run_probe(args)

    assert payload["safe_mode"] == "read_only_no_orders"
    assert payload["connected_count"] == 0
    assert payload["providers"][0]["connected"] is False
