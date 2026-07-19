"""
Wolfram Alpha Quantitative Provider — Math verification for financial models.

Integrates Wolfram Alpha Short Answers API for:
  - Monte Carlo probability verification
  - Statistical computation (Sharpe, VaR, standard error)
  - Option pricing sanity checks (Black-Scholes reference values)
  - Numerical validation of F51 engine outputs

Uses the full Wolfram Alpha v2 API (not Short Answers — more flexible).
Rate limit: 2000 calls/month (free tier), ~0.05 req/s sustained.
"""

from __future__ import annotations

import logging
import os
import time
import urllib.parse
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    import requests as _requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ── Quantitative templates ──────────────────────────────────────────────────

_QUANT_TEMPLATES: dict[str, str] = {
    "sharpe": (
        "compute annualized Sharpe ratio: "
        "mean daily return={mean_return}, risk-free rate={risk_free}, "
        "daily volatility={volatility}, trading days=252"
    ),
    "black_scholes": (
        "Black-Scholes call option price: "
        "spot={spot}, strike={strike}, time to expiry={tte} years, "
        "risk-free rate={rate}, volatility={sigma}"
    ),
    "var_parametric": (
        "VaR parametric: portfolio value={pv}, confidence={confidence}, "
        "horizon days={horizon}, annual volatility={sigma}"
    ),
    "compound_growth": (
        "compound annual growth rate: initial={initial}, final={final}, years={years}"
    ),
    "monte_carlo_prob": (
        "probability that normal random variable with "
        "mean={mean} and standard deviation={std} exceeds {threshold}"
    ),
}


class WolframProvider:
    """Wolfram Alpha quantitative verification provider."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("WOLFRAM_API_KEY")
        self._base = "https://api.wolframalpha.com/v2"
        self._last_call = 0.0
        self._min_interval = 3.0  # 2000 calls/month ≈ ~3s between calls sustained

    @property
    def healthy(self) -> bool:
        return bool(self.api_key)

    def _rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    def query(self, input_str: str, *, timeout: float = 12.0) -> Dict[str, Any]:
        """Raw Wolfram Alpha query — returns structured result."""
        if not self.api_key or not _HAS_REQUESTS:
            return {"error": "wolfram_api_key_missing", "input": input_str}

        self._rate_limit()
        try:
            encoded = urllib.parse.quote(input_str)
            url = f"{self._base}/query?input={encoded}&appid={self.api_key}&output=json&format=plaintext"
            resp = _requests.get(url, timeout=timeout)

            if resp.status_code == 403:
                return {"error": "wolfram_api_key_invalid", "input": input_str}
            if resp.status_code != 200:
                return {"error": f"wolfram_http_{resp.status_code}", "input": input_str}

            data = resp.json()
            query_result = data.get("queryresult", {})

            if not query_result.get("success"):
                error_msg = query_result.get("error", {})
                return {
                    "error": "wolfram_no_result",
                    "input": input_str,
                    "detail": str(error_msg)[:200],
                }

            # Extract plaintext results from pods
            pods_output: list[str] = []
            for pod in query_result.get("pods", []):
                pod_title = pod.get("title", "")
                for subpod in pod.get("subpods", []):
                    plaintext = subpod.get("plaintext", "").strip()
                    if plaintext:
                        pods_output.append(f"{pod_title}: {plaintext}")

            return {
                "input": input_str,
                "result": "\n".join(pods_output) if pods_output else "no_text_result",
                "pods": len(query_result.get("pods", [])),
                "timing": query_result.get("timing", 0),
            }

        except Exception as exc:
            logger.warning("[Wolfram] query failed: %s", exc)
            return {"error": f"wolfram_exception: {exc}", "input": input_str}

    def verify_sharpe(
        self,
        mean_return: float,
        volatility: float,
        risk_free: float = 0.04,
    ) -> Dict[str, Any]:
        """Verify Sharpe ratio computation."""
        template = _QUANT_TEMPLATES["sharpe"].format(
            mean_return=mean_return,
            risk_free=risk_free,
            volatility=volatility,
        )
        return self.query(template)

    def verify_option_price(
        self,
        spot: float,
        strike: float,
        tte: float,
        rate: float = 0.04,
        sigma: float = 0.25,
    ) -> Dict[str, Any]:
        """Verify Black-Scholes option pricing."""
        template = _QUANT_TEMPLATES["black_scholes"].format(
            spot=spot, strike=strike, tte=tte, rate=rate, sigma=sigma
        )
        return self.query(template)

    def verify_var(
        self,
        portfolio_value: float,
        confidence: float = 0.95,
        horizon: int = 1,
        sigma: float = 0.25,
    ) -> Dict[str, Any]:
        """Verify Value-at-Risk computation."""
        template = _QUANT_TEMPLATES["var_parametric"].format(
            pv=portfolio_value,
            confidence=confidence,
            horizon=horizon,
            sigma=sigma,
        )
        return self.query(template)

    def verify_cagr(
        self,
        initial: float,
        final: float,
        years: float,
    ) -> Dict[str, Any]:
        """Verify Compound Annual Growth Rate."""
        template = _QUANT_TEMPLATES["compound_growth"].format(
            initial=initial, final=final, years=years
        )
        return self.query(template)

    def verify_probability(
        self,
        mean: float,
        std: float,
        threshold: float,
    ) -> Dict[str, Any]:
        """Verify probability computation (e.g., Monte Carlo output)."""
        template = _QUANT_TEMPLATES["monte_carlo_prob"].format(
            mean=mean, std=std, threshold=threshold
        )
        return self.query(template)

    def compute(self, expression: str) -> Dict[str, Any]:
        """Generic mathematical computation."""
        return self.query(expression)

    def verify_f51_output(self, score: float, confidence: float) -> Dict[str, Any]:
        """Range-check legacy F51 numerical scores without implying calibration."""
        checks = []
        checks.append(f"is {score} between 0 and 1")
        checks.append(f"is {confidence} between 0 and 1")
        results = []
        for check in checks:
            result = self.query(check)
            results.append(
                {
                    "check": check,
                    "result": result.get("result", result.get("error", "?")),
                }
            )
        return {
            "f51_score": score,
            "f51_decision_score": confidence,
            "score_type": "uncalibrated_decision_score",
            "checks": results,
            "timestamp": time.time(),
        }
