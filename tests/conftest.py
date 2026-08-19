"""Fixtures compartilhados para testes do SuperEzio."""

import os
import pytest
import sys
from pathlib import Path

# Garante que src/ e tests/ estão no path para importar módulos e helpers
_PROJECT_ROOT = str(Path(__file__).parent.parent)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, _PROJECT_ROOT)  # scripts/ acessível via "from scripts import x"

# Desabilita OpenTelemetry globalmente nos testes
os.environ["DISABLE_OTEL"] = "1"
os.environ["SUPEREZIO_EDGE_AUTH"] = "false"
os.environ["SUPEREZIO_EDGE_SECRET"] = "pytest-secret-key-12345"
_PYTEST_OUTPUT = Path(_PROJECT_ROOT) / "output" / "pytest" / f"process-{os.getpid()}"
os.environ["SUPEREZIO_TRACE_DIR"] = str(_PYTEST_OUTPUT / "traces")
os.environ["SUPEREZIO_DECISION_TRACE_DB"] = str(_PYTEST_OUTPUT / "decision-traces.sqlite3")
os.environ["SUPEREZIO_SENTIMENT_DB"] = str(_PYTEST_OUTPUT / "sentiment.sqlite3")
os.environ["SUPEREZIO_DATA_DIR"] = str(_PYTEST_OUTPUT / "investor-data")
os.environ["SUPEREZIO_PAPER_JOURNAL_PATH"] = str(_PYTEST_OUTPUT / "paper-journal.jsonl")
os.environ["SUPEREZIO_BOB_PAIN_LOG"] = str(_PYTEST_OUTPUT / "bob-pain-log.jsonl")

from helpers import (  # noqa: E402
    CANNED_TECHNICALS,
    CANNED_DATA_COLLECTED,
    CANNED_EXPERT_RESPONSE,
    FakeGateway,
)


@pytest.fixture
def canned_technicals():
    return dict(CANNED_TECHNICALS)


@pytest.fixture
def canned_data_collected():
    return dict(CANNED_DATA_COLLECTED)


@pytest.fixture
def canned_expert_response():
    return dict(CANNED_EXPERT_RESPONSE)


@pytest.fixture
def fake_gateway():
    return FakeGateway()


@pytest.fixture
def skip_gateway(monkeypatch):
    """Opt-in fixture: pipeline sem gateway real para testes unitários."""
    monkeypatch.setenv("UNIVERSAL_SKIP_GATEWAY", "1")


@pytest.fixture(autouse=True)
def isolated_trading_state(monkeypatch, tmp_path):
    """Never let pytest open operator trading state or dead-letter storage."""

    monkeypatch.setenv("SUPEREZIO_TRADING_STATE_DB", str(tmp_path / "trading-state.sqlite3"))
    monkeypatch.setenv("SUPEREZIO_DEDUP_DIR", str(tmp_path / "dedup"))
    monkeypatch.setenv("SUPEREZIO_DEAD_LETTER_DIR", str(tmp_path / "dead-letter"))


def requires_deepseek_key():
    """Skip decorator para testes que precisam de API key."""
    key = os.getenv("SUPEREZIO_DEEPSEEK_API_KEY") or os.getenv("SUPEREZIO_PRIMARY_API_KEY")
    return pytest.mark.skipif(not key, reason="DeepSeek API key not set")


def requires_network():
    """Skip decorator para testes que precisam de internet."""
    import socket

    def _check():
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return False  # não skipa
        except OSError:
            return True  # skipa

    return pytest.mark.skipif(_check(), reason="No network connection")


# ── Browser Smoke (Playwright obrigatório — política F51) ──────────────────


def _browser_smoke_server_up(base_url: str) -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=3)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def browser_smoke():
    """Smoke test de UI com Playwright. Roda uma vez por sessão pytest.

    Política F51: Playwright é obrigatório em conjunto com qualquer teste.
    Se o servidor não estiver reachable, o smoke é skipped com warning.
    Chat real é opcional (env SUPEREZIO_SMOKE_CHAT=1).

    Modo visível: SUPEREZIO_SMOKE_HEADED=1 abre o browser para assistir
    em tempo real. SUPEREZIO_SMOKE_SLOW_MO=<ms> controla a velocidade
    (default 300ms por ação quando headed).
    """
    base_url = os.environ.get("SUPEREZIO_BROWSER_SMOKE_URL", "http://127.0.0.1:8002")
    if not _browser_smoke_server_up(base_url):
        pytest.skip(f"Browser smoke skipped: server not reachable at {base_url}")

    headed = os.environ.get("SUPEREZIO_SMOKE_HEADED") in ("1", "true", "yes")
    skip_chat = os.environ.get("SUPEREZIO_SMOKE_CHAT") not in ("1", "true", "yes")
    slow_mo_raw = os.environ.get("SUPEREZIO_SMOKE_SLOW_MO")
    slow_mo = int(slow_mo_raw) if slow_mo_raw and slow_mo_raw.isdigit() else (300 if headed else 0)

    from scripts.browser_smoke import run_smoke

    result = run_smoke(
        base_url=base_url,
        headed=headed,
        skip_chat=skip_chat,
        timeout_ms=120_000 if headed else 60_000,
        slow_mo=slow_mo,
    )
    yield result
