"""Kill switch — circuit breaker for SuperEzio trading."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from core.trading.workflow_store import TradeWorkflowStore, resolve_workflow_db_path


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
    last_reset_utc: str = ""


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
        *,
        store: TradeWorkflowStore | None = None,
        state_key: str = "global_kill_switch",
    ):
        self.daily_loss_limit = abs(daily_loss_limit)
        self.max_drawdown_pct = max_drawdown_pct
        self.max_consecutive_losses = max_consecutive_losses
        self._store = store
        self._state_key = state_key
        persisted = self._store.load_system_state(state_key) if self._store is not None else None
        if persisted is not None:
            reason = persisted.get("reason")
            persisted["reason"] = KillSwitchReason(reason) if reason else None
            self.state = KillSwitchState(**persisted)
        else:
            self.state = KillSwitchState(
                peak_equity=initial_equity,
                last_reset_utc=datetime.now(timezone.utc).date().isoformat(),
            )
            self._persist()
        self._history: list[dict[str, Any]] = []

    def _persist(self) -> None:
        if self._store is None:
            return
        data = asdict(self.state)
        data["reason"] = self.state.reason.value if self.state.reason else None
        self._store.save_system_state(self._state_key, data)

    @property
    def is_active(self) -> bool:
        self._reset_if_new_utc_day()
        return self.state.is_active

    def activate(self, reason: KillSwitchReason) -> None:
        if not self.state.is_active:
            self.state.is_active = True
            self.state.reason = reason
            self.state.activated_at = time.time()
            self._history.append(
                {
                    "event": "activated",
                    "reason": reason.value,
                    "timestamp": self.state.activated_at,
                    "daily_pnl": self.state.daily_pnl,
                }
            )
            self._persist()

    def deactivate(self) -> None:
        if self.state.is_active:
            self._history.append(
                {
                    "event": "deactivated",
                    "timestamp": time.time(),
                }
            )
            self.state.is_active = False
            self.state.reason = None
            self.state.activated_at = 0.0
            self._persist()

    def record_trade(self, pnl: float) -> bool:
        """Record a trade result. Returns True if kill switch triggered."""
        self._reset_if_new_utc_day()
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
            self._persist()
            return True

        if self.state.peak_equity > 0:
            drawdown = (self.state.peak_equity - current_equity) / self.state.peak_equity
            if drawdown >= self.max_drawdown_pct:
                self.activate(KillSwitchReason.MAX_DRAWDOWN)
                self._persist()
                return True

        if self.state.consecutive_losses >= self.max_consecutive_losses:
            self.activate(KillSwitchReason.CONSECUTIVE_LOSSES)
            self._persist()
            return True

        self._persist()
        return False

    def check(self) -> KillSwitchState:
        self._reset_if_new_utc_day()
        return self.state

    def reset_day(self) -> None:
        self.state.daily_pnl = 0.0
        self.state.trade_count = 0
        self.state.consecutive_losses = 0
        self.state.last_reset_utc = datetime.now(timezone.utc).date().isoformat()
        if not self.state.is_active or self.state.reason == KillSwitchReason.DAILY_LOSS_LIMIT:
            self.deactivate()
        self._persist()

    def _reset_if_new_utc_day(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if self.state.last_reset_utc != today:
            self.reset_day()

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)


_GLOBAL_KILL_SWITCH: KillSwitch | None = None
_GLOBAL_KILL_SWITCH_PATH: Path | None = None


def get_kill_switch() -> KillSwitch:
    """Return the process-wide paper-trading kill switch."""

    global _GLOBAL_KILL_SWITCH, _GLOBAL_KILL_SWITCH_PATH
    configured_path = resolve_workflow_db_path()
    if _GLOBAL_KILL_SWITCH is None or _GLOBAL_KILL_SWITCH_PATH != configured_path:
        from core.mission_context import get_mission_equity

        _GLOBAL_KILL_SWITCH = KillSwitch(
            initial_equity=get_mission_equity(),
            store=TradeWorkflowStore(configured_path),
        )
        _GLOBAL_KILL_SWITCH_PATH = configured_path
    _GLOBAL_KILL_SWITCH.check()
    return _GLOBAL_KILL_SWITCH


def reset_kill_switch_for_test() -> KillSwitch:
    """Reset the singleton in tests without touching production journal state."""

    global _GLOBAL_KILL_SWITCH, _GLOBAL_KILL_SWITCH_PATH
    from core.mission_context import get_mission_equity

    _GLOBAL_KILL_SWITCH = KillSwitch(initial_equity=get_mission_equity())
    _GLOBAL_KILL_SWITCH_PATH = resolve_workflow_db_path()
    return _GLOBAL_KILL_SWITCH
