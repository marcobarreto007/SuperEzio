from __future__ import annotations

import math

import numpy as np
import pytest

from core.math.portfolio import covariance_matrix, hrp_allocate


def _returns() -> dict[str, list[float]]:
    rng = np.random.default_rng(20260719)
    market = rng.normal(0.0004, 0.008, 180)
    return {
        "LOW": list(0.35 * market + rng.normal(0.0, 0.002, 180)),
        "MID": list(0.75 * market + rng.normal(0.0, 0.006, 180)),
        "HIGH": list(1.20 * market + rng.normal(0.0, 0.018, 180)),
    }


def test_hrp_weights_form_simplex_and_cap_excess_stays_cash():
    result = hrp_allocate(_returns(), capital=12_345.67, max_single_position=0.25)

    assert sum(result["weights"].values()) == pytest.approx(1.0, abs=1e-9)
    assert sum(result["allocations"].values()) == pytest.approx(12_345.67, abs=0.01)
    assert all(result["weights"][ticker] <= 0.25 for ticker in _returns())
    assert result["weights"]["CASH"] >= 0.25
    assert result["covariance_estimator"] == "Ledoit-Wolf shrinkage"
    assert result["cluster_linkage"] == "single"


def test_hrp_is_invariant_to_input_mapping_permutation():
    original = _returns()
    permuted = {ticker: original[ticker] for ticker in reversed(list(original))}

    first = hrp_allocate(original, max_single_position=0.8)
    second = hrp_allocate(permuted, max_single_position=0.8)

    assert first["weights"] == second["weights"]
    assert first["allocations"] == second["allocations"]
    assert first["total_risk"] == second["total_risk"]


def test_hrp_assigns_more_risk_budget_to_lower_variance_asset():
    result = hrp_allocate(_returns(), max_single_position=1.0)

    assert result["weights"]["LOW"] > result["weights"]["HIGH"]
    assert "CASH" not in result["weights"]


def test_single_asset_cap_is_not_renormalized_away():
    result = hrp_allocate({"ONLY": [0.01, -0.01, 0.005]}, max_single_position=0.2)

    assert result["weights"] == {"ONLY": 0.2, "CASH": 0.8}


def test_ledoit_wolf_covariance_is_finite_symmetric_and_order_stable():
    returns = _returns()
    covariance = covariance_matrix(returns)
    tickers = sorted(returns)
    matrix = np.array([[covariance[left][right] for right in tickers] for left in tickers])

    assert np.isfinite(matrix).all()
    assert np.allclose(matrix, matrix.T)
    assert all(math.isfinite(covariance[ticker][ticker]) for ticker in tickers)
    assert np.linalg.eigvalsh(matrix).min() >= -1e-12


@pytest.mark.parametrize("cap", [0.0, -0.1, 1.1])
def test_invalid_position_cap_is_rejected(cap: float):
    with pytest.raises(ValueError, match="max_single_position"):
        hrp_allocate(_returns(), max_single_position=cap)
