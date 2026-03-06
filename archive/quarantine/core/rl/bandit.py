"""
Contextual Bandit for agent selection in SuperEzio.

LinUCB with disjoint linear models — the industry-standard algorithm
for contextual decision-making under uncertainty. Proven in production
recommendation systems (Yahoo, Microsoft, Netflix) and directly
applicable to selecting which financial agents to invoke for a given
asset profile.

State:  AssetProfile + market features (dimensionality ~20)
Action: subset of 5 penny stock agents (encoded as 5-dim binary vector)
Reward: trade outcome PnL (from lab_journal) or user feedback signal

Reference: Li et al. "A Contextual-Bandit Approach to Personalized
News Article Recommendation" (WWW 2010).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from core.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = PROJECT_ROOT / "data" / "rl" / "agent_bandit.json"
NUM_AGENTS = 5
AGENT_ORDER = [
    "fraud_hunter",
    "flow_analyst",
    "ruin_calculator",
    "sentiment_detective",
    "market_context",
]

# Hyperparameters
DEFAULT_ALPHA = 1.0  # exploration bonus (higher = more exploration)
DEFAULT_LAMBDA = 0.1  # L2 regularization
FEATURE_DIM = 24  # AssetProfile + market features


def _build_feature_vector(
    asset_profile: dict[str, Any] | None = None,
    market_features: dict[str, Any] | None = None,
) -> np.ndarray:
    """Build a fixed-length feature vector from asset profile and market data.

    Returns a (FEATURE_DIM,) numpy float64 array. Missing fields → 0.0.
    """
    vec = np.zeros(FEATURE_DIM, dtype=np.float64)

    profile = asset_profile or {}
    features = market_features or {}

    # ── Asset profile signals (first 12 dims) ──
    vec[0] = 1.0 if profile.get("asset_type") == "crypto" else 0.0
    vec[1] = 1.0 if profile.get("has_reddit_mentions") else 0.0
    vec[2] = 1.0 if profile.get("has_high_volume") else 0.0
    vec[3] = 1.0 if profile.get("is_crypto") else 0.0
    vec[4] = 1.0 if profile.get("is_macro_sensitive") else 0.0
    vec[5] = 1.0 if profile.get("has_quant_data") else 0.0
    vec[6] = {"low": 0.0, "moderate": 0.33, "high": 0.66, "extreme": 1.0}.get(
        profile.get("volatility_level", "unknown"), 0.0
    )
    vec[7] = 1.0 if profile.get("market") == "CA" else 0.0
    vec[8] = 1.0 if profile.get("market") == "US" else 0.0
    vec[9] = 1.0 if profile.get("market") == "BR" else 0.0
    vec[10] = 1.0 if profile.get("has_options") else 0.0
    vec[11] = 1.0 if profile.get("has_earnings_soon") else 0.0

    # ── Market / F51 features (next 12 dims) ──
    vec[12] = float(features.get("price", 0) or 0)
    vec[13] = float(features.get("daily_return", 0) or 0)
    vec[14] = float(features.get("volume_z_score", 0) or 0)
    vec[15] = float(features.get("market_cap", 0) or 0)
    vec[16] = float(features.get("rsi_14", 50) or 50) / 100.0
    vec[17] = float(features.get("annual_volatility", 0.2) or 0.2)
    vec[18] = float(features.get("sharpe_ratio", 0) or 0)
    vec[19] = float(features.get("hype_keyword_count", 0) or 0)
    vec[20] = float(features.get("sentiment_score", 0) or 0)
    vec[21] = float(features.get("missing_data_ratio", 0) or 0)
    vec[22] = float(features.get("monte_carlo_prob_up", 50) or 50) / 100.0
    vec[23] = float(features.get("ml_prob_up", 50) or 50) / 100.0

    # Clip outliers
    vec = np.clip(vec, -10.0, 10.0)

    return vec


class AgentBandit:
    """LinUCB contextual bandit for penny stock agent selection.

    Maintains one linear model per agent. For each agent i:
        expected_reward = theta_i · x
        upper_bound = theta_i · x + alpha * sqrt(x^T A_i^{-1} x)

    Selects the top-k agents by upper confidence bound.

    Persistence: models saved to JSON on update; loaded on init.
    """

    def __init__(
        self,
        alpha: float = DEFAULT_ALPHA,
        reg_lambda: float = DEFAULT_LAMBDA,
        model_path: Path | None = None,
        num_agents: int = NUM_AGENTS,
        feature_dim: int = FEATURE_DIM,
    ) -> None:
        self.alpha = alpha
        self.reg_lambda = reg_lambda
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.num_agents = num_agents
        self.feature_dim = feature_dim

        # LinUCB parameters per agent
        # A_a: (d x d) covariance matrix
        # b_a: (d,) reward-weighted feature sum
        # theta_a: (d,) learned coefficients
        self.A = [reg_lambda * np.eye(feature_dim) for _ in range(num_agents)]
        self.b = [np.zeros(feature_dim) for _ in range(num_agents)]
        self.theta = [np.zeros(feature_dim) for _ in range(num_agents)]

        self.total_updates = 0
        self._load()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def predict(
        self,
        asset_profile: dict[str, Any] | None = None,
        market_features: dict[str, Any] | None = None,
        top_k: int = 3,
    ) -> list[tuple[str, float, float]]:
        """Return top-k agents by upper confidence bound.

        Returns list of (agent_name, expected_reward, upper_bound).
        """
        x = _build_feature_vector(asset_profile, market_features)
        scored = []

        for i in range(self.num_agents):
            A_inv = np.linalg.inv(self.A[i])
            theta = self.theta[i]
            expected = float(np.dot(theta, x))
            # Upper confidence bound
            margin = self.alpha * float(np.sqrt(np.dot(np.dot(x, A_inv), x)))
            ucb = expected + margin
            scored.append((AGENT_ORDER[i], expected, ucb))

        scored.sort(key=lambda item: -item[2])  # sort by UCB descending
        return scored[:top_k]

    def agent_mask(
        self,
        asset_profile: dict[str, Any] | None = None,
        market_features: dict[str, Any] | None = None,
        top_k: int = 3,
    ) -> list[str]:
        """Return list of agent names to invoke."""
        return [
            name
            for name, _expected, _ucb in self.predict(
                asset_profile, market_features, top_k=top_k
            )
        ]

    def update(
        self,
        asset_profile: dict[str, Any] | None,
        market_features: dict[str, Any] | None,
        agent_mask: list[str],
        reward: float,
    ) -> None:
        """Update the bandit with a single (context, action, reward) triplet.

        agent_mask: list of agent names that were invoked.
        reward: scalar in [-1, 1] where positive = good outcome.
        """
        x = _build_feature_vector(asset_profile, market_features)
        for agent_name in agent_mask:
            if agent_name not in AGENT_ORDER:
                continue
            i = AGENT_ORDER.index(agent_name)
            self.A[i] += np.outer(x, x)
            self.b[i] += reward * x
            self.theta[i] = np.linalg.solve(self.A[i], self.b[i])

        self.total_updates += 1
        # Auto-save every 25 updates
        if self.total_updates % 25 == 0:
            self._save()

    def batch_update(
        self,
        episodes: list[dict[str, Any]],
    ) -> int:
        """Update from a batch of episodes.

        Each episode dict must have:
            asset_profile, market_features, agent_mask, reward

        Returns number of episodes processed.
        """
        count = 0
        for ep in episodes:
            try:
                self.update(
                    asset_profile=ep.get("asset_profile"),
                    market_features=ep.get("market_features"),
                    agent_mask=ep.get("agent_mask", []),
                    reward=float(ep.get("reward", 0)),
                )
                count += 1
            except Exception:
                pass
        if count:
            self._save()
        return count

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "alpha": self.alpha,
            "reg_lambda": self.reg_lambda,
            "num_agents": self.num_agents,
            "feature_dim": self.feature_dim,
            "total_updates": self.total_updates,
            "A": [mat.tolist() for mat in self.A],
            "b": [vec.tolist() for vec in self.b],
            "theta": [vec.tolist() for vec in self.theta],
        }
        self.model_path.write_text(json.dumps(payload), encoding="utf-8")

    def _load(self) -> None:
        if not self.model_path.exists():
            return
        try:
            data = json.loads(self.model_path.read_text(encoding="utf-8"))
            if data.get("feature_dim") != self.feature_dim:
                logger.warning(
                    "Bandit model feature_dim mismatch (%s != %s), starting fresh",
                    data.get("feature_dim"),
                    self.feature_dim,
                )
                return
            self.total_updates = int(data.get("total_updates", 0))
            for i, (a_rows, b_vec, t_vec) in enumerate(
                zip(data["A"], data["b"], data["theta"])
            ):
                if i >= self.num_agents:
                    break
                self.A[i] = np.array(a_rows)
                self.b[i] = np.array(b_vec)
                self.theta[i] = np.array(t_vec)
        except Exception:
            logger.warning("Failed to load bandit model, starting fresh")

    def stats(self) -> dict[str, Any]:
        """Return diagnostic statistics."""
        return {
            "total_updates": self.total_updates,
            "alpha": self.alpha,
            "reg_lambda": self.reg_lambda,
            "theta_norms": [float(np.linalg.norm(t)) for t in self.theta],
            "agent_order": AGENT_ORDER,
        }

    def reset(self) -> None:
        """Reset all learned parameters."""
        self.A = [
            self.reg_lambda * np.eye(self.feature_dim) for _ in range(self.num_agents)
        ]
        self.b = [np.zeros(self.feature_dim) for _ in range(self.num_agents)]
        self.theta = [np.zeros(self.feature_dim) for _ in range(self.num_agents)]
        self.total_updates = 0
        if self.model_path.exists():
            self.model_path.unlink()
