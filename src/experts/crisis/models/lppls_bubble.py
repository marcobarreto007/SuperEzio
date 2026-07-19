"""Multi-window Log-Periodic Power Law Singularity (LPPLS) bubble filter."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import minimize

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


@dataclass(frozen=True)
class LPPLSFit:
    tc: float
    m: float
    omega: float
    a: float
    b: float
    c1: float
    c2: float
    r_squared: float
    relative_error: float
    damping: float
    oscillations: float
    accepted: bool
    converged: bool


def _second_derivative(y: np.ndarray) -> np.ndarray:
    """Second discrete derivative retained for compatibility diagnostics."""
    values = np.asarray(y, dtype=float)
    if len(values) < 3:
        return np.zeros_like(values)
    result = np.empty_like(values)
    result[1:-1] = values[2:] - 2.0 * values[1:-1] + values[:-2]
    result[0] = values[2] - 2.0 * values[1] + values[0]
    result[-1] = values[-1] - 2.0 * values[-2] + values[-3]
    return result


def _zero_crossings(y: np.ndarray) -> int:
    values = np.asarray(y, dtype=float)
    return int(np.sum(values[:-1] * values[1:] < 0.0))


def _linear_lppls(
    log_prices: np.ndarray, t: np.ndarray, tc: float, m: float, omega: float
) -> tuple[np.ndarray, np.ndarray]:
    distance = tc - t
    if np.any(distance <= 0.0):
        raise ValueError("LPPLS critical time must be strictly after the fitted window")
    power = distance**m
    phase = omega * np.log(distance)
    design = np.column_stack(
        [np.ones_like(t), power, power * np.cos(phase), power * np.sin(phase)]
    )
    coefficients, _, rank, _ = np.linalg.lstsq(design, log_prices, rcond=None)
    if rank < 4:
        raise ValueError("LPPLS linear design is rank deficient")
    return coefficients, design @ coefficients


def _lppls_fit_quality(
    log_prices: np.ndarray, t: np.ndarray, tc: float, m: float, omega: float
) -> float:
    """Compatibility helper returning R-squared for the complete A/B/C1/C2 model."""
    try:
        coefficients, fitted = _linear_lppls(log_prices, t, tc, m, omega)
    except (ValueError, np.linalg.LinAlgError):
        return 0.0
    total = float(np.sum((log_prices - np.mean(log_prices)) ** 2))
    if total <= 1e-16 or coefficients[1] >= 0.0:
        return 0.0
    residual = float(np.sum((log_prices - fitted) ** 2))
    return max(0.0, min(1.0, 1.0 - residual / total))


def _fit_lppls_window(log_prices: np.ndarray) -> LPPLSFit:
    """Profile A/B/C1/C2 and optimize tc/m/omega with deterministic multistart."""
    log_prices = np.asarray(log_prices, dtype=float)
    n = len(log_prices)
    if n < 60 or not np.isfinite(log_prices).all() or float(np.ptp(log_prices)) <= 1e-10:
        raise ValueError("LPPLS requires at least 60 finite, non-constant log prices")
    t = np.arange(n, dtype=float)
    last_time = float(n - 1)
    bounds = [(last_time + 1.0, last_time + 0.35 * n), (0.1, 0.9), (6.0, 13.0)]
    total_variation = float(np.sum((log_prices - np.mean(log_prices)) ** 2))

    def objective(parameters: np.ndarray) -> float:
        try:
            _, fitted = _linear_lppls(
                log_prices, t, float(parameters[0]), float(parameters[1]), float(parameters[2])
            )
        except (ValueError, np.linalg.LinAlgError):
            return 1e6
        return float(np.sum((log_prices - fitted) ** 2) / total_variation)

    best = None
    for critical_fraction in (0.05, 0.15, 0.30):
        for initial_m in (0.25, 0.55, 0.80):
            for initial_omega in (6.5, 9.0, 12.0):
                initial = np.array(
                    [last_time + max(1.0, critical_fraction * n), initial_m, initial_omega]
                )
                candidate = minimize(
                    objective,
                    initial,
                    method="L-BFGS-B",
                    bounds=bounds,
                    options={"maxiter": 350, "ftol": 1e-12},
                )
                if best is None or candidate.fun < best.fun:
                    best = candidate
    if best is None or not np.isfinite(best.fun):
        raise ValueError("LPPLS nonlinear optimization failed")

    tc, m, omega = (float(value) for value in best.x)
    coefficients, fitted = _linear_lppls(log_prices, t, tc, m, omega)
    a, b, c1, c2 = (float(value) for value in coefficients)
    residual_sum = float(np.sum((log_prices - fitted) ** 2))
    r_squared = max(0.0, min(1.0, 1.0 - residual_sum / total_variation))
    price_range = max(float(np.ptp(log_prices)), 1e-12)
    relative_error = math.sqrt(residual_sum / n) / price_range
    amplitude = math.hypot(c1, c2)
    damping = math.inf if amplitude <= 1e-14 else m * abs(b) / (omega * amplitude)
    oscillations = omega / (2.0 * math.pi) * math.log(tc / (tc - last_time))
    amplitude_ratio = amplitude / max(abs(b), 1e-14)
    accepted = bool(
        best.success
        and b < 0.0
        and r_squared >= 0.95
        and relative_error <= 0.10
        and damping >= 1.0
        and oscillations >= 2.5
        and 0.01 <= amplitude_ratio <= 1.0
        and log_prices[-1] > log_prices[0]
    )
    return LPPLSFit(
        tc=tc,
        m=m,
        omega=omega,
        a=a,
        b=b,
        c1=c1,
        c2=c2,
        r_squared=r_squared,
        relative_error=relative_error,
        damping=damping,
        oscillations=oscillations,
        accepted=accepted,
        converged=bool(best.success),
    )


class LPPLSBubbleModel:
    MIN_DAYS = 90

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        market = input_data.market_series or []
        as_of = market[-1].date if market else None
        if len(market) < self.MIN_DAYS:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                f"Multi-window LPPLS requires at least {self.MIN_DAYS} market observations.",
                horizon=f"1 to 35% of fitted {input_data.frequency} window ahead",
                sample_size=len(market),
                as_of=as_of,
            )

        log_prices = np.log(np.asarray([point.close for point in market], dtype=float))
        n = len(log_prices)
        window_sizes = sorted(
            {
                max(60, n // 2),
                max(75, 3 * n // 4),
                min(120, n),
                min(180, n),
                n,
            }
        )
        fits: list[tuple[int, LPPLSFit]] = []
        for window in window_sizes:
            if window < 60:
                continue
            try:
                fits.append((window, _fit_lppls_window(log_prices[-window:])))
            except ValueError:
                continue
        if len(fits) < 2:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                "LPPLS optimization did not produce at least two valid window fits.",
                horizon=f"1 to 35% of fitted {input_data.frequency} window ahead",
                sample_size=n,
                as_of=as_of,
            )

        accepted = [fit for _, fit in fits if fit.accepted]
        accepted_fraction = len(accepted) / len(fits)
        confirmed = len(accepted) >= 2 and accepted_fraction >= 0.50
        if confirmed:
            median_r_squared = float(np.median([fit.r_squared for fit in accepted]))
            score = min(1.0, accepted_fraction * median_r_squared)
        else:
            score = 0.0
        convergence_fraction = sum(fit.converged for _, fit in fits) / len(fits)
        confidence = min(0.92, 0.35 + 0.35 * convergence_fraction + 0.15 * len(fits) / 5.0)

        fit_details = []
        for window, fit in fits:
            fit_details.append(
                {
                    "window": window,
                    "tc_offset": round(fit.tc - (window - 1), 6),
                    "m": round(fit.m, 6),
                    "omega": round(fit.omega, 6),
                    "A": round(fit.a, 8),
                    "B": round(fit.b, 8),
                    "C1": round(fit.c1, 8),
                    "C2": round(fit.c2, 8),
                    "r_squared": round(fit.r_squared, 6),
                    "relative_error": round(fit.relative_error, 6),
                    "damping": round(fit.damping, 6) if math.isfinite(fit.damping) else None,
                    "oscillations": round(fit.oscillations, 6),
                    "accepted": fit.accepted,
                    "converged": fit.converged,
                }
            )

        return BaseCrisisModel._result(
            sensor_name=self.__class__.__name__,
            score=score,
            confidence=confidence,
            explanation=(
                f"Complete LPPLS A/B/C1/C2 filter accepted {len(accepted)}/{len(fits)} "
                f"windows; multi-window bubble confirmation is {confirmed}."
            ),
            method_kind="statistical_model",
            horizon=f"1 to 35% of fitted {input_data.frequency} window ahead",
            sample_size=n,
            as_of=as_of,
            calibration_status="multi_window_filtered",
            details={
                "confirmed": confirmed,
                "accepted_windows": len(accepted),
                "fitted_windows": len(fits),
                "accepted_fraction": round(accepted_fraction, 6),
                "filters": {
                    "m": [0.1, 0.9],
                    "omega": [6.0, 13.0],
                    "B_negative": True,
                    "r_squared_min": 0.95,
                    "damping_min": 1.0,
                    "oscillations_min": 2.5,
                },
                "window_fits": fit_details,
            },
        )
