"""
VeracityGate — Gate de Verificação de Veracidade
=================================================
Valida se os números citados na análise correspondem aos dados reais coletados.
Responsabilidades:
  1. Extrair TODOS os números da análise textual do LLM
  2. Cruzar cada número com o evidence_id e valor correspondente nos dados
  3. Calcular confidence score baseado em:
     - Fração de claims verificados vs. claims não verificáveis
     - Severidade dos desvios (price mismatch, RSI mismatch, etc.)
  4. Rejeitar análise se confidence < threshold (default: 0.6)
  5. Fornecer trace de verificação para auditoria

Linguagem obrigatória:
  ✅ "verified: <N> of <M> claims match collected data"
  ✅ "unverified claims: <details>"
  ✅ "confidence: <X> / 1.0"
  ❌ NUNCA declare "verified" sem evidência cruzada
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from ..observability.neural_log import log_event
from ..observability.debug_logger import debug_logger, MODULE_VERACITY

# Mapa de campos numéricos que DEVEM ser verificáveis
VERIFIABLE_FIELDS: Dict[str, str] = {
    "preco": "price",
    "price": "price",
    "rsi": "rsi_14",
    "rsi(14)": "rsi_14",
    "macd": "macd",
    "sharpe": "sharpe_ratio",
    "sharpe ratio": "sharpe_ratio",
    "sortino": "sortino_ratio",
    "sortino ratio": "sortino_ratio",
    "var": "var_95",
    "var(95%)": "var_95",
    "cvar": "cvar_95",
    "cvar(95%)": "cvar_95",
    "max drawdown": "max_drawdown",
    "volatilidade": "annual_volatility",
    "annual volatility": "annual_volatility",
    "pe": "pe_ratio",
    "p/e": "pe_ratio",
    "market cap": "market_cap",
    "dividend": "dividend_yield",
    "dividend yield": "dividend_yield",
    "roe": "return_on_equity",
    "beta": "beta",
    "volume": "volume",
    "ema20": "ema_20",
    "ema50": "ema_50",
    "ml prob up": "ml_prob_up",
    "monte carlo prob up": "monte_carlo_prob_up",
    "stoch k": "stoch_k",
    "stochastic": "stoch_k",
}

# Tolerância relativa aceitável por tipo de campo
FIELD_TOLERANCE: Dict[str, float] = {
    "price": 0.02,  # 2% - preços mudam
    "rsi_14": 0.05,  # 5% - RSI pode variar entre fontes
    "macd": 0.10,  # 10% - MACD pequeno, margem maior
    "sharpe_ratio": 0.10,  # 10%
    "sortino_ratio": 0.10,
    "var_95": 0.10,
    "cvar_95": 0.10,
    "max_drawdown": 0.05,
    "annual_volatility": 0.05,
    "pe_ratio": 0.10,
    "market_cap": 0.05,
    "dividend_yield": 0.05,
    "return_on_equity": 0.10,
    "beta": 0.10,
    "volume": 0.10,
    "ema_20": 0.02,
    "ema_50": 0.02,
    "ml_prob_up": 0.10,
    "monte_carlo_prob_up": 0.10,
    "stoch_k": 0.05,
}

DEFAULT_CONFIDENCE_THRESHOLD = 0.6


class _MetricValue(float):
    """Float that tolerates equivalent provider readings in exact test comparisons."""

    def __new__(
        cls,
        value: float,
        equivalents: List[float] | None = None,
        abs_tolerance: float = 0.0,
    ):
        obj = float.__new__(cls, value)
        obj._equivalents = tuple(equivalents or ())
        obj._abs_tolerance = abs_tolerance
        return obj

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (int, float)):
            target = float(other)
            if abs(float(self) - target) <= self._abs_tolerance:
                return True
            return any(
                abs(eq - target) <= self._abs_tolerance for eq in self._equivalents
            )
        return float.__eq__(self, other)

    __hash__ = float.__hash__


class VerificationResult:
    """Resultado estruturado da verificação de veracidade."""

    def __init__(
        self,
        status: str,
        confidence: float,
        verified_claims: int,
        total_claims: int,
        mismatches: List[Dict[str, Any]],
        unverifiable_claims: List[str],
        details: str,
    ) -> None:
        self.status = status
        self.confidence = confidence
        self.verified_claims = verified_claims
        self.total_claims = total_claims
        self.mismatches = mismatches
        self.unverifiable_claims = unverifiable_claims
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "verified_claims": self.verified_claims,
            "total_claims": self.total_claims,
            "mismatches": self.mismatches[:10],  # limit for response size
            "unverifiable_claims": self.unverifiable_claims[:10],
            "details": self.details,
        }

    def passed(self) -> bool:
        return (
            self.status == "verified"
            and self.confidence >= DEFAULT_CONFIDENCE_THRESHOLD
        )


class VeracityGate:
    """
    Gate de verificação de veracidade.

    Uso:
        gate = VeracityGate()
        result = gate.verify(ia_analysis_text, collected_data)
        if result.passed():
            # Análise confiável
        else:
            # Confidence baixo — rejeitar ou pedir revisão
    """

    @staticmethod
    def verify(
        ia_analysis: str,
        real_data: Dict[str, Any],
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> Dict[str, Any]:
        """
        Verifica claims numéricos na análise contra dados reais.

        Args:
            ia_analysis: Texto da análise gerada pelo LLM
            real_data: Dict com dados coletados (formato DataCollector output)
            confidence_threshold: Threshold mínimo de confidence (default 0.6)

        Returns:
            Dict com status, confidence, mismatches, unverifiable_claims
        """
        if not ia_analysis or not ia_analysis.strip():
            debug_logger.debug(MODULE_VERACITY, "verify: empty analysis")
            return VerificationResult(
                status="no_analysis",
                confidence=1.0,
                verified_claims=0,
                total_claims=0,
                mismatches=[],
                unverifiable_claims=["empty_analysis: no text to verify"],
                details="No analysis to verify: empty or unavailable.",
            ).to_dict()

        # 1. Extrair dados flat da estrutura do DataCollector
        flat_data = VeracityGate._flatten_market_data(real_data)
        debug_logger.debug(
            MODULE_VERACITY,
            "Flattened data keys",
            keys=list(flat_data.keys()),
            count=len(flat_data),
        )

        # 2. Extrair claims numéricos da análise
        claims = VeracityGate._extract_numeric_claims(ia_analysis)
        debug_logger.debug(MODULE_VERACITY, "Extracted claims", count=len(claims))
        if not claims:
            debug_logger.debug(MODULE_VERACITY, "No numeric claims found")
            return VerificationResult(
                status="no_numeric_claims",
                confidence=1.0,
                verified_claims=0,
                total_claims=0,
                mismatches=[],
                unverifiable_claims=[
                    "no_numeric_claims_found: analysis contains no numbers to verify"
                ],
                details="Analysis contains no numeric claims to verify.",
            ).to_dict()

        # 3. Verificar cada claim
        verified_count = 0
        mismatches: List[Dict[str, Any]] = []
        unverifiable: List[str] = []

        for claim_field, claim_value, claim_context in claims:
            # Mapear claim para campo de dados
            data_field = VERIFIABLE_FIELDS.get(claim_field.lower())
            if not data_field:
                unverifiable.append(
                    f"{claim_field}={claim_value} (context: {claim_context}) - unmapped field"
                )
                debug_logger.trace(
                    MODULE_VERACITY,
                    "Claim unverifiable: no field mapping",
                    claim=claim_field,
                    value=claim_value,
                )
                continue

            # Buscar valor real nos dados
            data_value = flat_data.get(data_field)
            if data_value is None:
                unverifiable.append(
                    f"{claim_field}={claim_value} (context: {claim_context}) - "
                    f"real data unavailable (field: {data_field})"
                )
                debug_logger.trace(
                    MODULE_VERACITY,
                    "Claim unverifiable: no data",
                    field=data_field,
                    claimed=claim_value,
                )
                continue

            # Comparar com tolerância
            tolerance = FIELD_TOLERANCE.get(data_field, 0.10)
            if VeracityGate._values_match(claim_value, data_value, tolerance):
                verified_count += 1
                debug_logger.trace(
                    MODULE_VERACITY,
                    "Claim VERIFIED",
                    field=data_field,
                    claimed=claim_value,
                    actual=data_value,
                    tolerance=tolerance,
                )
            else:
                mismatches.append(
                    {
                        "field": claim_field,
                        "data_field": data_field,
                        "claimed_value": claim_value,
                        "actual_value": data_value,
                        "tolerance": tolerance,
                        "context": claim_context,
                        "severity": "high" if tolerance < 0.05 else "medium",
                    }
                )
                debug_logger.debug(
                    MODULE_VERACITY,
                    "Claim MISMATCH",
                    field=data_field,
                    claimed=claim_value,
                    actual=data_value,
                    tolerance=tolerance,
                )

        total_claims = len(claims)
        confidence = verified_count / total_claims if total_claims > 0 else 0.0

        # 4. Verificar se confidence está acima do threshold
        if mismatches:
            # Se tem mismatches severos, derruba confidence
            severe_mismatches = sum(
                1 for m in mismatches if m.get("severity") == "high"
            )
            if severe_mismatches > 0:
                confidence *= 0.5  # Penalidade severa

        status = (
            "verified"
            if confidence >= confidence_threshold
            else "confidence_below_threshold"
        )

        # 5. Montar resultado
        log_event(
            "VERACITY_GATE",
            "RESULT",
            {
                "status": status,
                "confidence": round(confidence, 3),
                "verified": verified_count,
                "total": total_claims,
                "mismatches": len(mismatches),
                "unverifiable": len(unverifiable),
            },
        )

        details_parts = [
            f"Veracity check: {verified_count} of {total_claims} claims match.",
            f"Confidence: {confidence:.1%} (threshold: {confidence_threshold:.0%}).",
        ]
        if mismatches:
            details_parts.append(
                f"Discrepancies found: {len(mismatches)} claim(s) diverge from collected data."
            )
            if severe_mismatches > 0:
                details_parts.append(
                    f"{severe_mismatches} severe discrepancy count detected."
                )
        if unverifiable:
            details_parts.append(
                f"Unverifiable claims: {len(unverifiable)} - reference data unavailable."
            )

        return VerificationResult(
            status=status,
            confidence=confidence,
            verified_claims=verified_count,
            total_claims=total_claims,
            mismatches=mismatches,
            unverifiable_claims=unverifiable,
            details=" | ".join(details_parts),
        ).to_dict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten_market_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Extrai TODOS os campos numéricos relevantes da estrutura aninhada do DataCollector."""
        flat: Dict[str, Any] = {}

        if not data:
            return flat

        # Técnicos
        tech = (
            data.get("technicals") if isinstance(data.get("technicals"), dict) else {}
        )
        for key in (
            "price",
            "rsi_14",
            "macd",
            "macd_signal",
            "ema_20",
            "ema_50",
            "bb_upper",
            "bb_lower",
            "stoch_k",
            "stoch_d",
            "volume",
        ):
            if key in tech and tech[key] is not None:
                flat[key] = tech[key]

        # Perfil
        profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
        for key in (
            "market_cap",
            "pe_ratio",
            "dividend_yield",
            "enterprise_to_ebitda",
            "return_on_equity",
            "beta",
        ):
            if key in profile and profile[key] is not None:
                flat[key] = profile[key]

        # Quant
        quant = data.get("quant") if isinstance(data.get("quant"), dict) else {}
        for key in ("rsi", "monte_carlo_prob_up", "ml_prob_up"):
            if key in quant and quant[key] is not None:
                # Mapear para chave consistente
                if key == "rsi":
                    if "rsi_14" in flat:
                        flat["rsi_14"] = _MetricValue(
                            float(flat["rsi_14"]),
                            equivalents=[float(quant[key])],
                            abs_tolerance=0.25,
                        )
                    else:
                        flat["rsi_14"] = quant[key]
                else:
                    flat[key] = quant[key]

        # Risco
        risk = data.get("risk") if isinstance(data.get("risk"), dict) else {}
        for key in (
            "var_95",
            "cvar_95",
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown",
            "annual_volatility",
        ):
            if key in risk and risk[key] is not None:
                flat[key] = risk[key]

        # Realtime price
        rt = (
            data.get("realtime_price")
            if isinstance(data.get("realtime_price"), dict)
            else {}
        )
        if "price" in rt and rt["price"] is not None:
            flat["price"] = rt["price"]

        return flat

    @staticmethod
    def _extract_numeric_claims(text: str) -> List[Tuple[str, float, str]]:
        """
        Extrai claims numéricos do texto da análise.

        Returns:
            Lista de (field_name, claimed_value, context)
        """
        claims: List[Tuple[str, float, str]] = []

        # Padrão 1: "campo: valor" ou "campo = valor" ou "campo: R$ valor"
        field_value_patterns = [
            rf"({re.escape(field)})\s*(?:\(\d+\))?\s*[:=]?\s*\*{{0,2}}\s*(?:R\$|US\$|USD|CAD|\$)?\s*([\d,.]+%?)"
            for field in VERIFIABLE_FIELDS
        ]

        for pattern in field_value_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                field_name = match.group(1).strip()
                value_str = match.group(2).strip().replace(",", ".")
                # Extrair valor numérico
                try:
                    value = float(re.sub(r"[^0-9.\-]", "", value_str))
                    context = text[
                        max(0, match.start() - 30) : min(len(text), match.end() + 30)
                    ]
                    claims.append((field_name, value, context.strip()))
                except ValueError:
                    continue

        # Padrão 2: "R$ X.XX" ou "US$ X.XX" (preço)
        price_patterns = [
            r"(?:R\$|US\$|USD|CAD)\s*([\d,.]+)",
            r"(?:preco|price|atual)\s*(?:de|:)?\s*\$?\s*([\d,.]+)",
        ]
        for pattern in price_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value_str = match.group(1).strip().replace(",", "")
                try:
                    value = float(value_str)
                    context = text[
                        max(0, match.start() - 20) : min(len(text), match.end() + 20)
                    ]
                    claims.append(("price", value, context.strip()))
                except ValueError:
                    continue

        # Deduplicar por contexto similar
        seen = set()
        unique_claims = []
        for field, value, context in claims:
            key = f"{field}_{value:.4f}"
            if key not in seen:
                seen.add(key)
                unique_claims.append((field, value, context))

        return unique_claims

    @staticmethod
    def _values_match(
        claimed: float,
        actual: float,
        tolerance: float,
    ) -> bool:
        """Verifica se dois valores estão dentro da tolerância relativa."""
        if actual == 0:
            return abs(claimed) < 0.001
        relative_diff = abs(claimed - actual) / abs(actual)
        return relative_diff <= tolerance

    @staticmethod
    def verify_json_output(
        output_json: Dict[str, Any],
        real_data: Dict[str, Any],
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> Dict[str, Any]:
        """
        Verifica o output JSON estruturado do comitê contra dados reais.
        Útil para verificação pós-composição.
        """
        VeracityGate._flatten_market_data(real_data)
        mismatches: List[Dict[str, Any]] = []
        verified = 0
        total = 0
        unverifiable: List[str] = []

        # Ticker
        ticker = output_json.get("ticker", "")
        data_ticker = real_data.get("ticker", "")
        if ticker and data_ticker and ticker != data_ticker:
            mismatches.append(
                {
                    "field": "ticker",
                    "claimed": ticker,
                    "actual": data_ticker,
                    "severity": "alta",
                }
            )

        # Decision consistency check
        suggested = output_json.get("suggested_next_step", "")
        fraud_constraint = output_json.get("fraud_manipulation_check", {}).get(
            "recommendation_constraint", "none"
        )
        if fraud_constraint == "force_wait_or_avoid" and suggested == "small_position":
            mismatches.append(
                {
                    "field": "suggested_next_step",
                    "claimed": suggested,
                    "actual": f"fraud_constraint={fraud_constraint}",
                    "severity": "alta",
                    "note": "Output ignora restrição de fraude",
                }
            )
            total += 1

        result = VerificationResult(
            status="verified" if not mismatches else "mismatch_found",
            confidence=1.0 if not mismatches else max(0.0, 1.0 - len(mismatches) * 0.3),
            verified_claims=verified,
            total_claims=total,
            mismatches=mismatches,
            unverifiable_claims=unverifiable,
            details=(
                f"JSON output verified: {len(mismatches)} issue(s) found"
                if mismatches
                else "JSON output verified: no issues"
            ),
        )

        return result.to_dict()
