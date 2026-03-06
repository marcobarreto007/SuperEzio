"""Fixtures compartilhados para testes do SuperEzio."""

import os
import pytest
import sys
from pathlib import Path

# Garante que src/ e tests/ estão no path para importar módulos e helpers
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

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
    key = os.getenv("SUPEREZIO_DEEPSEEK_API_KEY") or os.getenv(
        "SUPEREZIO_PRIMARY_API_KEY"
    )
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
