"""Kill switch — circuit breaker for SuperEzio trading."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KillSwitchReason(Enum):
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_DRAWDOWN = "max_drawdown"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    MANUAL = "manual"
    VOLATILITY_SPIKE = "volatility_spike"


@dataclass
class KillSwitchState:
    is_active: bool = False
    reason: KillSwitchReason | None = None
    activated_at: float = 0.0
    daily_pnl: float = 0.0
    trade_count: int = 0
    consecutive_losses: int = 0
    peak_equity: float = 0.0


class KillSwitch:
    """Circuit breaker that halts trading when limits are hit.

    Triggers:
    - Daily loss exceeds limit
    - Drawdown from peak exceeds threshold
    - Consecutive losses exceed max
    - Manual activation
    """

    def __init__(
        self,
        daily_loss_limit: float = 500.0,
        max_drawdown_pct: float = 0.10,
        max_consecutive_losses: int = 5,
        initial_equity: float = 10000.0,
    ):
        self.daily_loss_limit = abs(daily_loss_limit)
        self.max_drawdown_pct = max_drawdown_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.state = KillSwitchState(peak_equity=initial_equity)
        self._history: list[dict[str, Any]] = []

    @property
    def is_active(self) -> bool:
        return self.state.is_active

    def activate(self, reason: KillSwitchReason) -> None:
        if not self.state.is_active:
            self.state.is_active = True
            self.state.reason = reason
            self.state.activated_at = time.time()
            self._history.append({
                "event": "activated",
                "reason": reason.value,
                "timestamp": self.state.activated_at,
                "daily_pnl": self.state.daily_pnl,
            })

    def deactivate(self) -> None:
        if self.state.is_active:
            self._history.append({
                "event": "deactivated",
                "timestamp": time.time(),
            })
            self.state.is_active = False
            self.state.reason = None
            self.state.activated_at = 0.0

    def record_trade(self, pnl: float) -> bool:
        """Record a trade result. Returns True if kill switch triggered."""
        self.state.daily_pnl += pnl
        self.state.trade_count += 1
        current_equity = self.state.peak_equity + self.state.daily_pnl

        if pnl >= 0:
            self.state.consecutive_losses = 0
            self.state.peak_equity = max(self.state.peak_equity, current_equity)
        else:
            self.state.consecutive_losses += 1

        # Recalculate after peak update
        current_equity = self.state.peak_equity + self.state.daily_pnl

        # Check triggers
        if self.state.daily_pnl <= -self.daily_loss_limit:
            self.activate(KillSwitchReason.DAILY_LOSS_LIMIT)
            return True

        if self.state.peak_equity > 0:
            drawdown = (self.state.peak_equity - current_equity) / self.state.peak_equity
            if drawdown >= self.max_drawdown_pct:
                self.activate(KillSwitchReason.MAX_DRAWDOWN)
                return True

        if self.state.consecutive_losses >= self.max_consecutive_losses:
            self.activate(KillSwitchReason.CONSECUTIVE_LOSSES)
            return True

        return False

    def check(self) -> KillSwitchState:
        return self.state

    def reset_day(self) -> None:
        self.state.daily_pnl = 0.0
        self.state.trade_count = 0
        if not self.state.is_active or self.state.reason == KillSwitchReason.DAILY_LOSS_LIMIT:
            self.deactivate()

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)
