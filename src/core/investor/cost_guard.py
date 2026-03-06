import threading
from typing import Any


class CostGuard:
    def __init__(
        self, daily_budget_usd: float = 10.0, max_runs_per_day: int = 50
    ) -> None:
        self.daily_budget_usd: float = daily_budget_usd
        self.max_runs_per_day: int = max_runs_per_day
        self._cost_today_usd: float = 0.0
        self._runs_today: int = 0

    def check(self) -> None:
        if self._runs_today >= self.max_runs_per_day:
            raise RuntimeError("daily_runs_exceeded")
        if self._cost_today_usd >= self.daily_budget_usd:
            raise RuntimeError("daily_budget_exceeded")

    def record(self, input_tokens: int, output_tokens: int, model: str) -> None:
        self._runs_today += 1
        # Estimativa simples de custo
        cost: float = (input_tokens + output_tokens) * 0.00001
        self._cost_today_usd += cost

    def validate_decision(self, ticker: str, action: str, pnl: float) -> dict[str, Any]:
        return {"safe": True, "reason": "OK"}

    def status(self) -> dict[str, Any]:
        return {
            "daily_budget_usd": self.daily_budget_usd,
            "max_runs_per_day": self.max_runs_per_day,
            "cost_today_usd": round(self._cost_today_usd, 6),
            "runs_today": self._runs_today,
            "budget_remaining_usd": round(
                self.daily_budget_usd - self._cost_today_usd, 6
            ),
            "runs_remaining": max(0, self.max_runs_per_day - self._runs_today),
        }


_LOCK: threading.Lock = threading.Lock()
_INSTANCE: CostGuard | None = None


def get_cost_guard() -> CostGuard:
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                _INSTANCE = CostGuard()
    return _INSTANCE
