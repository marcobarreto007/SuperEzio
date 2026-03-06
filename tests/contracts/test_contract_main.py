"""Contract tests: agent_server.main — FastAPI app creation & startup helpers."""

import os

import pytest


@pytest.fixture(autouse=True)
def _skip_gateway():
    """Prevent edge gateway from trying to connect during tests."""
    os.environ["UNIVERSAL_SKIP_GATEWAY"] = "1"
    yield


def test_fastapi_app_creation():
    from agent_server.main import app

    assert app is not None
    assert app.title is not None
    assert "SuperEzio" in app.title or "A2A" in app.title


def test_fastapi_app_routes():
    from agent_server.main import app

    # Collect all route paths recursively
    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        elif hasattr(route, "routes"):
            for sub_route in route.routes:
                if hasattr(sub_route, "path"):
                    paths.add(sub_route.path)

    assert "/" in paths or any("/api" in p for p in paths)
    assert any("submit" in p for p in paths)


def test_env_bool():
    from agent_server.main import _env_bool

    assert _env_bool("NONEXISTENT_VAR_XYZ_123", default=True) is True
    assert _env_bool("NONEXISTENT_VAR_XYZ_123", default=False) is False


def test_build_edge_gateway_skip():
    from agent_server.main import _build_edge_gateway

    gw = _build_edge_gateway()
    assert gw is not None


def test_validate_edge_runtime_config():
    from agent_server.main import _validate_edge_runtime_config

    # Should not raise — UNIVERSAL_SKIP_GATEWAY=1 skips validation
    _validate_edge_runtime_config()


def test_app_has_middleware():
    from agent_server.main import app

    # FastAPI middleware is stored in user_middleware list
    assert len(app.user_middleware) >= 1


def test_run_function_exists():
    from agent_server.main import run

    assert callable(run)
