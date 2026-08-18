"""Testes do isolamento anti-crash do AKShareProvider (INV-R29).

O caminho ``ak.get_us_stock_name()`` usa py_mini_racer (V8), que aborta o
processo Python inteiro com 0x80000003 nesta máquina. A chamada agora roda
em subprocesso — estes testes cobrem o contrato do isolamento sem rede e
sem instanciar o V8.
"""

import subprocess

import pandas as pd

from data.akshare_provider import (
    AKShareProvider,
    _parse_names_csv,
    _us_stock_names_via_subprocess,
)


def _fake_proc(returncode: int, stdout: bytes = b"", stderr: bytes = b""):
    class _Fake:
        pass

    p = _Fake()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def test_via_subprocess_success(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _fake_proc(0, stdout="code,name\n105.AAPL,Apple Inc\n".encode("utf-8")),
    )
    payload = _us_stock_names_via_subprocess()
    assert "names_csv" in payload
    assert "105.AAPL" in payload["names_csv"]


def test_via_subprocess_native_crash_is_error(monkeypatch):
    """rc != 0 (ex.: crash fatal do V8) vira erro capturável — processo pai vive."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _fake_proc(3, stderr=b"Windows fatal exception: code 0x80000003"),
    )
    payload = _us_stock_names_via_subprocess()
    assert "error" in payload
    assert "rc=3" in payload["error"]


def test_via_subprocess_timeout_is_error(monkeypatch):
    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=25)

    monkeypatch.setattr(subprocess, "run", _boom)
    payload = _us_stock_names_via_subprocess()
    assert payload == {"error": "akshare_js_timeout"}


def test_parse_names_csv_roundtrip():
    df = _parse_names_csv("code,name\n105.AAPL,Apple Inc\n")
    assert df is not None
    assert list(df.columns) == ["code", "name"]
    assert df.iloc[0]["name"] == "Apple Inc"


def test_parse_names_csv_empty_returns_none():
    assert _parse_names_csv("") is None


def test_get_profile_never_touches_real_akshare(monkeypatch):
    """get_profile deve passar pelo subprocesso — nunca chamar ak direto."""
    monkeypatch.setattr(
        "data.akshare_provider._us_stock_names_via_subprocess",
        lambda **k: {"error": "akshare_js_subprocess_rc=3 fatal"},
    )

    def _fail_if_spawned(*a, **k):
        raise AssertionError("get_profile tentou spawnar subprocesso de verdade")

    monkeypatch.setattr(subprocess, "run", _fail_if_spawned)

    result = AKShareProvider().get_profile("AAPL")
    assert "error" in result
    assert "rc=3" in result["error"]


def test_get_profile_parses_isolated_csv(monkeypatch):
    monkeypatch.setattr(
        "data.akshare_provider._us_stock_names_via_subprocess",
        lambda **k: {"names_csv": "code,name,cname\n105.AAPL,Apple Inc,苹果"},
    )
    result = AKShareProvider().get_profile("AAPL")
    assert result["name"] == "Apple Inc"
    assert result["chinese_name"] == "苹果"
    assert result["provider"] == "akshare"


def test_parse_names_csv_dataframe_types():
    df = _parse_names_csv("code,name\n105.AAPL,Apple Inc\n")
    assert isinstance(df, pd.DataFrame)
