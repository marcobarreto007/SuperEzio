"""Pipeline v4 graph builder - thin, readable, no business logic."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, AsyncGenerator, Generator

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from core.evidence import EvidenceRun, generate_html_report, save_evidence
from core.math.math_hub import MathHub

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
from .nodes.guardrail_hub import node_guardrail_hub
from .nodes.trinity import node_trinity

logger = logging.getLogger(__name__)

__all__ = ["PipelineApp", "build_graph", "route_after_orchestrator", "route_after_trinity"]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


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
    """Esteira linear — sem desvios. Tudo vai pro agente."""
    return "agent"


def route_after_trinity(state: dict) -> str:
    """Esteira linear — sem desvios. Tudo vai pro agente."""
    return "agent"


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


async def _do_collect(working_state, output, should_collect_market, route, config, _merge, _mark):
    """Extracted collector body for try_run_async wrapping."""
    collector_result: dict[str, Any] = {}
    if should_collect_market and not working_state.get("scan") and not working_state.get("data"):
        collector_route = (
            "ticker_analysis"
            if working_state.get("ticker") and route != "market_scan"
            else "market_scan"
        )
        collector_result = await node_collector(
            {**working_state, "route": collector_route},
            config=config,
        )
    if collector_result:
        _merge(working_state, output, collector_result)
        _mark("data_collection")


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

    # ── CASE tracking ──
    financial_case = working_state.get("financial_case")
    # Preserve case_pending from orchestrator (survives state propagation)
    output["case_pending"] = list(working_state.get("case_pending") or [])
    output["case_context"] = working_state.get("case_context") or ""

    paper_only_research = _env_bool("SUPEREZIO_RESEARCH_PAPER_ONLY", False) or _env_bool(
        "SUPEREZIO_DAYTRADE_PAPER_ONLY", False
    )
    live_disabled = _env_bool("SUPEREZIO_LIVE_TRADING_DISABLED", False)
    if paper_only_research or live_disabled:
        safety = {
            "paper_only": bool(paper_only_research),
            "live_trading_disabled": bool(live_disabled),
        }
        output["research_safety"] = safety
        working_state["research_safety"] = safety

    def _mark_step(step_name: str, evidence: dict | None = None):
        if financial_case:
            financial_case.mark_complete(step_name, evidence)
            output["case_steps"] = {
                name: {"completed": s.completed, "error": s.error}
                for name, s in financial_case.steps.items()
            }
            output["case_is_complete"] = financial_case.is_complete
            output["case_pending"] = financial_case.pending_steps

    # ── Clean ticker-specific state between requests ──
    # Prevents ticker leakage: "analise AAPL" → "invista em outros" still sees AAPL
    if route == "general" and not working_state.get("ticker"):
        for key in (
            "ticker",
            "data",
            "data_context",
            "expert_results",
            "expert_summary",
            "expert_verdicts",
            "trinity_report",
            "f51_verdict",
            "math_report",
            "math_prompt",
            "neural_decision",
            "rag_context",
        ):
            working_state.pop(key, None)
        logger.debug("[auto_full_analysis] Cleaned ticker-specific state for route=general")

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "auto_full_analysis",
            "status": "started",
            "route": route,
        }
    )

    # Collector must run BEFORE Bob for any data-dependent request.
    _msg = str(working_state.get("message") or "").lower()
    _has_ticker = bool(working_state.get("ticker") or working_state.get("case_ticker"))
    _needs_scan = any(
        w in _msg
        for w in (
            "scan",
            "ache",
            "encontre",
            "find",
            "busque",
            "procure",
            "penny",
            "momentum",
            "catalyst",
            "catalisador",
            "recomend",
            "recomendacao",
            "sugira",
            "sugestao",
            "papel",
            "ticket",
            "ordem",
            "comprar",
            "vender",
            "trade",
            "investir",
            "investimento",
            "acao",
            "stock",
            "analise",
            "analyze",
            "analisa",  # single-ticker analysis
        )
    )
    should_collect_market = bool(
        route in {"market_scan", "ticker_analysis"}
        or working_state.get("force_auto_collect")
        or _needs_scan  # ANY data-related request, with or without ticker
    )

    from core.pipeline.resilience import try_run_async

    # Run collector SYNCHRONOUSLY when data is needed.
    # Previously ran via try_run_async which fire-and-forgets — collector
    # finished AFTER agent already built its prompt without data_context.
    if should_collect_market:
        try:
            await _do_collect(
                working_state,
                output,
                should_collect_market,
                route,
                config,
                _merge_node_update,
                _mark_step,
            )
        except Exception as collect_err:
            _merge_node_update(
                working_state,
                output,
                {"errors": [f"auto_full_analysis.collect_data:{collect_err}"]},
            )
    else:
        # Non-critical collection can run async
        _, collect_err = await try_run_async(
            "auto_full_analysis.collect_data",
            _do_collect,
            working_state,
            output,
            should_collect_market,
            route,
            config,
            _merge_node_update,
            _mark_step,
            fallback=None,
            log_level="warning",
        )
        if collect_err:
            _merge_node_update(
                working_state,
                output,
                {"errors": [f"auto_full_analysis.collect_data:{collect_err}"]},
            )

    ticker = str(
        working_state.get("ticker") or (working_state.get("data") or {}).get("ticker") or ""
    ).upper()
    data_context = str(working_state.get("data_context") or working_state.get("message") or "")

    try:
        math_hub = MathHub()
        math_report = math_hub.calculate_all(working_state)
        math_prompt = math_hub.to_deepseek_prompt(math_report)
        math_update: dict[str, Any] = {"math_report": math_report, "math_prompt": math_prompt}
        if math_prompt:
            existing_context = str(working_state.get("data_context") or data_context or "")
            math_update["data_context"] = (
                f"{existing_context}\n\n{math_prompt}" if existing_context else math_prompt
            )
        _merge_node_update(working_state, output, math_update)
        _mark_step("math_hub")
        data_context = str(working_state.get("data_context") or data_context)
        writer(
            {
                "type": "MATH_REPORT",
                "run_id": run_id,
                "ticker": math_report.get("ticker"),
                "coverage": math_report.get("coverage"),
                "summary": math_report.get("summary"),
                "modules": math_report.get("modules"),
                "numbers": math_report.get("numbers"),
            }
        )
    except Exception as exc:
        _merge_node_update(
            working_state,
            output,
            {"errors": [f"auto_full_analysis.math_hub:{exc}"]},
        )

    # Market experts only run after market/ticker evidence is actually present.
    # SKIP if data came from learner cache (already pre-computed)
    expert_results: list[dict[str, Any]] = []
    data_from_cache = working_state.get("_data_from_cache") or (
        isinstance(working_state.get("data"), dict)
        and working_state["data"].get("price", {}).get("source") == "learner_24_7_cache"
    )
    should_run_market_stack = (
        not data_from_cache
        and bool(working_state.get("scan") or working_state.get("data"))
        and (
            should_collect_market
            or route in {"market_scan", "ticker_analysis"}
            or working_state.get("force_auto_market_stack")
        )
    )
    if data_from_cache:
        _mark_step("experts", {"status": "skipped", "reason": "cache_hit"})
    if should_run_market_stack:
        if not ticker:
            scan_candidates = (working_state.get("scan") or {}).get("candidates", [])
            if scan_candidates:
                ticker = str(scan_candidates[0].get("ticker") or "").upper()
                if ticker:
                    working_state["ticker"] = ticker

        roles = [
            "macro_risk",
            "fundamental_value",
            "momentum_technical",
            "contrarian_opportunity",
            "sentiment",
            "social_forensics",
        ]

        replicas = max(1, int(os.getenv("SUPEREZIO_EXPERT_REPLICAS", "1")))
        concurrency = max(1, int(os.getenv("SUPEREZIO_EXPERT_CONCURRENCY", "3")))
        semaphore = asyncio.Semaphore(concurrency)

        async def _run_one_expert(role: str, replica_id: int) -> list[dict[str, Any]]:
            async with semaphore:
                try:
                    res = await node_expert(
                        {
                            **working_state,
                            "role": role,
                            "replica_id": replica_id,
                            "ticker": ticker,
                            "data_context": data_context,
                        },
                        gateway=gateway,
                    )
                    out: list[dict[str, Any]] = []
                    for expert_result in res.get("expert_results", []):
                        expert_result.setdefault("role", role)
                        expert_result.setdefault("replica_id", replica_id)
                        expert_result.setdefault(
                            "provider", EXPERT_PROVIDERS.get(role, "unknown")
                        )
                        out.append(expert_result)
                    return out
                except Exception as exc:
                    return [
                        {
                            "role": role,
                            "replica_id": replica_id,
                            "ok": False,
                            "error": str(exc)[:200],
                            "provider": EXPERT_PROVIDERS.get(role, "?"),
                        }
                    ]

        jobs = [
            _run_one_expert(role, replica_id)
            for role in roles
            for replica_id in range(1, replicas + 1)
        ]
        for batch in await asyncio.gather(*jobs):
            expert_results.extend(batch)

        _merge_node_update(working_state, output, {"expert_results": expert_results})
        _mark_step(
            "expert_committee",
            {
                "roles_ran": len(expert_results),
                "replicas": replicas,
                "concurrency": concurrency,
            },
        )
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

        red_team_agents = max(0, int(os.getenv("SUPEREZIO_RED_TEAM_AGENTS", "0")))
        judge_agents = max(0, int(os.getenv("SUPEREZIO_JUDGE_AGENTS", "0")))
        red_team_results: list[dict[str, Any]] = []
        judge_results: list[dict[str, Any]] = []
        auditor_result: dict[str, Any] | None = None

        if red_team_agents > 0:
            red_jobs = [
                _run_one_expert(f"red_team_agent_{i}", 1) for i in range(1, red_team_agents + 1)
            ]
            for batch in await asyncio.gather(*red_jobs):
                red_team_results.extend(batch)
            _merge_node_update(working_state, output, {"red_team_results": red_team_results})

        if judge_agents > 0:
            async def _run_judge(idx: int) -> list[dict[str, Any]]:
                async with semaphore:
                    try:
                        res = await node_expert(
                            {
                                **working_state,
                                "role": f"judge_agent_{idx}",
                                "replica_id": 1,
                                "ticker": ticker,
                                "data_context": data_context,
                                "provider_name": "daytrade_judge",
                            },
                            gateway=gateway,
                        )
                        return list(res.get("expert_results", []))
                    except Exception as exc:
                        return [
                            {
                                "role": f"judge_agent_{idx}",
                                "ok": False,
                                "error": str(exc)[:200],
                                "provider": "daytrade_judge",
                            }
                        ]

            judge_jobs = [_run_judge(i) for i in range(1, judge_agents + 1)]
            for batch in await asyncio.gather(*judge_jobs):
                judge_results.extend(batch)
            _merge_node_update(working_state, output, {"judge_results": judge_results})

        if os.getenv("SUPEREZIO_DAYTRADE_AUDITOR_MODEL"):
            try:
                auditor_res = await node_expert(
                    {
                        **working_state,
                        "role": "auditor_agent",
                        "replica_id": 1,
                        "ticker": ticker,
                        "data_context": data_context,
                        "provider_name": "daytrade_auditor",
                    },
                    gateway=gateway,
                )
                if auditor_res.get("expert_results"):
                    auditor_result = auditor_res["expert_results"][0]
            except Exception as exc:
                auditor_result = {
                    "role": "auditor_agent",
                    "ok": False,
                    "error": str(exc)[:200],
                    "provider": "daytrade_auditor",
                }
            _merge_node_update(working_state, output, {"auditor_result": auditor_result})
    # ── IBKR portfolio snapshot: always inject current positions ──
    try:
        from core.trading.portfolio_snapshot import fetch_portfolio_snapshot

        loop = asyncio.get_running_loop()
        portfolio_context = await asyncio.wait_for(
            loop.run_in_executor(None, fetch_portfolio_snapshot, "en"),
            timeout=8.0,
        )
        _merge_node_update(working_state, output, {"portfolio_snapshot": portfolio_context})
        _mark_step("system_status")
        _mark_step("portfolio_snapshot")
    except Exception as exc:
        logger.warning(
            "IBKR snapshot failed (%s: %s) — falling back to offline", type(exc).__name__, exc
        )
        _merge_node_update(
            working_state,
            output,
            {"portfolio_snapshot": "IBKR offline — portfolio data unavailable"},
        )
        _mark_step("system_status", {"ibkr": "offline"})

    # ═══════════════════════════════════════════════════════
    # PARALLEL: f51, neural, sdca, rag, guardrails — todos independentes
    # ═══════════════════════════════════════════════════════
    if ticker:
        # These nodes are sequential by contract: neural depends on F51,
        # SDCA depends on neural, and RAG/guardrails need the full state.
        decision_nodes = [
            ("f51", node_f51_verdict),
            ("neural_decision", node_neural_decision),
            ("sdca_firewall", node_sdca_firewall),
            ("rag_forensics", node_rag_forensics),
            ("guardrail_hub", node_guardrail_hub),
        ]

        for label, node in decision_nodes:
            try:
                result = await node(working_state)
            except Exception as exc:
                _merge_node_update(
                    working_state, output, {"errors": [f"auto_full_analysis.{label}:{exc}"]}
                )
            else:
                _merge_node_update(working_state, output, result)
    else:
        try:
            result = await node_sdca_firewall(working_state)
            _merge_node_update(working_state, output, result)
        except Exception as exc:
            _merge_node_update(
                working_state, output, {"errors": [f"auto_full_analysis.sdca_firewall:{exc}"]}
            )
        try:
            result = await node_guardrail_hub(working_state)
            _merge_node_update(working_state, output, result)
            _mark_step("guardrails")
        except Exception as exc:
            _merge_node_update(
                working_state, output, {"errors": [f"auto_full_analysis.guardrail_hub:{exc}"]}
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
            "has_portfolio": bool(working_state.get("portfolio_snapshot")),
            "has_math_report": bool(working_state.get("math_report")),
            "has_guardrail_hub": bool(working_state.get("guardrail_hub")),
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

    async def _trinity(state: dict) -> dict:
        return await node_trinity(state, gateway=gateway)

    async def _agent(state: dict) -> dict:
        return await node_agent(state, gateway=gateway, config=config, mandamentos=mandamentos)

    async def _tool_executor(state: dict) -> dict:
        return await node_tool_executor(state, gateway=gateway, config=config)

    from .nodes.auto_execute_paper import (
        auto_execute_paper as _auto_execute_paper,
    )  # extracted from inline (Phase 3)

    async def _explanation(state: dict) -> dict:
        return await node_explanation(state)

    async def _blocked(state: dict) -> dict:
        return await node_blocked(state)

    builder = StateGraph(PipelineState)

    builder.add_node("orchestrator_primary", _orchestrator)
    builder.add_node("auto_full_analysis", _auto)
    builder.add_node("trinity", _trinity)
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
    # After full analysis, run Trinity deliberation before Bob sees the state.
    builder.add_edge("auto_full_analysis", "trinity")
    builder.add_conditional_edges(
        "trinity",
        route_after_trinity,
        {
            "agent": "agent",
            "respond_blocked": "respond_blocked",
        },
    )

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

        # ── Bob Memory: UnifiedRetriever com perfil + contexto formatado ──
        try:
            from core.memory import get_unified_retriever

            retriever = get_unified_retriever()

            # 1. Extrai/atualiza perfil da mensagem
            profile_updates = retriever.extract_profile_from_message(message)
            for key, value, confidence in profile_updates:
                retriever.upsert_profile(key, value, confidence)

            # 2. Renderiza contexto completo no formato EXATO
            memory_context = retriever.render_memory_context(
                session_id=session_id,
                message=message,
                ticker=ticker,
            )

            # 3. Injeta no context (antes do prompt do Bob)
            if memory_context:
                context = f"{memory_context}\n\n{context}" if context else memory_context

            # 4. Injeta lições aprendidas do FeedbackLoop
            try:
                from core.trading.feedback_loop import get_feedback_loop

                fb_loop = get_feedback_loop()
                if fb_loop:
                    learning_context = fb_loop.render_for_bob(max_chars=1000)
                    if learning_context:
                        context = (
                            f"{context}\n\n{learning_context}" if context else learning_context
                        )
                        logger.debug(
                            "[memory] Injected learning context (%d chars)", len(learning_context)
                        )
            except Exception as exc:
                logger.debug("[memory] Failed to load learning context: %s", exc)

        except Exception as exc:
            logger.warning("[memory] Failed to load unified context: %s", exc)

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

            # ── Bob Memory: salva turno + inger no Knowledge Graph ──
            if response_chunks:
                try:
                    from core.memory import (
                        get_conversation_memory,
                        get_graph_bridge,
                    )

                    mem = get_conversation_memory()
                    response_text = "".join(response_chunks)

                    # Extrai metadados da resposta
                    category = "general"
                    verdict = ""
                    confidence = 0.0
                    thesis = ""

                    # Tenta extrair veredito do final_answer
                    if "Model verdict:" in response_text or "Final verdict:" in response_text:
                        for line in response_text.split("\n"):
                            if "Model verdict:" in line or "Final verdict:" in line:
                                verdict = line.split(":")[-1].strip().upper()
                                break

                    # Tenta extrair confiança
                    import re

                    conf_match = re.search(r"Confidence:\s*(\d+)", response_text)
                    if conf_match:
                        confidence = float(conf_match.group(1))

                    # Detecta categoria baseada no state
                    if ticker:
                        category = "ticker_analysis"
                    elif "scan" in context.lower() or "candidates" in response_text.lower():
                        category = "market_scan"

                    # Cria turno
                    turn = mem.add_turn(
                        session_id=session_id,
                        user_message=message,
                        bob_response=response_text[:5000],
                        context_summary=context[:500] if context else "",
                        ticker_discussed=ticker,
                        thesis_formed=thesis,
                        verdict=verdict,
                        confidence=confidence,
                        category=category,
                    )
                    logger.debug("[memory] Saved turn for session %s", session_id)

                    # ── Knowledge Graph: ingere turno (Fase 4) ──
                    try:
                        graph_bridge = get_graph_bridge()
                        graph_bridge.ingest_conversation_turn(turn)
                        logger.debug("[memory] Ingested turn into knowledge graph")
                    except Exception as e:
                        logger.debug("[memory] Graph ingestion skipped: %s", e)

                except Exception as exc:
                    logger.warning("[memory] Failed to save conversation turn: %s", exc)

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
                "trinity",
                "math_hub",
                "guardrail_hub",
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
