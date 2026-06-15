#!/usr/bin/env python
"""IBKR paper order CLI — called as subprocess from the pipeline.

Usage:
  python scripts/_ibkr_order.py BUY NVDA 4 206.85
  python scripts/_ibkr_order.py SELL PLUG 5 3.20

Output: JSON with order result to stdout.
Exit 0 = success, exit 1 = error.
"""

import json
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT / "src"))


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

    try:
        from ib_insync import IB, Stock, LimitOrder, MarketOrder

        ib = IB()
        ib.connect("127.0.0.1", 7497, clientId=99, timeout=10)
        contract = Stock(ticker, "SMART", "USD")
        ib.qualifyContracts(contract)

        if limit_price > 0:
            order = LimitOrder(action, qty, limit_price)
            order.tif = 'DAY'  # Explicit TIF — prevents TWS preset cancellation
        else:
            order = MarketOrder(action, qty)
            order.tif = 'DAY'

        trade = ib.placeOrder(contract, order)
        ib.sleep(3)

        result = {
            "order_id": trade.order.orderId,
            "symbol": ticker,
            "action": action,
            "qty": qty,
            "limit_price": limit_price if limit_price > 0 else None,
            "status": trade.orderStatus.status,
            "filled": trade.orderStatus.filled,
            "avg_price": trade.orderStatus.avgFillPrice,
        }

        for p in ib.positions():
            if p.contract.symbol == ticker:
                result["position"] = f"{p.position} shares @ avg {p.avgCost}"

        ib.disconnect()
        print(json.dumps(result))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)[:200]}))
        sys.exit(1)


if __name__ == "__main__":
    main()
