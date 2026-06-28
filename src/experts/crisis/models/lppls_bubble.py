"""
LPPLS Bubble Sensor — detecção de bolhas via Log-Periodic Power Law (versão lite).

Referência: Sornette et al. — LPPLS model:
    ln(p(t)) = A + B*(tc - t)^m + C*(tc - t)^m * cos(ω*ln(tc - t) + φ)

Versão simplificada para dados diários:
- Detecta aceleração super-exponencial nos log-preços
- Conta oscilações log-periódicas via zero-crossings da segunda derivada
- Score combinado: aceleração + frequência de oscilações + volatilidade crescente
"""

from __future__ import annotations
import math

import numpy as np

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


def _second_derivative(y: np.ndarray) -> np.ndarray:
    """Segunda derivada discreta (centrais, edges com forward/backward)."""
    n = len(y)
    d2 = np.zeros(n)
    if n < 3:
        return d2
    d2[0] = y[2] - 2 * y[1] + y[0]
    d2[-1] = y[-1] - 2 * y[-2] + y[-3]
    for i in range(1, n - 1):
        d2[i] = y[i + 1] - 2 * y[i] + y[i - 1]
    return d2


def _zero_crossings(y: np.ndarray) -> int:
    """Conta quantas vezes a série cruza zero (muda de sinal)."""
    return int(np.sum((y[:-1] * y[1:]) < 0))


def _lppls_fit_quality(
    log_prices: np.ndarray, t: np.ndarray, tc: float, m: float, omega: float
) -> float:
    """Calcula R² de um fit LPPLS simplificado (sem otimização não-linear pesada).

    Fit: ln(p) ≈ A + B*(tc - t)^m + C*(tc - t)^m * cos(ω*ln(tc - t))
    Resolve A, B, C via mínimos quadrados lineares para (tc, m, ω) fixos.
    """
    dt = tc - t
    valid = dt > 0
    if not np.any(valid):
        return 0.0

    dt = dt[valid]
    lp = log_prices[valid]

    pow_term = dt**m
    # cos term — adiciona pequeno epsilon para evitar log(0)
    log_dt = np.log(np.maximum(dt, 1e-9))
    cos_term = pow_term * np.cos(omega * log_dt)

    # Design matrix para [A, B, C]
    X = np.column_stack([np.ones_like(pow_term), pow_term, cos_term])

    # Mínimos quadrados: beta = (X'X)^(-1) X'y
    try:
        beta = np.linalg.lstsq(X, lp, rcond=None)[0]
        fitted = X @ beta
        ss_res = np.sum((lp - fitted) ** 2)
        ss_tot = np.sum((lp - np.mean(lp)) ** 2)
        if ss_tot == 0:
            # Série constante (variância zero) — não é bolha, é dado degenerado.
            # Retornar 1.0 aqui pintaria falso positivo de "fit perfeito".
            return 0.0
        r2 = 1.0 - ss_res / ss_tot
        # Penaliza B > 0 (bolha requer B < 0, i.e., preço acelerando para cima)
        if beta[1] > 0:
            r2 *= 0.3
        return max(0.0, r2)
    except Exception:
        return 0.0


class LPPLSBubbleModel:
    MIN_DAYS = 60
    THRESHOLD_SCORE = 0.50

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        market = input_data.market_series
        if not market or len(market) < self.MIN_DAYS:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                f"LPPLS requer ≥{self.MIN_DAYS} dias de série de preços.",
            )

        closes = np.array([m.close for m in market if m.close > 0])
        n = len(closes)
        if n < self.MIN_DAYS:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                f"Preços válidos insuficientes ({n} < {self.MIN_DAYS}).",
            )

        log_prices = np.log(closes)
        t = np.arange(n, dtype=float)

        # ── 1. Aceleração super-exponencial ─────────────────────────────────────
        # Fit quadrático: ln(p) = a + b*t + c*t^2
        # Se c > 0 e significativo → aceleração super-exponencial
        X_quad = np.column_stack([np.ones(n), t, t**2])
        try:
            beta_quad = np.linalg.lstsq(X_quad, log_prices, rcond=None)[0]
            accel = float(beta_quad[2])  # coeficiente quadrático
        except Exception:
            accel = 0.0

        # Resíduos do fit linear (para detectar oscilações)
        X_lin = np.column_stack([np.ones(n), t])
        try:
            beta_lin = np.linalg.lstsq(X_lin, log_prices, rcond=None)[0]
            fitted_lin = X_lin @ beta_lin
            residuals = log_prices - fitted_lin
        except Exception:
            residuals = np.zeros(n)

        # ── 2. Oscilações log-periódicas ────────────────────────────────────────
        d2_res = _second_derivative(residuals)
        oscillations = _zero_crossings(d2_res)
        # Frequência: oscilações por unidade de log-tempo
        log_span = math.log(max(n, 2))
        freq = oscillations / log_span if log_span > 0 else 0.0

        # ── 3. Fit LPPLS simplificado em grid ───────────────────────────────────
        # Grid search leve em (tc, m, omega)
        best_r2 = 0.0
        best_params = {}
        # tc varia entre t[-1] + 1 (imediato) e t[-1] + 60 (2-3 meses)
        tc_base = float(n)
        for tc_offset in [1, 7, 14, 21, 30, 45, 60]:
            tc = tc_base + tc_offset
            for m in [0.2, 0.33, 0.5, 0.66, 0.8]:
                for omega in [4.0, 6.0, 8.0, 10.0, 12.0]:
                    r2 = _lppls_fit_quality(log_prices, t, tc, m, omega)
                    if r2 > best_r2:
                        best_r2 = r2
                        best_params = {
                            "tc_offset": tc_offset,
                            "m": m,
                            "omega": omega,
                            "r2": r2,
                        }

        # ── 4. Volatilidade crescente (sinal de bolha) ──────────────────────────
        if n >= 30:
            vol_window = 20
            vols = []
            for i in range(vol_window, n):
                window_rets = np.diff(log_prices[i - vol_window : i])
                vols.append(float(np.std(window_rets)))
            vols = np.array(vols)
            vol_trend = (
                float(np.polyfit(np.arange(len(vols)), vols, 1)[0]) if len(vols) >= 10 else 0.0
            )
        else:
            vol_trend = 0.0

        # ── Score combinado ─────────────────────────────────────────────────────
        # Componentes normalizados para [0, 1]
        score_accel = max(0.0, min(1.0, accel * 5000.0))  # heurístico
        score_osc = max(0.0, min(1.0, freq / 3.0))
        score_r2 = max(0.0, min(1.0, best_r2))
        score_vol = max(0.0, min(1.0, vol_trend * 500.0))

        # Pesos: R² do fit LPPLS pesa mais
        score = 0.30 * score_accel + 0.15 * score_osc + 0.35 * score_r2 + 0.20 * score_vol
        score = max(0.0, min(1.0, score))

        # Confiança: quanto mais dados e melhor o fit, maior a confiança
        confidence = max(0.3, min(0.95, 0.4 + 0.4 * best_r2 + 0.01 * n / 30))

        explanation = (
            f"LPPLS bubble: aceleração={accel:.2e}, oscilações={oscillations}, "
            f"freq={freq:.2f}, best_R²={best_r2:.3f}, vol_trend={vol_trend:.2e}. "
            f"Score={score:.2f}."
        )

        return BaseCrisisModel._result(
            sensor_name=self.__class__.__name__,
            score=score,
            confidence=confidence,
            explanation=explanation,
            details={
                "n_days": n,
                "acceleration": round(accel, 6),
                "oscillations": oscillations,
                "log_frequency": round(freq, 3),
                "best_r2": round(best_r2, 3),
                "best_params": best_params,
                "volatility_trend": round(vol_trend, 6),
                "score_components": {
                    "acceleration": round(score_accel, 3),
                    "oscillations": round(score_osc, 3),
                    "lppls_fit": round(score_r2, 3),
                    "vol_trend": round(score_vol, 3),
                },
            },
        )
