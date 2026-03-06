"""Pipeline v4 graph builder — thin, readable, no business logic."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from .contracts import PipelineState
from .nodes import (
    node_blocked,
    node_ceo,
    node_collect_experts,
    node_collector,
    node_expert,
    node_explanation,
    node_f51_verdict,
    node_orchestrator,
    node_rag_forensics,
    route_after_f51,
    route_after_orchestrator,
)


def build_graph(
    gateway=None,
    config=None,
    mandamentos: list[Any] | None = None,
) -> StateGraph:
    """Build and compile the SuperEzio pipeline graph.

    Args:
        gateway: ModelGateway instance (or None for no-gateway mode).
        config: UniversalConfig instance (or None for auto-detect).
        mandamentos: User rules list (or None for empty).

    Returns:
        A compiled LangGraph StateGraph ready for .astream().
    """
    mandamentos = mandamentos or []

    # ── Node factories: bind gateway/config/mandamentos to each node ──
    async def _orchestrator(state: dict) -> dict:
        return await node_orchestrator(state, gateway=gateway, config=config)

    async def _collector(state: dict) -> dict:
        return await node_collector(state, config=config)

    async def _f51(state: dict) -> dict:
        return await node_f51_verdict(state)

    async def _expert(state: dict) -> dict:
        return await node_expert(state, gateway=gateway)

    async def _collect_experts(state: dict) -> dict:
        return await node_collect_experts(state)

    async def _rag(state: dict) -> dict:
        return await node_rag_forensics(state)

    async def _ceo(state: dict) -> dict:
        return await node_ceo(state, gateway=gateway, config=config, mandamentos=mandamentos)

    async def _explanation(state: dict) -> dict:
        return await node_explanation(state)

    async def _blocked(state: dict) -> dict:
        return await node_blocked(state)

    # ── Build graph ──
    builder = StateGraph(PipelineState)

    # Nodes
    builder.add_node("orchestrator_primary", _orchestrator)
    builder.add_node("data", _collector)
    builder.add_node("f51_verdict", _f51)
    builder.add_node("pennylab", _node_pennylab_stub)
    builder.add_node("run_expert", _expert)
    builder.add_node("collect_experts", _collect_experts)
    builder.add_node("rag_forensics", _rag)
    builder.add_node("ceo_primary", _ceo)
    builder.add_node("explanation", _explanation)
    builder.add_node("respond_blocked", _blocked)

    # Edges
    builder.add_edge(START, "orchestrator_primary")
    builder.add_conditional_edges(
        "orchestrator_primary",
        route_after_orchestrator,
        {
            "data": "data",
            "ceo_primary": "ceo_primary",
            "respond_blocked": "respond_blocked",
        },
    )
    builder.add_edge("data", "f51_verdict")
    builder.add_edge("data", "pennylab")
    builder.add_conditional_edges(
        "f51_verdict",
        route_after_f51,
        {
            "run_expert": "run_expert",
            "collect_experts": "collect_experts",
        },
    )
    builder.add_edge("run_expert", "collect_experts")
    builder.add_edge("pennylab", "collect_experts")
    builder.add_edge("collect_experts", "rag_forensics")
    builder.add_edge("rag_forensics", "ceo_primary")
    builder.add_edge("ceo_primary", "explanation")
    builder.add_edge("explanation", END)
    builder.add_edge("respond_blocked", END)

    return builder.compile()


async def _node_pennylab_stub(state: dict) -> dict:
    """PennyLab stub — delegates to the real PennyLab pipeline hook."""
    ticker = state.get("ticker", "")
    if not ticker:
        return {"pennylab": {}}

    try:
        from experts.pennylab.pipeline_hook import analyze_ticker_sync

        result = await __import__("asyncio").to_thread(analyze_ticker_sync, ticker)
        return {"pennylab": result}
    except ImportError:
        return {"pennylab": {"ticker": ticker, "decision": None, "error": "unavailable"}}
    except Exception as exc:
        return {"pennylab": {"ticker": ticker, "decision": None, "error": str(exc)[:200]}}
