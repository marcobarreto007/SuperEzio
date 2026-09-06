"""Pipeline v4 graph builder - thin, readable, no business logic."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from core.config.logging_config import get_logger
from core.evidence import EvidenceRun, generate_html_report, save_evidence
from core.math.math_hub import MathHub

from .contracts import PipelineState
from .nodes import (
    node_agent,
    node_blocked,
    node_collector,
    node_explanation,
    node_orchestrator,
    node_tool_executor,
    route_after_agent,
)
from .nodes.experts import (
    EXPERT_PROVIDERS,
    EXPERT_ROLES,
    expert_concurrency,
    node_collect_experts,
    node_expert,
)
from .nodes.f51 import node_f51_verdict
from .nodes.guardrail_hub import node_guardrail_hub
from .nodes.neural_decision import node_neural_decision
from .nodes.rag import node_rag_forensics
from .nodes.sdca_firewall import node_sdca_firewall
from .nodes.trinity import node_trinity

logger = get_logger(__name__)


def _is_real_evidence_response(text: str) -> bool:
    """True only when the response holds real content.

    The explanation node streams straight to the client and marks its output
    with the "(streamed)" placeholder — that placeholder must not satisfy
    "evidence.response already recorded", or the streamed chunks never get
    persisted (runtime-verifier 2026-08-23).
    """
    return text not in ("", "(streamed)")


__all__ = ["PipelineApp", "build_graph", "route_after_orchestrator", "route_after_trinity"]


def route_after_agent_paper_gate(state: dict) -> str:
    """Route agent output to tool_executor / explanation / auto_execute_paper.

    auto_execute_paper is only reachable when the cognitive contract granted
    the submit_paper_order tool — advisory and casual prompts never enter the
    paper-execution node (fail-closed: no grant, no auto-execution).
    """
    base = route_after_agent(state)
    if base != "explanation":
        return base
    if "submit_paper_order" in (state.get("allowed_tools") or []):
        return "auto_execute_paper"
    return "explanation"


# Words that require market data collection. Matched WORD-INITIALLY (prefix
# boundary): "acao" must not fire inside "educacao"/"alocacao" (reproduced
# 2026-08-21 — a PT allocation prompt triggered a full market scan through a
# substring hit), while inflected forms ("analisando", "investirei") and
# stems ("recomend...") keep working.
_SCAN_NEED_KEYWORDS = (
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
    "analisa",
)


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
        # scanner_allowed comes from orchestrator's cognitive_contract — it
        # is True when the user's message is an explicit market discovery /
        # scan request, even if a ticker happens to be in the UI state.
        _is_market_discovery = bool(working_state.get("scanner_allowed"))
        collector_route = (
            "ticker_analysis"
            if working_state.get("ticker") and route != "market_scan" and not _is_market_discovery
            else "market_scan"
        )
        collector_result = await node_collector(
            {**working_state, "route": collector_route},
            config=config,
        )
    if collector_result:
        _merge(working_state, output, collector_result)
        _mark("data_collection")


def _refresh_math_f51_unified(working_state: dict, output: dict) -> None:
    """Fill math_report.f51_unified after the F51 node runs.

    MathHub runs before experts/F51, so the module is skipped at that stage
    on purpose. Once a real verdict exists, expose it instead of leaving
    the skip as if F51 never ran.
    """
    verdict = working_state.get("f51_verdict")
    math_report = working_state.get("math_report")
    if not isinstance(verdict, dict) or not verdict or not isinstance(math_report, dict):
        return
    modules = math_report.setdefault("modules", {})
    if not isinstance(modules, dict):
        return
    modules["f51_unified"] = {"status": "ok", "values": dict(verdict)}
    coverage = math_report.get("coverage")
    if isinstance(coverage, dict):
        skipped = [name for name in (coverage.get("skipped") or []) if name != "f51_unified"]
        ok = list(coverage.get("ok") or [])
        if "f51_unified" not in ok:
            ok.append("f51_unified")
        coverage["skipped"] = skipped
        coverage["ok"] = ok
        coverage["ok_modules"] = len(ok)
        coverage["skipped_modules"] = len(skipped)
    numbers = math_report.get("numbers")
    if isinstance(numbers, dict):
        numbers["f51_decision_score"] = verdict.get("decision_score", verdict.get("confidence"))
    working_state["math_report"] = math_report
    output["math_report"] = math_report


def _is_simple_query(state: dict) -> bool:
    """Check if user query is simple enough to skip Trinity (fast path).

    Simple = 1 ticker + basic indicator keywords only.
    Complex = portfolio, strategy, macro, valuation, DCF, or multi-ticker.
    Buy/sell/recommendation questions NEVER fast-path — Bob must consult
    Trinity, experts, F51 and SDCA before answering.
    """
    msg = str(state.get("message") or "").lower()
    ticker = str(state.get("ticker") or "").upper()
    if not ticker:
        return False

    # Decision questions — NEVER fast-path (full pipeline required)
    decision_keywords = (
        "compro",
        "comprar",
        "compra",
        "vendo",
        "vender",
        "venda",
        "buy",
        "sell",
        "short",
        "recomendação",
        "recomendacao",
        "recomenda",
        "recomendaria",
        "vale a pena",
        "ou não",
        "ou nao",
        "analisa",
        "analise",
        "análise",
        "analyze",
        "dica",
        "tese",
        "thesis",
        "invalidacao",
        "invalidação",
        "alvo",
        "stop",
        "direcao",
        "direção",
        "investir",
        "investimento",
        "grafico",
        "gráfico",
        "chart",
        "vela",
        "velas",
        "candle",
        "porque",
        "por que",
        "evidencia",
        "evidência",
        "experts",
        "expert",
        "duvida",
        "dúvida",
    )
    if any(kw in msg for kw in decision_keywords):
        return False

    # Complex topics — NEVER fast-path
    complex_keywords = (
        "portfolio",
        "alocação",
        "alocacao",
        "estrategia",
        "estratégia",
        "macro",
        "crise",
        "valuation",
        "dcf",
        "divida",
        "dívida",
        "balanço",
        "balanco",
        "crescimento",
        "projeção",
        "projecao",
        "setor",
        "concorrencia",
        "concorrência",
        "diversificação",
        "diversificacao",
        "hedge",
        "lucro",
        "receita",
        "margem",
        "ebitda",
    )
    if any(kw in msg for kw in complex_keywords):
        return False

    # Strip ticker from message
    msg_clean = msg.replace(ticker.lower(), "").strip()
    if not msg_clean:
        return True  # just the ticker → simple

    # Allow simple indicator keywords and common stopwords only
    simple_keywords = {
        "price",
        "preço",
        "preco",
        "cotação",
        "cotacao",
        "rsi",
        "macd",
        "tendência",
        "tendencia",
        "agora",
        "now",
        "valor",
        "atual",
        "current",
        "hoje",
        "today",
        "status",
        "indicador",
        "indicadores",
        "quote",
        "cotation",
    }
    stopwords = {
        "the",
        "is",
        "de",
        "da",
        "do",
        "em",
        "para",
        "com",
        "um",
        "uma",
        "os",
        "as",
        "no",
        "na",
        "a",
        "o",
        "e",
        "que",
        "dos",
        "das",
        "num",
        "numa",
        "me",
        "se",
        "por",
        "ao",
        "aos",
        "nao",
        "não",
    }
    allowed = simple_keywords | stopwords

    words = {w.strip(".,!?;:()[]{}\"'") for w in msg_clean.split()}
    meaningful = {w for w in words if len(w) > 1}
    extra = meaningful - allowed
    if extra:
        logger.debug("FAST_PATH_BLOCKED ticker=%s extra_words=%s", ticker, extra)
        return False

    return True


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
    from core.pipeline.intents import _is_casual_message

    _is_casual = _is_casual_message(_msg) or working_state.get("cognitive_mode") == "CASUAL"
    _has_ticker = bool(working_state.get("ticker") or working_state.get("case_ticker"))
    _needs_scan = any(re.search(rf"\b{re.escape(w)}", _msg) for w in _SCAN_NEED_KEYWORDS)
    if _is_casual:
        should_collect_market = False
    else:
        should_collect_market = bool(
            route in {"market_scan", "ticker_analysis"}
            or working_state.get("force_auto_collect")
            or _needs_scan  # ANY data-related request, with or without ticker
            or _has_ticker  # ANY ticker present — MathHub needs data for RSI/MACD/Sharpe
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
        # Catch amplo deliberado: node_collector é fronteira de melhor
        # esforço (rede/scanner podem falhar de formas imprevisíveis); o
        # pipeline segue com erro registrado em vez de abortar.
        except Exception as collect_err:  # noqa: BLE001
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

    # MathHub is a declared PipelineState key (math_report): every non-casual
    # answer carries one, even without collected data — allocation/framework
    # answers compute portfolio math from the message, not OHLCV. Only pure
    # casual greetings skip it (fast path).
    if not _is_casual:
        logger.info(
            "MATHHUB_INPUT has_data=%s ohlcv_count=%s ticker=%s",
            "data" in working_state,
            len(working_state.get("data", {}).get("ohlcv", [])),
            ticker,
        )
        try:
            math_hub = MathHub()
            math_report = math_hub.calculate_all(working_state)
            math_prompt = math_hub.to_deepseek_prompt(math_report)
            math_update: dict[str, Any] = {"math_report": math_report, "math_prompt": math_prompt}
            _merge_node_update(working_state, output, math_update)
            _mark_step("math_hub")
            data_context = str(working_state.get("data_context") or data_context)
            logger.info(
                "MATHHUB_RESULT ticker=%s coverage=%s latest_price=%s modules_ok=%s",
                math_report.get("ticker"),
                math_report.get("coverage"),
                "summary" in math_report and math_report.get("summary", {}).get("latest_price"),
                "coverage" in math_report and math_report.get("coverage", {}).get("ok_modules"),
            )
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
        # Catch amplo deliberado: MathHub degrada internamente, mas erros
        # residuais (matemática/format) não podem abortar o pipeline — vão
        # para a lista de erros e o fluxo segue.
        except Exception as exc:  # noqa: BLE001
            _merge_node_update(
                working_state,
                output,
                {"errors": [f"auto_full_analysis.math_hub:{exc}"]},
            )

    from core.pipeline.intents import is_investment_thesis_request

    _requires_full_committee = bool(
        _has_ticker and is_investment_thesis_request(str(working_state.get("message") or ""))
    )

    # ── FAST PATH: skip Trinity for simple queries ──
    # Simple queries (single ticker + basic indicator) go directly to Bob
    # with math_report + f51_verdict, bypassing Genie/Deep deliberation.
    # Investment tip/thesis with a ticker never fast-paths.
    if not _is_casual and not _requires_full_committee and _is_simple_query(working_state):
        skip_update = {
            "skip_trinity": True,
            "trinity_report": "TRINITY_SKIPPED_FAST_PATH",
            "trinity_structured": {"skipped": True, "reason": "fast_path_simple_query"},
            "trinity_blocked": False,
        }
        _merge_node_update(working_state, output, skip_update)
        logger.info(
            "FAST_PATH ticker=%s route=%s reason=simple_query",
            ticker,
            route,
        )

    # Market experts run after evidence exists. Cache may skip the committee
    # only on a true quote/indicator fast-path — never on a decision.
    expert_results: list[dict[str, Any]] = []
    data_from_cache = working_state.get("_data_from_cache") or (
        isinstance(working_state.get("data"), dict)
        and working_state["data"].get("price", {}).get("source") == "learner_24_7_cache"
    )
    # Cache can skip the expert committee only on true quote/indicator fast-path.
    # Decision, chart, and analysis questions still consult the living stack.
    skip_experts_for_cache = (
        bool(data_from_cache) and _is_simple_query(working_state) and not _requires_full_committee
    )
    should_run_market_stack = (
        not _is_casual
        and not skip_experts_for_cache
        and (
            bool(working_state.get("scan") or working_state.get("data")) or _requires_full_committee
        )
        and (
            should_collect_market
            or route in {"market_scan", "ticker_analysis"}
            or working_state.get("force_auto_market_stack")
            or _requires_full_committee
        )
    )
    if skip_experts_for_cache:
        _mark_step("experts", {"status": "skipped", "reason": "cache_hit"})
    if should_run_market_stack:
        if not ticker:
            scan_candidates = (working_state.get("scan") or {}).get("candidates", [])
            if scan_candidates:
                ticker = str(scan_candidates[0].get("ticker") or "").upper()
                if ticker:
                    working_state["ticker"] = ticker

        roles = EXPERT_ROLES

        # The official profile has one inference slot. Replicas above one
        # multiply wall-clock latency without adding model diversity.
        replicas = 1
        # Experts run on the cloud DeepSeek API (2026-09-05): the old
        # concurrency=1 pinned a single local llama-server slot and serialized
        # the committee. Fan out now (env SUPEREZIO_EXPERT_CONCURRENCY).
        concurrency = expert_concurrency(len(roles))
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
                        expert_result.setdefault("provider", EXPERT_PROVIDERS.get(role, "unknown"))
                        out.append(expert_result)
                    return out
                # Fronteira de melhor esforço: chamada LLM (node_expert) falha
                # de formas heterogêneas (rede, parse, provider); o expert vira
                # resultado de erro estruturado, nunca aborta o stack.
                except Exception as exc:  # noqa: BLE001
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
        # Nó de pipeline arbitrário (comitê de experts) — catch amplo
        # deliberado: falha vira resumo de erro, o pipeline segue.
        except Exception as exc:  # noqa: BLE001
            _merge_node_update(
                working_state,
                output,
                {
                    "expert_summary": f"Expert collection error: {exc}",
                    "errors": [f"auto_full_analysis.experts:{exc}"],
                },
            )

        red_team_agents = min(max(0, int(os.getenv("SUPEREZIO_RED_TEAM_AGENTS", "0"))), 1)
        judge_agents = min(max(0, int(os.getenv("SUPEREZIO_JUDGE_AGENTS", "0"))), 1)
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
                    # Mesma fronteira de melhor esforço do expert: falha do
                    # juiz vira resultado de erro estruturado.
                    except Exception as exc:  # noqa: BLE001
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
            # Fronteira de melhor esforço: auditor falho vira resultado de
            # erro estruturado em vez de abortar o stack de decisão.
            except Exception as exc:  # noqa: BLE001
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
    # Fronteira deliberada de melhor esforço: snapshot IBKR roda em executor
    # (thread) e pode falhar de muitas formas (timeout, rede, ib_insync);
    # qualquer falha degrada para "IBKR offline", nunca aborta o turno.
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "IBKR snapshot failed (%s: %s) — falling back to offline", type(exc).__name__, exc
        )
        _merge_node_update(
            working_state,
            output,
            {"portfolio_snapshot": "IBKR offline — portfolio data unavailable"},
        )
        _mark_step("system_status", {"ibkr": "offline"})

    # ── PennyLab auto-detection (whale, pump & dump, volume spike) ──
    # Automatico — roda em todo ticker com dados, sem depender do Bob chamar tools
    if ticker and (working_state.get("data") or working_state.get("scan")):
        try:
            from experts.pennylab.experts.pump_dump_expert import PumpDumpExpert
            from experts.pennylab.experts.volume_spike_expert import VolumeSpikeExpert
            from experts.pennylab.experts.whale_print_expert import WhalePrintExpert
            from experts.pennylab.schemas import SignalInput

            _data = working_state.get("data") or {}
            _tech = _data.get("technicals") or {}
            _profile = _data.get("profile") or {}
            _price_data = _data.get("price") or {}

            _signal = SignalInput(
                ticker=ticker,
                price=_tech.get("price") or _price_data.get("latest") or _price_data.get("price"),
                prev_close=_tech.get("prev_close") or _tech.get("previousClose"),
                volume=_tech.get("volume"),
                avg_volume_10d=_tech.get("avg_volume_10d") or _tech.get("averageVolume"),
                market_cap=_profile.get("market_cap") or _profile.get("marketCap"),
                shares_float=_profile.get("shares_float") or _profile.get("floatShares"),
                rsi_14=_tech.get("rsi_14") or _tech.get("rsi"),
                source="pipeline_auto",
            )

            _vol_res = VolumeSpikeExpert().evaluate(_signal)
            _whale_res = WhalePrintExpert().evaluate(_signal)
            _pump_res = PumpDumpExpert().evaluate(_signal)

            _merge_node_update(
                working_state,
                output,
                {
                    "pennylab_detection": {
                        "volume_spike": {
                            "score": _vol_res.score,
                            "ratio": _vol_res.ratio,
                            "label": _vol_res.label,
                            "confidence": _vol_res.confidence,
                        },
                        "whale_print": {
                            "score": _whale_res.score,
                            "label": _whale_res.label,
                            "confidence": _whale_res.confidence,
                        },
                        "pump_dump": {
                            "score": _pump_res.score,
                            "phase": _pump_res.phase,
                            "confidence": _pump_res.confidence,
                        },
                    },
                },
            )
            _mark_step(
                "pennylab_detection",
                {
                    "volume_spike": _vol_res.label,
                    "whale_print": _whale_res.label,
                    "pump_dump": _pump_res.phase,
                },
            )
            writer(
                {
                    "type": "PENNYLAB_DETECTION",
                    "run_id": run_id,
                    "ticker": ticker,
                    "volume_spike": {"label": _vol_res.label, "score": _vol_res.score},
                    "whale_print": {"label": _whale_res.label, "score": _whale_res.score},
                    "pump_dump": {"phase": _pump_res.phase, "score": _pump_res.score},
                }
            )
        # Catch amplo deliberado: bloco PennyLab importa e executa experts
        # arbitrários; detecção é complementar (não crítica) — qualquer
        # falha vira erro registrado, o pipeline segue.
        except Exception as exc:  # noqa: BLE001
            _merge_node_update(
                working_state,
                output,
                {"errors": [f"auto_full_analysis.pennylab:{exc}"]},
            )

    # ── Mangala Engine — caçador de oportunidades baratas ──
    # Roda em qualquer scan/análise de mercado, busca ativamente stocks < $10
    if route in {"market_scan", "ticker_analysis"} or _needs_scan:
        try:
            from core.pipeline.nodes.mangala import (
                format_mangala_for_bob,
                scan_mangala_opportunities,
            )
            from core.scanner.penny_scanner import scan_penny_stocks
            from data.data_hub import hub as data_hub

            mangala_opps = scan_mangala_opportunities(
                data_hub=data_hub,
                scanner=scan_penny_stocks,
            )

            if mangala_opps:
                high_conviction = [o for o in mangala_opps if o.get("signal") == "MANGALA!"]
                mangala_update: dict[str, Any] = {
                    "mangala_opportunities": mangala_opps,
                    "mangala_has_high_conviction": len(high_conviction) > 0,
                }

                if high_conviction:
                    mangala_update["mangala_prompt"] = format_mangala_for_bob(mangala_opps)
                    writer(
                        {
                            "type": "MANGALA_OPPORTUNITIES",
                            "run_id": run_id,
                            "opportunities": [
                                {"ticker": o["ticker"], "score": o["score"], "signal": o["signal"]}
                                for o in high_conviction
                            ],
                        }
                    )

                _merge_node_update(working_state, output, mangala_update)

            _mark_step("mangala_scan")
        # Catch amplo deliberado: scan Mangala importa scanners e hubs
        # arbitrários; caça de oportunidades é melhor esforço — falha vira
        # erro registrado, o pipeline segue.
        except Exception as exc:  # noqa: BLE001
            _merge_node_update(
                working_state,
                output,
                {"errors": [f"auto_full_analysis.mangala:{exc}"]},
            )

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
            # Fronteira de melhor esforço: nós de decisão arbitrários (f51,
            # neural, sdca, rag, guardrails) falham de formas imprevisíveis;
            # o erro é registrado e os demais nós do loop seguem.
            except Exception as exc:  # noqa: BLE001
                _merge_node_update(
                    working_state, output, {"errors": [f"auto_full_analysis.{label}:{exc}"]}
                )
            else:
                _merge_node_update(working_state, output, result)
                if label == "f51":
                    _refresh_math_f51_unified(working_state, output)
    else:
        try:
            result = await node_sdca_firewall(working_state)
            _merge_node_update(working_state, output, result)
        # Nó de pipeline arbitrário — catch amplo deliberado: falha vira erro
        # registrado e o guardrail a seguir ainda roda.
        except Exception as exc:  # noqa: BLE001
            _merge_node_update(
                working_state, output, {"errors": [f"auto_full_analysis.sdca_firewall:{exc}"]}
            )
        try:
            result = await node_guardrail_hub(working_state)
            _merge_node_update(working_state, output, result)
            _mark_step("guardrails")
        # Nó de pipeline arbitrário — catch amplo deliberado: falha de
        # guardrails vira erro registrado, nunca aborta o turno.
        except Exception as exc:  # noqa: BLE001
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
) -> PipelineApp:
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
        if state.get("skip_trinity"):
            ticker = state.get("ticker", "")
            logger.info("FAST_PATH_SKIP_TRINITY ticker=%s", ticker)
            return {}
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
    # are auto-submitted to IBKR when Bob produces a PAPER_TICKET — but only
    # when the cognitive contract granted the submit_paper_order tool.
    # Advisory/casual prompts (allocation, greetings) never enter the
    # paper-execution node (fail-closed: no grant, no auto-execution).
    builder.add_conditional_edges(
        "agent",
        route_after_agent_paper_gate,
        {
            "tool_executor": "tool_executor",
            "explanation": "explanation",
            "auto_execute_paper": "auto_execute_paper",
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
            # Catch amplo deliberado: shutdown não pode falhar por erro de
            # descarregamento de gateway — melhor esforço com log.
            except Exception as exc:  # noqa: BLE001
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
            evidence = EvidenceRun(prompt=message, ticker=ticker, run_id=run_id)
            evidence.start()
        # Evidência é best-effort: falha ao iniciar não pode abortar o turno.
        except Exception as exc:  # noqa: BLE001
            logger.debug("[evidence] Failed to start evidence run: %s", exc)

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
            # Melhor esforço deliberado: lições do FeedbackLoop são
            # enriquecimento — falha não pode abortar o contexto.
            except Exception as exc:  # noqa: BLE001
                logger.debug("[memory] Failed to load learning context: %s", exc)

        # Catch amplo deliberado: memória (retriever/perfil/contexto) é
        # melhor esforço — falha degrada para sem contexto, nunca aborta.
        except Exception as exc:  # noqa: BLE001
            logger.warning("[memory] Failed to load unified context: %s", exc)

        def _finalize_evidence() -> None:
            nonlocal evidence_saved
            if evidence is None or evidence_saved:
                return
            try:
                if response_chunks and not _is_real_evidence_response(evidence.response):
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
            # Melhor esforço deliberado: falha ao salvar evidência não pode
            # abortar a resposta do pipeline.
            except Exception as exc:  # noqa: BLE001
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
                                elif evt_type == "EXPERT_DONE":
                                    # experts.py emits EXPERT_DONE {role, provider,
                                    # response} — the recorder listened for a
                                    # legacy event name and experts.json was
                                    # always empty (runtime-verifier 2026-08-23).
                                    evidence.record_expert(
                                        expert_name=payload.get("role", "unknown"),
                                        verdict=payload.get("verdict", "?"),
                                        confidence=float(payload.get("confidence", 0)),
                                        provider=payload.get("provider", "unknown"),
                                        bob_readable=payload.get("response", ""),
                                    )
                                elif evt_type == "SDCA_COMPLETE":
                                    evidence.record_risk(payload)
                                elif evt_type == "SDCA_FIREWALL":
                                    # sdca_firewall.py emits SDCA_FIREWALL with
                                    # decision/confidence/ghost_tokens — risk.json
                                    # was always empty for the same reason.
                                    evidence.record_risk(payload)
                                elif evt_type == "F51_VERDICT":
                                    evidence.record_verdict(payload)
                            # Gravação de evidência é best-effort: falha
                            # pontual não pode quebrar o stream.
                            except Exception as exc:  # noqa: BLE001
                                logger.debug("[evidence] event record skipped: %s", exc)

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
                                    if node_name == "explanation" and _is_real_evidence_response(
                                        str(node_output.get("explanation", ""))
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
                        # Gravação de evidência é best-effort: falha no
                        # processamento de updates não pode quebrar o stream.
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("[evidence] updates record skipped: %s", exc)
                    continue

            _finalize_evidence()
            yield {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "graph",
                "status": "completed",
                "evidence_run_id": evidence.run_id if evidence else None,
            }
        # Fronteira final do stream: o grafo inteiro (nós arbitrários) roda
        # aqui — qualquer falha vira evento ERROR para o cliente, nunca deixa
        # o stream morrer silenciosamente.
        except Exception as exc:  # noqa: BLE001
            detail = str(exc) or exc.__class__.__name__
            if evidence is not None:
                try:
                    evidence.record_error("pipeline", detail)
                # Best-effort: falha ao registrar erro não pode mascarar o
                # erro principal do pipeline.
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[evidence] error record skipped: %s", exc)
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
                    # Ingestão no Knowledge Graph é melhor esforço; falha não
                    # pode abortar o salvamento do turno.
                    except Exception as e:  # noqa: BLE001
                        logger.debug("[memory] Graph ingestion skipped: %s", e)

                # Catch amplo deliberado: persistência de memória é melhor
                # esforço — falha não pode abortar o encerramento do turno.
                except Exception as exc:  # noqa: BLE001
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
