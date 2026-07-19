#!/usr/bin/env python
"""Retired raw IBKR transport.

Orders are accepted only through InteractiveBrokersAdapter after the central
pipeline has attached F51, approval, consensus, and adaptive-policy evidence.
This compatibility entrypoint never contacts IBKR.
"""

from __future__ import annotations

import json
import os


def main() -> int:
    raw_enabled = os.getenv("F51_ALLOW_RAW_IBKR_CLI", "false").strip().lower()
    if raw_enabled not in {"1", "true", "yes", "on"}:
        reason = "BLOCKED_RAW_CLI_DISABLED"
    else:
        frozen = os.getenv("F51_TRADING_EXECUTION_FREEZE", "true").strip().lower()
        if frozen not in {"0", "false", "no", "off"}:
            reason = "BLOCKED_BY_FREEZE"
        else:
            paper = os.getenv("F51_PAPER_MODE_CONFIRMED", "false").strip().lower()
            reason = (
                "BLOCKED_RETIRED_TRANSPORT"
                if paper in {"1", "true", "yes", "on"}
                else "BLOCKED_PAPER_NOT_CONFIRMED"
            )
    print(
        json.dumps(
            {
                "blocked": True,
                "reason": reason,
                "message": "Raw IBKR CLI is retired; use the prepared adapter path.",
            }
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
