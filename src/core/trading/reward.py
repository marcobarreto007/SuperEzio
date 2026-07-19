"""Reward function — computes RL reward signals from trade outcomes."""

from __future__ import annotations

import math
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
    confidence_at_entry: float | None
    verdict_at_entry: float | None
    risk_at_entry: float | None = None
    fees: float = 0.0
    slippage: float = 0.0
    stop_loss_hit: bool = False
    take_profit_hit: bool = False
    ceo_response_text: str = ""
    pipeline_state: dict | None = None


@dataclass(frozen=True)
class RewardComponents:
    pnl_reward: float
    risk_adjusted_reward: float
    confidence_alignment: float
    duration_penalty: float
    coverage_penalty: float
    total_reward: float


class RewardFunction:
    """Computes reward signals for RL training.

    Components:
    - PnL reward: proportional to profit, penalizes losses
    - Risk-adjusted: Sharpe-like reward normalized by risk taken
    - Confidence alignment: reward when confidence matches outcome
    - Duration penalty: penalizes holding too long without profit
    - Coverage penalty: penalizes missing required module mentions
    """

    def __init__(
        self,
        pnl_weight: float = 1.0,
        risk_weight: float = 0.5,
        confidence_weight: float = 0.3,
        duration_penalty_rate: float = 0.0001,
        max_duration_seconds: float = 86400.0,
        coverage_penalty_weight: float = 0.2,
    ):
        self.pnl_weight = pnl_weight
        self.risk_weight = risk_weight
        self.confidence_weight = confidence_weight
        self.duration_penalty_rate = duration_penalty_rate
        self.max_duration_seconds = max_duration_seconds
        self.coverage_penalty_weight = coverage_penalty_weight

    def compute(self, outcome: TradeOutcome) -> RewardComponents:
        pnl_reward = self._pnl_reward(outcome)
        risk_reward = self._risk_adjusted_reward(outcome)
        confidence = self._confidence_alignment(outcome)
        duration = self._duration_penalty(outcome)
        coverage_penalty = self._coverage_penalty(outcome)

        weighted_signal = (
            self.pnl_weight * pnl_reward
            + self.risk_weight * risk_reward
            + self.confidence_weight * confidence
        )
        total_weight = self.pnl_weight + self.risk_weight + self.confidence_weight
        total = weighted_signal / max(total_weight, 1e-12) - duration - coverage_penalty
        total = max(-1.0, min(1.0, total))

        return RewardComponents(
            pnl_reward=round(pnl_reward, 6),
            risk_adjusted_reward=round(risk_reward, 6),
            confidence_alignment=round(confidence, 6),
            duration_penalty=round(duration, 6),
            coverage_penalty=round(coverage_penalty, 6),
            total_reward=round(total, 6),
        )

    def _pnl_reward(self, outcome: TradeOutcome) -> float:
        notional = abs(outcome.entry_price * outcome.qty)
        if notional <= 0:
            return 0.0
        costs = max(0.0, outcome.fees) + max(0.0, outcome.slippage)
        net_return = (outcome.pnl - costs) / notional
        # Symmetric and scale invariant: the same percentage return receives
        # the same reward regardless of account or position size.
        return math.tanh(10.0 * net_return)

    def _risk_adjusted_reward(self, outcome: TradeOutcome) -> float:
        costs = max(0.0, outcome.fees) + max(0.0, outcome.slippage)
        if outcome.risk_at_entry is not None:
            risk = max(0.0, outcome.risk_at_entry) + costs
        else:
            # Missing ex-ante risk is unknown, not an invented 1% position risk.
            return 0.0
        if risk <= 0:
            return 0.0
        return max(-1.0, min(1.0, (outcome.pnl - costs) / risk))

    def _confidence_alignment(self, outcome: TradeOutcome) -> float:
        if outcome.confidence_at_entry is None or outcome.pnl == 0:
            return 0.0
        probability = max(0.0, min(1.0, float(outcome.confidence_at_entry)))
        target = 1.0 if outcome.pnl > 0 else 0.0
        # Brier skill relative to an uninformative 0.5 forecast.  A confident
        # wrong forecast is penalized more, not less.
        return max(-1.0, min(1.0, 1.0 - 4.0 * (probability - target) ** 2))

    def _duration_penalty(self, outcome: TradeOutcome) -> float:
        if outcome.pnl > 0 or outcome.hold_duration_seconds <= self.max_duration_seconds:
            return 0.0
        excess = outcome.hold_duration_seconds - self.max_duration_seconds
        return min(0.5, excess * self.duration_penalty_rate)

    def _coverage_penalty(self, outcome: TradeOutcome) -> float:
        if not outcome.ceo_response_text or not outcome.pipeline_state:
            return 0.0

        # Avoid circular imports since prompts builder imports PipelineState
        from ..pipeline.prompts.builder import _evaluate_module_coverage

        _, missing = _evaluate_module_coverage(outcome.ceo_response_text, outcome.pipeline_state)
        return len(missing) * self.coverage_penalty_weight
