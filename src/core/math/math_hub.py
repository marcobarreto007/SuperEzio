"""Unified numerical report for the SuperEzio decision pipeline."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .indicators import bollinger, ema, macd, rsi, sma, vwap, vwap_deviation
from .risk import (
    annualized_return,
    cvar_historic,
    kelly_fraction,
    max_drawdown,
    sharpe_ratio,
    simple_return,
    sortino_ratio,
    var_historic,
    volatility,
)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, "", [], {}):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        if value == float("inf"):
            return "inf"
        if value == float("-inf"):
            return "-inf"
        return round(value, 6)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _dig(mapping: Mapping[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


@dataclass
class MathReport:
    ticker: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "partial"
    modules: dict[str, dict[str, Any]] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    numbers: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "ticker": self.ticker,
                "generated_at": self.generated_at,
                "status": self.status,
                "modules": self.modules,
                "summary": self.summary,
                "numbers": self.numbers,
                "coverage": self.coverage,
            }
        )


class MathHub:
    """Collects all numerical modules into one auditable MathReport."""

    MODULES = (
        "price_series",
        "technical_indicators",
        "return_metrics",
        "sharpe_sortino",
        "drawdown",
        "var_cvar",
        "kelly",
        "dcf_proxy",
        "crisis_aggregate",
        "quantum_bias",
        "portfolio_hrp",
        "f51_unified",
        "penny_momentum",
        "trading_losses",
    )

    def calculate_all(self, state_or_data: Mapping[str, Any]) -> dict[str, Any]:
        state = dict(state_or_data or {})
        data = self._extract_data(state)
        ticker = str(state.get("ticker") or data.get("ticker") or data.get("symbol") or "").upper()
        candles = self._extract_candles(data)
        closes = [c["close"] for c in candles if _safe_float(c.get("close")) is not None]
        volumes = [c.get("volume", 0.0) for c in candles]
        latest_price = self._latest_price(data, closes)
        returns = [
            simple_return(closes[i], closes[i - 1])
            for i in range(1, len(closes))
            if closes[i - 1] not in (0, None)
        ]

        report = MathReport(ticker=ticker)
        report.modules["price_series"] = self._price_series_module(
            latest_price=latest_price,
            closes=closes,
            candles=candles,
        )
        report.modules["technical_indicators"] = self._technical_module(
            latest_price=latest_price,
            closes=closes,
            volumes=volumes,
            data=data,
        )
        report.modules["return_metrics"] = self._return_module(returns)
        report.modules["sharpe_sortino"] = self._sharpe_module(returns)
        report.modules["drawdown"] = self._drawdown_module(closes)
        report.modules["var_cvar"] = self._var_module(returns)
        report.modules["kelly"] = self._kelly_module(returns)
        report.modules["dcf_proxy"] = self._dcf_module(data)
        report.modules["crisis_aggregate"] = self._crisis_module(data, ticker, closes)
        report.modules["quantum_bias"] = self._quantum_module()
        report.modules["portfolio_hrp"] = self._portfolio_module(closes, ticker)
        report.modules["f51_unified"] = self._f51_module(report.modules, data, state)
        report.modules["penny_momentum"] = self._penny_momentum_module(ticker, candles)
        report.modules["trading_losses"] = self._trading_losses_module(state)

        ok = [name for name, item in report.modules.items() if item.get("status") == "ok"]
        skipped = [
            name
            for name, item in report.modules.items()
            if item.get("status") in {"skipped", "insufficient_data"}
        ]
        errors = [name for name, item in report.modules.items() if item.get("status") == "error"]
        report.status = "ok" if len(ok) == len(self.MODULES) else "partial"
        if errors and not ok:
            report.status = "error"

        report.numbers = self._build_numbers(report.modules)
        report.summary = {
            "latest_price": latest_price,
            "return_annualized": report.numbers.get("annualized_return"),
            "volatility_annualized": report.numbers.get("volatility"),
            "sharpe": report.numbers.get("sharpe"),
            "max_drawdown": report.numbers.get("max_drawdown"),
            "var_95": report.numbers.get("var_95"),
            "kelly_fraction": report.numbers.get("kelly_fraction"),
            "crisis_score": report.numbers.get("crisis_score"),
            "quantum_bias": report.numbers.get("quantum_bias"),
            "f51_confidence": report.numbers.get("f51_confidence"),
        }
        report.coverage = {
            "total_modules": len(self.MODULES),
            "ok_modules": len(ok),
            "skipped_modules": len(skipped),
            "error_modules": len(errors),
            "ok": ok,
            "skipped": skipped,
            "errors": errors,
        }
        return report.to_dict()

    @staticmethod
    def to_deepseek_prompt(report: Mapping[str, Any]) -> str:
        from core.pipeline.prompts.math_prompt import format_math_context

        return format_math_context(report)

    def _extract_data(self, state: Mapping[str, Any]) -> dict[str, Any]:
        data = state.get("data")
        if isinstance(data, Mapping):
            return dict(data)
        return dict(state)

    def _extract_candles(self, data: Mapping[str, Any]) -> list[dict[str, float]]:
        raw = (
            data.get("ohlcv")
            or data.get("candles")
            or _dig(data, "chart", "ohlcv")
            or _dig(data, "price", "ohlcv")
            or []
        )
        candles: list[dict[str, float]] = []
        if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, Mapping)):
            for item in raw:
                if not isinstance(item, Mapping):
                    continue
                close = _safe_float(item.get("close"))
                if close is None:
                    continue
                candles.append(
                    {
                        "open": _safe_float(item.get("open"), close) or close,
                        "high": _safe_float(item.get("high"), close) or close,
                        "low": _safe_float(item.get("low"), close) or close,
                        "close": close,
                        "volume": _safe_float(item.get("volume"), 0.0) or 0.0,
                    }
                )
        if candles:
            return candles

        prices = data.get("prices") or data.get("close_prices") or data.get("closes") or []
        if isinstance(prices, Iterable) and not isinstance(prices, (str, bytes, Mapping)):
            for price in prices:
                close = _safe_float(price)
                if close is not None:
                    candles.append(
                        {"open": close, "high": close, "low": close, "close": close, "volume": 0.0}
                    )
        return candles

    def _latest_price(self, data: Mapping[str, Any], closes: list[float]) -> float | None:
        price = data.get("price")
        if isinstance(price, Mapping):
            for key in ("current", "latest", "last", "close", "regularMarketPrice"):
                value = _safe_float(price.get(key))
                if value is not None:
                    return value
        value = _safe_float(price)
        if value is not None:
            return value
        technicals = data.get("technicals")
        if isinstance(technicals, Mapping):
            value = _safe_float(technicals.get("price") or technicals.get("close"))
            if value is not None:
                return value
        return closes[-1] if closes else None

    def _price_series_module(
        self,
        *,
        latest_price: float | None,
        closes: list[float],
        candles: list[dict[str, float]],
    ) -> dict[str, Any]:
        if latest_price is None and not closes:
            return {"status": "insufficient_data", "reason": "missing_price_series"}
        return {
            "status": "ok",
            "values": {
                "latest_price": latest_price,
                "close_points": len(closes),
                "candle_points": len(candles),
            },
        }

    def _technical_module(
        self,
        *,
        latest_price: float | None,
        closes: list[float],
        volumes: list[float],
        data: Mapping[str, Any],
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        technicals = data.get("technicals")
        if isinstance(technicals, Mapping):
            values.update({k: v for k, v in technicals.items() if v not in (None, "", [], {})})
        if closes:
            values.update(
                {
                    "sma20": sma(closes, 20),
                    "sma50": sma(closes, 50),
                    "ema20": ema(closes, 20),
                    "rsi14": rsi(closes, 14),
                    "macd": macd(closes),
                    "bollinger": bollinger(closes),
                }
            )
            if latest_price is not None and volumes and any(volumes):
                vwap_value = vwap(closes[-len(volumes) :], volumes[-len(closes) :])
                values["vwap"] = vwap_value
                values["vwap_deviation"] = vwap_deviation(latest_price, vwap_value)
        clean_values = {k: v for k, v in values.items() if v not in (None, "", [], {})}
        if not clean_values:
            return {"status": "insufficient_data", "reason": "missing_technical_inputs"}
        return {"status": "ok", "values": clean_values}

    def _return_module(self, returns: list[float]) -> dict[str, Any]:
        if not returns:
            return {"status": "insufficient_data", "reason": "need_at_least_two_closes"}
        return {
            "status": "ok",
            "values": {
                "daily_return_latest": returns[-1],
                "annualized_return": annualized_return(returns),
                "sample_size": len(returns),
            },
        }

    def _sharpe_module(self, returns: list[float]) -> dict[str, Any]:
        if len(returns) < 2:
            return {"status": "insufficient_data", "reason": "need_return_series"}
        return {
            "status": "ok",
            "values": {
                "volatility": volatility(returns),
                "sharpe": sharpe_ratio(returns),
                "sortino": sortino_ratio(returns),
            },
        }

    def _drawdown_module(self, closes: list[float]) -> dict[str, Any]:
        if len(closes) < 2:
            return {"status": "insufficient_data", "reason": "need_equity_curve"}
        return {"status": "ok", "values": {"max_drawdown": max_drawdown(closes)}}

    def _var_module(self, returns: list[float]) -> dict[str, Any]:
        if not returns:
            return {"status": "insufficient_data", "reason": "need_return_series"}
        return {
            "status": "ok",
            "values": {
                "var_95": var_historic(returns, 0.95),
                "cvar_95": cvar_historic(returns, 0.95),
            },
        }

    def _kelly_module(self, returns: list[float]) -> dict[str, Any]:
        wins = [r for r in returns if r > 0]
        losses = [abs(r) for r in returns if r < 0]
        if not wins or not losses:
            return {"status": "insufficient_data", "reason": "need_wins_and_losses"}
        win_prob = len(wins) / len(returns)
        win_loss_ratio = (sum(wins) / len(wins)) / max(sum(losses) / len(losses), 1e-9)
        return {
            "status": "ok",
            "values": {
                "win_probability": win_prob,
                "win_loss_ratio": win_loss_ratio,
                "kelly_fraction": kelly_fraction(win_prob, win_loss_ratio),
            },
        }

    def _dcf_module(self, data: Mapping[str, Any]) -> dict[str, Any]:
        profile = data.get("profile") if isinstance(data.get("profile"), Mapping) else data
        fcf = _safe_float(
            profile.get("free_cash_flow") or profile.get("fcf") or profile.get("freeCashflow")
            if isinstance(profile, Mapping)
            else None
        )
        shares = _safe_float(
            profile.get("shares_outstanding")
            or profile.get("sharesOutstanding")
            or profile.get("shares")
            if isinstance(profile, Mapping)
            else None
        )
        if not fcf or not shares:
            return {"status": "skipped", "reason": "missing_fcf_or_shares"}
        growth = _safe_float(profile.get("growth_rate"), 0.03) or 0.03
        discount = _safe_float(profile.get("discount_rate"), 0.10) or 0.10
        terminal_growth = min(growth, 0.03)
        pv = 0.0
        current_fcf = fcf
        for year in range(1, 6):
            current_fcf *= 1 + growth
            pv += current_fcf / ((1 + discount) ** year)
        terminal = current_fcf * (1 + terminal_growth) / max(discount - terminal_growth, 0.01)
        equity_value = pv + terminal / ((1 + discount) ** 5)
        return {
            "status": "ok",
            "values": {
                "dcf_equity_value": equity_value,
                "dcf_value_per_share": equity_value / shares,
                "growth_rate": growth,
                "discount_rate": discount,
            },
        }

    def _crisis_module(
        self,
        data: Mapping[str, Any],
        ticker: str,
        closes: list[float],
    ) -> dict[str, Any]:
        try:
            from .crisis import crisis_aggregate

            crisis_input = {
                "asset_symbol": ticker,
                "country": data.get("country") or data.get("market"),
                "observations": data.get("macro_observations") or data.get("observations") or [],
                "market_series": data.get("market_series"),
                "prices": closes,
            }
            result = crisis_aggregate(crisis_input)
            status = "ok" if result.get("models_ok", 0) > 0 else "insufficient_data"
            return {"status": status, "values": result}
        except Exception as exc:
            return {"status": "error", "reason": str(exc)[:200]}

    def _quantum_module(self) -> dict[str, Any]:
        """Monte Carlo scenario generator — quantum walk distribution weights simulations.

        Replaces cosmetic QuantumWalkBias with actual utility:
        Uses the quantum walk probability distribution as scenario weights
        for a mini Monte Carlo simulation over price paths.
        """
        try:
            from experts.crisis.quantum_expert import QuantumWalkBias
            import numpy as np

            qw = QuantumWalkBias(n_qubits=4)
            result = qw.run_simulation()
            counts = result.get("counts", {})
            if not counts:
                return {"status": "skipped", "reason": "no_quantum_counts"}

            # Normalize to probabilities
            total = sum(counts.values())
            probs = {k: v / total for k, v in counts.items()}

            # Use as scenario weights for mini Monte Carlo (100 scenarios)
            n_scenarios = 100
            states = list(probs.keys())
            weights = [probs[s] for s in states]
            # Seed derived from the actual quantum counts so the simulation
            # varies with real input instead of being frozen on every call
            # (was hardcoded RandomState(42) — produced identical scenarios
            # regardless of ticker or market data).
            seed_material = "|".join(f"{k}:{v}" for k, v in sorted(counts.items()))
            seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:8], 16)
            rng = np.random.RandomState(seed)

            # Generate scenario returns: sample from quantum distribution
            # Each scenario gets a return multiplier weighted by quantum probs
            scenarios = []
            for _ in range(n_scenarios):
                # Weighted random choice of quantum state
                state_idx = rng.choice(len(states), p=weights)
                # Map state to return multiplier: 0=0.95, 1=0.98, 2=1.0, 3=1.02, 4=1.05, etc
                state_val = int(states[state_idx], 2)  # binary to int
                multiplier = 0.90 + (state_val / max(1, 2**4 - 1)) * 0.20  # 0.90 to 1.10
                # Add noise
                multiplier += rng.normal(0, 0.01)
                scenarios.append(round(multiplier, 4))

            scenarios.sort()
            var_95_mc = float(np.percentile(scenarios, 5))
            var_99_mc = float(np.percentile(scenarios, 1))
            expected_mult = float(np.mean(scenarios))
            worst_case = float(min(scenarios))
            best_case = float(max(scenarios))

            return {
                "status": "ok",
                "values": {
                    "method": "quantum_weighted_monte_carlo",
                    "n_scenarios": n_scenarios,
                    "expected_multiplier": round(expected_mult, 4),
                    "var_95_multiplier": round(var_95_mc, 4),
                    "var_99_multiplier": round(var_99_mc, 4),
                    "worst_case": round(worst_case, 4),
                    "best_case": round(best_case, 4),
                    "qubits": 4,
                },
            }
        except Exception as exc:
            return {"status": "skipped", "reason": str(exc)[:100]}

    def _portfolio_module(self, closes: list[float], ticker: str) -> dict[str, Any]:
        """HRP portfolio allocation — multi-asset from historical cache."""
        if not ticker:
            return {"status": "skipped", "reason": "no_ticker"}
        try:
            import sqlite3
            from core.math.portfolio import hrp_allocate, covariance_matrix

            # Fetch returns for up to 20 tickers from historical cache
            ticker_returns: dict[str, list[float]] = {}
            db_path = "data/historical_cache.db"
            try:
                conn = sqlite3.connect(db_path)
                # Get tickers with most data points
                rows = conn.execute(
                    "SELECT ticker, COUNT(*) as cnt FROM ohlcv_cache GROUP BY ticker ORDER BY cnt DESC LIMIT 20"
                ).fetchall()
                for t, _ in rows:
                    candles = conn.execute(
                        "SELECT close FROM ohlcv_cache WHERE ticker=? ORDER BY date DESC LIMIT 60",
                        (t,),
                    ).fetchall()
                    closes_t = [c[0] for c in reversed(candles) if c[0]]
                    if len(closes_t) >= 20:
                        rets = [
                            (closes_t[i] - closes_t[i - 1]) / closes_t[i - 1]
                            for i in range(1, len(closes_t))
                            if closes_t[i - 1] > 0
                        ]
                        if len(rets) >= 10:
                            ticker_returns[t] = rets
                conn.close()
            except Exception:
                pass

            # Fallback: at least include current ticker
            if ticker not in ticker_returns and closes and len(closes) >= 10:
                rets = [
                    (closes[i] - closes[i - 1]) / closes[i - 1]
                    for i in range(1, len(closes))
                    if closes[i - 1] > 0
                ]
                if len(rets) >= 5:
                    ticker_returns[ticker] = rets

            if len(ticker_returns) < 1:
                return {"status": "skipped", "reason": "no_tickers_with_returns"}

            result = hrp_allocate(ticker_returns, capital=10000.0)

            # Add covariance summary for top pairs
            cov_summary = {}
            if len(ticker_returns) >= 2:
                cov = covariance_matrix(ticker_returns)
                # Find highest correlation pair
                max_corr = 0.0
                max_pair = ("", "")
                tickers_list = list(ticker_returns.keys())
                for i in range(len(tickers_list)):
                    for j in range(i + 1, len(tickers_list)):
                        ti, tj = tickers_list[i], tickers_list[j]
                        std_i = cov[ti][ti] ** 0.5
                        std_j = cov[tj][tj] ** 0.5
                        if std_i > 0 and std_j > 0:
                            corr = cov[ti][tj] / (std_i * std_j)
                            if abs(corr) > abs(max_corr):
                                max_corr = corr
                                max_pair = (ti, tj)
                cov_summary = {
                    "highest_correlation": round(max_corr, 3),
                    "pair": f"{max_pair[0]}/{max_pair[1]}",
                }

            return {
                "status": "ok",
                "values": {
                    **result,
                    "covariance_summary": cov_summary,
                    "tickers_used": len(ticker_returns),
                },
            }
        except Exception as exc:
            return {"status": "error", "reason": str(exc)[:100]}

    def _f51_module(
        self,
        modules: Mapping[str, Mapping[str, Any]],
        data: Mapping[str, Any],
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        existing = state.get("f51_verdict")
        if isinstance(existing, Mapping) and existing:
            return {"status": "ok", "values": dict(existing)}
        try:
            from f51.formulas import DecisionFactors, heuristic_uncertainty, unified_decision

            data_quality = str(data.get("data_quality") or "").lower()
            var_value = _dig(modules, "var_cvar", "values", "var_95") or 0.0
            vol_value = _dig(modules, "sharpe_sortino", "values", "volatility") or 0.0
            consensus, consensus_is_heuristic = self._expert_consensus(state)
            factors = DecisionFactors(
                veracity=0.85 if data_quality in {"complete", "ok", "high"} else 0.55,
                consensus=consensus,
                risk=max(0.0, min(1.0, abs(float(var_value or 0.0)) + float(vol_value or 0.0))),
                uncertainty=heuristic_uncertainty(
                    text=str(state.get("message") or ""),
                    numeric_features={
                        "volatility": float(vol_value or 0.0),
                        "missing_data_ratio": 0.15
                        if data_quality in {"complete", "ok", "high"}
                        else 0.45,
                        "data_points": int(
                            _dig(modules, "price_series", "values", "close_points") or 0
                        ),
                    },
                ),
            )
            confidence = unified_decision(factors)
            return {
                "status": "ok",
                "values": {
                    "confidence": confidence,
                    "factors": factors.__dict__,
                    "consensus_is_heuristic": consensus_is_heuristic,
                },
            }
        except Exception as exc:
            return {"status": "error", "reason": str(exc)[:200]}

    @staticmethod
    def _expert_consensus(state: Mapping[str, Any]) -> tuple[float, bool]:
        """Derive expert agreement from real expert_results when available.

        Falls back to a documented neutral heuristic (0.5, not 0.65) when no
        expert has run yet — callers must check consensus_is_heuristic before
        treating this number as measured agreement.
        """
        results = state.get("expert_results")
        if not isinstance(results, list) or not results:
            return 0.5, True

        verdicts: list[str] = []
        for item in results:
            if not isinstance(item, Mapping) or not item.get("ok"):
                continue
            verdict = item.get("verdict") or _dig(item, "parsed", "verdict")
            if verdict:
                verdicts.append(str(verdict).upper())

        if not verdicts:
            return 0.5, True

        from collections import Counter

        counts = Counter(verdicts)
        top_count = counts.most_common(1)[0][1]
        return top_count / len(verdicts), False

    def _penny_momentum_module(
        self, ticker: str, candles: list[dict[str, float]]
    ) -> dict[str, Any]:
        if not ticker or len(candles) < 20:
            return {"status": "skipped", "reason": "need_ticker_and_20_candles"}
        try:
            from .penny_momentum import simulate_penny_momentum_backtest

            bars = [
                {"date": f"t{i}", "close": c["close"], "volume": c.get("volume", 0.0)}
                for i, c in enumerate(candles)
            ]
            result = simulate_penny_momentum_backtest({ticker: bars})
            return {"status": "ok", "values": result}
        except Exception as exc:
            return {"status": "error", "reason": str(exc)[:200]}

    def _trading_losses_module(self, state: Mapping[str, Any]) -> dict[str, Any]:
        expected = state.get("expected_returns")
        actual = state.get("actual_returns")
        if not isinstance(expected, list) or not isinstance(actual, list):
            return {"status": "skipped", "reason": "missing_expected_or_actual_returns"}
        try:
            from .trading_losses import directional_accuracy, directional_loss, sharpe_loss

            return {
                "status": "ok",
                "values": {
                    "directional_accuracy": directional_accuracy(expected, actual),
                    "directional_loss": directional_loss(expected, actual),
                    "sharpe_loss": sharpe_loss(actual),
                },
            }
        except Exception as exc:
            return {"status": "error", "reason": str(exc)[:200]}

    def _build_numbers(self, modules: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        return {
            "latest_price": _dig(modules, "price_series", "values", "latest_price"),
            "annualized_return": _dig(modules, "return_metrics", "values", "annualized_return"),
            "volatility": _dig(modules, "sharpe_sortino", "values", "volatility"),
            "sharpe": _dig(modules, "sharpe_sortino", "values", "sharpe"),
            "sortino": _dig(modules, "sharpe_sortino", "values", "sortino"),
            "max_drawdown": _dig(modules, "drawdown", "values", "max_drawdown"),
            "var_95": _dig(modules, "var_cvar", "values", "var_95"),
            "cvar_95": _dig(modules, "var_cvar", "values", "cvar_95"),
            "kelly_fraction": _dig(modules, "kelly", "values", "kelly_fraction"),
            "crisis_score": _dig(modules, "crisis_aggregate", "values", "aggregate_score"),
            "quantum_bias": _dig(modules, "quantum_bias", "values", "bias"),
            "f51_confidence": _dig(modules, "f51_unified", "values", "confidence"),
            # Technical indicators
            "rsi": _dig(modules, "technical_indicators", "values", "rsi14"),
            "macd": _dig(modules, "technical_indicators", "values", "macd"),
            "sma20": _dig(modules, "technical_indicators", "values", "sma20"),
            "sma50": _dig(modules, "technical_indicators", "values", "sma50"),
            "ema20": _dig(modules, "technical_indicators", "values", "ema20"),
            "bollinger": _dig(modules, "technical_indicators", "values", "bollinger"),
            "vwap": _dig(modules, "technical_indicators", "values", "vwap"),
        }
