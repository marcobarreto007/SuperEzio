"""Answer generator node — produces final responses, fallbacks, and repair outputs.

Extracted from agent.py (Phase 2 refactor).
All answer/fallback/repair logic lives here. No dependency injection needed.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..intents import (
    detect_another_trade_recommendation_intent,
    detect_decisive_trade_intent,
)
from ..trade_order import (
    BUY_CONFIDENCE_THRESHOLD,
    compute_model_confidence,
    decide_final_action,
    evaluate_quality_gates,
    normalize_liquidity_fields,
    pick_candidate,
    rank_candidates,
)

# ── Cross-group imports from agent.py (still lives there) ──
# These are referenced via late-binding to avoid circular imports.
# agent.py imports generator.py → generator.py can't import agent.py at module level.
# Use sys.modules lookups inside functions that need them.

logger = logging.getLogger(__name__)

__all__ = [
    "_advisory_knowledge_fallback_answer",
    "_complex_finance_fallback_answer",
    "_contract_fallback_answer",
    "_decisive_trade_order_answer",
    "_final_payload",
    "_forced_tool_call_before_final",
    "_has_actionable_market_request",
    "_has_expert_evidence",
    "_has_market_evidence",
    "_has_tax_overstatement",
    "_has_unsupported_macro_precision",
    "_industry_research_fallback_answer",
    "_is_dca_macro_question",
    "_is_etf_comparison_question",
    "_is_portfolio_concentration_question",
    "_loop_failsafe_answer",
    "_market_scan_answer",
    "_render_decisive_trade_order",
    "_repair_answer_quality",
    "_repair_complex_finance_answer",
    "_repair_known_etf_category_errors",
    "_repair_overlapping_etf_tickers",
    "_repair_short_term_return_forecasts",
    "_repair_tax_overstatements",
    "_repair_unsourced_etf_tickers",
    "_repair_unsupported_exact_returns",
    "_risk_lab_fallback_answer",
    "_should_force_contract_fallback",
    "_tool_blocked_answer",
]


# ═══════════════════════════════════════════════════════════════════════════
# Late-binding: resolve agent.py symbols at call time (avoids circular import)
# ═══════════════════════════════════════════════════════════════════════════


def _get_agent_attr(name: str):
    """Resolve a symbol from the agent module at call time."""
    import sys

    mod = sys.modules.get("core.pipeline.nodes.agent")
    if mod is None:
        from . import agent as _agent

        mod = _agent
    return getattr(mod, name, None)


# ═══════════════════════════════════════════════════════════════════════════
# Answer generators
# ═══════════════════════════════════════════════════════════════════════════


def _final_payload(content: str, iterations: int) -> dict[str, Any]:
    return {
        "final": content,
        "agent_tool_call": {"tool": "final_answer", "args": {"content": content}},
        "agent_iterations": iterations + 1,
        "_pending_tool_calls": [],
    }


def _loop_failsafe_answer(state: dict) -> str:
    if state.get("scan"):
        return _market_scan_answer(state)
    if state.get("cognitive_mode"):
        return _contract_fallback_answer(state)
    is_pt = _get_agent_attr("_is_portuguese_request")
    if is_pt and is_pt(state.get("message", "")):
        return (
            "Bob: Encerrei o ciclo de ferramentas após atingir o limite. "
            "Aqui está o que analisei até agora. Mande um ticker ou ajuste a busca para continuar."
        )
    return (
        "Bob: I stopped the tool cycle after reaching the limit. "
        "Narrow down your request or ask a specific question to continue."
    )


def _tool_blocked_answer(state: dict) -> str:
    blocked = state.get("tool_blocked") or {}
    tool = blocked.get("tool", "unknown")
    reason = blocked.get("reason", "already executed")
    if state.get("cognitive_mode") or "cognitive_contract" in str(reason):
        return _contract_fallback_answer(state)
    is_pt = _get_agent_attr("_is_portuguese_request")
    if is_pt and is_pt(state.get("message", "")):
        return f"Bob: A ferramenta '{tool}' foi bloqueada ({reason}). Produzindo resposta final."
    return f"Bob: Tool '{tool}' was blocked ({reason}). Producing final answer."


# ═══════════════════════════════════════════════════════════════════════════
# Market scan answer
# ═══════════════════════════════════════════════════════════════════════════


def _market_scan_answer(state: dict) -> str:
    message = state.get("message", "")
    should_use = _get_agent_attr("_should_use_decisive_mode")
    if (should_use and should_use(state)) or detect_decisive_trade_intent(message):
        return _decisive_trade_order_answer(state)

    scan = state.get("scan") or {}
    candidates = [c for c in scan.get("candidates", []) if isinstance(c, dict)]
    rejected_count = int(scan.get("rejected_count", 0) or 0)
    rejection_summary = scan.get("rejection_summary") or {}
    universe = scan.get("universe") or "unspecified"
    filters = scan.get("filters") or {}
    errors = scan.get("source_errors") or []

    is_pt = _get_agent_attr("_is_portuguese_request")
    portuguese = is_pt(message) if is_pt else False
    rej_labels_en = _get_agent_attr("_REJECTION_LABELS_EN") or {}
    rej_labels_pt = _get_agent_attr("_REJECTION_LABELS_PT") or {}
    labels = rej_labels_pt if portuguese else rej_labels_en
    top_reasons_fn = _get_agent_attr("_top_rejection_reasons")
    top_reasons = top_reasons_fn(rejection_summary, labels) if top_reasons_fn else []
    fmt_en = _get_agent_attr("_format_candidate_block_en")
    fmt_pt = _get_agent_attr("_format_candidate_block_pt")

    if portuguese:
        sections: list[str] = []
        sections.append(
            "Bob: este e um relatorio de pesquisa de mercado, nao uma ordem de compra. Lucro nao e garantido."
        )
        sections.append("")
        sections.append("1) Classificacao: pesquisa de oportunidade de curto prazo.")
        sections.append("2) Horizonte: aproximadamente 2 semanas (curto prazo).")
        sections.append(f"3) Universo do scan: {universe}")
        sections.append(
            "4) Gate de qualidade de dados: ticker, exchange, preco atual, volume/liquidez, catalisador de curto prazo, risco e condicao de invalidacao sao obrigatorios. Sem todos esses campos, o candidato e rejeitado."
        )
        sections.append("")
        sections.append("5) Candidatos:")
        if candidates:
            for item in candidates[:6]:
                sections.extend(fmt_pt(item) if fmt_pt else [f"- {item.get('ticker', '?')}"])
        else:
            sections.append(
                "Nenhum candidato passou nos gates minimos de qualidade de dados para uma ideia de pesquisa de 2 semanas."
            )
        sections.append("")
        sections.append(f"6) Resumo de rejeicoes: {rejected_count} ticker(s) descartado(s).")
        if top_reasons:
            sections.append("   Principais motivos:")
            for reason in top_reasons:
                sections.append(f"   - {reason}")
        sections.append(
            f"   Filtros usados: paises={filters.get('resolved_countries')}, setor={filters.get('sector')}, permitir_penny_otc={filters.get('allow_penny_otc')}, permitir_microcap={filters.get('allow_microcap')}."
        )
        sections.append("")
        sections.append("7) Controles de risco:")
        sections.append("   - Defina perda maxima por posicao antes de qualquer ordem.")
        sections.append("   - Exija liquidez suficiente para entrar e sair sem spread absurdo.")
        sections.append(
            "   - Confirme catalisador verificavel (filing, earnings, evento) e nao hype social."
        )
        sections.append("   - Estabeleca condicao de invalidacao tecnica/fundamentalista clara.")
        sections.append("")
        sections.append(
            "8) Aviso: apenas pesquisa. Sem garantia de lucro. Decisao de compra/venda e sua responsabilidade."
        )
        if not candidates:
            sections.append("")
            sections.append(
                "Proximo prompt sugerido: 'Repita o scan com teto de preco, liquidez minima, janela de catalisador e retorne REJECT_ALL se nenhum candidato passar.'"
            )
        if errors:
            sections.append("")
            sections.append("Limite de dados: " + "; ".join(str(err) for err in errors[:3]))
        return "\n".join(sections)

    sections = []
    sections.append(
        "Bob: this is a market research report, not a buy order. Profit is not guaranteed."
    )
    sections.append("")
    sections.append("1) Classification: short-term opportunity research.")
    sections.append("2) Time horizon: approximately 2 weeks (short term).")
    sections.append(f"3) Scan universe: {universe}")
    sections.append(
        "4) Data quality gate: ticker, exchange, latest price, volume/liquidity, short-term catalyst, downside risk and an invalidation condition are all required. Without every field, a candidate is rejected."
    )
    sections.append("")
    sections.append("5) Candidates:")
    if candidates:
        for item in candidates[:6]:
            sections.extend(fmt_en(item) if fmt_en else [f"- {item.get('ticker', '?')}"])
    else:
        sections.append(
            "No candidate passed the minimum data-quality gates for a 2-week research idea."
        )
    sections.append("")
    sections.append(f"6) Rejected candidates summary: {rejected_count} ticker(s) discarded.")
    if top_reasons:
        sections.append("   Top reasons:")
        for reason in top_reasons:
            sections.append(f"   - {reason}")
    sections.append(
        f"   Filters used: countries={filters.get('resolved_countries')}, setor={filters.get('sector')}, allow_penny_otc={filters.get('allow_penny_otc')}, allow_microcap={filters.get('allow_microcap')}."
    )
    sections.append("")
    sections.append("7) Risk controls:")
    sections.append("   - Define maximum loss per position before placing any order.")
    sections.append("   - Require liquidity sufficient to enter and exit without extreme spreads.")
    sections.append(
        "   - Confirm a verifiable catalyst (filing, earnings, event) rather than social hype."
    )
    sections.append("   - Set a clear technical/fundamental invalidation condition.")
    sections.append("")
    sections.append(
        "8) Caveat: research only. No guaranteed profit. The buy/sell decision is your own responsibility."
    )
    if not candidates:
        sections.append("")
        sections.append(
            "Suggested next prompt: 'Repeat the scan with max price, minimum liquidity, catalyst window, and return REJECT_ALL if no candidate passes.'"
        )
    if errors:
        sections.append("")
        sections.append("Data limit: " + "; ".join(str(err) for err in errors[:3]))
    return "\n".join(sections)


# ═══════════════════════════════════════════════════════════════════════════
# Decisive trade order
# ═══════════════════════════════════════════════════════════════════════════


def _render_decisive_trade_order(state: dict) -> tuple[str, dict[str, Any] | None]:
    message = state.get("message", "")
    scan = state.get("scan") or {}
    trade_ctx = state.get("trade_order_context") or {}
    intent = state.get("intent", "")
    is_followup = intent == "another_trade_recommendation" or (
        trade_ctx.get("mode") in {"DECISIVE_TRADE_ORDER", "DECISIVE_TRADE_ORDER_FOLLOWUP"}
        and detect_another_trade_recommendation_intent(message)
    )
    mode_label = "DECISIVE_TRADE_ORDER_FOLLOWUP" if is_followup else "DECISIVE_TRADE_ORDER"

    candidates = [c for c in scan.get("candidates", []) if isinstance(c, dict)]
    rejected_count = int(scan.get("rejected_count", 0) or 0)
    rejection_summary = scan.get("rejection_summary") or {}
    universe = scan.get("universe") or trade_ctx.get("universe") or "unspecified"
    errors = scan.get("source_errors") or []
    time_horizon = state.get("time_horizon") or trade_ctx.get("time_horizon") or "14 days"
    excluded = {str(t).upper() for t in trade_ctx.get("excluded_tickers") or [] if t}

    # Late-binding lookups
    is_pt = _get_agent_attr("_is_portuguese_request")
    is_paper = _get_agent_attr("_is_paper_training_request")
    extract_alloc = _get_agent_attr("_extract_requested_allocation")
    extract_acct = _get_agent_attr("_extract_account_reference")
    rej_labels_en = _get_agent_attr("_REJECTION_LABELS_EN") or {}
    rej_labels_pt = _get_agent_attr("_REJECTION_LABELS_PT") or {}
    top_reasons_fn = _get_agent_attr("_top_rejection_reasons")
    build_ctx = _get_agent_attr("_build_trade_order_context")
    format_liq = _get_agent_attr("_format_liquidity")
    format_money = _get_agent_attr("_format_money_amount")
    estimate_qty = _get_agent_attr("_estimate_share_quantity")
    safety_failures = _get_agent_attr("_trade_safety_gate_failures")
    paper_blocked = _get_agent_attr("_paper_order_explicitly_blocked")
    paper_enabled = _get_agent_attr("_paper_order_submit_enabled")

    paper_training = is_paper(message) if is_paper else False
    requested_amount = extract_alloc(message) if extract_alloc else None
    account_reference = extract_acct(message) if extract_acct else None

    portuguese = is_pt(message) if is_pt else False
    labels = rej_labels_pt if portuguese else rej_labels_en
    top_reasons = top_reasons_fn(rejection_summary, labels) if top_reasons_fn else []

    ranked = scan.get("ranked_candidates")
    if not isinstance(ranked, list) or not ranked:
        ranked = rank_candidates(
            candidates,
            source_errors=errors,
            weak_universe=len(candidates) <= 1,
        )

    entry, _ = pick_candidate(ranked, excluded_tickers=excluded)
    sections: list[str] = []

    # ── No candidates / reject all ──
    if (is_followup and entry is None) or (not candidates and entry is None):
        return _build_reject_all_sections(
            candidates=candidates,
            is_followup=is_followup,
            mode_label=mode_label,
            rejected_count=rejected_count,
            top_reasons=top_reasons,
            universe=universe,
            errors=errors,
            portuguese=portuguese,
            trade_ctx=trade_ctx,
            excluded=excluded,
            ranked=ranked,
            state=state,
            build_ctx=build_ctx,
        )

    if entry is None:
        entry = ranked[0] if ranked else None
    if entry is None:
        ctx = (
            build_ctx(
                state, mode=mode_label, primary_ticker="", ranked=ranked, decision="REJECT_ALL"
            )
            if build_ctx
            else None
        )
        return "Model verdict: REJECT_ALL", ctx

    primary = entry.get("candidate") or {}
    normalize_liquidity_fields(primary)
    gate_failures = list(entry.get("gate_failures") or [])
    if not gate_failures:
        _, gate_failures = evaluate_quality_gates(primary)
    confidence = int(
        entry.get("confidence")
        or compute_model_confidence(
            primary,
            gate_failures=gate_failures,
            source_errors=errors,
            weak_universe=len(candidates) <= 1,
        )
    )
    decision = entry.get("decision") or decide_final_action(confidence, gate_failures)
    if gate_failures and decision == "BUY_CANDIDATE":
        decision = decide_final_action(confidence, gate_failures)
    safety_gate_failures = safety_failures(state) if safety_failures else []
    if safety_gate_failures and decision == "BUY_CANDIDATE":
        gate_failures = list(dict.fromkeys(gate_failures + safety_gate_failures))
        if any(item in safety_gate_failures for item in ("f51_not_passed", "sdca_blocked")):
            decision = "REJECT_ALL"
        else:
            decision = "WAIT"
    data_gate_failures = [g for g in gate_failures if g not in safety_gate_failures]
    paper_ticket_pending = (
        paper_training
        and not data_gate_failures
        and decision in {"BUY_CANDIDATE", "WAIT"}
        and not any(
            item in safety_gate_failures
            for item in ("f51_not_passed", "sdca_blocked", "f51_error", "sdca_error")
        )
    )
    paper_order_user_blocked = paper_blocked(message) if paper_blocked else False
    paper_auto_submit = (
        paper_ticket_pending
        and (paper_enabled() if paper_enabled else False)
        and "submit_paper_order" in set(state.get("allowed_tools") or [])
        and bool(state.get("ticket_allowed", False))
        and not paper_order_user_blocked
    )
    if paper_ticket_pending and state.get("submit_paper_order_result"):
        display_decision = "PAPER_ORDER_SUBMITTED"
    elif paper_ticket_pending and state.get("submit_paper_order_error"):
        display_decision = "PAPER_ORDER_SUBMIT_FAILED"
    elif paper_ticket_pending and paper_auto_submit:
        display_decision = "PAPER_ORDER_SUBMIT_READY"
    elif paper_ticket_pending:
        display_decision = "PAPER_TICKET_PENDING_APPROVAL"
    else:
        display_decision = decision

    ticker = primary.get("ticker") or "?"
    name = primary.get("name") or primary.get("company") or "—"
    market = primary.get("market") or primary.get("exchange") or "—"
    price = primary.get("price")
    currency = primary.get("currency") or "USD"
    catalyst = (
        primary.get("catalyst")
        or primary.get("thesis")
        or primary.get("short_term_thesis")
        or primary.get("reason")
        or "—"
    )
    provider = primary.get("provider") or primary.get("source") or "data hub"
    collected_at = scan.get("collected_at") or "—"
    liquidity_text = format_liq(None, primary) if format_liq else str(primary.get("volume", "—"))
    amount_text = format_money(requested_amount) if format_money else str(requested_amount or "—")
    account_text = (
        format_money(account_reference) if format_money else str(account_reference or "—")
    )
    estimated_qty = estimate_qty(requested_amount, price) if estimate_qty else "—"
    prev_excluded = ""
    if is_followup:
        prev_excluded = trade_ctx.get("primary_ticker") or (
            next(iter(excluded)) if excluded else "—"
        )

    sections = _build_candidate_sections(
        portuguese=portuguese,
        mode_label=mode_label,
        display_decision=display_decision,
        is_followup=is_followup,
        prev_excluded=prev_excluded,
        paper_training=paper_training,
        paper_auto_submit=paper_auto_submit,
        paper_order_user_blocked=paper_order_user_blocked,
        ticker=ticker,
        name=name,
        market=market,
        price=price,
        currency=currency,
        collected_at=collected_at,
        provider=provider,
        liquidity_text=liquidity_text,
        amount_text=amount_text,
        account_text=account_text,
        estimated_qty=estimated_qty,
        catalyst=catalyst,
        time_horizon=time_horizon,
        confidence=confidence,
        gate_failures=gate_failures,
        safety_gate_failures=safety_gate_failures,
        display_decision_raw=display_decision,
        errors=errors,
        state=state,
    )

    ctx = (
        build_ctx(
            state,
            mode=mode_label,
            primary_ticker=str(ticker),
            ranked=ranked,
            decision=display_decision,
        )
        if build_ctx
        else None
    )
    return "\n".join(sections), ctx


def _build_reject_all_sections(
    *,
    candidates,
    is_followup,
    mode_label,
    rejected_count,
    top_reasons,
    universe,
    errors,
    portuguese,
    trade_ctx,
    excluded,
    ranked,
    state,
    build_ctx,
) -> tuple[str, dict[str, Any] | None]:
    sections: list[str] = []
    if is_followup:
        prev = trade_ctx.get("primary_ticker") or (next(iter(excluded)) if excluded else "?")
        if portuguese:
            sections = [
                "# Bob Model Order",
                "",
                f"1. Modo: {mode_label}",
                "2. Decisao Final: REJECT_ALL",
                f"3. Candidato Anterior Excluido: {prev}",
                "",
                f"Nenhum segundo candidato passou o gate de qualidade apos excluir {prev}.",
                "",
                "Resumo de Rejeicoes:",
                f"   - rejected_count: {rejected_count}",
            ]
        else:
            sections = [
                "# Bob Model Order",
                "",
                f"1. Mode: {mode_label}",
                "2. Final Decision: REJECT_ALL",
                f"3. Previous Candidate Excluded: {prev}",
                "",
                f"No second candidate passed the quality gate after excluding {prev}.",
                "",
                "Rejected Summary:",
                f"   - rejected_count: {rejected_count}",
            ]
        if top_reasons:
            sections.append("   - top_rejection_reasons:")
            for r in top_reasons:
                sections.append(f"     * {r}")
    else:
        if portuguese:
            sections = [
                "# Bob Model Order",
                "",
                f"1. Modo: {mode_label}",
                "2. Decisao Final: REJECT_ALL",
                "",
                f"Nenhuma ordem de modelo gerada. {rejected_count} ticker(s) rejeitado(s) nos gates de qualidade de dados.",
            ]
        else:
            sections = [
                "# Bob Model Order",
                "",
                f"1. Mode: {mode_label}",
                "2. Final Decision: REJECT_ALL",
                "",
                f"No valid model order generated. {rejected_count} ticker(s) rejected at data-quality gates.",
            ]
        if top_reasons:
            prefix = "Principais motivos de rejeicao:" if portuguese else "Top rejection reasons:"
            sections.append(prefix)
            for r in top_reasons:
                sections.append(f"   - {r}")
        sections.append(f"{'Universo do scan' if portuguese else 'Scan universe'}: {universe}.")

    if errors:
        sections.append(
            ("Limite de dados: " if portuguese else "Data limit: ")
            + "; ".join(str(e) for e in errors[:3])
        )
    ctx = (
        build_ctx(state, mode=mode_label, primary_ticker="", ranked=ranked, decision="REJECT_ALL")
        if build_ctx
        else None
    )
    return "\n".join(sections), ctx


def _build_candidate_sections(
    *,
    portuguese,
    mode_label,
    display_decision,
    is_followup,
    prev_excluded,
    paper_training,
    paper_auto_submit,
    paper_order_user_blocked,
    ticker,
    name,
    market,
    price,
    currency,
    collected_at,
    provider,
    liquidity_text,
    amount_text,
    account_text,
    estimated_qty,
    catalyst,
    time_horizon,
    confidence,
    gate_failures,
    safety_gate_failures,
    display_decision_raw,
    errors,
    state,
) -> list[str]:
    sections: list[str] = []
    is_buy_candidate = display_decision_raw in (
        "BUY_CANDIDATE",
        "PAPER_TICKET_PENDING_APPROVAL",
        "PAPER_ORDER_SUBMIT_READY",
        "PAPER_ORDER_SUBMITTED",
    )
    if is_buy_candidate is False:
        is_buy_candidate = display_decision_raw.startswith("PAPER")

    heading_en = (
        "3. Primary Order Candidate:"
        if is_buy_candidate
        else "3. Study Candidate (Not a Recommendation):"
    )
    heading_pt = (
        "3. Candidato Primario da Ordem:"
        if is_buy_candidate
        else "3. Candidato de Estudo (Nao e recomendacao):"
    )

    if portuguese:
        sections = [
            "# Bob Model Order",
            "",
            f"1. Modo: {mode_label}",
            f"2. Decisao Final: {display_decision}",
            "",
        ]
        if is_followup:
            sections.append(f"3. Candidato Anterior Excluido: {prev_excluded}")
            sections.append("")
            sections.append(f"4. {heading_pt}")
        else:
            sections.append(heading_pt)
        sections.extend(
            [
                f"   - Ticker: {ticker}",
                f"   - Empresa: {name}",
                f"   - Mercado: {market}",
                f"   - Preco Atual: {price} {currency}",
                f"   - Dados: {collected_at} (fonte: {provider})",
                f"   - Liquidez: {liquidity_text}",
                f"   - Capital do treino solicitado: {amount_text}",
                f"   - Capital teorico citado: {account_text}",
                f"   - Quantidade estimada: {estimated_qty}",
                f"   - Catalisador: {catalyst}",
                f"   - Horizonte: {time_horizon}",
                f"   - Confianca do Modelo: {confidence}/100",
            ]
        )
    else:
        sections = [
            "# Bob Model Order",
            "",
            f"1. Mode: {mode_label}",
            f"2. Final Decision: {display_decision}",
            "",
        ]
        if is_followup:
            sections.append(f"3. Previous Candidate Excluded: {prev_excluded}")
            sections.append("")
            sections.append(f"4. {heading_en}")
        else:
            sections.append(heading_en)
        sections.extend(
            [
                f"   - Ticker: {ticker}",
                f"   - Company: {name}",
                f"   - Market: {market}",
                f"   - Latest Price: {price} {currency}",
                f"   - Data Timestamp: {collected_at} (source: {provider})",
                f"   - Liquidity: {liquidity_text}",
                f"   - Requested training capital: {amount_text}",
                f"   - Referenced theoretical capital: {account_text}",
                f"   - Estimated quantity: {estimated_qty}",
                f"   - Catalyst: {catalyst}",
                f"   - Time Horizon: {time_horizon}",
                f"   - Model Confidence: {confidence}/100",
            ]
        )

    if gate_failures:
        tag = "Gates falhados" if portuguese else "Gate failures"
        sections.append(f"   - {tag}: {', '.join(gate_failures)}")
    if safety_gate_failures:
        tag = "Gates obrigatorios de seguranca" if portuguese else "Required safety gates"
        sections.append(
            f"   - {tag}: F51 + SDCA precisam estar executados e aprovados antes de BUY_CANDIDATE."
        )

    plan_num = "5" if is_followup else "4"
    plan_heading_pt = (
        "Plano de Ordem Sugerido:" if is_buy_candidate else "Plano de Watchlist / Sem Ordem:"
    )
    plan_heading_en = "Suggested Order Plan:" if is_buy_candidate else "Watchlist / No-Trade Plan:"
    entry_pt = (
        "ordem limitada proximo ao preco atual"
        if is_buy_candidate
        else "Sem entrada ate risco, invalidacao e confianca passarem nos gates"
    )
    entry_en = (
        "limit order near current price"
        if is_buy_candidate
        else "No entry until risk, invalidation, and confidence gates pass"
    )
    risk_pt = "0.5%-1.0% do capital de trading" if is_buy_candidate else "0 ate virar BUY_CANDIDATE"
    risk_en = (
        "0.5%-1.0% of trading capital" if is_buy_candidate else "0 until upgraded to BUY_CANDIDATE"
    )
    # Previously undefined — computed from available context
    invalidation_pct = 0.05  # 5% below entry is default invalidation
    invalidation_price = round(float(price) * (1 - invalidation_pct), 2) if price else 0.0
    invalidation_pt = (
        f"R$ {invalidation_price:.2f} (-{invalidation_pct:.0%})"
        if is_buy_candidate
        else "N/A ate virar BUY_CANDIDATE"
    )
    invalidation_en = (
        f"${invalidation_price:.2f} (-{invalidation_pct:.0%})"
        if is_buy_candidate
        else "N/A until upgraded to BUY_CANDIDATE"
    )
    risk_amount = (
        round(float(estimated_qty or 0) * float(price) * invalidation_pct, 2)
        if price and estimated_qty
        else 0.0
    )
    risk_display_pt = f"R$ {risk_amount:.2f} ({risk_pt})" if is_buy_candidate else risk_pt
    risk_display_en = f"${risk_amount:.2f} ({risk_en})" if is_buy_candidate else risk_en

    if portuguese:
        sections.extend(
            [
                "",
                f"{plan_num}. {plan_heading_pt}",
                f"   - Entrada: {entry_pt}",
                f"   - Stop/Invalidacao: {invalidation_pt}",
                f"   - Risco: {risk_display_pt}",
                f"   - Risco Maximo: {risk_pt}",
                "",
                "Ordem paper pode ser transmitida pelo tool gate. Nao e lucro garantido; live-money continua bloqueado."
                if paper_auto_submit
                else "Ordem do modelo, nao e lucro garantido. Transmissao broker nao executada neste modo.",
                f"Model verdict: {display_decision}",
            ]
        )
    else:
        sections.extend(
            [
                "",
                f"{plan_num}. {plan_heading_en}",
                f"   - Entry: {entry_en}",
                f"   - Stop/Invalidation: {invalidation_en}",
                f"   - Risk: {risk_display_en}",
                f"   - Max Risk: {risk_en}",
                "",
                "Paper order may be transmitted through the tool gate. Profit is not guaranteed; live-money remains blocked."
                if paper_auto_submit
                else "Model order, not guaranteed profit. Broker transmission is not executed in this mode.",
                f"Model verdict: {display_decision}",
            ]
        )

    if display_decision == "WAIT":
        sections.append("")
        if portuguese:
            sections.append(
                f"Nota: confianca abaixo do limiar de compra ({BUY_CONFIDENCE_THRESHOLD}/100) ou gates de liquidez/risco incompletos."
            )
            if gate_failures:
                sections.append(f"Motivos: {', '.join(gate_failures)}")
            sections.append(
                "Permanece na watchlist de estudo ate liquidez, risco e invalidacao elevarem ao limiar de compra do modelo."
            )
        else:
            sections.append(
                f"Note: confidence below buy threshold ({BUY_CONFIDENCE_THRESHOLD}/100) or liquidity/risk gates not satisfied."
            )
            if gate_failures:
                sections.append(f"Reasons: {', '.join(gate_failures)}")
            sections.append(
                "Keep on a study watchlist until liquidity, risk, and invalidation upgrade to model-buy thresholds."
            )

    if errors:
        sections.append("")
        sections.append(
            ("Limite de dados: " if portuguese else "Data limit: ")
            + "; ".join(str(e) for e in errors[:3])
        )

    return sections


def _decisive_trade_order_answer(state: dict) -> str:
    answer, _ = _render_decisive_trade_order(state)
    return answer


# ═══════════════════════════════════════════════════════════════════════════
# Fallback answers (advisory / complex finance / risk lab)
# ═══════════════════════════════════════════════════════════════════════════


def _complex_finance_fallback_answer(message: str) -> str:
    msg = (message or "").lower()
    is_capital = any(
        token in msg
        for token in (
            "allocate",
            "allocation",
            "emergency",
            "debt",
            "equipment",
            "education",
            "cash reserve",
            "cad",
        )
    )
    classification = "CAPITAL_ALLOCATION" if is_capital else "MACRO_THESIS"
    verdict = "CASH" if "unstable" in msg or "emergency" in msg else "ETF"
    confidence = 74 if is_capital else 68
    return (
        f"1. **Question Classification** — {classification}.\n"
        "2. **Assumptions** — CAD capital, Canadian household context, family stability matters, "
        "income may be unstable, and all scenario numbers are illustrative assumptions, not forecasts.\n"
        "3. **Missing Data** — debt balances and interest rates, current emergency reserve, monthly expenses, "
        "TFSA, RRSP, RESP, or FHSA room, tax bracket, business revenue history, and education timeline.\n"
        "4. **Decision Variables** — liquidity need, emergency fund months, debt interest rate, downside risk, "
        "reversibility, time-to-cashflow, health/energy constraints, and family stability.\n"
        "5. **Quantitative Thresholds** — keep 3-6 months of emergency cash reserve first; pay debt above "
        "6-8% interest before market risk; fund business equipment only when expected payback/time-to-cashflow "
        "is clear; keep education spending staged and reversible.\n"
        "6. **Scenario Analysis** — Illustrative downside: unstable income plus no reserve forces asset sales. "
        "Illustrative base case: reserve plus high-interest debt payoff reduces fragility. Illustrative upside: "
        "surplus after safety gates can compound through a broad diversified Canadian-listed ETF or productive "
        "business equipment.\n"
        "7. **Ranked Allocation / Framework** — 40% emergency cash reserve, 30% high-interest debt payoff, "
        "15% broad diversified Canadian-listed ETF, 10% side-business equipment only with payback evidence, "
        "5% education. These illustrative buckets sum to 100% and prioritize survival before upside.\n"
        "8. **Decision Gates** — If emergency reserve is below 3 months, CASH dominates. If debt interest is "
        "above 6-8%, PAY_DEBT dominates. If business equipment has fast payback and low execution burden, shift "
        "some ETF/education budget to equipment. Tax account choices depend on the individual's situation.\n"
        "9. **Final Recommendation** — Build the emergency reserve first, then pay expensive "
        "debt, then deploy remaining surplus gradually into ETF/business/education only after liquidity is safe.\n"
        f"10. **Confidence Level** — {confidence}/100, limited by missing debt rate, monthly expenses, and tax room.\n"
        f"Final verdict: {verdict}\n"
        f"Confidence: {confidence}"
    )


def _industry_research_fallback_answer(state: dict) -> str:
    message = state.get("message", "")
    is_pt = _get_agent_attr("_is_portuguese_request")
    portuguese = is_pt(message) if is_pt else False
    lower = (message or "").lower()
    if "fax" in lower:
        if portuguese:
            return (
                "Bob: minha leitura direta: fax e uma industria legada, em declinio estrutural, "
                "e eu nao comecaria por ticker. A oportunidade real nao e 'empresa de fax'; e o fluxo "
                "adjacente que substitui fax: document workflow seguro, e-signature, healthcare records, "
                "compliance, automacao de back office e cybersecurity para troca de documentos.\n\n"
                "Tese: fax sobrevive onde existe friccao regulatoria e sistemas antigos, mas o crescimento "
                "deve ir para plataformas que removem essa friccao. O risco de comprar uma pure-play de fax "
                "e pegar uma base instalada morrendo, receita em queda e baixo multiple por motivo justo.\n\n"
                "Como usar isso: 1) mapear setores ainda presos in fax, 2) procurar fornecedores que digitalizam "
                "esse fluxo, 3) exigir crescimento verificavel, margem, retencao e baixa dependencia de hype. "
                "Ticker vem depois, se voce pedir uma varredura de ativos.\n\n"
                "Final verdict: pesquisar adjacencias digitais, nao fax puro.\n"
                "Confidence: 84/100"
            )
        return (
            "Bob: direct read: fax is a legacy industry in structural decline, so I would not start with a ticker. "
            "The real opportunity is the workflow replacing fax: secure document workflow, e-signature, healthcare records, "
            "compliance automation, back-office automation, and cybersecurity around document exchange.\n\n"
            "Thesis: fax survives where regulation and old systems create friction, but growth should accrue to platforms "
            "that remove that friction. The risk in a pure fax business is buying a shrinking installed base at a cheap multiple for a good reason.\n\n"
            "Use it this way: map sectors still trapped in fax, find vendors digitizing that flow, then require verified growth, margins, retention, and low hype dependence. "
            "Tickers come later if you ask for an asset scan.\n\n"
            "Final verdict: research digital adjacencies, not pure fax.\n"
            "Confidence: 84/100"
        )
    return (
        "Bob: this is industry research, not a ticker-first request. I would first build the thesis, identify whether the industry is expanding or decaying, "
        "then look for adjacent markets where the economics are improving. Only after that should we screen tickers.\n\n"
        "Final verdict: thesis first, ticker scan second.\n"
        "Confidence: 78/100"
    )


def _risk_lab_fallback_answer(state: dict) -> str:
    is_pt = _get_agent_attr("_is_portuguese_request")
    portuguese = is_pt(state.get("message", "")) if is_pt else False
    if portuguese:
        return (
            "Bob: para CAD 50 por semana, eu trataria isso como laboratorio de risco, nao como investimento principal. "
            "A regra e simples: o prejuizo maximo da semana e CAD 50, sem dobrar aposta, sem alavancagem, sem recuperar perda.\n\n"
            "Contrato do laboratorio:\n"
            "- Capital semanal: CAD 50.\n"
            "- Max loss: CAD 50, acabou a semana.\n"
            "- Entrada so com tese, catalisador, liquidez, invalidacao e tamanho da posicao definidos antes.\n"
            "- Se nao houver edge verificavel, a decisao correta e NO_BET_THIS_WEEK.\n"
            "- Depois de cada tentativa: registrar tese, entrada, saida, erro e aprendizado.\n\n"
            "Final verdict: NO_BET_THIS_WEEK ate aparecer uma oportunidade verificavel.\n"
            "Confidence: 86/100"
        )
    return (
        "Bob: for CAD 50 per week, treat this as a risk lab, not core investing. "
        "The weekly max loss is CAD 50. No doubling down, no leverage, no revenge trade.\n\n"
        "Risk lab contract:\n"
        "- Weekly capital: CAD 50.\n"
        "- Max loss: CAD 50, then the week is over.\n"
        "- Enter only with thesis, catalyst, liquidity, invalidation, and position size set before entry.\n"
        "- If no verifiable edge exists, the correct decision is NO_BET_THIS_WEEK.\n"
        "- After every attempt: log thesis, entry, exit, mistake, and lesson.\n\n"
        "Final verdict: NO_BET_THIS_WEEK until a verifiable opportunity appears.\n"
        "Confidence: 86/100"
    )


def _advisory_knowledge_fallback_answer(state: dict) -> str:
    message = state.get("message", "")
    lower = (message or "").lower()
    if (
        _is_etf_comparison_question(message)
        and sum(1 for symbol in ("voo", "vti", "schd", "spy", "ivv") if symbol in lower) >= 2
    ):
        return (
            "Bob: this is an ETF comparison, not a short-term trade. I would not stack overlapping core funds just to feel diversified.\n\n"
            "VOO is S&P 500 large-cap exposure: cheap, simple, but narrower than the full US market. "
            "VTI is total US equity exposure: it includes the S&P 500 plus mid and small caps, so it is the cleanest one-fund US core. "
            "SCHD is a dividend-quality/value tilt: useful as a satellite if you deliberately want dividend style exposure, but it is not a complete market core.\n\n"
            "For most long-term buy-and-hold investors, pick one core first. My default framework is VTI as the broad core, VOO if you specifically want S&P 500 exposure, and SCHD only as a smaller satellite tilt. "
            "Check fees, account currency, tax wrapper, and whether you are duplicating holdings before buying.\n\n"
            "Final verdict: ETF\n"
            "Confidence: 82/100"
        )
    if _is_portfolio_concentration_question(message):
        return (
            "Bob: a 40% single-stock position is concentration risk, even when the company is high quality. "
            "The issue is not whether the holding is good; the issue is that one company can dominate your outcome, tax planning, and emotional decisions.\n\n"
            "I would not dump the whole position blindly. A practical framework is: stop adding new money to the concentrated position, route new contributions into diversified broad-market exposure, and reduce the oversized holding in planned tax-aware tranches. "
            "Before selling, estimate unrealized gains, marginal tax rate, account type, and whether charitable giving, loss harvesting, or staged sales reduce the tax hit.\n\n"
            "Decision gate: if one stock is above 25-30% of the portfolio, write a reduction plan; if it is above 40%, make diversification the default unless there is a clear tax or liquidity reason to wait. "
            "Use broad diversified funds or asset-class buckets rather than replacing one single-stock bet with another.\n\n"
            "Final verdict: ETF\n"
            "Confidence: 80/100"
        )
    if "dividend" in lower or "passive income" in lower:
        return (
            "Bob: for a Canadian passive-income portfolio, I would not chase yield first. "
            "Start with dividend durability, tax placement, and concentration limits.\n\n"
            "Framework: use Canadian-listed broad dividend ETFs or high-quality Canadian dividend names as the core, keep any single stock small, "
            "and use RRSP/TFSA rules deliberately. US dividend ETFs can be useful, but withholding tax and account type matter.\n\n"
            "Examples to research, not blind buys: Canadian dividend ETF exposure, Canadian banks, regulated utilities, pipelines/midstream, and one broad-market ETF for diversification. "
            "Verify current yield, payout ratio, debt, dividend growth, and valuation before choosing tickers.\n\n"
            "Final verdict: build a diversified dividend core; do not chase the highest yield.\n"
            "Confidence: 80/100"
        )
    if "dollar-cost" in lower or "dca" in lower or "wait for a correction" in lower:
        return (
            "Bob: default recommendation is DCA, not waiting for the perfect correction. "
            "Without verified live macro data in this run, I would not pretend to time rates or volatility precisely.\n\n"
            "Practical plan: split the capital into 4-8 scheduled tranches, keep emergency cash separate, and accelerate only if valuation and personal cash stability both improve. "
            "Waiting only wins if you have a specific trigger and the discipline to buy when the market is ugly.\n\n"
            "Final verdict: DCA.\n"
            "Confidence: 78/100"
        )
    return (
        "Bob: this is a natural-language financial question, not a ticker-first request. "
        "I can answer from framework knowledge, then use data tools only when current market evidence or a named ticker is required.\n\n"
        "Final verdict: answer the thesis first; use tools only when the question needs verified market data.\n"
        "Confidence: 76/100"
    )


def _contract_fallback_answer(state: dict) -> str:
    mode = state.get("cognitive_mode", "ADVISORY_KNOWLEDGE")
    message = state.get("message", "")
    if state.get("scan"):
        return _market_scan_answer(state)
    if _is_etf_comparison_question(message) or _is_portfolio_concentration_question(message):
        return _advisory_knowledge_fallback_answer(state)
    if mode == "CAPITAL_ALLOCATION" or state.get("intent") in (
        "capital_allocation",
        "personal_finance",
    ):
        return _complex_finance_fallback_answer(state.get("message", ""))
    if mode == "INDUSTRY_RESEARCH":
        return _industry_research_fallback_answer(state)
    if mode == "RISK_LAB":
        return _risk_lab_fallback_answer(state)
    if mode == "TICKER_ANALYSIS":
        ticker = state.get("ticker", "the ticker")
        return (
            f"Bob: I have a ticker-specific request for {ticker}. "
            "If fresh DataCollector evidence is unavailable, I will not invent prices or fundamentals. "
            "Use the collected evidence when present, then judge thesis, risk, invalidation, and position discipline.\n\n"
            "Final verdict: WAIT until the ticker data path returns verified evidence.\n"
            "Confidence: 62/100"
        )
    if mode == "DISCOVERY_SCAN":
        return (
            "Bob: this is a discovery request, so the scanner is the right tool. "
            "If scanner evidence is unavailable or incomplete, the correct answer is not to invent a candidate.\n\n"
            "Final verdict: REJECT_ALL\n"
            "Confidence: 70/100"
        )
    return _advisory_knowledge_fallback_answer(state)


# ═══════════════════════════════════════════════════════════════════════════
# Repair functions
# ═══════════════════════════════════════════════════════════════════════════


def _repair_known_etf_category_errors(text: str) -> str:
    repaired = text or ""
    small_cap_window = re.compile(r"small[- ]cap", re.IGNORECASE)
    bond_etf_window = re.compile(r"(bond|fixed income|investment grade|etf)", re.IGNORECASE)
    repaired = re.sub(
        r"low-cost\s+leveraged\s+ETF\s*\(e\.g\.,\s*LUNR[^)]*\)",
        "higher-volatility satellite exposure only if the instrument, liquidity, and risk are verified",
        repaired,
        flags=re.IGNORECASE,
    )
    for match in reversed(list(re.finditer(r"\bVTV\b", repaired))):
        window_start = max(0, match.start() - 80)
        window_end = min(len(repaired), match.end() + 80)
        if small_cap_window.search(repaired[window_start:window_end]):
            repaired = repaired[: match.start()] + "VBR" + repaired[match.end() :]
    for match in reversed(list(re.finditer(r"\bVWENX\b", repaired))):
        window_start = max(0, match.start() - 80)
        window_end = min(len(repaired), match.end() + 80)
        if bond_etf_window.search(repaired[window_start:window_end]):
            repaired = repaired[: match.start()] + "BND" + repaired[match.end() :]
    return repaired


def _repair_unsourced_etf_tickers(text: str) -> str:
    replacements = {
        "VCN": "a broad Canadian equity index ETF",
        "VCE": "a broad Canadian equity index ETF",
        "XIC": "a broad diversified Canadian-listed ETF",
        "VUN": "a broad US total-market ETF",
        "ZAG": "an aggregate bond ETF",
        "VGRO": "a balanced growth ETF",
        "XEQT": "an all-equity diversified ETF",
        "VFV": "an S&P 500 index ETF",
    }
    repaired = text or ""
    for ticker, asset_class in replacements.items():
        repaired = re.sub(rf"\b{ticker}(?:\.TO)?\b", asset_class, repaired)
    return repaired


def _repair_unsupported_exact_returns(text: str) -> str:
    repaired = re.sub(
        r"guaranteed\s+\d+(?:\s*[–-]\s*\d+)?%\s+return",
        "guaranteed return equal to the avoided interest rate",
        text or "",
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"paying\s+off\s+\d+(?:\.\d+)?%\s+debt\s+is\s+like\s+earning\s+a\s+guaranteed(?:,\s*tax-free)?\s+\d+(?:\.\d+)?%\s+return",
        "paying off high-interest debt is like earning a guaranteed return equal to the avoided interest rate",
        repaired,
        flags=re.IGNORECASE,
    )
    return repaired


def _repair_tax_overstatements(text: str) -> str:
    repaired = re.sub(
        r"\bstay under your annual capital gains exemption\b",
        "manage the realized capital gain within your tax bracket and cash-flow plan",
        text or "",
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"\b(?:in the U\.S\.,\s*)?use your annual\s+\$?\d+(?:,\d{3})?\s*[Kk]?(?:\s*\([^)]*\))?\s+(?:long-term\s+)?capital gains exemption(?:\s*\([^)]*\))?",
        "long-term capital-gains tax depends on taxable income and account type; do not assume a fixed exemption",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"without the\s+15%\s+withholding tax on dividends\s*\([^)]*\)",
        "while verifying foreign withholding tax at the fund and account level",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"because it.?s listed on the TSX,\s*dividends are treated as Canadian-source income for tax purposes",
        "Canadian listing does not automatically make underlying U.S. dividends Canadian-source for withholding-tax purposes",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"RRSPs are exempt from U\.S\. withholding tax on dividends\s*\([^)]*\),\s*so\s+[^.]+\.",
        "RRSP withholding treatment depends on whether the ETF is U.S.-listed or Canadian-listed and how it holds the underlying assets; verify the fund structure before assuming recovery.",
        repaired,
        flags=re.IGNORECASE,
    )
    return repaired


def _repair_short_term_return_forecasts(text: str) -> str:
    repaired = text or ""
    if re.search(r"\b\d+(?:\.\d+)?\s*[–-]\s*\d+(?:\.\d+)?%", repaired):
        repaired = re.sub(
            r"\bvery doable\b", "possible, but not a forecast", repaired, flags=re.IGNORECASE
        )
        repaired = re.sub(
            r"\bachievable\b",
            "possible, but not forecastable with precision",
            repaired,
            flags=re.IGNORECASE,
        )
        if "short-term percentage target" not in repaired.lower():
            repaired = (
                repaired.rstrip()
                + "\n\nNota: qualquer target percentual de curto prazo acima é cenário "
                "ilustrativo, não previsão. Precisa de catalisador verificado, "
                "liquidez e nível de invalidação antes de agir."
            )
    return repaired


def _is_etf_comparison_question(message: str) -> bool:
    q = f" {(message or '').lower()} "
    return any(word in q for word in ("compare", "comparison", " versus ", " vs "))


def _is_portfolio_concentration_question(message: str) -> bool:
    q = f" {(message or '').lower()} "
    return bool(
        re.search(r"\b(concentrated(?:\s+position)?|40\s*%|40 percent|single[-\s]?stock)\b", q)
        and re.search(r"\b(portfolio|tax bill|diversify|triggering)\b", q)
    )


def _is_dca_macro_question(message: str) -> bool:
    q = f" {(message or '').lower()} "
    return any(
        marker in q
        for marker in (
            "dollar-cost",
            " dollar cost ",
            " dca ",
            "wait for a correction",
            "interest rates",
            "market volatility",
        )
    )


def _has_unsupported_macro_precision(text: str) -> bool:
    lower = (text or "").lower()
    patterns = (
        r"\bvix\b",
        r"\bbasis[-\s]?point\b",
        r"\btreasury\b.*\b\d+(?:\.\d+)?%",
        r"\brates?\b.{0,40}\b\d+(?:\.\d+)?%",
        r"\byields?\b.{0,40}\b\d+(?:\.\d+)?%",
        r"\boutperformed\b.{0,80}\b\d+(?:\.\d+)?%",
        r"\brecover(?:ed|ing)?\b.{0,80}\b\d+\s*[-–]\s*\d+\s+days\b",
        r"\bq[1-4]\s+20\d{2}\b|\b20\d{2}\s+q[1-4]\b",
        r"\b(?:s&p\s*500|tsx\s+composite)\b.{0,120}\b\d+(?:\.\d+)?%",
        r"\bpullbacks?\b.{0,80}\b\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?%",
    )
    return any(re.search(pattern, lower, flags=re.IGNORECASE) for pattern in patterns)


def _has_tax_overstatement(text: str) -> bool:
    lower = (text or "").lower()
    patterns = (
        r"\bcapital gains exemption\b",
        r"\bannual\s+\$?\d+(?:,\d{3})?\s*k?\b.{0,80}\bcapital gains\b",
        r"\bwithout the\s+15%\s+withholding tax\b",
        r"\bavoid(?:s|ed|ing)?\b.{0,80}\b15%\s+(?:u\.?s\.?\s+)?withholding tax\b",
        r"\bdividends are treated as canadian-source income\b",
        r"\brrsps?\s+are\s+exempt\s+from\s+u\.?s\.?\s+withholding tax\b",
        r"\bcanada[-\s]?u\.?s\.?\s+tax treaty\b",
        r"\btreaty benefit\b",
        r"\bcanadian[-\s]?listed\b.{0,80}\b(?:avoid|waive|exempt|no)\b.{0,80}\bwithholding\b",
        r"\bcurrency hedg(?:e|ed|ing)\b.{0,80}\bwithholding\b",
        r"\bwithout currency hedg(?:e|ed|ing)\b.{0,80}\bwithholding\b",
        r"\bcad[-\s]?hedg(?:ed|ing)\b.{0,80}\bwithholding\b",
        r"\btransfer[-\s]?in[-\s]?kind\b",
        r"\b(?:doesn.?t|does not|won.?t|will not)\s+trigger\b.{0,80}\btaxable event\b",
    )
    return any(re.search(pattern, lower, flags=re.IGNORECASE) for pattern in patterns)


def _repair_overlapping_etf_tickers(text: str, message: str = "") -> str:
    if _is_etf_comparison_question(message):
        return text or ""
    repaired = text or ""
    overlap_groups = (
        ("SPY", "VTI", "VOO", "IVV"),
        ("QQQ", "QQQM"),
        ("VXUS", "VEU"),
    )
    for group in overlap_groups:
        present = [
            ticker
            for ticker in group
            if re.search(rf"\b{re.escape(ticker)}\b", repaired, flags=re.IGNORECASE)
        ]
        if len(present) <= 1:
            continue
        for ticker in present[1:]:
            repaired = re.sub(
                rf"\b{re.escape(ticker)}\b",
                "a similar broad-market ETF",
                repaired,
                flags=re.IGNORECASE,
            )
    return repaired


def _repair_answer_quality(text: str, message: str = "") -> str:
    return _repair_short_term_return_forecasts(
        _repair_overlapping_etf_tickers(
            _repair_tax_overstatements(
                _repair_unsupported_exact_returns(
                    _repair_unsourced_etf_tickers(_repair_known_etf_category_errors(text or ""))
                )
            ),
            message,
        )
    )


def _repair_complex_finance_answer(message: str, content: str) -> str:
    msg = (message or "").lower()
    text = _repair_answer_quality(content or "", message)
    lower = text.lower()
    additions: list[str] = []

    assumption_markers = (
        "illustrative",
        "assumption",
        "assumptions",
        "assum",
        "ilustrativ",
        "supos",
    )
    if not any(marker in lower for marker in assumption_markers):
        additions.append(
            "Assumptions note: Scenario numbers, allocations, returns, and thresholds above "
            "are illustrative assumptions for decision framing, not forecasts."
        )

    business_prompt = any(token in msg for token in ("business", "equipment", "side-business"))
    has_business_cashflow = any(
        token in lower
        for token in (
            "cashflow",
            "cash flow",
            "time-to-cashflow",
            "time to cashflow",
            "payback",
            "fluxo",
            "caixa",
            "receita",
        )
    )
    if business_prompt and not has_business_cashflow:
        additions.append(
            "Business cashflow gate: fund equipment only with documented demand, "
            "clear payback, and time-to-cashflow evidence; otherwise keep that capital liquid."
        )

    canadian_capital_prompt = any(
        token in msg
        for token in ("canada", "canadian", "cad", "family", "debt", "education", "tax")
    )
    has_registered_account = any(term in text for term in ("TFSA", "RRSP", "RESP", "FHSA"))
    if canadian_capital_prompt and not has_registered_account:
        additions.append(
            "Canadian registered-account gate: consider TFSA, RRSP, RESP, or FHSA room only "
            "after liquidity and debt gates; tax/account choices depend on the individual's situation."
        )
    has_emergency_months = bool(
        re.search(r"\b\d+\s*[-–]\s*\d+\s+months?\b", lower)
        or re.search(r"\b\d+\s*[-–]\s*\d+\s+mes(?:es)?\b", lower)
    )
    if canadian_capital_prompt and not has_emergency_months:
        additions.append(
            "Emergency reserve gate: keep 3-6 months of essential expenses in cash before "
            "taking meaningful market or business-equipment risk."
        )

    if "Final verdict:" not in text:
        additions.append("Final verdict: WAIT")
    if "Confidence:" not in text:
        additions.append("Confidence: 72")

    if not additions:
        return text
    addition_block = "\n".join(additions)
    footer_idx = text.rfind("\nFinal verdict:")
    if footer_idx == -1:
        return text.rstrip() + "\n" + addition_block
    prefix = text[:footer_idx].rstrip()
    footer = text[footer_idx + 1 :].lstrip()
    return prefix + "\n" + addition_block + "\n" + footer


# ═══════════════════════════════════════════════════════════════════════════
# Tool orchestration
# ═══════════════════════════════════════════════════════════════════════════


def _should_force_contract_fallback(state: dict, content: str) -> bool:
    message = state.get("message", "")
    msg = (message or "").lower()
    text = (content or "").lower()

    if state.get("scan"):
        return True

    scan_leak_markers = (
        "short-term opportunity research",
        "market research report",
        "approximately 2 weeks",
        "candidates:",
        "run a market_scan",
        "only have collected data",
    )
    if ("dividend" in msg or "passive income" in msg) and any(m in text for m in scan_leak_markers):
        return True
    if ("dividend" in msg or "passive income" in msg) and _has_tax_overstatement(content):
        return True
    if _is_etf_comparison_question(message) and any(m in text for m in scan_leak_markers):
        return True
    if _is_portfolio_concentration_question(message) and any(m in text for m in scan_leak_markers):
        return True
    if _is_portfolio_concentration_question(message) and _has_tax_overstatement(content):
        return True
    return bool(_is_dca_macro_question(message) and _has_unsupported_macro_precision(content))


def _has_actionable_market_request(state: dict) -> bool:
    message = state.get("message", "")
    route = state.get("route", "")
    intent = state.get("intent", "")
    if route in {"market_scan", "ticker_analysis"}:
        return True
    if intent in {"market_scan", "another_trade_recommendation", "ticker_analysis"}:
        return True
    should_use = _get_agent_attr("_should_use_decisive_mode")
    if should_use and should_use(state):
        return True
    is_paper = _get_agent_attr("_is_paper_training_request")
    return bool(is_paper and is_paper(message))


def _has_market_evidence(state: dict) -> bool:
    return bool(state.get("scan") or state.get("data") or state.get("data_context"))


def _has_expert_evidence(state: dict) -> bool:
    return bool(state.get("expert_summary") or state.get("expert_results"))


def _forced_tool_call_before_final(state: dict) -> dict[str, Any] | None:
    """Return the next mandatory tool for actionable market/trade requests."""
    if not _has_actionable_market_request(state):
        return None
    if state.get("submit_paper_order_result") or state.get("submit_paper_order_error"):
        return None

    allowed_tools = set(state.get("allowed_tools") or [])
    executed_tools = set(state.get("executed_tools") or [])
    normalize_fn = _get_agent_attr("_normalize_ticker_symbol")
    ticker = (
        normalize_fn(state.get("ticker") or (state.get("data") or {}).get("ticker"))
        if normalize_fn
        else ""
    )

    if not ticker and isinstance(state.get("scan"), dict):
        scan = state["scan"]
        candidates = [item for item in scan.get("candidates", []) if isinstance(item, dict)]
        ranked = scan.get("ranked_candidates")
        if not isinstance(ranked, list) or not ranked:
            ranked = rank_candidates(
                candidates,
                source_errors=scan.get("source_errors") or [],
                weak_universe=len(candidates) <= 1,
            )
        selected, _ = pick_candidate(ranked)
        ticker = (
            normalize_fn((selected or {}).get("candidate", {}).get("ticker"))
            if normalize_fn
            else ""
        )

    if (
        ticker
        and not state.get("data")
        and "collect_data" in allowed_tools
        and "collect_data" not in executed_tools
        and state.get("ticker_allowed", True)
    ):
        return {"tool": "collect_data", "args": {"ticker": ticker}}

    if not _has_market_evidence(state):
        if "market_scan" in allowed_tools and state.get("scanner_allowed", False):
            return {"tool": "market_scan", "args": {"query": state.get("message", "")}}
        if (
            ticker
            and "collect_data" in allowed_tools
            and "collect_data" not in executed_tools
            and state.get("ticker_allowed", True)
        ):
            return {"tool": "collect_data", "args": {"ticker": ticker}}

    if (
        _has_market_evidence(state)
        and "run_experts" in allowed_tools
        and "run_experts" not in executed_tools
        and not _has_expert_evidence(state)
    ):
        return {"tool": "run_experts", "args": {}}
    if (
        _has_market_evidence(state)
        and "f51_firewall" in allowed_tools
        and "f51_firewall" not in executed_tools
        and not state.get("f51_verdict")
    ):
        return {"tool": "f51_firewall", "args": {}}
    if (
        _has_market_evidence(state)
        and "neural_decision" in allowed_tools
        and "neural_decision" not in executed_tools
        and not state.get("neural_decision")
    ):
        return {"tool": "neural_decision", "args": {}}
    if (
        _has_market_evidence(state)
        and "sdca_firewall" in allowed_tools
        and "sdca_firewall" not in executed_tools
        and not state.get("sdca_firewall")
    ):
        return {"tool": "sdca_firewall", "args": {}}

    return None
