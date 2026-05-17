"""
NeuralDecisionExpert — Decision & Risk Copilot for market setup validation.
Protects against pump-and-dump, fake breakouts, and high-asymmetry risks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


class FeatureContractValidator:
    """Validates real-time payloads against the feature_contract.json specification."""

    def __init__(self, contract_path: Path | None = None):
        if contract_path is None:
            contract_path = Path(__file__).parent / "feature_contract.json"
        
        try:
            with open(contract_path, "r", encoding="utf-8") as f:
                self.contract = json.load(f)
        except Exception as exc:
            # Fallback inline contract if file loading fails (e.g. tests running in isolation)
            self.contract = {
                "required_features": {
                    "return_1": {"type": "float", "min": -1.0, "max": 1.0},
                    "return_5": {"type": "float", "min": -1.0, "max": 1.0},
                    "rsi_14": {"type": "float", "min": 0.0, "max": 100.0},
                    "atr_pct": {"type": "float", "min": 0.0, "max": 1.0},
                    "volume_zscore": {"type": "float", "min": -10.0, "max": 100.0},
                    "price_vs_ema_21": {"type": "float", "min": -1.0, "max": 1.0},
                    "trend_slope": {"type": "float", "min": -10.0, "max": 10.0},
                    "volatility_regime": {"type": "string", "enum": ["low", "normal", "high", "extreme"]},
                    "liquidity_sweep": {"type": "boolean"}
                },
                "required_context": {
                    "macro_risk": {"type": "string", "enum": ["low", "neutral", "high", "unknown"]},
                    "news_sentiment": {"type": "string", "enum": ["bullish", "neutral", "bearish", "mixed"]},
                    "fraud_risk": {"type": "float", "min": 0.0, "max": 1.0},
                    "veracity_score": {"type": "float", "min": 0.0, "max": 1.0}
                }
            }

    def validate(self, features: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
        """Validate both features and context against contract types, ranges, and enums.
        
        Returns a list of validation error strings. If valid, returns an empty list.
        """
        errors = []

        # Validate Features
        req_features = self.contract.get("required_features", {})
        for name, spec in req_features.items():
            if name not in features:
                errors.append(f"Missing required feature: '{name}'")
                continue

            val = features[name]
            expected_type = spec["type"]

            # Type Validation
            if expected_type == "float":
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    errors.append(f"Feature '{name}' must be float/int, got {type(val).__name__}")
                    continue
                # Range Validation
                if "min" in spec and val < spec["min"]:
                    errors.append(f"Feature '{name}' value {val} is below minimum {spec['min']}")
                if "max" in spec and val > spec["max"]:
                    errors.append(f"Feature '{name}' value {val} is above maximum {spec['max']}")

            elif expected_type == "string":
                if not isinstance(val, str):
                    errors.append(f"Feature '{name}' must be string, got {type(val).__name__}")
                    continue
                if "enum" in spec and val not in spec["enum"]:
                    errors.append(f"Feature '{name}' value '{val}' not in permitted enum options: {spec['enum']}")

            elif expected_type == "boolean":
                if not isinstance(val, bool):
                    errors.append(f"Feature '{name}' must be boolean, got {type(val).__name__}")

        # Validate Context
        req_context = self.contract.get("required_context", {})
        for name, spec in req_context.items():
            if name not in context:
                errors.append(f"Missing required context field: '{name}'")
                continue

            val = context[name]
            expected_type = spec["type"]

            # Type Validation
            if expected_type == "float":
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    errors.append(f"Context '{name}' must be float/int, got {type(val).__name__}")
                    continue
                # Range Validation
                if "min" in spec and val < spec["min"]:
                    errors.append(f"Context '{name}' value {val} is below minimum {spec['min']}")
                if "max" in spec and val > spec["max"]:
                    errors.append(f"Context '{name}' value {val} is above maximum {spec['max']}")

            elif expected_type == "string":
                if not isinstance(val, str):
                    errors.append(f"Context '{name}' must be string, got {type(val).__name__}")
                    continue
                if "enum" in spec and val not in spec["enum"]:
                    errors.append(f"Context '{name}' value '{val}' not in permitted enum options: {spec['enum']}")

        return errors


class NeuralDecisionExpert:
    """Expert in charge of assessing setup quality, trend validity, and fraud risk."""

    def __init__(self, contract_path: Path | None = None):
        self.validator = FeatureContractValidator(contract_path)

    def validate_input(
        self, symbol: str, timeframe: str, features: Dict[str, Any], context: Dict[str, Any]
    ) -> List[str]:
        """Perform full validation of payload contract."""
        errors = []
        if not symbol or not isinstance(symbol, str):
            errors.append("Invalid or missing 'symbol'")
        if not timeframe or not isinstance(timeframe, str):
            errors.append("Invalid or missing 'timeframe'")

        # Validate features and context structure
        if not isinstance(features, dict):
            errors.append("'features' must be an object/dict")
            return errors
        if not isinstance(context, dict):
            errors.append("'context' must be an object/dict")
            return errors

        contract_errors = self.validator.validate(features, context)
        errors.extend(contract_errors)
        return errors

    def predict(
        self, symbol: str, timeframe: str, features: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess technical signal validity and evaluate directional probability.
        
        Calibrates uncertainty dynamically based on forensic fraud risk and veracity gaps.
        """
        # Validate first
        errors = self.validate_input(symbol, timeframe, features, context)
        if errors:
            return {
                "expert": "NeuralDecisionExpert",
                "symbol": symbol,
                "error": "Contract validation failed",
                "validation_errors": errors,
                "recommendation": "veto_block",
                "veto": True,
                "reason": f"Contract violations found: {', '.join(errors)}"
            }

        # ── 1. Extrair Variáveis e Metas do Contexto / Features ──
        fraud_risk = float(context["fraud_risk"])
        veracity_score = float(context["veracity_score"])
        rsi = float(features["rsi_14"])
        vol_zscore = float(features["volume_zscore"])
        trend_slope = float(features["trend_slope"])
        return_1 = float(features["return_1"])

        # ── 2. Calcular a Incerteza Calibrada (Uncertainty) ──
        # Se a veracidade for baixa, ou o risco de fraude for alto, a incerteza sobe!
        # Sem incerteza calibrada, o modelo vira um bêbado confiante.
        veracity_gap = 1.0 - veracity_score
        base_uncertainty = 0.15
        
        # Penalidades por fraud_risk e veracity_gap
        uncertainty = base_uncertainty + (0.45 * fraud_risk) + (0.35 * veracity_gap)
        if features["volatility_regime"] == "extreme":
            uncertainty += 0.10
        
        uncertainty = max(0.05, min(0.95, uncertainty))

        # ── 3. Classificar o Regime de Mercado ──
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

        # ── 4. Calcular Probabilidades de Direção & Retorno Esperado ──
        # Mocking real distribution matching the regime and technical features
        up_prob = 0.33
        down_prob = 0.33
        sideways_prob = 0.34

        if regime == "trend_real":
            up_prob, down_prob, sideways_prob = 0.62, 0.25, 0.13
            expected_return = 0.0075
            drawdown_risk = 0.25
        elif regime == "pump_artificial":
            # Posição extremamente perigosa - alta chance de crash iminente
            up_prob, down_prob, sideways_prob = 0.15, 0.75, 0.10
            expected_return = -0.0520
            drawdown_risk = 0.95
        elif regime == "liquidity_hunt":
            up_prob, down_prob, sideways_prob = 0.40, 0.45, 0.15
            expected_return = -0.0020
            drawdown_risk = 0.70
        else:
            # Neutro / Sem edge
            expected_return = 0.0010
            drawdown_risk = 0.35

        # ── 5. Ajustar Drawdown Risk e Veto com Base em Guardrails ──
        # Elevar o drawdown_risk se a fraude for patente
        if fraud_risk > 0.4:
            drawdown_risk = max(drawdown_risk, fraud_risk)
        
        # Vetar se o risco de fraude for extremo ou a incerteza for ingovernável
        veto = (fraud_risk > 0.5) or (veracity_score < 0.5) or (drawdown_risk > 0.8)

        # ── 6. Determinar Recomendação de Reação de Governança ──
        if veto:
            recommendation = "veto_block"
            reason = (
                f"Sinal bloqueado pelos guardrails de fraude ({fraud_risk:.0%}) "
                f"ou integridade de dados ({veracity_score:.0%}). Risco assimétrico contra o usuário."
            )
        elif regime == "trend_real" and uncertainty < 0.4:
            recommendation = "alerta_forte"
            reason = "Tendência sólida confirmada com baixo ruído de manipulação e volume convergente."
        elif expected_return > 0.003 and drawdown_risk < 0.45:
            recommendation = "alerta_fraco"
            reason = "Relação risco/retorno favorável, mas incerteza média recomenda cautela e tamanho reduzido."
        else:
            recommendation = "observar"
            reason = "Sem edge direcional claro. Incerteza e volatilidade recomendam aguardar fora do mercado."

        return {
            "expert": "NeuralDecisionExpert",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction_prob": {
                "up": round(up_prob, 2),
                "down": round(down_prob, 2),
                "sideways": round(sideways_prob, 2)
            },
            "expected_return": round(expected_return, 4),
            "drawdown_risk": round(drawdown_risk, 2),
            "uncertainty": round(uncertainty, 2),
            "regime": regime,
            "recommendation": recommendation,
            "veto": veto,
            "reason": reason
        }
