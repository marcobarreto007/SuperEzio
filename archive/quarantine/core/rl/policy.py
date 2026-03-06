"""
Experimental reinforcement-learning utilities for SuperEzio.

Usage:
    from core.rl import PolicyLearner
    learner = PolicyLearner()
    agents = learner.select_agents(asset_profile, market_features)
"""

from __future__ import annotations

import logging
from typing import Any

from .bandit import AgentBandit, AGENT_ORDER
from .rewards import RewardCalculator

logger = logging.getLogger(__name__)


class PolicyLearner:
    """High-level experimental policy wrapper around the bandit.

    Falls back to deterministic penny-stock selector while cold.
    """

    MIN_UPDATES_FOR_PREDICTION = 20

    def __init__(self) -> None:
        self.bandit = AgentBandit()
        self.reward_calc = RewardCalculator()
        self._selector = None

    def select_agents(
        self,
        asset_profile: dict[str, Any] | None = None,
        market_features: dict[str, Any] | None = None,
        top_k: int = 3,
    ) -> list[str]:
        if self.bandit.total_updates >= self.MIN_UPDATES_FOR_PREDICTION:
            selected = self.bandit.agent_mask(
                asset_profile=asset_profile,
                market_features=market_features,
                top_k=top_k,
            )
            logger.debug(
                "RL selected agents: %s (updates=%d)",
                selected,
                self.bandit.total_updates,
            )
            return selected
        return self._fallback_select(asset_profile, market_features, top_k)

    def observe(
        self,
        ticker: str,
        agent_mask: list[str],
        expert_results: dict[str, Any] | None = None,
        data_quality: str = "unknown",
        trade_outcome: dict[str, Any] | None = None,
        asset_profile: dict[str, Any] | None = None,
        market_features: dict[str, Any] | None = None,
    ) -> float:
        reward = self.reward_calc.compute(
            ticker=ticker,
            trade_outcome=trade_outcome,
            expert_results=expert_results,
            data_quality=data_quality,
        )
        self.bandit.update(
            asset_profile=asset_profile,
            market_features=market_features,
            agent_mask=agent_mask,
            reward=reward,
        )
        logger.info(
            "RL observe: ticker=%s agents=%s reward=%.3f total_updates=%d",
            ticker,
            agent_mask,
            reward,
            self.bandit.total_updates,
        )
        return reward

    def train_from_history(self, ticker_filter: str | None = None) -> int:
        journal = self.reward_calc._get_journal()
        if journal is None:
            logger.warning("LabJournal unavailable — cannot train from history")
            return 0

        all_entries = journal.all_entries()
        if ticker_filter:
            all_entries = [
                e
                for e in all_entries
                if e.get("ticker", "").upper() == ticker_filter.upper()
            ]

        by_ticker: dict[str, list[dict]] = {}
        for entry in all_entries:
            t = entry.get("ticker", "").upper()
            if t:
                by_ticker.setdefault(t, []).append(entry)

        total = 0
        for ticker, entries in by_ticker.items():
            agent_mask = list(AGENT_ORDER)
            episodes = []
            for entry in entries:
                pnl_pct = entry.get("pnl_pct")
                if pnl_pct is None:
                    continue
                reward = self.reward_calc._pnl_to_reward(float(pnl_pct))
                report = entry.get("report_snapshot") or {}
                scores = report.get("scores", {})

                asset_profile = {
                    "volatility_level": (
                        "extreme"
                        if scores.get("trap_risk", 0) > 0.7
                        else "high"
                        if scores.get("trap_risk", 0) > 0.4
                        else "moderate"
                    ),
                    "has_high_volume": scores.get("volume_spike_risk", 0) > 0.5,
                    "market": ("CA" if ".TO" in ticker or ".V" in ticker else "US"),
                }
                market_features = {
                    "price": entry.get("entry_price", 0),
                    "missing_data_ratio": 0.3,
                }
                episodes.append(
                    {
                        "asset_profile": asset_profile,
                        "market_features": market_features,
                        "agent_mask": agent_mask,
                        "reward": reward,
                    }
                )

            total += self.bandit.batch_update(episodes)

        logger.info(
            "RL trained from history: %d episodes across %d tickers",
            total,
            len(by_ticker),
        )
        return total

    def stats(self) -> dict[str, Any]:
        return {
            **self.bandit.stats(),
            "cold_start": self.bandit.total_updates < self.MIN_UPDATES_FOR_PREDICTION,
        }

    def reset(self) -> None:
        self.bandit.reset()

    def _fallback_select(
        self,
        asset_profile: dict[str, Any] | None = None,
        market_features: dict[str, Any] | None = None,
        top_k: int = 3,
    ) -> list[str]:
        if self._selector is None:
            from core.agent_runtime.agent_selector import (
                AssetProfile,
                PennyStockAgentSelector,
            )

            self._selector = PennyStockAgentSelector()

        profile = AssetProfile(
            ticker="",
            **(asset_profile or {}),
        )
        context = ""
        if market_features:
            context = " ".join(f"{k}={v}" for k, v in market_features.items() if v)
        selected = self._selector.select(profile, context)
        return selected[:top_k]


policy_learner = PolicyLearner()
