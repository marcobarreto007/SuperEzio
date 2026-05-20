"""Pipeline v4 graph builder — thin, readable, no business logic."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncGenerator, Generator

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
    node_neural_decision,
    node_orchestrator,
    node_rag_forensics,
    node_sdca_firewall,
    route_after_f51,
    route_after_orchestrator,
    route_after_sdca_firewall,
)

logger = logging.getLogger(__name__)

__all__ = ["PipelineApp", "build_graph"]


def build_graph(
    gateway=None,
    config=None,
    mandamentos: list[Any] | None = None,
) -> "PipelineApp":
    """Build, compile, and wrap the SuperEzio pipeline graph.

    Returns a PipelineApp instance with shutdown(), chat(), stream_events(),
    and get_status() methods.
    """
    mandamentos = mandamentos or []

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

    async def _neural(state: dict) -> dict:
        return await node_neural_decision(state)

    async def _sdca(state: dict) -> dict:
        return await node_sdca_firewall(state)

    async def _ceo(state: dict) -> dict:
        return await node_ceo(state, gateway=gateway, config=config, mandamentos=mandamentos)

    async def _explanation(state: dict) -> dict:
        return await node_explanation(state)

    async def _blocked(state: dict) -> dict:
        return await node_blocked(state)

    builder = StateGraph(PipelineState)

    builder.add_node("orchestrator_primary", _orchestrator)
    builder.add_node("data", _collector)
    builder.add_node("f51_verdict", _f51)
    builder.add_node("pennylab", _node_pennylab_stub)
    builder.add_node("run_expert", _expert)
    builder.add_node("collect_experts", _collect_experts)
    builder.add_node("rag_forensics", _rag)
    builder.add_node("neural_decision", _neural)
    builder.add_node("sdca_firewall", _sdca)
    builder.add_node("ceo_primary", _ceo)
    builder.add_node("explanation", _explanation)
    builder.add_node("respond_blocked", _blocked)

    builder.add_edge(START, "orchestrator_primary")
    builder.add_conditional_edges(
        "orchestrator_primary",
        route_after_orchestrator,
        {"data": "data"},
    )
    builder.add_edge("data", "f51_verdict")
    builder.add_edge("f51_verdict", "pennylab")
    builder.add_conditional_edges(
        "pennylab",
        route_after_f51,
        {
            "run_expert": "run_expert",
            "collect_experts": "collect_experts",
        },
    )
    builder.add_edge("run_expert", "collect_experts")
    builder.add_edge("collect_experts", "neural_decision")
    builder.add_edge("neural_decision", "sdca_firewall")
    builder.add_conditional_edges(
        "sdca_firewall",
        route_after_sdca_firewall,
        {
            "rag_forensics": "rag_forensics",
            "respond_blocked": "respond_blocked",
        },
    )
    builder.add_edge("rag_forensics", "ceo_primary")
    builder.add_edge("ceo_primary", "explanation")
    builder.add_edge("explanation", END)
    builder.add_edge("respond_blocked", END)

    compiled = builder.compile()
    return PipelineApp(
        graph=compiled,
        gateway=gateway,
        config=config,
        mandamentos=mandamentos,
    )


class PipelineApp:
    """Production wrapper around CompiledStateGraph.

    Provides the public API expected by agent_server:
    - shutdown() — graceful teardown
    - stream_events() — async event stream
    - chat() / chat_sync() — convenience methods
    - get_status() — health/status dict
    """

    def __init__(
        self,
        graph,
        gateway=None,
        config=None,
        mandamentos: list[Any] | None = None,
    ):
        self.graph = graph
        self.gateway = gateway
        self.config = config
        self.mandamentos = mandamentos or []
        self._shutting_down = False

    def shutdown(self) -> None:
        logger.info("PipelineApp shutting down...")
        self._shutting_down = True
        if self.gateway:
            try:
                self.gateway.unload_all()
            except Exception as exc:
                logger.warning("Gateway unload error during shutdown: %s", exc)

    async def stream_events(
        self,
        message: str,
        context: str = "",
        session_id: str = "default",
        memory_mode: str = "relevant_all",
        rigor: str = "strict",
        ticker: str = "",
    ) -> AsyncGenerator[dict[str, Any], None]:
        run_id = uuid.uuid4().hex[:12]
        initial: dict[str, Any] = {
            "run_id": run_id,
            "message": message,
            "context": context,
            "session_id": session_id,
            "memory_mode": memory_mode,
            "rigor": rigor,
            "errors": [],
        }
        if ticker:
            initial["ticker"] = ticker

        yield {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "graph",
            "status": "started",
        }

        try:
            async for item in self.graph.astream(
                initial,
                stream_mode=["custom", "updates"],
            ):
                if isinstance(item, dict):
                    mode = item.get("type", "")
                    payload = item.get("data")
                elif isinstance(item, tuple) and len(item) == 2:
                    mode, payload = item
                else:
                    continue

                if mode == "custom":
                    if isinstance(payload, dict):
                        payload.setdefault("run_id", run_id)
                        yield payload
                    elif payload is not None:
                        yield {
                            "type": "CHUNK",
                            "run_id": run_id,
                            "content": str(payload),
                        }
                elif mode == "updates":
                    continue

            yield {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "graph",
                "status": "completed",
            }
        except Exception as exc:
            detail = str(exc) or exc.__class__.__name__
            yield {"type": "ERROR", "run_id": run_id, "detail": detail[:500]}

    async def chat_async(
        self,
        message: str,
        context: str = "",
        session_id: str = "default",
        memory_mode: str = "relevant_all",
        rigor: str = "strict",
        ticker: str = "",
    ) -> AsyncGenerator[str, None]:
        async for event in self.stream_events(
            message,
            context=context,
            session_id=session_id,
            memory_mode=memory_mode,
            rigor=rigor,
            ticker=ticker,
        ):
            if event.get("type") == "CHUNK":
                yield str(event.get("content", ""))
            elif event.get("type") == "ERROR":
                yield f"[ERROR] {event.get('detail', '')}"

    def chat(self, message: str, context: str = "") -> Generator[str, None, None]:
        yield _run_async(self._chat_collect_async(message, context))

    async def _chat_collect_async(self, message: str, context: str = "") -> str:
        chunks: list[str] = []
        async for chunk in self.chat_async(message, context):
            chunks.append(chunk)
        return "".join(chunks)

    def chat_sync(self, message: str, context: str = "") -> str:
        return _run_async(self._chat_collect_async(message, context))

    def get_status(self) -> dict[str, Any]:
        return {
            "mode": "pipeline_v4_stategraph",
            "nodes": [
                "orchestrator_primary",
                "data",
                "f51_verdict",
                "pennylab",
                "run_expert",
                "collect_experts",
                "neural_decision",
                "rag_forensics",
                "ceo_primary",
                "explanation",
                "respond_blocked",
            ],
            "gateway_available": self.gateway is not None,
            "providers": ([p.name for p in self.gateway.providers] if self.gateway else []),
            "mandamentos_count": len(self.mandamentos),
        }


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


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
