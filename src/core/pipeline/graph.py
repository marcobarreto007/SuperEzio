"""Pipeline v4 graph builder - thin, readable, no business logic."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncGenerator, Generator

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from core.evidence import EvidenceRun, generate_html_report, save_evidence

from .contracts import PipelineState
from .nodes import (
    node_agent,
    node_collector,
    node_tool_executor,
    route_after_agent,
    node_explanation,
    node_blocked,
    node_orchestrator,
)
from .nodes.experts import node_collect_experts, node_expert, EXPERT_PROVIDERS
from .nodes.f51 import node_f51_verdict
from .nodes.neural_decision import node_neural_decision
from .nodes.sdca_firewall import node_sdca_firewall
from .nodes.rag import node_rag_forensics

logger = logging.getLogger(__name__)

__all__ = ["PipelineApp", "build_graph", "route_after_orchestrator"]


def _scan_evidence_payload(
    node_output: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, list[str]] | None:
    scan_output = node_output.get("scan")
    if isinstance(scan_output, dict):
        scan_trace = scan_output.get("scan_trace") or {}
        sources = scan_trace.get("provider_sources_used") or []
        return (
            scan_output.get("candidates", []),
            int(scan_output.get("rejected_count", 0) or 0),
            list(sources),
        )
    if node_output.get("candidates"):
        return (
            node_output.get("candidates", []),
            int(node_output.get("rejected", 0) or 0),
            list(node_output.get("sources_used", [])),
        )
    return None


def route_after_orchestrator(state: dict) -> str:
    """Route scope-blocked plans before the agent can call tools or the model."""
    if state.get("route") == "needs_scope" or state.get("action") in {
        "ask_for_ticker",
        "ask_for_scope",
    }:
        return "respond_blocked"
    return "agent"


async def _auto_full_analysis_legacy(state: dict) -> dict:
    """Run ALL experts, verdicts, and calculators automatically.

    This node fires on every request BEFORE Bob sees the data.
    Bob gets complete evidence — no more parrot mode.
    """
    ticker = state.get("ticker", "")
    message = state.get("message", "")
    data_context = state.get("data_context", "")

    results: dict[str, Any] = {}

    # ── 1. Data collection (if not already done) ──
    if not data_context and ticker:
        try:
            collector_result = await node_collector({**state, "route": "ticker_analysis"})
            data_context = collector_result.get("data_context", "")
            results["data_collected"] = True
        except Exception as e:
            results["data_error"] = str(e)[:100]

    # ── 2. Expert committee (6 experts fan-out) ──
    expert_results = []
    roles = ["macro_risk", "fundamental_value", "momentum_technical",
             "contrarian_opportunity", "sentiment", "social_forensics"]
    for role in roles:
        try:
            expert_state = {
                **state, "role": role, "ticker": ticker,
                "data_context": data_context or message,
            }
            res = await node_expert(expert_state)
            for er in res.get("expert_results", []):
                er["role"] = role
                er["provider"] = EXPERT_PROVIDERS.get(role, "unknown")
                expert_results.append(er)
        except Exception as e:
            expert_results.append({"role": role, "error": str(e)[:100], "provider": EXPERT_PROVIDERS.get(role, "?")})

    state["expert_results"] = expert_results

    # ── 3. Collect expert summary ──
    try:
        collect_res = await node_collect_experts({**state, "expert_results": expert_results})
        results["expert_summary"] = collect_res.get("expert_summary", "")
    except Exception as e:
        results["expert_summary"] = f"Expert collection error: {e}"

    # ── 4. F51 Verdict engine ──
    try:
        f51_res = await node_f51_verdict(state)
        results["f51_verdict"] = f51_res.get("f51_verdict", {})
    except Exception as e:
        results["f51_error"] = str(e)[:100]

    # ── 5. Neural Decision ──
    try:
        neural_res = await node_neural_decision(state)
        results["neural_decision"] = neural_res.get("neural_decision", {})
    except Exception as e:
        results["neural_error"] = str(e)[:100]

    # ── 6. SDCA Firewall ──
    try:
        sdca_res = await node_sdca_firewall(state)
        results["sdca_firewall"] = sdca_res.get("sdca_firewall", {})
    except Exception as e:
        results["sdca_error"] = str(e)[:100]

    # ── 7. RAG Forensics ──
    try:
        rag_res = await node_rag_forensics(state)
        results["rag_forensics"] = rag_res.get("rag_context", "")
    except Exception as e:
        results["rag_error"] = str(e)[:100]

    return results


def _merge_node_update(
    working_state: dict[str, Any],
    output: dict[str, Any],
    update: dict[str, Any],
) -> None:
    """Merge node output into the working state and the graph update."""

    for key, value in (update or {}).items():
        if key == "errors":
            combined = list(working_state.get("errors") or []) + [
                str(item) for item in (value or [])
            ]
            working_state["errors"] = combined
            output["errors"] = combined
            continue
        working_state[key] = value
        output[key] = value


async def _auto_full_analysis(
    state: dict,
    *,
    gateway=None,
    config=None,
) -> dict:
    """Collect evidence and run the decision stack before Bob answers.

    The critical contract is state propagation: collector output must feed the
    experts, F51, neural decision, SDCA, RAG, and then Bob's prompt.
    """

    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    route = state.get("route", "general")
    working_state: dict[str, Any] = {**state}
    output: dict[str, Any] = {}

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "auto_full_analysis",
            "status": "started",
            "route": route,
        }
    )

    try:
        collector_result: dict[str, Any] = {}
        if route == "market_scan" and not working_state.get("scan"):
            collector_result = await node_collector(
                {**working_state, "route": "market_scan"},
                config=config,
            )
        elif (
            working_state.get("ticker")
            and not working_state.get("data")
            and route in {"ticker_analysis", "market_scan"}
        ):
            collector_result = await node_collector(
                {**working_state, "route": "ticker_analysis"},
                config=config,
            )
        if collector_result:
            _merge_node_update(working_state, output, collector_result)
    except Exception as exc:
        _merge_node_update(
            working_state,
            output,
            {"errors": [f"auto_full_analysis.collect_data:{exc}"]},
        )

    ticker = str(
        working_state.get("ticker")
        or (working_state.get("data") or {}).get("ticker")
        or ""
    ).upper()
    data_context = str(
        working_state.get("data_context") or working_state.get("message") or ""
    )

    if ticker:
        expert_results: list[dict[str, Any]] = []
        roles = [
            "macro_risk",
            "fundamental_value",
            "momentum_technical",
            "contrarian_opportunity",
            "sentiment",
            "social_forensics",
        ]
        for role in roles:
            try:
                res = await node_expert(
                    {
                        **working_state,
                        "role": role,
                        "ticker": ticker,
                        "data_context": data_context,
                    },
                    gateway=gateway,
                )
                for expert_result in res.get("expert_results", []):
                    expert_result.setdefault("role", role)
                    expert_result.setdefault(
                        "provider", EXPERT_PROVIDERS.get(role, "unknown")
                    )
                    expert_results.append(expert_result)
            except Exception as exc:
                expert_results.append(
                    {
                        "role": role,
                        "ok": False,
                        "error": str(exc)[:200],
                        "provider": EXPERT_PROVIDERS.get(role, "?"),
                    }
                )

        _merge_node_update(working_state, output, {"expert_results": expert_results})
        try:
            collect_res = await node_collect_experts(
                {**working_state, "expert_results": expert_results}
            )
            _merge_node_update(working_state, output, collect_res)
        except Exception as exc:
            _merge_node_update(
                working_state,
                output,
                {
                    "expert_summary": f"Expert collection error: {exc}",
                    "errors": [f"auto_full_analysis.experts:{exc}"],
                },
            )
    else:
        _merge_node_update(
            working_state,
            output,
            {"expert_summary": "Experts skipped: no ticker selected by scanner or user."},
        )

    if ticker:
        for label, node in (
            ("f51", node_f51_verdict),
            ("neural_decision", node_neural_decision),
            ("sdca_firewall", node_sdca_firewall),
            ("rag_forensics", node_rag_forensics),
        ):
            try:
                result = await node(working_state)
                _merge_node_update(working_state, output, result)
            except Exception as exc:
                _merge_node_update(
                    working_state,
                    output,
                    {"errors": [f"auto_full_analysis.{label}:{exc}"]},
                )
    else:
        try:
            result = await node_sdca_firewall(working_state)
            _merge_node_update(working_state, output, result)
        except Exception as exc:
            _merge_node_update(
                working_state,
                output,
                {"errors": [f"auto_full_analysis.sdca_firewall:{exc}"]},
            )

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "auto_full_analysis",
            "status": "completed",
            "ticker": ticker,
            "has_data": bool(working_state.get("data")),
            "has_scan": bool(working_state.get("scan")),
            "has_f51": bool(working_state.get("f51_verdict")),
            "has_sdca": bool(working_state.get("sdca_firewall")),
            "has_experts": bool(working_state.get("expert_summary")),
        }
    )
    return output


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

    async def _auto(state: dict) -> dict:
        return await _auto_full_analysis(state, gateway=gateway, config=config)

    async def _agent(state: dict) -> dict:
        return await node_agent(state, gateway=gateway, config=config, mandamentos=mandamentos)

    async def _tool_executor(state: dict) -> dict:
        return await node_tool_executor(state, gateway=gateway, config=config)

    async def _auto_execute_paper(state: dict) -> dict:
        """Auto-submit paper orders when Bob produces a PAPER_TICKET.

        Parses the agent's final_answer for ticker/shares/action and
        calls the IBKR paper adapter to place the order in TWS.
        """
        import os as _os
        import re
        from langgraph.config import get_stream_writer
        from core.pipeline.nodes.tool_executor import _submit_paper_order

        # Enable paper order submission for this pipeline execution
        _os.environ.setdefault("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")

        writer = get_stream_writer()
        run_id = state.get("run_id", "")

        writer({
            "type": "PIPELINE_STEP", "run_id": run_id,
            "step": "auto_execute_paper", "status": "started",
        })

        final = state.get("final_answer", "")
        scan = state.get("scan") or {}
        candidates = scan.get("candidates", []) if isinstance(scan, dict) else []

        # ── Strategy 1: PAPER_TICKET in Bob's response ──
        if final and "PAPER_TICKET" in final:
            ticker_match = re.search(r"(?:Ticker|ticker):\s*([A-Z]{1,5}(?:\.[A-Z]{2})?)", final)
            ticker = ticker_match.group(1) if ticker_match else state.get("ticker", "")
            qty_match = re.search(r"(?:quantity|qty|shares|Estimated quantity):\s*([\d,.]+)", final)
            qty = float(qty_match.group(1).replace(",", "")) if qty_match else 10
            action = "sell" if "SELL" in final or "short" in final.lower() else "buy"

        # ── Strategy 2: Fallback — pick top scan candidate ──
        elif candidates and state.get("route") in ("market_scan",):
            top = candidates[0] if isinstance(candidates[0], dict) else {}
            ticker = str(top.get("ticker", top.get("symbol", ""))).upper()
            if not ticker:
                writer({
                    "type": "PIPELINE_STEP", "run_id": run_id,
                    "step": "auto_execute_paper", "status": "skipped",
                    "reason": "no_ticker_in_scan_candidates",
                })
                return {}
            price = float(top.get("price", top.get("latest_price", 0)) or 0)
            qty = max(1, int(1000 / price)) if price > 0 else 10
            action = "buy"

        else:
            writer({
                "type": "PIPELINE_STEP", "run_id": run_id,
                "step": "auto_execute_paper", "status": "skipped",
                "reason": "no_paper_ticket_or_scan_candidates",
            })
            return {}

        if not ticker:
            writer({
                "type": "PIPELINE_STEP", "run_id": run_id,
                "step": "auto_execute_paper", "status": "skipped",
                "reason": "no_ticker_parsed",
            })
            return {"paper_exec_note": "no ticker parsed"}

        writer({
            "type": "PAPER_EXEC", "run_id": run_id,
            "ticker": ticker, "action": action, "qty": qty,
        })

        # Paper order submission requires:
        # - ticket_allowed=True in state (cognitive contract)
        # - order_type=LMT (limit order, safer for paper)
        # - limit_price from scan data or default near current price
        order_state = {**state, "ticket_allowed": True}
        limit_price = 0.0
        if isinstance(scan, dict):
            for c in (scan.get("candidates") or []):
                if isinstance(c, dict) and str(c.get("ticker", "")).upper() == ticker:
                    limit_price = float(c.get("price", c.get("latest_price", 0)) or 0)
                    break
        if limit_price <= 0:
            limit_price = float(state.get("latest_price", 99.0)) or 99.0

        result = await _submit_paper_order(order_state, {
            "ticker": ticker,
            "action": action,
            "qty": qty,
            "order_type": "LMT",
            "limit_price": limit_price,
        })

        writer({
            "type": "PIPELINE_STEP", "run_id": run_id,
            "step": "auto_execute_paper", "status": "completed",
            "result": result,
        })

        return {"paper_exec_result": result, "paper_exec_ticker": ticker, "paper_exec_qty": qty}

    async def _explanation(state: dict) -> dict:
        return await node_explanation(state)

    async def _blocked(state: dict) -> dict:
        return await node_blocked(state)

    builder = StateGraph(PipelineState)

    builder.add_node("orchestrator_primary", _orchestrator)
    builder.add_node("auto_full_analysis", _auto)
    builder.add_node("agent", _agent)
    builder.add_node("auto_execute_paper", _auto_execute_paper)
    builder.add_node("tool_executor", _tool_executor)
    builder.add_node("explanation", _explanation)
    builder.add_node("respond_blocked", _blocked)

    builder.add_edge(START, "orchestrator_primary")
    builder.add_conditional_edges(
        "orchestrator_primary",
        route_after_orchestrator,
        {
            "respond_blocked": "respond_blocked",
            "agent": "auto_full_analysis",
        },
    )
    # After full analysis (experts + F51 + neural + SDCA + RAG), go to agent
    builder.add_edge("auto_full_analysis", "agent")

    # Agent decides whether to call a tool or output the final answer.
    # Route through auto_execute_paper before explanation so paper orders
    # are auto-submitted to IBKR when Bob produces a PAPER_TICKET.
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tool_executor": "tool_executor",
            "explanation": "auto_execute_paper",
        },
    )

    # After a tool executes, return control to the agent
    builder.add_edge("tool_executor", "agent")

    # Auto-execute paper orders, then go to explanation
    builder.add_edge("auto_execute_paper", "explanation")

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
    - shutdown(): graceful teardown
    - stream_events(): async event stream
    - chat() / chat_sync(): convenience methods
    - get_status(): health/status dict
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
        trade_order_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        run_id = uuid.uuid4().hex[:12]

        evidence: EvidenceRun | None = None
        evidence_saved = False
        response_chunks: list[str] = []
        try:
            evidence = EvidenceRun(prompt=message, ticker=ticker)
            evidence.start()
        except Exception:
            pass

        def _finalize_evidence() -> None:
            nonlocal evidence_saved
            if evidence is None or evidence_saved:
                return
            try:
                if response_chunks and not evidence.response:
                    response_text = "".join(response_chunks)
                    evidence.record_response(
                        response_text=response_text,
                        tokens=len(response_text.split()),
                    )
                evidence.finish()
                run_dir = save_evidence(evidence)
                generate_html_report(evidence, run_dir)
                evidence_saved = True
                logger.info("[evidence] Saved: %s", run_dir)
            except Exception as exc:
                logger.warning("[evidence] Save failed: %s", exc)

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
        if trade_order_context:
            initial["trade_order_context"] = trade_order_context

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

                        # Evidence: capture pipeline events.
                        if evidence is not None:
                            evt_type = payload.get("type", "")
                            try:
                                if evt_type in {"CHUNK", "EXPLANATION_CHUNK"} and payload.get(
                                    "content"
                                ):
                                    response_chunks.append(str(payload.get("content", "")))
                                if evt_type == "DATA_COLLECTED":
                                    provider = payload.get("provider") or (
                                        ", ".join(payload.get("providers") or []) or "scanner"
                                    )
                                    capability = payload.get("capability") or payload.get(
                                        "quality", "market_data"
                                    )
                                    evidence.record_source(
                                        provider=provider,
                                        capability=capability,
                                        status=payload.get("status", "collected"),
                                        data=payload,
                                    )
                                elif evt_type == "SCAN_COMPLETE":
                                    evidence.record_scan(
                                        candidates=payload.get("candidates", []),
                                        rejected=payload.get("rejected", 0),
                                        sources_used=payload.get("sources", []),
                                    )
                                elif evt_type == "EXPERT_COMPLETE":
                                    evidence.record_expert(
                                        expert_name=payload.get("expert", "unknown"),
                                        verdict=payload.get("verdict", "?"),
                                        confidence=float(payload.get("confidence", 0)),
                                        provider=payload.get("provider", "unknown"),
                                        bob_readable=payload.get("bob_readable", ""),
                                    )
                                elif evt_type == "SDCA_COMPLETE":
                                    evidence.record_risk(payload)
                                elif evt_type == "F51_VERDICT":
                                    evidence.record_verdict(payload)
                            except Exception:
                                pass

                        yield payload
                    elif payload is not None:
                        yield {
                            "type": "CHUNK",
                            "run_id": run_id,
                            "content": str(payload),
                        }
                elif mode == "updates":
                    # Evidence: capture node outputs from updates.
                    if evidence is not None and isinstance(payload, dict):
                        try:
                            for node_name, node_output in payload.items():
                                if isinstance(node_output, dict):
                                    if node_name == "explanation" and node_output.get(
                                        "explanation"
                                    ):
                                        evidence.record_response(
                                            response_text=str(node_output["explanation"]),
                                            tokens=len(str(node_output["explanation"]).split()),
                                        )
                                    scan_payload = _scan_evidence_payload(node_output)
                                    if scan_payload is not None:
                                        candidates, rejected, sources_used = scan_payload
                                        evidence.record_scan(
                                            candidates=candidates,
                                            rejected=rejected,
                                            sources_used=sources_used,
                                        )
                        except Exception:
                            pass
                    continue

            _finalize_evidence()
            yield {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "graph",
                "status": "completed",
                "evidence_run_id": evidence.run_id if evidence else None,
            }
        except Exception as exc:
            detail = str(exc) or exc.__class__.__name__
            if evidence is not None:
                try:
                    evidence.record_error("pipeline", detail)
                except Exception:
                    pass
            yield {"type": "ERROR", "run_id": run_id, "detail": detail[:500]}

        finally:
            _finalize_evidence()

    async def chat_async(
        self,
        message: str,
        context: str = "",
        session_id: str = "default",
        memory_mode: str = "relevant_all",
        rigor: str = "strict",
        ticker: str = "",
        trade_order_context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        async for event in self.stream_events(
            message,
            context=context,
            session_id=session_id,
            memory_mode=memory_mode,
            rigor=rigor,
            ticker=ticker,
            trade_order_context=trade_order_context,
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
                "auto_full_analysis",
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
