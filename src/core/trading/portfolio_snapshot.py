"""Unified IBKR portfolio snapshot — single source of truth.

Used by both agent.py (for in-prompt portfolio injection) and graph.py
(auto_full_analysis pipeline node). Never opens a second ib_insync client.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def fetch_portfolio_snapshot(language: str = "en") -> str:
    """Format the IBKRService cache. No extra Gateway clientId."""
    try:
        from adapters.broker.ibkr_service import get_ibkr_service

        service = get_ibkr_service()
        status = service.get_status()
        if not status.get("connected"):
            return "IBKR offline — portfolio data unavailable"
        positions = service.get_positions(wait_timeout=0.0)
        equity = float(service.get_account_equity(wait_timeout=0.0) or 0.0)
        if not positions:
            if language == "pt":
                return (
                    f"CARTEIRA ATUAL (IBKR paper):\n"
                    f"  Equity: ${equity:,.2f}\n"
                    f"  (vazia — sem posições)\n"
                )
            return (
                f"CURRENT PORTFOLIO (IBKR paper):\n"
                f"  Equity: ${equity:,.2f}\n"
                f"  (empty — no positions)\n"
            )

        total_value = 0.0
        position_lines = []
        for p in positions:
            symbol = str(p.get("symbol") or p.get("ticker") or "")
            qty = float(p.get("quantity") or p.get("shares") or 0)
            avg = float(p.get("avg_cost") or 0)
            price = float(p.get("current_price") or avg)
            pos_val = float(p.get("market_value") or qty * price)
            pnl = (price - avg) * qty
            total_value += pos_val
            if language == "pt":
                position_lines.append(
                    f"  {symbol}: {qty:g} ações @ avg ${avg:.2f} "
                    f"(atual ${price:.2f}) = ${pos_val:,.2f} [PnL: ${pnl:+,.2f}]"
                )
            else:
                position_lines.append(
                    f"    {symbol}: {qty:g} shares @ avg ${avg:.2f} "
                    f"(current ${price:.2f}) = ${pos_val:,.2f} [PnL: ${pnl:+,.2f}]"
                )

        cash = equity - total_value
        concentration_pct = (total_value / equity * 100) if equity > 0 else 0
        concentration_warning = "⚠️ ALTA" if concentration_pct > 50 else "OK"
        if language == "pt":
            return (
                f"CARTEIRA ATUAL (IBKR paper):\n"
                f"  Equity: ${equity:,.2f}  |  Posições: {len(positions)}\n"
                + "\n".join(position_lines)
                + "\n"
                + f"  Total investido: ${total_value:,.2f}  |  Cash: ${cash:,.2f}\n"
                + f"  Concentração: {concentration_warning} ({concentration_pct:.0f}% do equity)\n"
            )
        return (
            f"CURRENT PORTFOLIO (IBKR paper):\n"
            f"  Equity: ${equity:,.2f}\n"
            f"  Positions: {len(positions)}\n"
            + "".join(f"{p}\n" for p in position_lines)
            + f"  Total invested: ${total_value:,.2f}\n"
            + f"  Cash: ${cash:,.2f}\n"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("IBKR portfolio snapshot failed: %s", exc)
        return "IBKR offline — portfolio data unavailable"


def get_cached_snapshot(state: dict, language: str = "en") -> str:
    """Get portfolio snapshot from state cache, falling back to service cache."""
    pf = state.get("portfolio_snapshot") or state.get("portfolio_context") or ""
    if pf and "offline" not in pf.lower():
        return pf
    return fetch_portfolio_snapshot(language)
