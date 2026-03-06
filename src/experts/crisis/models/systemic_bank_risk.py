"""
Systemic Bank Risk Sensor — SRISK / LRMES simplificado.

Referências:
- Acharya et al. (2012) SRISK
- Brownlees & Engle (2017) LRMES

Versão simplificada (macro + mercado):
- LRMES_i ≈ β_i × Expected Shortfall do mercado  (aproximação linear)
- SRISK_i = max(0, k × L_i − (1 − LRMES_i) × W_i)
- Sem dados bancários individuais, usamos proxy setorial via credit_spread,
  equity_index e realized_volatility do mercado.
"""

from __future__ import annotations
import math

import numpy as np

from ..contracts.schemas import CrisisInput, SensorResult


def _lrmes_simple(beta: float, market_es: float) -> float:
    """Long Run Marginal Expected Shortfall aproximado."""
    # LRMES ≈ 1 - exp(-β × |market_es|)  (aproximação exponencial)
    if market_es >= 0:
        return 0.0
    return 1.0 - math.exp(beta * market_es)


def _srisk_simple(
    lrmes: float, market_cap: float, liabilities: float, k: float = 0.08
) -> float:
    """SRISK = max(0, k×L − (1−LRMES)×W)."""
    equity = max(market_cap, 0.0)
    debt = max(liabilities, 0.0)
    return max(0.0, k * debt - (1.0 - lrmes) * equity)


class SystemicBankRiskModel:
    MIN_OBS = 24
    K_REGULATORY = 0.08  # razão de capital mínimo (Basel III ~8%)

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        obs = input_data.observations
        market = input_data.market_series or []

        if len(obs) < self.MIN_OBS and len(market) < self.MIN_OBS:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation=f"SRISK requer ≥{self.MIN_OBS} observações mensais ou diárias.",
            )

        # ── 1. Calcula retornos do mercado (proxy equity_index ou close) ───────
        returns = []
        if market and len(market) >= self.MIN_OBS:
            for i in range(1, len(market)):
                prev = market[i - 1].close
                curr = market[i].close
                if prev > 0:
                    returns.append((curr - prev) / prev)
        elif len(obs) >= self.MIN_OBS:
            # Usa equity_index como proxy de mercado
            eq_vals = [o.equity_index for o in obs if o.equity_index is not None]
            if len(eq_vals) >= self.MIN_OBS:
                for i in range(1, len(eq_vals)):
                    prev = eq_vals[i - 1]
                    curr = eq_vals[i]
                    if prev > 0:
                        returns.append((curr - prev) / prev)

        if len(returns) < self.MIN_OBS:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.0,
                status="insufficient_data",
                explanation="Retornos de mercado insuficientes para calcular ES e β.",
            )

        returns_arr = np.array(returns)

        # ── 2. Expected Shortfall do mercado (CVaR 5%) ──────────────────────────
        var_95 = np.percentile(returns_arr, 5.0)
        tail = returns_arr[returns_arr <= var_95]
        market_es = float(np.mean(tail)) if len(tail) > 0 else var_95

        # ── 3. Beta do sistema bancário vs mercado ──────────────────────────────
        # Sem série bancária individual, usamos um proxy:
        # beta ≈ correlação(mercado, credit_spread) com sinal invertido
        # (spread sobe quando mercado cai)
        cs_vals = [o.credit_spread for o in obs if o.credit_spread is not None]
        beta_proxy = 1.0  # default
        if len(cs_vals) >= 12 and len(returns) >= len(cs_vals):
            # Alinha tamanhos
            n_common = min(len(cs_vals), len(returns))
            cs_arr = np.array(cs_vals[-n_common:])
            ret_arr = returns_arr[-n_common:]
            # Δcredit_spread como proxy de retorno bancário (negativo)
            cs_diff = np.diff(cs_arr)
            ret_diff = ret_arr[-len(cs_diff) :]
            if len(cs_diff) > 1 and np.std(cs_diff) > 0 and np.std(ret_diff) > 0:
                cov = np.cov(cs_diff, ret_diff)[0][1]
                var_m = np.var(ret_diff, ddof=1)
                if var_m != 0:
                    # Beta bancário = -cov(Δspread, mercado) / var(mercado)
                    beta_proxy = max(0.5, min(3.0, abs(-cov / var_m)))

        # ── 4. LRMES ────────────────────────────────────────────────────────────
        lrmes = _lrmes_simple(beta_proxy, market_es)

        # ── 5. SRISK simplificado (proxy setorial) ──────────────────────────────
        # Usa equity_index como proxy de market cap agregado do setor
        last_eq = None
        for o in reversed(obs):
            if o.equity_index is not None:
                last_eq = o.equity_index
                break
        if last_eq is None and market:
            last_eq = market[-1].close

        # Liabilities proxy: credit_to_gdp × normalizador
        # credit_to_gdp é % do PIB; assumimos PIB proxy = equity_index / 0.5
        last_credit_gdp = None
        for o in reversed(obs):
            if o.credit_to_gdp is not None:
                last_credit_gdp = o.credit_to_gdp
                break

        if last_eq is None or last_credit_gdp is None:
            return SensorResult(
                sensor_name=self.__class__.__name__,
                score=0.0,
                confidence=0.3,
                status="insufficient_data",
                explanation="Dados macro (equity_index, credit_to_gdp) ausentes para proxy SRISK.",
            )

        # Proxy: market_cap_setor ≈ equity_index (normalizado arbitrário)
        # liabilities ≈ credit_to_gdp × equity_index / 0.5
        market_cap_proxy = abs(last_eq) * 1_000_000  # escala arbitrária
        liabilities_proxy = max(market_cap_proxy * last_credit_gdp / 100.0, 0.0)

        srisk = _srisk_simple(
            lrmes, market_cap_proxy, liabilities_proxy, k=self.K_REGULATORY
        )

        # ── 6. Score ────────────────────────────────────────────────────────────
        # Normaliza SRISK como fração do equity (mais interpretável)
        srisk_capital_ratio = srisk / max(market_cap_proxy, 1.0)
        score = max(0.0, min(1.0, srisk_capital_ratio * 5.0))  # ratio=0.2 → score=1.0

        # Confiança baseada em quantidade de dados
        confidence = max(0.3, min(0.95, 0.4 + 0.01 * len(returns) / 10))

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
                f"SRISK proxy: β={beta_proxy:.2f}, LRMES={lrmes:.2%}, "
                f"market_ES={market_es:.2%}, SRISK/equity={srisk_capital_ratio:.2%}. "
                f"Score={score:.2f}."
            ),
            details={
                "beta_proxy": round(beta_proxy, 2),
                "lrmes": round(lrmes, 4),
                "market_es": round(market_es, 4),
                "srisk_proxy": round(srisk, 2),
                "srisk_capital_ratio": round(srisk_capital_ratio, 4),
                "n_returns": len(returns),
            },
        )
