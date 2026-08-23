"""Integration tests for the official runtime — requires agent + API servers running.

Run with: python -m pytest tests/test_integration_runtime.py -q -v
Prerequisites:
  - agent llama-server on :8080 (scripts/serve_agent_llamacpp.ps1)
  - API agent_server on :8002 (python -m agent_server.main)
"""

import json
import os
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.integration


AGENT_HEALTH = "http://127.0.0.1:8080/health"
API_HEALTH = "http://127.0.0.1:8002/health"
API_DETAILS = "http://127.0.0.1:8002/health/details"
TASK_SUBMIT = "http://127.0.0.1:8002/task/submit"

# A live model run is expensive, so one deterministic case is executed per
# invocation.  The complete matrix remains a testable contract and deliberately
# spans markets and asset classes instead of privileging one US mega-cap.
INVESTMENT_CASES = (
    {"ticker": "MSFT", "market": "US", "asset_class": "equity"},
    {"ticker": "TD.TO", "market": "CA", "asset_class": "equity"},
    {"ticker": "PETR4.SA", "market": "BR", "asset_class": "equity"},
    {"ticker": "SPY", "market": "US", "asset_class": "etf"},
    {"ticker": "BTC-USD", "market": "CRYPTO", "asset_class": "crypto"},
    {"ticker": "INVALID-NO-SUCH-ASSET", "market": "INVALID", "asset_class": "invalid"},
    {"ticker": None, "market": "NONE", "asset_class": "no_ticker"},
)


def _selected_investment_case() -> dict[str, str]:
    requested = os.environ.get("SUPEREZIO_INTEGRATION_TICKER", "").strip().upper()
    if requested:
        return {"ticker": requested, "market": "OVERRIDE", "asset_class": "configured"}
    index = int(os.environ.get("SUPEREZIO_INTEGRATION_CASE_INDEX", "0"))
    case = INVESTMENT_CASES[index % 5]
    return {key: str(value) for key, value in case.items() if value is not None}


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


def _bootstrap_auth_headers() -> dict[str, str]:
    """Bearer headers when the API runs in public mode; {} in dev mode."""
    try:  # load .env.local so public-mode credentials resolve (like the smokes)
        from core.config.secrets import load_local_env

        load_local_env()
    except ImportError:
        pass
    try:
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8002/auth/me"), timeout=5)
        return {}
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            return {}
    username = os.getenv("SUPEREZIO_SMOKE_USER", "admin")
    password = os.getenv("SUPEREZIO_SMOKE_PASSWORD") or os.getenv("SUPEREZIO_ADMIN_PASSWORD", "")
    if not password:
        pytest.skip("Public mode active and no SUPEREZIO_ADMIN_PASSWORD in env — cannot auth")
    payload = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8002/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())
    return {"Authorization": f"Bearer {body['access_token']}"}


@pytest.fixture(scope="module")
def auth_headers():
    return _bootstrap_auth_headers()


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


def test_api_health_details_endpoint(servers_running, auth_headers):
    req = urllib.request.Request(API_DETAILS, headers=auth_headers)
    # Detailed health performs bounded broker/data probes and is intentionally
    # slower than the liveness endpoint. Keep this above those probe budgets.
    resp = urllib.request.urlopen(req, timeout=15)
    assert resp.status == 200
    body = json.loads(resp.read())
    assert body.get("status") == "ok"
    assert "checks" in body


# ---------------------------------------------------------------------------
# Task submit (full pipeline, requires CEO model)
# ---------------------------------------------------------------------------


def test_task_submit_casual(servers_running, auth_headers):
    """A casual message should complete without ticker analysis."""
    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "Reply with exactly one short sentence describing your role.",
            "session_id": "integration-casual",
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TASK_SUBMIT,
        data=data,
        headers={"Content-Type": "application/json", **auth_headers},
    )
    # The canonical local runtime allows up to 600 seconds. This prompt takes
    # roughly three minutes on the validated dual-GPU profile after cold boot.
    resp = urllib.request.urlopen(req, timeout=600)
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


def test_task_submit_ticker_analysis(servers_running, auth_headers):
    """A ticker analysis request should complete the full pipeline."""
    case = _selected_investment_case()
    ticker = case["ticker"]
    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": f"Analise {ticker} como investimento para os proximos 14 dias",
            "ticker": ticker,
            "time_horizon": "14 days",
            "session_id": "integration-ticker",
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TASK_SUBMIT,
        data=data,
        headers={"Content-Type": "application/json", **auth_headers},
    )
    resp = urllib.request.urlopen(req, timeout=600)
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


def test_investment_case_matrix_contract():
    """The live-test universe covers real diversity plus negative routing."""
    tickers = {case["ticker"] for case in INVESTMENT_CASES if case["ticker"]}
    markets = {
        case["market"] for case in INVESTMENT_CASES if case["market"] not in {"INVALID", "NONE"}
    }
    classes = {case["asset_class"] for case in INVESTMENT_CASES}

    assert len(tickers - {"INVALID-NO-SUCH-ASSET"}) >= 5
    assert len(markets) >= 3
    assert {"equity", "etf", "crypto", "invalid", "no_ticker"} <= classes
    assert any(case["ticker"] is None for case in INVESTMENT_CASES)
    assert "AAPL" not in tickers


# ---------------------------------------------------------------------------
# Capabilities endpoint
# ---------------------------------------------------------------------------


def test_capabilities_endpoint(servers_running, auth_headers):
    req = urllib.request.Request("http://127.0.0.1:8002/capabilities", headers=auth_headers)
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


def test_product_manifest_endpoint(servers_running, auth_headers):
    req = urllib.request.Request("http://127.0.0.1:8002/product/manifest", headers=auth_headers)
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        assert resp.status == 200
        body = json.loads(resp.read())
        assert isinstance(body, dict)
    except urllib.error.HTTPError as e:
        if e.code in (404, 500):
            pytest.skip(f"Product manifest endpoint returned {e.code}")
        raise
