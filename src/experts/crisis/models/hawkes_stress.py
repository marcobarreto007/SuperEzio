"""Exponential Hawkes process calibrated by maximum likelihood."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


@dataclass(frozen=True)
class HawkesFit:
    mu: float
    alpha: float
    beta: float
    branching_ratio: float
    log_likelihood: float
    poisson_log_likelihood: float
    converged: bool


def _hawkes_log_likelihood(
    event_times: np.ndarray, horizon: float, mu: float, alpha: float, beta: float
) -> float:
    """Log likelihood for ``lambda(t)=mu+alpha*sum(exp(-beta*(t-ti)))``."""
    if mu <= 0.0 or alpha < 0.0 or beta <= 0.0 or alpha / beta >= 1.0:
        return -np.inf
    excitation = 0.0
    log_intensity = 0.0
    previous_time = 0.0
    for index, event_time in enumerate(event_times):
        if index:
            excitation = math.exp(-beta * (event_time - previous_time)) * (1.0 + excitation)
        intensity = mu + alpha * excitation
        if intensity <= 0.0 or not math.isfinite(intensity):
            return -np.inf
        log_intensity += math.log(intensity)
        previous_time = float(event_time)
    compensator = mu * horizon + (alpha / beta) * np.sum(
        1.0 - np.exp(-beta * (horizon - event_times))
    )
    return float(log_intensity - compensator)


def _fit_exponential_hawkes(event_times: np.ndarray, horizon: float) -> HawkesFit:
    """Fit a stationary exponential Hawkes process with deterministic multistart MLE."""
    event_times = np.asarray(event_times, dtype=float)
    if (
        event_times.ndim != 1
        or len(event_times) < 5
        or not np.isfinite(event_times).all()
        or np.any(np.diff(event_times) <= 0.0)
        or event_times[0] <= 0.0
        or event_times[-1] >= horizon
    ):
        raise ValueError("Hawkes MLE requires >=5 finite, unique events strictly inside horizon")

    empirical_rate = len(event_times) / horizon
    mean_gap = float(np.mean(np.diff(event_times)))
    poisson_log_likelihood = float(len(event_times) * math.log(empirical_rate) - len(event_times))

    def unpack(parameters: np.ndarray) -> tuple[float, float, float, float]:
        mu = math.exp(float(parameters[0]))
        beta = math.exp(float(parameters[1]))
        branching_ratio = 0.995 * float(expit(parameters[2]))
        return mu, branching_ratio * beta, beta, branching_ratio

    def objective(parameters: np.ndarray) -> float:
        mu, alpha, beta, _ = unpack(parameters)
        value = _hawkes_log_likelihood(event_times, horizon, mu, alpha, beta)
        return -value if math.isfinite(value) else 1e100

    best = None
    for initial_branching in (0.05, 0.30, 0.70):
        for beta_factor in (0.5, 1.0, 2.0):
            initial = np.array(
                [
                    math.log(max(empirical_rate * (1.0 - initial_branching), 1e-6)),
                    math.log(max(beta_factor / mean_gap, 1e-6)),
                    logit(initial_branching / 0.995),
                ]
            )
            candidate = minimize(
                objective,
                initial,
                method="L-BFGS-B",
                bounds=[(-16.0, 5.0), (-12.0, 6.0), (-12.0, 12.0)],
                options={"maxiter": 1000, "ftol": 1e-12},
            )
            if best is None or candidate.fun < best.fun:
                best = candidate

    if best is None or not np.isfinite(best.fun):
        raise ValueError("Hawkes MLE failed to find a finite solution")
    mu, alpha, beta, branching_ratio = unpack(best.x)
    return HawkesFit(
        mu=mu,
        alpha=alpha,
        beta=beta,
        branching_ratio=branching_ratio,
        log_likelihood=-float(best.fun),
        poisson_log_likelihood=poisson_log_likelihood,
        converged=bool(best.success),
    )


class HawkesStressModel:
    THRESHOLD_RETURN = -0.02
    MIN_RETURNS = 90
    MIN_EVENTS = 5

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        market = input_data.market_series or []
        as_of = market[-1].date if market else None
        if len(market) < self.MIN_RETURNS + 1:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                f"Hawkes MLE requires at least {self.MIN_RETURNS + 1} market observations.",
                horizon=f"current {input_data.frequency} intensity",
                sample_size=max(0, len(market) - 1),
                as_of=as_of,
            )

        closes = np.asarray([point.close for point in market], dtype=float)
        returns = np.diff(np.log(closes))
        event_times = np.flatnonzero(returns < self.THRESHOLD_RETURN).astype(float) + 1.0
        horizon = float(len(returns) + 1)
        if len(event_times) < self.MIN_EVENTS:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                f"Hawkes MLE needs at least {self.MIN_EVENTS} adverse events; found {len(event_times)}.",
                horizon=f"current {input_data.frequency} intensity",
                sample_size=len(returns),
                as_of=as_of,
            )

        try:
            fit = _fit_exponential_hawkes(event_times, horizon)
        except ValueError as exc:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                str(exc),
                horizon=f"current {input_data.frequency} intensity",
                sample_size=len(returns),
                as_of=as_of,
            )

        current_intensity = fit.mu + fit.alpha * float(
            np.exp(-fit.beta * (horizon - event_times)).sum()
        )
        stationary_intensity = fit.mu / (1.0 - fit.branching_ratio)
        intensity_ratio = current_intensity / stationary_intensity
        likelihood_ratio = max(0.0, 2.0 * (fit.log_likelihood - fit.poisson_log_likelihood) - 4.0)
        evidence = 1.0 - math.exp(-likelihood_ratio / 10.0)
        current_excess = min(1.0, max(0.0, intensity_ratio - 1.0) / 2.0)
        score = min(
            1.0,
            0.60 * fit.branching_ratio + 0.25 * current_excess + 0.15 * evidence,
        )
        confidence = min(0.95, 0.35 + 0.03 * len(event_times) + 0.20 * evidence)
        if not fit.converged:
            confidence *= 0.7

        return BaseCrisisModel._result(
            sensor_name=self.__class__.__name__,
            score=score,
            confidence=confidence,
            explanation=(
                f"Exponential Hawkes MLE estimated branching ratio "
                f"{fit.branching_ratio:.2f} and current/stationary intensity "
                f"ratio {intensity_ratio:.2f}."
            ),
            method_kind="statistical_model",
            horizon=f"current {input_data.frequency} intensity",
            sample_size=len(returns),
            as_of=as_of,
            calibration_status="in_sample_mle",
            details={
                "event_definition": f"log_return < {self.THRESHOLD_RETURN:.2%}",
                "n_events": len(event_times),
                "mu": round(fit.mu, 8),
                "alpha": round(fit.alpha, 8),
                "beta": round(fit.beta, 8),
                "branching_ratio": round(fit.branching_ratio, 8),
                "current_intensity": round(current_intensity, 8),
                "stationary_intensity": round(stationary_intensity, 8),
                "intensity_ratio": round(intensity_ratio, 6),
                "log_likelihood": round(fit.log_likelihood, 6),
                "poisson_log_likelihood": round(fit.poisson_log_likelihood, 6),
                "converged": fit.converged,
            },
        )
