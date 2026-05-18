"""
Network Contagion Sensor — DebtRank / CoVaR simplificado.

Referências:
- Billio et al. (2012) — network measures of connectedness
- Adrian & Brunnermeier (2016) — CoVaR
- Battiston et al. (2012) — DebtRank

Versão simplificada (sem matriz de exposição interbancária completa):
- CoVaR proxy: VaR condicional baseado em correlação mercado × ativo
- DebtRank-lite: propagação de choques em rede via PageRank-like em matriz
de correlação de retornos (proxy de exposição)
"""

from __future__ import annotations

import numpy as np

from ..contracts.schemas import CrisisInput, SensorResult


def _covar_simple(asset_var: float, correlation: float, market_vol: float) -> float:
    """CoVaR simplificado: VaR do sistema condicional ao ativo em distress.

    Aproximação: CoVaR_system|asset ≈ Φ⁻¹(q) × σ_system × ρ
    onde usamos asset_var como proxy de distress do ativo.
    """
    if market_vol <= 0:
        return 0.0
    # asset_var é negativo (VaR); quanto mais negativo, maior o stress
    # CoVaR do sistema = ρ × asset_var  (aproximação linear)
    return correlation * asset_var


def _pagerank_like(matrix: np.ndarray, damping: float = 0.85, max_iter: int = 50) -> np.ndarray:
    """PageRank em matriz de adjacência (colunas normalizadas)."""
    n = matrix.shape[0]
    if n == 0:
        return np.array([])
    # Normaliza colunas
    col_sums = matrix.sum(axis=0)
    col_sums[col_sums == 0] = 1.0
    M = matrix / col_sums

    pr = np.ones(n) / n
    for _ in range(max_iter):
        pr_new = (1.0 - damping) / n + damping * (M @ pr)
        if np.allclose(pr_new, pr, atol=1e-8):
            break
        pr = pr_new
    return pr


class NetworkContagionModel:
    MIN_DAYS = 30

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        market = input_data.market_series

        if not market or len(market) < self.MIN_DAYS:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation=f"Contágio requer ≥{self.MIN_DAYS} dias de série de preços.",
            )

        # ── 1. Retornos diários ─────────────────────────────────────────────────
        returns = []
        for i in range(1, len(market)):
            prev = market[i - 1].close
            curr = market[i].close
            if prev > 0:
                returns.append((curr - prev) / prev)

        if len(returns) < self.MIN_DAYS:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation="Retornos insuficientes após cálculo.",
            )

        ret_arr = np.array(returns)
        n = len(ret_arr)

        # ── 2. CoVaR proxy ──────────────────────────────────────────────────────
        # VaR do ativo (5%)
        asset_var = float(np.percentile(ret_arr, 5.0))
        # Volatilidade do mercado (proxy: desvio padrão dos retornos)
        market_vol = float(np.std(ret_arr, ddof=1))

        # Correlação do ativo com "sistema": auto-correlação de curto prazo como
        # proxy de momentum (se o ativo caiu ontem, tende a cair hoje = distress)
        if n > 5:
            lag1 = ret_arr[:-1]
            lag0 = ret_arr[1:]
            if np.std(lag1) > 0 and np.std(lag0) > 0:
                correlation = float(np.corrcoef(lag0, lag1)[0][1])
            else:
                correlation = 0.0
        else:
            correlation = 0.0

        covar = _covar_simple(asset_var, correlation, market_vol)

        # ── 3. DebtRank-lite via matriz de correlação de janelas ────────────────
        # Cria múltiplas "instituições" sintéticas = janelas de retornos diferentes
        # (momentum short, medium, long) e calcula propagação de choques
        window = min(20, n // 3)
        if window < 5:
            debt_rank = 0.0
            network_density = 0.0
        else:
            # 3 séries sintéticas: EWMA curto, médio, longo
            series = []
            for alpha in [0.3, 0.2, 0.1]:
                ewma = ret_arr[0]
                ewma_series = [ewma]
                for r in ret_arr[1:]:
                    ewma = alpha * r + (1 - alpha) * ewma
                    ewma_series.append(ewma)
                series.append(np.array(ewma_series))

            # Adiciona a série original
            series.append(ret_arr)
            k = len(series)

            # Matriz de correlação como proxy de rede de exposição
            corr_matrix = np.eye(k)
            for i in range(k):
                for j in range(i + 1, k):
                    si = series[i]
                    sj = series[j]
                    min_len = min(len(si), len(sj))
                    if min_len > 1 and np.std(si[-min_len:]) > 0 and np.std(sj[-min_len:]) > 0:
                        c = float(np.corrcoef(si[-min_len:], sj[-min_len:])[0][1])
                    else:
                        c = 0.0
                    corr_matrix[i][j] = max(0.0, c)  # apenas exposures positivos
                    corr_matrix[j][i] = corr_matrix[i][j]

            # DebtRank-lite: choque inicial no nó mais volátil, propagação
            vols = [float(np.std(s, ddof=1)) for s in series]
            shock_node = int(np.argmax(vols))
            shock = 0.10  # 10% de perda inicial

            # Propagação: h = shock × (I - C)^(-1)  aproximado por iteração
            h = np.zeros(k)
            h[shock_node] = shock
            for _ in range(10):
                h_new = shock * (corr_matrix @ h)
                h_new[shock_node] = max(h_new[shock_node], shock)
                if np.allclose(h_new, h, atol=1e-6):
                    break
                h = h_new

            debt_rank = float(np.sum(h))
            network_density = float(np.sum(corr_matrix) - k) / (k * (k - 1)) if k > 1 else 0.0

        # ── 4. Score combinado ──────────────────────────────────────────────────
        # CoVaR negativo grande = sistema em risco quando ativo cai
        covar_score = max(0.0, min(1.0, -covar / 0.10))  # covar = -10% → score 1.0
        debt_rank_score = max(0.0, min(1.0, debt_rank / 0.30))  # debt_rank = 30% → score 1.0
        density_score = max(0.0, min(1.0, network_density))

        score = 0.40 * covar_score + 0.40 * debt_rank_score + 0.20 * density_score
        score = max(0.0, min(1.0, score))

        # Confiança
        confidence = max(0.3, min(0.95, 0.4 + 0.01 * n / 20))

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
                f"Contágion: CoVaR={covar:.2%}, DebtRank-lite={debt_rank:.2%}, "
                f"network_density={network_density:.2f}. Score={score:.2f}."
            ),
            details={
                "n_days": n,
                "asset_var": round(asset_var, 4),
                "market_vol": round(market_vol, 4),
                "correlation": round(correlation, 3),
                "covar": round(covar, 4),
                "debt_rank_lite": round(debt_rank, 4),
                "network_density": round(network_density, 3),
                "score_components": {
                    "covar": round(covar_score, 3),
                    "debt_rank": round(debt_rank_score, 3),
                    "density": round(density_score, 3),
                },
            },
        )
