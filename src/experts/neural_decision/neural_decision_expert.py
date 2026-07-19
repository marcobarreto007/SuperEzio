"""Snapshot data-integrity and setup-risk copilot.

This component deliberately does not forecast direction.  Only the causal,
calibrated candle model may emit a directional probability distribution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FeatureContractValidator:
    """Validate real-time payloads against the checked-in feature contract."""

    def __init__(self, contract_path: Path | None = None) -> None:
        path = contract_path or Path(__file__).parent / "feature_contract.json"
        try:
            self.contract = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.contract = {
                "required_features": {
                    "return_1": {"type": "float", "min": -1.0, "max": 1.0},
                    "return_5": {"type": "float", "min": -1.0, "max": 1.0},
                    "rsi_14": {"type": "float", "min": 0.0, "max": 100.0},
                    "atr_pct": {"type": "float", "min": 0.0, "max": 1.0},
                    "volume_zscore": {"type": "float", "min": -10.0, "max": 100.0},
                    "price_vs_ema_21": {"type": "float", "min": -1.0, "max": 1.0},
                    "trend_slope": {"type": "float", "min": -10.0, "max": 10.0},
                    "volatility_regime": {
                        "type": "string",
                        "enum": ["low", "normal", "high", "extreme"],
                    },
                    "liquidity_sweep": {"type": "boolean"},
                },
                "required_context": {
                    "macro_risk": {
                        "type": "string",
                        "enum": ["low", "neutral", "high", "unknown"],
                    },
                    "news_sentiment": {
                        "type": "string",
                        "enum": ["bullish", "neutral", "bearish", "mixed"],
                    },
                    "fraud_risk": {"type": "float", "min": 0.0, "max": 1.0},
                    "veracity_score": {"type": "float", "min": 0.0, "max": 1.0},
                },
            }

    def validate(self, features: dict[str, Any], context: dict[str, Any]) -> list[str]:
        """Return all contract violations; an empty list means valid."""
        errors: list[str] = []
        errors.extend(self._validate_group("Feature", features, "required_features"))
        errors.extend(self._validate_group("Context", context, "required_context"))
        return errors

    def _validate_group(
        self, label: str, values: dict[str, Any], contract_key: str
    ) -> list[str]:
        errors: list[str] = []
        for name, spec in self.contract.get(contract_key, {}).items():
            if name not in values:
                noun = "feature" if label == "Feature" else "context field"
                errors.append(f"Missing required {noun}: '{name}'")
                continue
            value = values[name]
            expected_type = spec["type"]
            if expected_type == "float":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    errors.append(
                        f"{label} '{name}' must be float/int, got {type(value).__name__}"
                    )
                    continue
                if "min" in spec and value < spec["min"]:
                    errors.append(f"{label} '{name}' value {value} is below minimum {spec['min']}")
                if "max" in spec and value > spec["max"]:
                    errors.append(f"{label} '{name}' value {value} is above maximum {spec['max']}")
            elif expected_type == "string":
                if not isinstance(value, str):
                    errors.append(f"{label} '{name}' must be string, got {type(value).__name__}")
                    continue
                if "enum" in spec and value not in spec["enum"]:
                    errors.append(
                        f"{label} '{name}' value '{value}' not in permitted enum options: "
                        f"{spec['enum']}"
                    )
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"{label} '{name}' must be boolean, got {type(value).__name__}")
        return errors


class NeuralDecisionExpert:
    """Assess input integrity and setup risk without inventing market odds."""

    def __init__(self, contract_path: Path | None = None) -> None:
        self.validator = FeatureContractValidator(contract_path)

    def validate_input(
        self,
        symbol: str,
        timeframe: str,
        features: dict[str, Any],
        context: dict[str, Any],
    ) -> list[str]:
        """Perform full validation of payload contract."""
        errors: list[str] = []
        if not symbol or not isinstance(symbol, str):
            errors.append("Invalid or missing 'symbol'")
        if not timeframe or not isinstance(timeframe, str):
            errors.append("Invalid or missing 'timeframe'")
        if not isinstance(features, dict):
            errors.append("'features' must be an object/dict")
            return errors
        if not isinstance(context, dict):
            errors.append("'context' must be an object/dict")
            return errors
        errors.extend(self.validator.validate(features, context))
        return errors

    def predict(
        self,
        symbol: str,
        timeframe: str,
        features: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a safety assessment and explicitly abstain on direction."""
        errors = self.validate_input(symbol, timeframe, features, context)
        if errors:
            return {
                "expert": "NeuralDecisionExpert",
                "symbol": symbol,
                "error": "Contract validation failed",
                "validation_errors": errors,
                "status": "error",
                "decision": "ABSTAIN",
                "direction_prob": {},
                "recommendation": "veto_block",
                "veto": True,
                "reason_codes": ["CONTRACT_INVALID"],
                "reason": f"Contract violations found: {', '.join(errors)}",
            }

        fraud_risk = float(context["fraud_risk"])
        veracity_score = float(context["veracity_score"])
        rsi = float(features["rsi_14"])
        vol_zscore = float(features["volume_zscore"])
        trend_slope = float(features["trend_slope"])
        return_1 = float(features["return_1"])
        atr_pct = float(features["atr_pct"])

        # Integrity uncertainty, not predictive calibration.
        uncertainty = 1.0 - veracity_score * (1.0 - fraud_risk)
        if features["volatility_regime"] == "extreme":
            uncertainty = max(uncertainty, min(1.0, abs(return_1) / max(atr_pct, 1e-9)))
        uncertainty = max(0.0, min(1.0, uncertainty))

        regime = "no_edge"
        if fraud_risk > 0.6:
            regime = "pump_artificial"
        elif vol_zscore > 3.0 and abs(return_1) > 0.05:
            regime = "liquidity_hunt"
        elif trend_slope > 0.15 and rsi > 65:
            regime = "trend_real"
        elif trend_slope < -0.15 and rsi < 35:
            regime = "reversal_weak"
        elif features["volatility_regime"] in ("high", "extreme"):
            regime = "high_asymmetry"

        normalized_shock = abs(return_1) / max(3.0 * atr_pct, 1e-9)
        drawdown_risk = max(fraud_risk, 1.0 - veracity_score, min(1.0, normalized_shock))
        drawdown_risk = max(0.0, min(1.0, drawdown_risk))
        veto = (fraud_risk > 0.5) or (veracity_score < 0.5) or (drawdown_risk > 0.8)

        if veto:
            recommendation = "veto_block"
            reason = (
                f"Sinal bloqueado pelos guardrails de fraude ({fraud_risk:.0%}) "
                f"ou integridade de dados ({veracity_score:.0%}). Risco assimetrico."
            )
        elif regime == "trend_real" and uncertainty < 0.4:
            recommendation = "alerta_forte"
            reason = "Tendencia observada; falta qualificacao direcional pelo modelo causal."
        else:
            recommendation = "observar"
            reason = "Sem previsao direcional qualificada; aguardar dados causais e calibracao."

        reason_codes = ["DIRECTION_MODEL_REQUIRED"]
        if veto:
            reason_codes.append("SAFETY_VETO")
        return {
            "expert": "NeuralDecisionExpert",
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "abstain",
            "decision": "ABSTAIN",
            "direction_prob": {},
            "calibration_status": "unavailable",
            "skill_status": "unqualified",
            "model_id": None,
            "as_of": None,
            "horizon": timeframe,
            "reason_codes": reason_codes,
            "drawdown_risk": round(drawdown_risk, 4),
            "uncertainty": round(uncertainty, 4),
            "regime": regime,
            "recommendation": recommendation,
            "veto": veto,
            "reason": reason,
        }
