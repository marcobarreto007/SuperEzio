"""
Main CrisisMathExpert orchestrator.
"""

import logging
from typing import List

from ..contracts.schemas import CrisisInput, CrisisReport, SensorResult
from ..io.report import build_crisis_summary, get_default_limitations
from ..logic.ensemble import aggregate_scores
from ..logic.scoring import classify_alert_level, classify_regime

# Import models dynamically to avoid crash if one fails
from ..models.bis_credit_gap import BISCreditGapModel
from ..models.credit_asset_growth import CreditAssetGrowthModel
from ..models.debt_service_ratio import DebtServiceRatioModel
from ..models.growth_at_risk import GrowthAtRiskModel
from ..models.hawkes_stress import HawkesStressModel
from ..models.imf_mispricing import IMFMispricingModel
from ..models.lppls_bubble import LPPLSBubbleModel
from ..models.markov_regime import MarkovRegimeModel
from ..models.minsky_keen import MinskyKeenModel
from ..models.network_contagion import NetworkContagionModel
from ..models.shiller_valuation import ShillerValuationModel
from ..models.systemic_bank_risk import SystemicBankRiskModel

logger = logging.getLogger(__name__)


class _NoopNotifier:
    """Notifier stub used when none is injected and core is unreachable."""

    def send_alert(self, message: str, level: str = "INFO") -> None:
        logger.debug("Noop crisis notifier ignored %s alert: %s", level, message[:120])


class CrisisMathExpert:
    """
    100% mathematical/quantitative expert for systemic risk detection.
    """

    def __init__(self, notifier=None, fraud_rag=None):
        self.sensors = [
            BISCreditGapModel(),
            DebtServiceRatioModel(),
            CreditAssetGrowthModel(),
            ShillerValuationModel(),
            IMFMispricingModel(),
            MarkovRegimeModel(),
            MinskyKeenModel(),
            GrowthAtRiskModel(),
            SystemicBankRiskModel(),
            NetworkContagionModel(),
            LPPLSBubbleModel(),
            HawkesStressModel(),
        ]
        self._notifier = notifier
        self._fraud_rag = fraud_rag

    def _get_notifier(self):
        if self._notifier is not None:
            return self._notifier
        return _NoopNotifier()

    def _get_fraud_rag(self):
        if self._fraud_rag is not None:
            return self._fraud_rag
        try:
            from core.rag.fraud_rag import fraud_rag

            return fraud_rag
        except Exception as exc:
            logger.warning("Fraud RAG unavailable for CrisisMath: %s", exc)
            return None

    def analyze(self, input_data: CrisisInput) -> CrisisReport:
        # --- RAG de Fraude ---
        fraud_evidence = []
        rag = self._get_fraud_rag()
        if input_data.asset_symbol and rag is not None:
            fraud_evidence = rag.search_patterns(input_data.asset_symbol)
        input_data.metadata["fraud_evidence"] = fraud_evidence
        sensor_results: List[SensorResult] = []

        # 1. Executa sensores
        for sensor in self.sensors:
            try:
                res = sensor.evaluate(input_data)
                sensor_results.append(res)
            except Exception as e:
                sensor_results.append(
                    SensorResult(
                        sensor_name=sensor.__class__.__name__,
                        score=0.0,
                        confidence=0.0,
                        status="error",
                        explanation=f"Erro interno no sensor: {str(e)}",
                    )
                )

        # 2. Agregação e Ensemble
        agg = aggregate_scores(sensor_results)

        # 3. Classificação
        alert = classify_alert_level(agg["final_risk_score"])
        regime = classify_regime(
            agg["final_risk_score"],
            agg["bubble_risk_score"],
            agg["liquidity_stress_score"],
        )

        # 4. Monta Relatório Parcial
        report = CrisisReport(
            systemic_risk_score=agg["systemic_risk_score"],
            bubble_risk_score=agg["bubble_risk_score"],
            liquidity_stress_score=agg["liquidity_stress_score"],
            credit_fragility_score=agg["credit_fragility_score"],
            final_risk_score=agg["final_risk_score"],
            regime=regime,
            alert_level=alert,
            confidence=agg["confidence"],
            sensor_results=sensor_results,
            summary="",
            recommendations=[],
            limitations=get_default_limitations(),
        )

        # 5. Adiciona sumário explicativo
        report.summary = build_crisis_summary(report)

        # 6. Dispara notificações se necessário
        alert_notifier = self._get_notifier()
        if report.alert_level == "black":
            alert_notifier.send_alert(
                f"CRISE SISTÊMICA DETECTADA: {report.summary}", level="BLACK"
            )
        elif report.alert_level == "red":
            alert_notifier.send_alert(
                "Risco sistêmico elevado detectado.", level="CRITICAL"
            )

        return report
