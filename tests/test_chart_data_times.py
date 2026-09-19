"""Regression: chart OHLCV candles and indicator series must carry real epoch times.

History: the 2026-08-20 checkpoint recorded a critical defect — every candle
returned by /api/chart-data had time=0, collapsing every chart. The provider
shapes the timestamp as an ISO-8601 string under the "datetime" key; the
endpoint normalizes it via _parse_candle_time. These tests pin that contract.

Second contract pinned here (2026-09-12): the ``CHART_DATA`` event on the chat
stream must carry ``server_ts``, the same epoch-seconds stamp the live candle
stream already sends in its ``snapshot``/``candle`` payloads. The chart card was
the only card with no server time to render, so its header could not be
timestamped while every sibling card could.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


class _MockPipeline:
    """Minimal pipeline stand-in: yields the events the test hands it.

    Defines ``stream_events``, so /task/submit takes the modern branch and each
    dict is forwarded verbatim.
    """

    def __init__(self) -> None:
        self.events_to_yield: list[object] = []

    async def stream_events(self, prompt: str, **kwargs):
        for ev in self.events_to_yield:
            yield ev

    def get_status(self) -> dict:
        return {"status": "ok", "nodes": []}

    def shutdown(self) -> None:
        pass


class _MockChatPipeline:
    """Old-branch pipeline: no ``stream_events``, so /task/submit falls back to
    ``chat_async``, where a JSON-encoded string chunk is unwrapped as an event."""

    def __init__(self) -> None:
        self.chunks_to_yield: list[object] = []

    async def chat_async(self, prompt: str, **kwargs):
        for ch in self.chunks_to_yield:
            yield ch

    def get_status(self) -> dict:
        return {"status": "ok", "nodes": []}

    def shutdown(self) -> None:
        pass


@pytest.fixture
def chart_client(monkeypatch):
    """TestClient with a mock pipeline and dev-anon auth (mirrors the module
    convention above: importing agent_server.main leaks the operator's
    PUBLIC_MODE/secret into the process env).

    The import runs FIRST on purpose: ``load_local_env()`` runs at import time
    and would otherwise reinstate the operator's PUBLIC_MODE/secret on top of
    the values pinned below, handing the first request a 401.
    """

    from agent_server.main import app

    monkeypatch.delenv("SUPEREZIO_JWT_SECRET", raising=False)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "0")
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")

    original = getattr(app.state, "pipeline", None)

    def _install(mock_p):
        app.state.pipeline = mock_p
        return mock_p, TestClient(app)

    yield _install, original
    if original is not None:
        app.state.pipeline = original
    else:
        try:
            delattr(app.state, "pipeline")
        except AttributeError:
            pass


def _ndjson_events(response) -> list[dict]:
    return [json.loads(line) for line in response.text.strip().split("\n") if line.strip()]


def _submit(client, *, message: str, ticker: str = "MSFT", session: str = "s-chart-ts"):
    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {"message": message, "session_id": session, "ticker": ticker},
    }
    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200, response.text
    return _ndjson_events(response)


def test_chart_data_event_carries_server_ts(chart_client):
    """The chart card must be timestampable: CHART_DATA needs server_ts."""
    install, _ = chart_client
    _, client = install(_MockPipeline())
    before = int(time.time())
    events = _submit(client, message="analise o MSFT", ticker="MSFT")
    after = int(time.time())

    chart_events = [ev for ev in events if ev.get("type") == "CHART_DATA"]
    assert chart_events, f"no CHART_DATA emitted; got {[e.get('type') for e in events]}"
    chart = chart_events[0]
    assert chart["ticker"] == "MSFT"
    assert "server_ts" in chart, f"CHART_DATA must carry server_ts; got {chart}"
    assert isinstance(chart["server_ts"], int), (
        f"server_ts must be epoch seconds as int (same as the candle stream); "
        f"got {type(chart['server_ts']).__name__}"
    )
    assert before <= chart["server_ts"] <= after, (
        f"server_ts {chart['server_ts']} outside the request window [{before}, {after}]"
    )


def test_chart_data_server_ts_reuses_candle_stream_convention(chart_client):
    """One convention, not two: server_ts is what the candle stream already sends.

    Pins the reuse decision — if someone later renames the stamp on either side,
    this fails instead of silently splitting the contract in half.
    """
    import inspect

    import agent_server.endpoints as ep

    candle_src = inspect.getsource(ep.stream_chart_data)
    assert '"server_ts": int(time.time())' in candle_src, (
        "the candle stream is the reference convention for server_ts"
    )

    install, _ = chart_client
    _, client = install(_MockPipeline())
    events = _submit(client, message="analise o MSFT", ticker="MSFT", session="s-chart-conv")
    chart = next(ev for ev in events if ev.get("type") == "CHART_DATA")
    assert set(chart.keys()) >= {"type", "ticker", "server_ts"}
    assert chart["type"] == "CHART_DATA"


def test_stream_events_passthrough_without_ts_is_stamped(chart_client):
    """A CHART_DATA forwarded from the pipeline must not reach the UI time-less.

    /task/submit takes the ``stream_events`` branch for the current pipeline and
    forwards every dict verbatim — so the stamp has to happen on the way out.
    """
    install, _ = chart_client
    mock_p, client = install(_MockPipeline())
    mock_p.events_to_yield = [
        {"type": "CHART_DATA", "ticker": "MSFT"},
        {"type": "CHUNK", "content": "ok"},
    ]
    before = int(time.time())
    events = _submit(client, message="analise o MSFT", ticker="MSFT", session="s-chart-pass")
    after = int(time.time())

    charts = [ev for ev in events if ev.get("type") == "CHART_DATA"]
    assert len(charts) >= 2, "expected the header CHART_DATA plus the piped one"
    piped = charts[-1]
    assert "server_ts" in piped, f"piped CHART_DATA arrived without server_ts: {piped}"
    assert before <= piped["server_ts"] <= after


def test_stream_events_passthrough_keeps_its_own_ts(chart_client):
    """An emitter that already stamped server_ts must not be overwritten."""
    install, _ = chart_client
    mock_p, client = install(_MockPipeline())
    mock_p.events_to_yield = [
        {"type": "CHART_DATA", "ticker": "MSFT", "server_ts": 1234567890},
        {"type": "CHUNK", "content": "ok"},
    ]
    events = _submit(client, message="analise o MSFT", ticker="MSFT", session="s-chart-keep")
    charts = [ev for ev in events if ev.get("type") == "CHART_DATA"]
    assert charts[-1]["server_ts"] == 1234567890


def test_chat_async_passthrough_without_ts_is_stamped(chart_client):
    """Same invariant on the legacy ``chat_async`` branch (JSON string chunks)."""
    install, _ = chart_client
    mock_p, client = install(_MockChatPipeline())
    mock_p.chunks_to_yield = [
        json.dumps({"type": "CHART_DATA", "ticker": "MSFT"}),
        json.dumps({"type": "CHUNK", "content": "ok"}),
    ]
    before = int(time.time())
    events = _submit(client, message="analise o MSFT", ticker="MSFT", session="s-chart-chat")
    after = int(time.time())

    charts = [ev for ev in events if ev.get("type") == "CHART_DATA"]
    assert len(charts) >= 2, "expected the header CHART_DATA plus the piped one"
    assert charts[-1].get("server_ts") is not None
    assert before <= charts[-1]["server_ts"] <= after


def test_chat_async_passthrough_keeps_its_own_ts(chart_client):
    """Legacy branch must not clobber an emitter's own stamp either."""
    install, _ = chart_client
    mock_p, client = install(_MockChatPipeline())
    mock_p.chunks_to_yield = [
        json.dumps({"type": "CHART_DATA", "ticker": "MSFT", "server_ts": 1234567890}),
        json.dumps({"type": "CHUNK", "content": "ok"}),
    ]
    events = _submit(client, message="analise o MSFT", ticker="MSFT", session="s-chart-chat2")
    charts = [ev for ev in events if ev.get("type") == "CHART_DATA"]
    assert charts[-1]["server_ts"] == 1234567890


def _make_candles(n: int = 30) -> list[dict]:
    base = datetime(2026, 8, 1, tzinfo=UTC)
    return [
        {
            "datetime": (base + timedelta(days=i)).isoformat(),
            "open": 10.0 + i * 0.1,
            "high": 11.0 + i * 0.1,
            "low": 9.5 + i * 0.1,
            "close": 10.5 + i * 0.1,
            "volume": 1000 + i,
        }
        for i in range(n)
    ]


def test_chart_data_candles_have_epoch_times(monkeypatch):
    import agent_server.endpoints as ep

    # This test owns the candle-time contract, not auth: importing
    # agent_server.main runs load_local_env() and leaks the operator's
    # PUBLIC_MODE=1 + secret into the process env (the endpoint would 401).
    # Pin dev-anon mode for the TestClient.
    monkeypatch.delenv("SUPEREZIO_JWT_SECRET", raising=False)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "0")
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")

    monkeypatch.setattr(
        ep.hub, "get_candles", lambda ticker, timeframe="6M": {"candles": _make_candles()}
    )
    monkeypatch.setattr(ep.hub, "get_profile", lambda ticker: {"name": "Test Co"})

    from agent_server.main import app

    client = TestClient(app)
    resp = client.get("/api/chart-data/TEST?timeframe=1M")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    times = [candle["time"] for candle in body["ohlcv"]]
    assert len(times) > 0
    assert all(t > 0 for t in times), f"candles with time=0 found: {times[:5]}"

    sma20 = (body.get("indicators") or {}).get("sma20", [])
    sma_times = [point["time"] for point in sma20]
    assert all(t > 0 for t in sma_times), f"sma20 with time=0 found: {sma_times[:5]}"


def test_ohlcv_builder_parses_iso_datetime_and_epoch(monkeypatch):
    from agent_server.endpoints import _build_ohlcv

    candles = [
        {
            "datetime": "2026-08-21T04:00:00+00:00",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "volume": 10,
        },
        {"time": 1787284800, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"date": "2026-08-19", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
    ]
    ohlcv = _build_ohlcv(candles)
    date_epoch = int(
        datetime.fromisoformat("2026-08-19").timestamp()
    )  # naive local, mirrors endpoint fromisoformat parsing
    assert [c["time"] for c in ohlcv] == [1787284800, 1787284800, date_epoch]


# ---------------------------------------------------------------------------
# 2026-09-19 — the "DATA: DEGRADADO" root cause.
#
# /api/chart-data/{ticker} carried no server stamp at all. frontend/js/health.js
# #dataState looked for as_of/fetched_at/timestamp/last_update on the payload,
# found none, and fell through to {"state": "degraded"} — unconditionally, on
# every ticker and timeframe, with perfectly healthy candles. The cockpit footer
# therefore read "DATA: DEGRADADO" forever and the label was not a data verdict.
#
# The fix is two halves and BOTH are required — the endpoint stamping server_ts
# alone changes nothing on screen, because health.js did not know that name:
#   B) the endpoint stamps server_ts, reusing the convention the candle stream
#      already sends (pinned above by
#      test_chart_data_server_ts_reuses_candle_stream_convention);
#   A) health.js reads it, and falls back to the last candle's own time.
#
# The front half is exercised for real: the production health.js is loaded into
# node with a minimal window shim and buildSnapshot() is called on it. Asserting
# on the source text would have passed while the state stayed "degraded".
# ---------------------------------------------------------------------------

_HEALTH_DRIVER = """
const fs = require('fs'), vm = require('vm');
let raw = '';
process.stdin.on('data', d => { raw += d; });
process.stdin.on('end', () => {
  const payload = JSON.parse(raw);
  const ctx = {
    document: { readyState: 'loading', addEventListener() {} },
    window: { SZ: { state: { chartData: payload.chartData } } },
    console,
  };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(payload.script, 'utf8'), ctx);
  process.stdout.write(JSON.stringify(ctx.window.SZ.health.buildSnapshot(payload.details)));
});
"""


def _health_data_state(chart_data):
    """Drive the real frontend/js/health.js in node; return snapshot.data.

    ``chart_data`` is what the cockpit puts in SZ.state.chartData — the raw
    /api/chart-data payload. Returns the ``data`` branch the status bar renders.
    """
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node") or pytest.skip("node is required to exercise the real health.js")

    health_js = Path(__file__).parents[1] / "frontend" / "js" / "health.js"
    payload = json.dumps(
        {
            "chartData": chart_data,
            "details": {"checks": {}, "mission": {}},
            "script": str(health_js),
        }
    )
    proc = subprocess.run(
        [node, "-e", _HEALTH_DRIVER],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"health.js failed under node: {proc.stderr}"
    return json.loads(proc.stdout)["data"]


def _assert_stamp_is_now(as_of) -> None:
    parsed = datetime.fromisoformat(str(as_of))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    assert abs((parsed - datetime.now(UTC)).total_seconds()) < 120, as_of


def test_chart_data_response_carries_server_ts(monkeypatch):
    """The REST chart payload must stamp server_ts (epoch seconds), like the SSE."""
    import agent_server.endpoints as ep

    monkeypatch.delenv("SUPEREZIO_JWT_SECRET", raising=False)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "0")
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
    monkeypatch.setattr(
        ep.hub, "get_candles", lambda ticker, timeframe="6M": {"candles": _make_candles()}
    )
    monkeypatch.setattr(ep.hub, "get_profile", lambda ticker: {"name": "Test Co"})
    ep._CHART_CACHE.clear()  # a warm entry from another test would mask the stamp

    from agent_server.main import app

    client = TestClient(app)
    before = int(time.time())
    resp = client.get("/api/chart-data/TEST?timeframe=1M")
    after = int(time.time())
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert "server_ts" in body, f"chart payload has no server_ts: {sorted(body)}"
    assert isinstance(body["server_ts"], int), (
        f"server_ts must be epoch seconds as int (same as the candle stream); "
        f"got {type(body['server_ts']).__name__}"
    )
    assert before <= body["server_ts"] <= after, (
        f"server_ts {body['server_ts']} outside the request window [{before}, {after}]"
    )


def test_health_js_reads_server_ts_as_epoch_seconds():
    """The stamp is epoch SECONDS: read raw it is 1970, which renders as "stale"."""
    now = int(time.time())
    snap = _health_data_state(
        {
            "ticker": "TD.TO",
            "server_ts": now,
            "ohlcv": [{"time": now - 3600, "close": 1.0}],
        }
    )
    assert snap["state"] == "live", snap
    _assert_stamp_is_now(snap["asOf"])


def test_health_js_falls_back_to_last_candle_time_when_unstamped():
    """A payload with no stamp is still datable from its own last bar."""
    now = int(time.time())
    snap = _health_data_state({"ticker": "TD.TO", "ohlcv": [{"time": now - 60, "close": 1.0}]})
    assert snap["state"] == "live", snap
    _assert_stamp_is_now(snap["asOf"])


def test_health_js_marks_a_daily_bar_stale_not_live():
    """The 15-minute freshness window is intraday. A daily bar is honestly stale."""
    now = int(time.time())
    snap = _health_data_state({"ticker": "TD.TO", "ohlcv": [{"time": now - 86400, "close": 1.0}]})
    assert snap["state"] == "stale", snap


def test_health_js_still_reads_the_legacy_stamp_names():
    """as_of / fetched_at / timestamp / last_update must keep working."""
    snap = _health_data_state(
        {
            "ohlcv": [{"time": 1, "close": 1.0}],
            "as_of": datetime.now(UTC).isoformat(),
        }
    )
    assert snap["state"] == "live", snap


def test_health_js_reports_offline_without_candles():
    """No candles stays "offline" — the new stamp must not mask an empty chart."""
    assert _health_data_state({"ticker": "X", "ohlcv": []})["state"] == "offline"


def test_health_js_reports_unknown_without_chart():
    assert _health_data_state(None)["state"] == "unknown"
