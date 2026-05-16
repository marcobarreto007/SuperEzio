"""Reward function — computes RL reward signals from trade outcomes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeOutcome:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    hold_duration_seconds: float
    confidence_at_entry: float
    verdict_at_entry: float
    stop_loss_hit: bool = False
    take_profit_hit: bool = False


@dataclass(frozen=True)
class RewardComponents:
    pnl_reward: float
    risk_adjusted_reward: float
    confidence_alignment: float
    duration_penalty: float
    total_reward: float


class RewardFunction:
    """Computes reward signals for RL training.

    Components:
    - PnL reward: proportional to profit, penalizes losses
    - Risk-adjusted: Sharpe-like reward normalized by risk taken
    - Confidence alignment: reward when confidence matches outcome
    - Duration penalty: penalizes holding too long without profit
    """

    def __init__(
        self,
        pnl_weight: float = 1.0,
        risk_weight: float = 0.5,
        confidence_weight: float = 0.3,
        duration_penalty_rate: float = 0.0001,
        max_duration_seconds: float = 86400.0,
    ):
        self.pnl_weight = pnl_weight
        self.risk_weight = risk_weight
        self.confidence_weight = confidence_weight
        self.duration_penalty_rate = duration_penalty_rate
        self.max_duration_seconds = max_duration_seconds

    def compute(self, outcome: TradeOutcome) -> RewardComponents:
        pnl_reward = self._pnl_reward(outcome)
        risk_reward = self._risk_adjusted_reward(outcome)
        confidence = self._confidence_alignment(outcome)
        duration = self._duration_penalty(outcome)

        total = (
            self.pnl_weight * pnl_reward
            + self.risk_weight * risk_reward
            + self.confidence_weight * confidence
            - duration
        )
        total = max(-1.0, min(1.0, total))

        return RewardComponents(
            pnl_reward=round(pnl_reward, 6),
            risk_adjusted_reward=round(risk_reward, 6),
            confidence_alignment=round(confidence, 6),
            duration_penalty=round(duration, 6),
            total_reward=round(total, 6),
        )

    def _pnl_reward(self, outcome: TradeOutcome) -> float:
        if outcome.pnl > 0:
            return min(1.0, outcome.pnl / 1000.0)
        return max(-1.0, outcome.pnl / 500.0)

    def _risk_adjusted_reward(self, outcome: TradeOutcome) -> float:
        risk = abs(outcome.entry_price - outcome.exit_price) * outcome.qty
        if risk == 0:
            return 0.0
        return max(-1.0, min(1.0, outcome.pnl / risk))

    def _confidence_alignment(self, outcome: TradeOutcome) -> float:
        if outcome.pnl > 0:
            return outcome.confidence_at_entry * 0.5
        return -(1.0 - outcome.confidence_at_entry) * 0.5

    def _duration_penalty(self, outcome: TradeOutcome) -> float:
        if outcome.hold_duration_seconds <= self.max_duration_seconds:
            return 0.0
        excess = outcome.hold_duration_seconds - self.max_duration_seconds
        return min(0.5, excess * self.duration_penalty_rate)
