"""Unified IBKR portfolio snapshot — single source of truth.

Used by both agent.py (for in-prompt portfolio injection) and graph.py
(auto_full_analysis pipeline node).
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_IBKR_HOST = "127.0.0.1"
_IBKR_PORT = 7497  # TWS paper trading port
_IBKR_TIMEOUT = 5.0


def fetch_portfolio_snapshot(language: str = "en") -> str:
    """Fetch current IBKR paper portfolio snapshot.

    Returns formatted string with equity, positions, PnL, and concentration.
    Returns "IBKR offline — portfolio data unavailable" if connection fails.

    Args:
        language: "en" for English, "pt" for Portuguese labels.
    """
    try:
        from ib_insync import IB, Stock

        ib = IB()
        ib.connect(
            _IBKR_HOST,
            _IBKR_PORT,
            clientId=int(time.time() * 1000) % 9000 + 100,
            timeout=_IBKR_TIMEOUT,
        )
        ib.reqMarketDataType(3)  # delayed data, free

        pos_list = ib.positions()
        equity = sum(float(v.value) for v in ib.accountSummary() if v.tag == "NetLiquidation")

        if not pos_list:
            ib.disconnect()
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

        contracts = [Stock(p.contract.symbol, "SMART", "USD") for p in pos_list]
        ib.qualifyContracts(*contracts)
        tickers = [ib.reqMktData(c) for c in contracts]
        ib.sleep(1.0)

        total_value = 0.0
        position_lines = []

        for p, ticker in zip(pos_list, tickers):
            ib.cancelMktData(p.contract)
            price = ticker.last or ticker.close or ticker.marketPrice() or float(p.avgCost)
            pos_val = float(p.position) * price
            pnl = (price - float(p.avgCost)) * float(p.position)
            total_value += pos_val

            if language == "pt":
                position_lines.append(
                    f"  {p.contract.symbol}: {p.position} ações @ avg ${float(p.avgCost):.2f} "
                    f"(atual ${price:.2f}) = ${pos_val:,.2f} [PnL: ${pnl:+,.2f}]"
                )
            else:
                position_lines.append(
                    f"    {p.contract.symbol}: {p.position} shares @ avg ${float(p.avgCost):.2f} "
                    f"(current ${price:.2f}) = ${pos_val:,.2f} [PnL: ${pnl:+,.2f}]"
                )

        ib.disconnect()

        cash = equity - total_value
        concentration_pct = (total_value / equity * 100) if equity > 0 else 0
        concentration_warning = "⚠️ ALTA" if concentration_pct > 50 else "OK"

        if language == "pt":
            return (
                f"CARTEIRA ATUAL (IBKR paper):\n"
                f"  Equity: ${equity:,.2f}  |  Posições: {len(pos_list)}\n"
                + "\n".join(position_lines)
                + "\n"
                + f"  Total investido: ${total_value:,.2f}  |  Cash: ${cash:,.2f}\n"
                + f"  Concentração: {concentration_warning} ({concentration_pct:.0f}% do equity)\n"
            )

        return (
            f"CURRENT PORTFOLIO (IBKR paper):\n"
            f"  Equity: ${equity:,.2f}\n"
            f"  Positions: {len(pos_list)}\n"
            + "".join(f"{p}\n" for p in position_lines)
            + (
                f"  Total invested: ${total_value:,.2f}\n"
                if position_lines
                else "  (empty — no positions)\n"
            )
            + f"  Cash: ${cash:,.2f}\n"
        )

    except Exception as exc:  # noqa: BLE001 — catch amplo deliberado: contrato "IBKR offline"; ib_insync lança exceções variadas e o fallback nunca levanta
        logger.warning("IBKR portfolio snapshot failed: %s", exc)
        return "IBKR offline — portfolio data unavailable"


def get_cached_snapshot(state: dict, language: str = "en") -> str:
    """Get portfolio snapshot from state cache, falling back to live fetch.

    Returns empty string if nothing available (graceful degradation).
    """
    pf = state.get("portfolio_snapshot") or state.get("portfolio_context") or ""
    if pf and "offline" not in pf.lower():
        return pf
    return fetch_portfolio_snapshot(language)
