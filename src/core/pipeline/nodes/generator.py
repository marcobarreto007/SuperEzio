"""Answer Generator — re-exports from agent.py (Phase 1 facade).

All answer/fallback/repair logic. Import from here instead of agent.py
to reduce coupling to the god object. Implementation still lives in agent.py
until cross-group dependency tests are in place.

Usage:
    from core.pipeline.nodes.generator import _market_scan_answer
"""

from __future__ import annotations

from .agent import (
    _advisory_knowledge_fallback_answer,
    _complex_finance_fallback_answer,
    _contract_fallback_answer,
    _decisive_trade_order_answer,
    _final_payload,
    _forced_tool_call_before_final,
    _has_actionable_market_request,
    _has_expert_evidence,
    _has_market_evidence,
    _has_tax_overstatement,
    _has_unsupported_macro_precision,
    _industry_research_fallback_answer,
    _is_dca_macro_question,
    _is_etf_comparison_question,
    _is_portfolio_concentration_question,
    _loop_failsafe_answer,
    _market_scan_answer,
    _render_decisive_trade_order,
    _repair_answer_quality,
    _repair_complex_finance_answer,
    _repair_known_etf_category_errors,
    _repair_overlapping_etf_tickers,
    _repair_short_term_return_forecasts,
    _repair_tax_overstatements,
    _repair_unsourced_etf_tickers,
    _repair_unsupported_exact_returns,
    _risk_lab_fallback_answer,
    _should_force_contract_fallback,
    _tool_blocked_answer,
)

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
