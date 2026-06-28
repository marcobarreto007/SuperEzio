#!/usr/bin/env python
"""IBKR paper order CLI — called as subprocess from the pipeline.

Usage:
  python scripts/_ibkr_order.py BUY NVDA 4 206.85
  python scripts/_ibkr_order.py SELL PLUG 5 3.20

Output: JSON with order result to stdout.
Exit 0 = success, exit 1 = error.
"""

import json
import os
import sys
import time
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT / "src"))


def _gate_check(action: str, ticker: str, qty: float, limit_price: float) -> dict:
    """F51 Trade Gate — mandatório para qualquer ordem via CLI.

    Retorna {"allowed": True} ou {"blocked": True, "reason": "..."}.
    """
    # ── GATE 0: Raw CLI must be explicitly enabled ──
    raw_cli_allowed = os.getenv("F51_ALLOW_RAW_IBKR_CLI", "false").strip().lower()
    if raw_cli_allowed not in ("1", "true", "yes", "on"):
        return {
            "blocked": True,
            "reason": "BLOCKED_RAW_CLI_DISABLED",
            "message": "Raw IBKR CLI is disabled by default. Set F51_ALLOW_RAW_IBKR_CLI=true to enable.",
        }

    # ── GATE 1: Execution freeze ──
    freeze = os.getenv("F51_TRADING_EXECUTION_FREEZE", "true").strip().lower()
    if freeze not in ("0", "false", "no", "off"):
        return {
            "blocked": True,
            "reason": "BLOCKED_BY_FREEZE",
            "message": "Trading execution is frozen. Set F51_TRADING_EXECUTION_FREEZE=false to trade.",
        }

    # ── GATE 2: Paper mode must be explicitly confirmed ──
    paper_confirmed = os.getenv("F51_PAPER_MODE_CONFIRMED", "false").strip().lower()
    if paper_confirmed not in ("1", "true", "yes", "on"):
        return {
            "blocked": True,
            "reason": "BLOCKED_PAPER_NOT_CONFIRMED",
            "message": "Paper trading mode not confirmed. Set F51_PAPER_MODE_CONFIRMED=true.",
        }

    # ── GATE 3: Full F51 Trade Gate validation ──
    try:
        from core.pipeline.f51_trade_gate import evaluate_trade_gate

        gate_decision = evaluate_trade_gate(
            message=f"CLI order: {action} {qty} {ticker} @ {limit_price}",
            ticker=ticker,
            thesis_ticker="",
            qty=int(qty),
            limit_price=limit_price,
            run_id=f"raw-cli-{int(time.time())}",
        )

        if gate_decision.status != "ALLOW":
            return {
                "blocked": True,
                "reason": f"f51_trade_gate:{gate_decision.reason_code}",
                "message": gate_decision.reason,
                "gates_failed": gate_decision.gates_failed,
            }
    except ImportError:
        return {
            "blocked": True,
            "reason": "f51_trade_gate_unavailable",
            "message": "F51 Trade Gate module not found — blocking all orders.",
        }
    except Exception as exc:
        return {
            "blocked": True,
            "reason": f"f51_trade_gate_error:{str(exc)[:80]}",
            "message": f"F51 Trade Gate error — blocking: {str(exc)[:120]}",
        }

    return {"allowed": True}


def main():
    if len(sys.argv) < 4:
        print(
            json.dumps({"error": "usage: _ibkr_order.py <BUY|SELL> <TICKER> <QTY> [LIMIT_PRICE]"})
        )
        sys.exit(1)

    action = sys.argv[1].upper()
    ticker = sys.argv[2].upper()
    qty = float(sys.argv[3])
    limit_price = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0

    # ═══════════════════════════════════════════════════════════
    # F51 TRADE GATE — Mandatory before any IBKR call
    # ═══════════════════════════════════════════════════════════
    gate_result = _gate_check(action, ticker, qty, limit_price)
    if gate_result.get("blocked"):
        print(json.dumps(gate_result))
        sys.exit(1)

    try:
        from ib_insync import IB, Stock, LimitOrder, MarketOrder

        ib = IB()
        client_id = int(time.time() * 1000) % 9000 + 100
        ib.connect("127.0.0.1", 7497, clientId=client_id, timeout=10)
        contract = Stock(ticker, "SMART", "USD")
        ib.qualifyContracts(contract)

        if limit_price > 0:
            order = LimitOrder(action, qty, limit_price)
            order.tif = 'GTC'  # Good-Til-Canceled — sobrevive ao preset DAY
        else:
            order = MarketOrder(action, qty)
            order.tif = 'GTC'

        trade = ib.placeOrder(contract, order)
        ib.sleep(5)  # Wait longer for order acknowledgment

        perm_id = getattr(trade.order, "permId", 0) or 0
        tws_order_id = getattr(trade.order, "orderId", 0) or 0
        result = {
            "order_id": perm_id or tws_order_id,
            "perm_id": perm_id or None,
            "tws_order_id": tws_order_id or None,
            "client_id": getattr(trade.order, "clientId", client_id),
            "symbol": ticker,
            "action": action,
            "qty": qty,
            "limit_price": limit_price if limit_price > 0 else None,
            "status": trade.orderStatus.status,
            "filled": trade.orderStatus.filled,
            "avg_price": trade.orderStatus.avgFillPrice,
            "gate_checked": True,
        }

        for p in ib.positions():
            if p.contract.symbol == ticker:
                result["position"] = f"{p.position} shares @ avg {p.avgCost}"

        ib.disconnect()
        print(json.dumps(result))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)[:200], "gate_checked": True}))
        sys.exit(1)


if __name__ == "__main__":
    main()
