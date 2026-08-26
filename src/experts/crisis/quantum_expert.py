"""Dependence-aware return resampling kept at this legacy import path.

The former implementation generated a quantum-walk distribution unrelated to
market observations. This module now exposes an honestly named stationary
bootstrap that resamples only the observed return series supplied by a caller.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

import numpy as np


class StationaryBlockBootstrap:
    """Politis-Romano stationary bootstrap for weakly dependent returns."""

    def __init__(
        self,
        *,
        n_scenarios: int = 2_000,
        mean_block_length: int | None = None,
        horizon: int | None = None,
        random_seed: int | None = None,
    ) -> None:
        if n_scenarios <= 0:
            raise ValueError("n_scenarios must be positive")
        if mean_block_length is not None and mean_block_length <= 0:
            raise ValueError("mean_block_length must be positive")
        if horizon is not None and horizon <= 0:
            raise ValueError("horizon must be positive")
        self.n_scenarios = n_scenarios
        self.mean_block_length = mean_block_length
        self.horizon = horizon
        self.random_seed = random_seed

    def run_simulation(self, returns: Sequence[float]) -> dict[str, Any]:
        observations = np.asarray(returns, dtype=float)
        if observations.ndim != 1 or observations.size < 2:
            raise ValueError("at least two observed returns are required")
        if not np.isfinite(observations).all():
            raise ValueError("returns must contain only finite observations")
        if np.any(observations < -1.0):
            raise ValueError("simple returns cannot be below -100%")

        sample_size = int(observations.size)
        block_length = self.mean_block_length or max(2, round(sample_size ** (1.0 / 3.0)))
        horizon = self.horizon or min(20, sample_size)
        restart_probability = min(1.0, 1.0 / block_length)
        seed = self.random_seed if self.random_seed is not None else self._data_seed(observations)
        rng = np.random.default_rng(seed)

        indices = rng.integers(0, sample_size, size=self.n_scenarios)
        sampled = np.empty((self.n_scenarios, horizon), dtype=float)
        sampled[:, 0] = observations[indices]
        for step in range(1, horizon):
            restart = rng.random(self.n_scenarios) < restart_probability
            new_starts = rng.integers(0, sample_size, size=self.n_scenarios)
            indices = np.where(restart, new_starts, (indices + 1) % sample_size)
            sampled[:, step] = observations[indices]

        cumulative_returns = np.prod(1.0 + sampled, axis=1) - 1.0
        return {
            "status": "complete",
            "method": "stationary_block_bootstrap",
            "estimator": "Politis-Romano stationary bootstrap",
            "input_source": "observed_simple_returns",
            "n_observations": sample_size,
            "n_scenarios": self.n_scenarios,
            "horizon_observations": horizon,
            "mean_block_length": block_length,
            "block_length_distribution": "geometric",
            "restart_probability": restart_probability,
            "seed_policy": (
                "caller_supplied" if self.random_seed is not None else "sha256_observed_returns"
            ),
            "expected_cumulative_return": float(np.mean(cumulative_returns)),
            "median_cumulative_return": float(np.median(cumulative_returns)),
            "return_quantile_05": float(np.quantile(cumulative_returns, 0.05)),
            "return_quantile_01": float(np.quantile(cumulative_returns, 0.01)),
            "worst_sampled_return": float(np.min(cumulative_returns)),
            "best_sampled_return": float(np.max(cumulative_returns)),
        }

    @staticmethod
    def _data_seed(observations: np.ndarray) -> int:
        digest = hashlib.sha256(observations.astype("<f8", copy=False).tobytes()).digest()
        return int.from_bytes(digest[:8], "big", signed=False)
