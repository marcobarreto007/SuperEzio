#!/usr/bin/env python
"""IBKR position check — called as subprocess from pipeline.

Usage: python scripts/_ibkr_position_check.py INTC
Output: JSON with position pct of equity.
"""

import json
import sys

from ib_insync import IB


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: _ibkr_position_check.py <TICKER>"}))
        sys.exit(1)

    ticker = sys.argv[1].upper()

    try:
        ib = IB()
        ib.connect("127.0.0.1", 7497, clientId=999, timeout=5)

        equity = 100_000.0
        for v in ib.accountSummary():
            if v.tag == "NetLiquidation":
                equity = float(v.value)

        position_shares = 0.0
        position_value = 0.0
        for p in ib.positions():
            if p.contract.symbol == ticker:
                position_shares = float(p.position)
                position_value = position_shares * float(p.avgCost)

        ib.disconnect()

        pct = (position_value / equity * 100) if equity > 0 else 0

        print(
            json.dumps(
                {
                    "ticker": ticker,
                    "shares": position_shares,
                    "value": round(position_value, 2),
                    "equity": round(equity, 2),
                    "pct_of_equity": round(pct, 1),
                }
            )
        )
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)[:200]}))
        sys.exit(1)


if __name__ == "__main__":
    main()
