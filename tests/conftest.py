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
    """
    base_url = os.environ.get("SUPEREZIO_BROWSER_SMOKE_URL", "http://127.0.0.1:8002")
    if not _browser_smoke_server_up(base_url):
        pytest.skip(f"Browser smoke skipped: server not reachable at {base_url}")

    skip_chat = os.environ.get("SUPEREZIO_SMOKE_CHAT") not in ("1", "true", "yes")
    from scripts.browser_smoke import run_smoke

    result = run_smoke(
        base_url=base_url,
        headed=False,
        skip_chat=skip_chat,
        timeout_ms=60_000,
    )
    yield result
    # session-scoped: nenhuma cleanup necessária além do browser já fechado
