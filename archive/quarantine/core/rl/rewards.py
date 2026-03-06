"""
Reward calculator for RL agent selection in SuperEzio.

Extracts reward signals from:
1. lab_journal trade outcomes (primary — real PnL)
2. Agent contradiction severity (proxy — lower is better)
3. Data completeness (proxy — more data = better decisions)

All rewards are normalized to [-1, 1].
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RewardCalculator:
    """Computes RL reward signals from SuperEzio decision outcomes.

    Primary signal: trade PnL from lab_journal
    Proxy signals: agent consensus, data completeness

    Formula:
        reward = 0.6 * pnl_signal + 0.25 * consensus_signal + 0.15 * data_signal
    """

    def __init__(self) -> None:
        self._lab_journal = None  # lazy

    def _get_journal(self):
        if self._lab_journal is None:
            try:
                from experts.pennylab.lab_journal import journal

                self._lab_journal = journal
            except Exception as exc:
                logger.debug("PennyLab lab_journal unavailable for rewards: %s", exc)
        return self._lab_journal

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self,
        ticker: str = "",
        trade_outcome: dict[str, Any] | None = None,
        expert_results: dict[str, Any] | None = None,
        data_quality: str = "unknown",
    ) -> float:
        """Compute the reward signal for a decision episode.

        Args:
            ticker: The ticker symbol.
            trade_outcome: Dict with pnl_pct, decision, etc. (from lab_journal).
            expert_results: Dict of agent results for consensus calculation.
            data_quality: Data quality label (ok, partial, timeout, error).
        """
        pnl = self._pnl_signal(ticker, trade_outcome)
        consensus = self._consensus_signal(expert_results or {})
        data = self._data_signal(data_quality)
        return round(0.6 * pnl + 0.25 * consensus + 0.15 * data, 3)

    def compute_from_journal(
        self,
        ticker: str,
        agent_mask: list[str],
    ) -> list[dict[str, Any]]:
        """Build RL episodes from historical lab_journal trades for a ticker.

        Returns list of episode dicts ready for AgentBandit.batch_update().
        """
        journal = self._get_journal()
        if journal is None:
            return []

        trades = journal.load_ticker(ticker)
        episodes = []

        for trade in trades:
            pnl_pct = trade.get("pnl_pct")
            if pnl_pct is None:
                continue
            reward = self._pnl_to_reward(float(pnl_pct))
            report = trade.get("report_snapshot") or {}
            scores = report.get("scores", {})

            asset_profile = {
                "asset_type": "stock",
                "volatility_level": (
                    "extreme"
                    if scores.get("trap_risk", 0) > 0.7
                    else "high"
                    if scores.get("trap_risk", 0) > 0.4
                    else "moderate"
                ),
                "has_reddit_mentions": False,
                "has_high_volume": scores.get("volume_spike_risk", 0) > 0.5,
                "market": (
                    "CA" if ".TO" in ticker.upper() or ".V" in ticker.upper() else "US"
                ),
            }

            market_features = {
                "price": trade.get("entry_price", 0),
                "hype_keyword_count": 0,
                "missing_data_ratio": 0.3,
            }

            episodes.append(
                {
                    "ticker": ticker,
                    "asset_profile": asset_profile,
                    "market_features": market_features,
                    "agent_mask": agent_mask,
                    "reward": reward,
                    "pnl_pct": pnl_pct,
                    "logged_at": trade.get("logged_at", ""),
                }
            )

        return episodes

    # ------------------------------------------------------------------
    # Signal components (all → [-1, 1])
    # ------------------------------------------------------------------

    @staticmethod
    def _pnl_signal(
        ticker: str = "",
        trade_outcome: dict[str, Any] | None = None,
    ) -> float:
        """Extract PnL signal from a trade outcome.

        Positive PnL → positive reward. Missing outcome → 0 (no signal).
        """
        if not trade_outcome:
            return 0.0
        pnl = trade_outcome.get("pnl_pct")
        if pnl is None:
            return 0.0
        return RewardCalculator._pnl_to_reward(float(pnl))

    @staticmethod
    def _pnl_to_reward(pnl_pct: float) -> float:
        """Map PnL percentage to [-1, 1] reward."""
        if pnl_pct > 0:
            return min(1.0, pnl_pct / 50.0)  # +50% → +1.0
        return max(-1.0, pnl_pct / 100.0)  # -100% → -1.0

    @staticmethod
    def _consensus_signal(expert_results: dict[str, Any]) -> float:
        """Reward agent consensus (low contradiction = high reward).

        Returns 1.0 if all agents agree, -1.0 if they violently disagree.
        """
        if not expert_results:
            return 0.0
        stances = []
        for result in expert_results.values():
            po = result.get("parsed_output", {})
            stance = po.get("stance", "")
            if stance:
                stances.append(stance)
        if len(stances) < 2:
            return 0.0
        unique = len(set(stances))
        if unique == 1:
            return 1.0
        if unique == 2:
            return 0.0
        # 3+ different stances → high disagreement
        return -0.5 * (unique - 2) / max(len(stances) - 2, 1)

    @staticmethod
    def _data_signal(data_quality: str) -> float:
        """Reward data completeness."""
        mapping = {
            "ok": 1.0,
            "provider_or_computed": 0.8,
            "partial": 0.3,
            "unknown": 0.0,
            "timeout": -0.5,
            "error": -1.0,
        }
        return mapping.get(data_quality, 0.0)
