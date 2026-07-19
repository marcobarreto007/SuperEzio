"""
Technical Neural Pipeline Hook
==============================
Funções assíncronas para conectar o Neural Expert no pipeline SuperEzio.
"""

import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def analyze_technical_neural_sync(ticker: str) -> Dict[str, Any]:
    """
    Função síncrona que puxa os candles via DataHub e aciona o Neural Expert.
    """
    from dotenv import load_dotenv

    load_dotenv()

    from data.data_hub import hub
    from .expert.neural_expert import TechnicalNeuralExpert

    try:
        # One year is the shortest supported provider window that normally leaves
        # enough observations for four chronological partitions plus leakage gaps.
        response = hub.get_candles(ticker, timeframe="1Y")
        if "error" in response:
            return {
                "ticker": ticker,
                "status": "insufficient_data",
                "decision": "ABSTAIN",
                "direction_prob": {},
                "calibration_status": "unavailable",
                "skill_status": "unqualified",
                "model_id": None,
                "as_of": None,
                "horizon": {"bars": 1},
                "reason_codes": ["CANDLE_COLLECTION_FAILED"],
                "confidence": 0.0,
                "error": response["error"],
                "source": "technical_neural",
            }

        data = response.get("data") or response.get("candles") or []
    except Exception as e:
        logger.error(f"Erro ao buscar candles para o Neural Expert: {e}")
        return {
            "ticker": ticker,
            "status": "error",
            "decision": "ABSTAIN",
            "direction_prob": {},
            "calibration_status": "unavailable",
            "skill_status": "unqualified",
            "model_id": None,
            "as_of": None,
            "horizon": {"bars": 1},
            "reason_codes": ["CANDLE_COLLECTION_FAILED"],
            "confidence": 0.0,
            "error": "Falha na coleta histórica",
            "source": "technical_neural",
        }

    # 2. Instanciar e avaliar
    expert = TechnicalNeuralExpert()
    result = expert.evaluate(ticker, data)
    result["ticker"] = ticker
    return result


async def run_technical_neural_analysis(ticker: str) -> Dict[str, Any]:
    """Wrapper assíncrono para ser chamado no grafo."""
    return await asyncio.to_thread(analyze_technical_neural_sync, ticker)
