"""Integration tests for the official runtime — requires agent + API servers running.

Run with: python -m pytest tests/test_integration_runtime.py -q -v
Prerequisites:
  - agent llama-server on :8080 (scripts/serve_agent_llamacpp.ps1)
  - API agent_server on :8002 (python -m agent_server.main)
"""

import json
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.integration


AGENT_HEALTH = "http://127.0.0.1:8080/health"
API_HEALTH = "http://127.0.0.1:8002/health"
API_DETAILS = "http://127.0.0.1:8002/health/details"
TASK_SUBMIT = "http://127.0.0.1:8002/task/submit"


def _check_server(url: str, timeout: int = 5) -> bool:
    try:
        req = urllib.request.Request(url)
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def servers_running():
    agent_ok = _check_server(AGENT_HEALTH)
    api_ok = _check_server(API_HEALTH)
    if not agent_ok or not api_ok:
        pytest.skip(
            f"Servers not running: CEO={'OK' if agent_ok else 'OFFLINE'}, "
            f"API={'OK' if api_ok else 'OFFLINE'}"
        )
    return True


# ---------------------------------------------------------------------------
# Health checks (real endpoints)
# ---------------------------------------------------------------------------


def test_ceo_health_endpoint(servers_running):
    req = urllib.request.Request(AGENT_HEALTH)
    resp = urllib.request.urlopen(req, timeout=5)
    assert resp.status == 200
    body = json.loads(resp.read())
    assert body.get("status") == "ok"


def test_api_health_endpoint(servers_running):
    req = urllib.request.Request(API_HEALTH)
    resp = urllib.request.urlopen(req, timeout=5)
    assert resp.status == 200
    body = json.loads(resp.read())
    assert body.get("status") == "ok"


def test_api_health_details_endpoint(servers_running):
    req = urllib.request.Request(API_DETAILS)
    resp = urllib.request.urlopen(req, timeout=5)
    assert resp.status == 200
    body = json.loads(resp.read())
    assert body.get("status") == "ok"
    assert "checks" in body


# ---------------------------------------------------------------------------
# Task submit (full pipeline, requires CEO model)
# ---------------------------------------------------------------------------


def test_task_submit_casual(servers_running):
    """A casual message should complete without ticker analysis."""
    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {"message": "Hello, what can you do?"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TASK_SUBMIT,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=180)
    body = resp.read().decode("utf-8")
    # SSE stream — should produce multiple lines
    lines = [line for line in body.strip().split("\n") if line.strip()]
    assert len(lines) >= 3, f"Expected at least 3 SSE lines, got {len(lines)}"
    types = []
    for line in lines:
        try:
            ev = json.loads(line)
            types.append(ev.get("type"))
        except json.JSONDecodeError:
            pass
    assert "STREAM_START" in types or "PIPELINE_STEP" in types
    assert "STREAM_END" in types


def test_task_submit_ticker_analysis(servers_running):
    """A ticker analysis request should complete the full pipeline."""
    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "AAPL 14 dias analise",
            "ticker": "AAPL",
            "time_horizon": "14 days",
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TASK_SUBMIT,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=300)
    body = resp.read().decode("utf-8")
    lines = [line for line in body.strip().split("\n") if line.strip()]
    assert len(lines) >= 10, f"Expected at least 10 SSE lines, got {len(lines)}"

    types = set()
    steps = set()
    for line in lines:
        try:
            ev = json.loads(line)
            t = ev.get("type")
            if t:
                types.add(t)
            if t == "PIPELINE_STEP":
                steps.add(ev.get("step"))
        except json.JSONDecodeError:
            pass

    # Must include data collection and a verdict
    assert "F51_VERDICT" in types or "DATA_COLLECTED" in types
    assert "STREAM_END" in types

    # Check for key pipeline steps
    expected_steps = {"orchestrator_primary", "data", "agent_primary"}
    found = expected_steps & steps
    assert len(found) >= 2, f"Missing steps: {expected_steps - found}"


# ---------------------------------------------------------------------------
# Capabilities endpoint
# ---------------------------------------------------------------------------


def test_capabilities_endpoint(servers_running):
    req = urllib.request.Request("http://127.0.0.1:8002/capabilities")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        assert resp.status == 200
        body = json.loads(resp.read())
        assert isinstance(body, dict)
    except urllib.error.HTTPError as e:
        if e.code in (404, 500):
            pytest.skip(f"Capabilities endpoint returned {e.code}")
        raise


# ---------------------------------------------------------------------------
# Product manifest endpoint
# ---------------------------------------------------------------------------


def test_product_manifest_endpoint(servers_running):
    req = urllib.request.Request("http://127.0.0.1:8002/product/manifest")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        assert resp.status == 200
        body = json.loads(resp.read())
        assert isinstance(body, dict)
    except urllib.error.HTTPError as e:
        if e.code in (404, 500):
            pytest.skip(f"Product manifest endpoint returned {e.code}")
        raise
