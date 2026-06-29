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
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform


def covariance_matrix(returns: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Build covariance matrix from dict of ticker→daily_returns."""
    tickers = list(returns.keys())
    n = len(tickers)
    if n < 2:
        return {t: {t: 1.0} for t in tickers}

    # Align all return series to same length
    min_len = min(len(r) for r in returns.values())
    aligned = np.array([returns[t][-min_len:] for t in tickers])
    cov = np.cov(aligned)
    return {tickers[i]: {tickers[j]: float(cov[i][j]) for j in range(n)} for i in range(n)}


def correlation_matrix(returns: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Build correlation matrix from returns."""
    tickers = list(returns.keys())
    n = len(tickers)
    if n < 2:
        return {t: {t: 1.0} for t in tickers}
    min_len = min(len(r) for r in returns.values())
    aligned = np.array([returns[t][-min_len:] for t in tickers])
    corr = np.corrcoef(aligned)
    return {tickers[i]: {tickers[j]: float(corr[i][j]) for j in range(n)} for i in range(n)}


def _hrp_weights(cov: np.ndarray) -> np.ndarray:
    """Core HRP algorithm: cluster → quasi-diagonalize → recursive bisection."""
    n = cov.shape[0]
    if n == 1:
        return np.array([1.0])
    if n == 0:
        return np.array([])

    corr = np.zeros_like(cov)
    std = np.sqrt(np.diag(cov))
    for i in range(n):
        for j in range(n):
            if std[i] > 0 and std[j] > 0:
                corr[i][j] = cov[i][j] / (std[i] * std[j])

    # Distance matrix (clamp correlation for numerical stability)
    corr_clipped = np.clip(corr, -1.0, 1.0)
    dist = np.sqrt(0.5 * (1.0 - corr_clipped))
    dist[np.isnan(dist)] = 1.0

    # Hierarchical clustering
    try:
        link = linkage(squareform(dist, checks=False), method="ward")
    except Exception:
        return np.ones(n) / n

    # Recursive bisection
    def _bisect(indices: list[int]) -> np.ndarray:
        if len(indices) <= 1:
            return np.ones(len(indices))

        # Split into 2 clusters
        cluster_ids = fcluster(link, t=2, criterion="maxclust")
        c1 = [i for i in indices if cluster_ids[i] == 1]
        c2 = [i for i in indices if cluster_ids[i] == 2]

        if not c1 or not c2:
            return np.ones(len(indices)) / len(indices)

        w1 = _bisect(c1)
        w2 = _bisect(c2)

        # Inverse-variance weighting per cluster
        cov1 = cov[np.ix_(c1, c1)]
        cov2 = cov[np.ix_(c2, c2)]
        var1 = (w1 @ cov1 @ w1) if len(c1) > 0 else 1.0
        var2 = (w2 @ cov2 @ w2) if len(c2) > 0 else 1.0
        alpha1 = 1.0 / max(var1, 1e-9)
        alpha2 = 1.0 / max(var2, 1e-9)
        total_alpha = alpha1 + alpha2

        scale1 = alpha1 / total_alpha if total_alpha > 0 else 0.5
        scale2 = alpha2 / total_alpha if total_alpha > 0 else 0.5

        result = np.zeros(len(indices))
        for i, idx in enumerate(c1):
            result[idx] = w1[i] * scale1
        for i, idx in enumerate(c2):
            result[idx] = w2[i] * scale2

        return result / result.sum()

    weights = _bisect(list(range(n)))
    return weights


def hrp_allocate(
    returns: dict[str, list[float]],
    capital: float = 10000.0,
    max_single_position: float = 0.25,
) -> dict[str, Any]:
    """Allocate capital across tickers using Hierarchical Risk Parity."""
    tickers = list(returns.keys())
    if not tickers:
        return {"weights": {}, "allocations": {}, "total_risk": 0.0}

    if len(tickers) == 1:
        t = tickers[0]
        w = 1.0
        return {
            "weights": {t: w},
            "allocations": {t: round(capital * w, 2)},
            "total_risk": float(np.std(returns[t])) if returns[t] else 0.0,
        }

    cov_dict = covariance_matrix(returns)
    tickers_sorted = sorted(tickers)
    cov_arr = np.array([[cov_dict[ti][tj] for tj in tickers_sorted] for ti in tickers_sorted])

    weights_raw = _hrp_weights(cov_arr)

    # Apply max position cap + renormalize
    weights = np.minimum(weights_raw, max_single_position)
    weights = weights / weights.sum()

    result_weights = {t: round(float(weights[i]), 4) for i, t in enumerate(tickers_sorted)}
    result_alloc = {t: round(float(weights[i] * capital), 2) for i, t in enumerate(tickers_sorted)}

    # Portfolio risk (annualized)
    port_var = weights @ cov_arr @ weights
    port_vol = math.sqrt(max(port_var, 0)) * math.sqrt(252)

    return {
        "weights": result_weights,
        "allocations": result_alloc,
        "total_risk": round(port_vol, 4),
        "method": "HRP",
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
