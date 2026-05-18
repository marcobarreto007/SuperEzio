"""
Growth-at-Risk Sensor — regressão quantílica com numpy puro.

Estima o percentil inferior (q=0.05) do crescimento futuro do PIB
usando features macro: credit_to_gdp, debt_service_ratio, house_price_index.
"""

from __future__ import annotations

import numpy as np

from ..contracts.schemas import CrisisInput, SensorResult


def _quantile_regression(
    X: np.ndarray, y: np.ndarray, q: float = 0.05, max_iter: int = 100
) -> np.ndarray:
    """Regressão quantílica via Iteratively Reweighted Least Squares (numpy puro)."""
    n, p = X.shape
    beta = np.zeros(p)
    for _ in range(max_iter):
        residuals = y - X @ beta
        weights = np.where(residuals > 0, q, 1.0 - q)
        W = np.diag(weights)
        try:
            beta_new = np.linalg.inv(X.T @ W @ X) @ (X.T @ W @ y)
        except np.linalg.LinAlgError:
            break
        if np.allclose(beta_new, beta, atol=1e-6):
            break
        beta = beta_new
    return beta


class GrowthAtRiskModel:
    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        obs = input_data.observations
        if len(obs) < 12:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation=f"Growth-at-Risk requer ≥12 observações mensais; temos {len(obs)}.",
            )

        # Monta matriz de features
        features = []
        targets = []
        for i in range(len(obs) - 1):
            o = obs[i]
            o_next = obs[i + 1]
            gdp_now = o.gdp_growth_yoy
            gdp_next = o_next.gdp_growth_yoy
            if gdp_now is None or gdp_next is None:
                continue
            row = [1.0]  # intercepto
            row.append(o.credit_to_gdp if o.credit_to_gdp is not None else 0.0)
            row.append(o.debt_service_ratio if o.debt_service_ratio is not None else 0.0)
            row.append(o.house_price_index if o.house_price_index is not None else 0.0)
            features.append(row)
            targets.append(gdp_next)

        if len(features) < 8:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation="Dados macro insuficientes após filtragem de missings.",
            )

        X = np.array(features)
        y = np.array(targets)

        # Regressão quantílica no percentil 5% (tail de baixo)
        beta = _quantile_regression(X, y, q=0.05)

        # Predição para a última observação
        last = obs[-1]
        x_last = np.array(
            [
                1.0,
                last.credit_to_gdp if last.credit_to_gdp is not None else 0.0,
                last.debt_service_ratio if last.debt_service_ratio is not None else 0.0,
                last.house_price_index if last.house_price_index is not None else 0.0,
            ]
        )
        pred_gdp_q05 = float(x_last @ beta)

        # Score: quanto mais negativo o predito, maior o risco
        # Normaliza: -5% GDP = score 1.0, 0% = score 0.0, +5% = score 0.0
        score = max(0.0, min(1.0, -pred_gdp_q05 / 0.05))

        # Confiança baseada no R² aproximado (fit da mediana)
        median_pred = X @ _quantile_regression(X, y, q=0.50, max_iter=50)
        ss_res = np.sum((y - median_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        confidence = max(0.3, min(0.95, r2))

        status = "ok"
        if score > 0.75:
            status = "crisis"
        elif score > 0.50:
            status = "stress"
        elif score > 0.25:
            status = "warning"

        return SensorResult(
            sensor_name=self.__class__.__name__,
            score=round(score, 3),
            confidence=round(confidence, 3),
            status=status,
            explanation=(
                f"Growth-at-Risk (5% quantil): GDP previsto = {pred_gdp_q05:.2%}. "
                f"Risco de crescimento negativo em {score:.0%}."
            ),
            details={
                "predicted_gdp_q05": round(pred_gdp_q05, 4),
                "r2_approx": round(r2, 3),
            },
        )
