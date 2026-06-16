"""Smoke test: pipeline v4 builds, streams, and shuts down correctly."""

import os
import sys

import pytest

pytestmark = pytest.mark.smoke

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("UNIVERSAL_SKIP_GATEWAY", "1")


def test_build_graph_returns_pipeline_app():
    from core.pipeline import PipelineApp, build_graph

    p = build_graph()
    assert isinstance(p, PipelineApp)


def test_pipeline_app_has_public_api():
    from core.pipeline import build_graph

    p = build_graph()
    assert hasattr(p, "shutdown")
    assert hasattr(p, "chat")
    assert hasattr(p, "chat_sync")
    assert hasattr(p, "stream_events")
    assert hasattr(p, "get_status")
    assert callable(p.shutdown)
    assert callable(p.get_status)


def test_pipeline_shutdown_no_crash():
    from core.pipeline import build_graph

    p = build_graph()
    p.shutdown()  # must not raise


def test_pipeline_get_status():
    from core.pipeline import build_graph

    p = build_graph()
    status = p.get_status()
    assert "nodes" in status
    assert "gateway_available" in status
    assert isinstance(status["nodes"], list)
    assert len(status["nodes"]) >= 6
    assert "trinity" in status["nodes"]
    assert "math_hub" in status["nodes"]
    assert "guardrail_hub" in status["nodes"]


def test_pipeline_graph_has_expected_nodes():
    from core.pipeline import build_graph

    p = build_graph()
    nodes = p.graph.nodes
    expected = {
        "__start__",
        "orchestrator_primary",
        "auto_full_analysis",
        "trinity",
        "agent",
        "tool_executor",
        "explanation",
        "respond_blocked",
    }
    assert expected.issubset(set(nodes.keys())), f"Missing: {expected - set(nodes.keys())}"


def test_route_after_orchestrator_always_reaches_agent():
    from core.pipeline.graph import route_after_orchestrator

    assert route_after_orchestrator({"route": "needs_scope"}) == "agent"
    assert route_after_orchestrator({"action": "ask_for_ticker"}) == "agent"
    assert route_after_orchestrator({"route": "general"}) == "agent"


def test_route_after_trinity_always_reaches_agent():
    from core.pipeline.graph import route_after_trinity

    assert route_after_trinity({"trinity_blocked": True}) == "agent"
    assert (
        route_after_trinity({"trinity_report": "CONSENSUS: BLOCK unanimous"})
        == "agent"
    )
    assert route_after_trinity({"trinity_report": "CONSENSUS: Both negative."}) == "agent"


@pytest.mark.asyncio
async def test_pipeline_stream_events_general():
    from core.pipeline import build_graph

    p = build_graph()
    events = []
    async for ev in p.stream_events("Ola"):
        events.append(ev)

    types = [e.get("type") for e in events]
    assert "PIPELINE_STEP" in types
    assert (
        len(events) >= 4
    )  # at least: graph started, orchestrator started/completed, graph completed

    p.shutdown()


@pytest.mark.asyncio
async def test_pipeline_stream_events_completes():
    from core.pipeline import build_graph

    p = build_graph()
    events = []
    async for ev in p.stream_events("O que e o SuperEzio?"):
        events.append(ev)

    steps = [e for e in events if e.get("type") == "PIPELINE_STEP" and e.get("step") == "graph"]
    statuses = [s.get("status") for s in steps]
    assert "started" in statuses
    assert "completed" in statuses

    p.shutdown()


@pytest.mark.asyncio
async def test_pipeline_stream_events_blocks_unscoped_ticket_reference(monkeypatch):
    from core.pipeline import build_graph

    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "1")

    p = build_graph()
    events = []
    async for ev in p.stream_events("cara vc esta travado neste ticket ?"):
        events.append(ev)

    chunks = [e.get("content", "") for e in events if e.get("type") == "CHUNK"]
    step_names = [e.get("step") for e in events if e.get("type") == "PIPELINE_STEP"]

    assert "respond_blocked" in step_names
    assert "agent" not in step_names
    assert any("ticker" in chunk.lower() for chunk in chunks)

    p.shutdown()


@pytest.mark.asyncio
async def test_pipeline_general_route_goes_to_ceo():
    from core.pipeline import build_graph

    p = build_graph()
    events = []
    async for ev in p.stream_events("Oi"):
        events.append(ev)

    steps = [e for e in events if e.get("type") == "PIPELINE_STEP"]
    step_names = [s.get("step") for s in steps]
    assert "orchestrator_primary" in step_names
    assert "explanation" in step_names

    p.shutdown()
