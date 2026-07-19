"""Portfolio optimization — Hierarchical Risk Parity (HRP) + covariance.

Best practice 2026: HRP from López de Prado. Replaces single-asset thinking
with proper multi-asset allocation using cluster-based risk budgeting.

Also provides structured number injection for Bob's prompt so he "sees"
numbers as data, not prose.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf


def _aligned_return_matrix(
    returns: dict[str, list[float]], tickers: list[str]
) -> np.ndarray:
    if not tickers:
        return np.empty((0, 0), dtype=float)
    min_len = min(len(returns[ticker]) for ticker in tickers)
    if min_len == 0:
        return np.empty((0, len(tickers)), dtype=float)
    matrix = np.column_stack(
        [np.asarray(returns[ticker][-min_len:], dtype=float) for ticker in tickers]
    )
    if not np.isfinite(matrix).all():
        raise ValueError("returns must contain only finite observations")
    return matrix


def _ledoit_wolf_covariance(observations: np.ndarray) -> np.ndarray:
    """Estimate a stable covariance matrix from rows=time and columns=assets."""
    if observations.shape[1] == 0:
        return np.empty((0, 0), dtype=float)
    if observations.shape[0] < 2:
        return np.zeros((observations.shape[1], observations.shape[1]), dtype=float)
    covariance = LedoitWolf(assume_centered=False).fit(observations).covariance_
    return np.asarray(covariance, dtype=float)


def covariance_matrix(returns: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Build a Ledoit-Wolf shrinkage covariance matrix from daily returns."""
    tickers = sorted(returns)
    n = len(tickers)
    if n == 0:
        return {}
    observations = _aligned_return_matrix(returns, tickers)
    cov = _ledoit_wolf_covariance(observations)
    return {tickers[i]: {tickers[j]: float(cov[i][j]) for j in range(n)} for i in range(n)}


def correlation_matrix(returns: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Build a correlation matrix from the shrinkage covariance estimate."""
    tickers = sorted(returns)
    n = len(tickers)
    if n == 0:
        return {}
    observations = _aligned_return_matrix(returns, tickers)
    cov = _ledoit_wolf_covariance(observations)
    corr = _covariance_to_correlation(cov)
    return {tickers[i]: {tickers[j]: float(corr[i][j]) for j in range(n)} for i in range(n)}


def _covariance_to_correlation(cov: np.ndarray) -> np.ndarray:
    std = np.sqrt(np.maximum(np.diag(cov), 0.0))
    denominator = np.outer(std, std)
    corr = np.divide(cov, denominator, out=np.zeros_like(cov), where=denominator > 0)
    corr = np.clip(corr, -1.0, 1.0)
    np.fill_diagonal(corr, 1.0)
    return corr


def _cluster_variance(cov: np.ndarray, indices: list[int]) -> float:
    cluster_cov = cov[np.ix_(indices, indices)]
    diagonal = np.maximum(np.diag(cluster_cov), 1e-18)
    inverse_variance = 1.0 / diagonal
    inverse_variance /= inverse_variance.sum()
    return float(inverse_variance @ cluster_cov @ inverse_variance)


def _hrp_weights(cov: np.ndarray) -> np.ndarray:
    """Core HRP algorithm: cluster → quasi-diagonalize → recursive bisection."""
    n = cov.shape[0]
    if n == 1:
        return np.array([1.0])
    if n == 0:
        return np.array([])

    corr = _covariance_to_correlation(cov)
    distance = np.sqrt(np.maximum(0.0, 0.5 * (1.0 - corr)))
    np.fill_diagonal(distance, 0.0)
    condensed = squareform(distance, checks=False)
    hierarchy = linkage(condensed, method="single", optimal_ordering=True)

    # leaves_list is the quasi-diagonal ordering of the covariance matrix.
    ordered_indices = [int(index) for index in leaves_list(hierarchy)]
    weights = np.ones(n, dtype=float)

    def _bisect(indices: list[int]) -> None:
        if len(indices) <= 1:
            return
        split = len(indices) // 2
        left = indices[:split]
        right = indices[split:]
        left_variance = _cluster_variance(cov, left)
        right_variance = _cluster_variance(cov, right)
        total_variance = left_variance + right_variance
        left_weight = right_variance / total_variance if total_variance > 0 else 0.5
        weights[left] *= left_weight
        weights[right] *= 1.0 - left_weight
        _bisect(left)
        _bisect(right)

    _bisect(ordered_indices)
    total = weights.sum()
    return weights / total if total > 0 else np.ones(n, dtype=float) / n


def hrp_allocate(
    returns: dict[str, list[float]],
    capital: float = 10000.0,
    max_single_position: float = 0.25,
) -> dict[str, Any]:
    """Allocate with HRP; capped asset weight is retained as uninvested CASH."""
    if capital < 0:
        raise ValueError("capital must be non-negative")
    if not 0 < max_single_position <= 1:
        raise ValueError("max_single_position must be in (0, 1]")
    tickers = sorted(returns)
    if not tickers:
        return {
            "weights": {},
            "allocations": {},
            "total_risk": 0.0,
            "method": "HRP",
            "n_assets": 0,
        }

    observations = _aligned_return_matrix(returns, tickers)
    cov_arr = _ledoit_wolf_covariance(observations)

    weights_raw = _hrp_weights(cov_arr)

    # Do not renormalize capped positions: doing so silently violates the cap.
    asset_weights = np.minimum(weights_raw, max_single_position)
    result_weights = {
        ticker: round(float(asset_weights[index]), 10)
        for index, ticker in enumerate(tickers)
    }
    cash_weight = round(max(0.0, 1.0 - sum(result_weights.values())), 10)
    if cash_weight > 0:
        result_weights["CASH"] = cash_weight

    result_alloc = {
        ticker: round(float(result_weights[ticker] * capital), 2) for ticker in tickers
    }
    if cash_weight > 0:
        result_alloc["CASH"] = round(capital - sum(result_alloc.values()), 2)

    # Portfolio risk (annualized)
    port_var = asset_weights @ cov_arr @ asset_weights
    port_vol = math.sqrt(max(port_var, 0)) * math.sqrt(252)

    return {
        "weights": result_weights,
        "allocations": result_alloc,
        "total_risk": round(port_vol, 4),
        "method": "HRP",
        "covariance_estimator": "Ledoit-Wolf shrinkage",
        "cluster_linkage": "single",
        "cash_policy": "unallocated_cap_excess",
        "n_assets": len(tickers),
    }


def structured_numbers_context(numbers: dict[str, Any]) -> str:
    """Inject structured numbers as JSON-LIKE block Bob can parse.

    Instead of 'Sharpe is 0.8' buried in prose, Bob receives:

    ```numbers
    {"sharpe": 0.8, "var_95": -0.02, "kelly": 0.12}
    ```

    This lets Bob reason about numbers as data, not text.
    """
    clean = {}
    for k, v in numbers.items():
        if isinstance(v, float):
            clean[k] = round(v, 6)
        elif isinstance(v, (int, str, bool)):
            clean[k] = v
        elif v is None:
            clean[k] = None

    import json

    json_block = json.dumps(clean, ensure_ascii=False)
    return f"\n```numbers\n{json_block}\n```\n"


def portfolio_snapshot_for_bob(
    ticker_returns: dict[str, list[float]],
    capital: float,
    numbers: dict[str, Any],
) -> str:
    """Full portfolio context for Bob's prompt — HRP weights + structured numbers."""
    alloc = hrp_allocate(ticker_returns, capital)
    num_ctx = structured_numbers_context(numbers)

    lines = [
        num_ctx,
        "=== PORTFOLIO ALLOCATION (HRP) ===",
        f"Method: Hierarchical Risk Parity | Assets: {alloc['n_assets']}",
        f"Portfolio Risk (ann.): {alloc['total_risk']:.1%}",
    ]
    for t, w in sorted(alloc["weights"].items(), key=lambda x: -x[1]):
        amount = alloc["allocations"][t]
        lines.append(f"  {t}: {w:.1%} (${amount:,.0f})")

    return "\n".join(lines)
