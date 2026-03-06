"""
Hawkes Stress Process — detecção de clustering de eventos adversos.

Versão simplificada para dados diários:
- Evento = retorno diário abaixo de threshold (ex: -2%)
- Intensidade λ(t) = μ + Σ α·exp(-β·(t - t_i)) para eventos passados
- Clustering = intensidade atual / intensidade baseline > 2
"""

from __future__ import annotations
import math


from ..contracts.schemas import CrisisInput, SensorResult


def _hawkes_intensity(
    events: list[float], t: float, mu: float, alpha: float, beta: float
) -> float:
    """Intensidade do processo Hawkes no tempo t."""
    lam = mu
    for ti in events:
        if ti < t:
            lam += alpha * math.exp(-beta * (t - ti))
    return lam


class HawkesStressModel:
    THRESHOLD_RETURN = -0.02  # evento = retorno < -2%

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        market = input_data.market_series
        if not market or len(market) < 30:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation="Hawkes requer ≥30 dias de séries de preço.",
            )

        # Calcula retornos diários
        returns = []
        for i in range(1, len(market)):
            prev = market[i - 1].close
            curr = market[i].close
            if prev > 0:
                returns.append((curr - prev) / prev)

        if len(returns) < 20:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation="Retornos insuficientes após cálculo.",
            )

        # Identifica eventos (retornos < threshold)
        events = [i for i, r in enumerate(returns) if r < self.THRESHOLD_RETURN]
        n_events = len(events)
        n_days = len(returns)

        if n_events < 3:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.8,
                status="ok",
                explanation=f"Apenas {n_events} eventos adversos em {n_days} dias — sem clustering.",
            )

        # Parâmetros Hawkes simplificados (calibrados via MLE aproximado)
        mu = max(0.01, n_events / n_days)  # taxa baseline
        alpha = 0.3  # excitação por evento
        beta = 0.5  # decaimento

        # Intensidade no último dia
        t_last = n_days - 1
        lam_current = _hawkes_intensity(events, t_last, mu, alpha, beta)
        lam_baseline = mu

        # Ratio de clustering
        ratio = lam_current / lam_baseline if lam_baseline > 0 else 1.0
        score = max(0.0, min(1.0, (ratio - 1.0) / 3.0))  # ratio=4 → score=1.0

        # Confiança baseada no número de eventos
        confidence = min(0.95, 0.5 + 0.05 * n_events)

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
                f"Hawkes clustering: {n_events} eventos em {n_days} dias. "
                f"Intensidade atual = {lam_current:.3f} (baseline={lam_baseline:.3f}). "
                f"Clustering ratio = {ratio:.2f}."
            ),
            details={
                "n_events": n_events,
                "lam_current": round(lam_current, 4),
                "lam_baseline": round(lam_baseline, 4),
                "ratio": round(ratio, 3),
            },
        )
