"""Two-regime Gaussian hidden Markov model for market stress."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.special import logsumexp

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


@dataclass(frozen=True)
class GaussianHMMFit:
    means: np.ndarray
    variances: np.ndarray
    transition: np.ndarray
    initial: np.ndarray
    filtered_probabilities: np.ndarray
    log_likelihood: float
    iterations: int
    converged: bool


def _log_emissions(values: np.ndarray, means: np.ndarray, variances: np.ndarray) -> np.ndarray:
    return -0.5 * (
        np.log(2.0 * math.pi * variances)[None, :]
        + ((values[:, None] - means[None, :]) ** 2) / variances[None, :]
    )


def _forward_filter(
    values: np.ndarray,
    means: np.ndarray,
    variances: np.ndarray,
    transition: np.ndarray,
    initial: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Scaled forward recursion; each row is causal by construction."""
    emissions = np.exp(_log_emissions(values, means, variances))
    filtered = np.empty((len(values), 2), dtype=float)
    scales = np.empty(len(values), dtype=float)

    unscaled = initial * emissions[0]
    scales[0] = max(float(unscaled.sum()), np.finfo(float).tiny)
    filtered[0] = unscaled / scales[0]
    for index in range(1, len(values)):
        unscaled = (filtered[index - 1] @ transition) * emissions[index]
        scales[index] = max(float(unscaled.sum()), np.finfo(float).tiny)
        filtered[index] = unscaled / scales[index]
    return filtered, scales, float(np.log(scales).sum())


def _fit_gaussian_hmm(
    values: np.ndarray, *, max_iter: int = 200, tolerance: float = 1e-7
) -> GaussianHMMFit:
    """Estimate a two-state Gaussian HMM with deterministic Baum-Welch EM."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) < 20 or not np.isfinite(values).all():
        raise ValueError("HMM requires at least 20 finite one-dimensional observations")
    total_variance = float(np.var(values))
    if total_variance <= 1e-12:
        raise ValueError("HMM cannot identify regimes in a constant series")

    center = float(np.median(values))
    high_variance = np.abs(values - center) > np.quantile(np.abs(values - center), 0.65)
    if high_variance.sum() < 3 or (~high_variance).sum() < 3:
        raise ValueError("HMM deterministic initialization is degenerate")

    means = np.array([values[~high_variance].mean(), values[high_variance].mean()])
    variance_floor = max(total_variance * 1e-5, 1e-12)
    variances = np.array(
        [
            max(float(np.var(values[~high_variance])), variance_floor),
            max(float(np.var(values[high_variance])), variance_floor),
        ]
    )
    transition = np.array([[0.97, 0.03], [0.08, 0.92]], dtype=float)
    initial = np.array([0.8, 0.2], dtype=float)

    previous_log_likelihood = -np.inf
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):
        log_emission = _log_emissions(values, means, variances)
        log_transition = np.log(np.clip(transition, 1e-12, 1.0))
        log_initial = np.log(np.clip(initial, 1e-12, 1.0))

        log_alpha = np.empty((len(values), 2), dtype=float)
        log_alpha[0] = log_initial + log_emission[0]
        for time in range(1, len(values)):
            log_alpha[time] = log_emission[time] + logsumexp(
                log_alpha[time - 1][:, None] + log_transition, axis=0
            )
        log_likelihood = float(logsumexp(log_alpha[-1]))

        log_beta = np.zeros((len(values), 2), dtype=float)
        for time in range(len(values) - 2, -1, -1):
            log_beta[time] = logsumexp(
                log_transition + log_emission[time + 1][None, :] + log_beta[time + 1],
                axis=1,
            )

        gamma = np.exp(log_alpha + log_beta - log_likelihood)
        gamma /= gamma.sum(axis=1, keepdims=True)
        xi_sum = np.zeros((2, 2), dtype=float)
        for time in range(len(values) - 1):
            log_xi = (
                log_alpha[time][:, None]
                + log_transition
                + log_emission[time + 1][None, :]
                + log_beta[time + 1][None, :]
                - log_likelihood
            )
            xi_sum += np.exp(log_xi)

        occupancy = np.maximum(gamma.sum(axis=0), 1e-9)
        initial = np.clip(gamma[0], 1e-8, None)
        initial /= initial.sum()
        transition = xi_sum / np.maximum(gamma[:-1].sum(axis=0)[:, None], 1e-9)
        transition = np.clip(transition, 1e-6, 1.0)
        transition /= transition.sum(axis=1, keepdims=True)
        means = (gamma * values[:, None]).sum(axis=0) / occupancy
        variances = (gamma * ((values[:, None] - means[None, :]) ** 2)).sum(axis=0) / occupancy
        variances = np.maximum(variances, variance_floor)

        if np.isfinite(previous_log_likelihood) and abs(
            log_likelihood - previous_log_likelihood
        ) <= tolerance * (1.0 + abs(previous_log_likelihood)):
            converged = True
            break
        previous_log_likelihood = log_likelihood

    filtered, _, filtered_log_likelihood = _forward_filter(
        values, means, variances, transition, initial
    )
    return GaussianHMMFit(
        means=means,
        variances=variances,
        transition=transition,
        initial=initial,
        filtered_probabilities=filtered,
        log_likelihood=filtered_log_likelihood,
        iterations=iterations,
        converged=converged,
    )


class MarkovRegimeModel:
    """Compatibility class name for a genuine Gaussian HMM implementation."""

    MIN_RETURNS = 60

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        market = input_data.market_series or []
        as_of = market[-1].date if market else None
        if len(market) < self.MIN_RETURNS + 1:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                f"Gaussian HMM requires at least {self.MIN_RETURNS + 1} market observations.",
                horizon=f"current {input_data.frequency} regime",
                sample_size=max(0, len(market) - 1),
                as_of=as_of,
            )

        closes = np.asarray([point.close for point in market], dtype=float)
        returns = np.diff(np.log(closes))
        try:
            fit = _fit_gaussian_hmm(returns)
        except ValueError as exc:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                str(exc),
                horizon=f"current {input_data.frequency} regime",
                sample_size=len(returns),
                as_of=as_of,
            )

        stress_state = int(np.argmax(fit.variances))
        calm_state = 1 - stress_state
        stress_probability = float(fit.filtered_probabilities[-1, stress_state])
        variance_ratio = float(fit.variances[stress_state] / fit.variances[calm_state])
        separation = min(1.0, max(0.0, math.log(max(variance_ratio, 1.0)) / math.log(6.0)))
        confidence = min(
            0.95,
            0.35 + 0.30 * separation + 0.20 * min(len(returns) / 250.0, 1.0),
        )
        if not fit.converged:
            confidence *= 0.7

        return BaseCrisisModel._result(
            sensor_name=self.__class__.__name__,
            score=stress_probability,
            confidence=confidence,
            explanation=(
                f"Gaussian HMM filtered stress probability is {stress_probability:.1%}; "
                f"stress/calm variance ratio is {variance_ratio:.2f}."
            ),
            method_kind="statistical_model",
            horizon=f"current {input_data.frequency} regime",
            sample_size=len(returns),
            as_of=as_of,
            calibration_status="in_sample_mle",
            details={
                "posterior_kind": "filtered_causal",
                "stress_state": stress_state,
                "state_means": fit.means.tolist(),
                "state_volatilities": np.sqrt(fit.variances).tolist(),
                "transition_matrix": fit.transition.tolist(),
                "log_likelihood": round(fit.log_likelihood, 6),
                "iterations": fit.iterations,
                "converged": fit.converged,
            },
        )
