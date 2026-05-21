"""Pipeline v4 graph builder — thin, readable, no business logic."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncGenerator, Generator

from langgraph.graph import END, START, StateGraph

from .contracts import PipelineState
from .nodes import (
    node_agent,
    node_tool_executor,
    route_after_agent,
    node_explanation,
    node_blocked,
    node_orchestrator,
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

    async def _agent(state: dict) -> dict:
        return await node_agent(state, gateway=gateway, config=config, mandamentos=mandamentos)

    async def _tool_executor(state: dict) -> dict:
        return await node_tool_executor(state, gateway=gateway, config=config)

    async def _explanation(state: dict) -> dict:
        return await node_explanation(state)

    async def _blocked(state: dict) -> dict:
        return await node_blocked(state)

    builder = StateGraph(PipelineState)

    builder.add_node("orchestrator_primary", _orchestrator)
    builder.add_node("agent", _agent)
    builder.add_node("tool_executor", _tool_executor)
    builder.add_node("explanation", _explanation)
    builder.add_node("respond_blocked", _blocked)

    # The flow: Orchestrator (parses initial intent) -> Agent Loop
    builder.add_edge(START, "orchestrator_primary")
    builder.add_edge("orchestrator_primary", "agent")
    
    # Agent decides whether to call a tool or output the final answer
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tool_executor": "tool_executor",
            "explanation": "explanation",
        }
    )
    
    # After a tool executes, return control to the agent
    builder.add_edge("tool_executor", "agent")

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
                "agent",
                "tool_executor",
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
