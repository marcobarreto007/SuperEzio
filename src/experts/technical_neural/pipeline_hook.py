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
        response = hub.get_candles(ticker, timeframe="6M")
        if "error" in response:
            return {
                "ticker": ticker,
                "neural_score": 0.5,
                "verdict": "WAIT",
                "confidence": 0.0,
                "error": response["error"],
                "source": "technical_neural"
            }
            
        data = response.get("data") or response.get("candles") or []
    except Exception as e:
        logger.error(f"Erro ao buscar candles para o Neural Expert: {e}")
        return {
            "ticker": ticker,
            "neural_score": 0.5,
            "verdict": "WAIT",
            "confidence": 0.0,
            "error": "Falha na coleta histórica",
            "source": "technical_neural"
        }
        
    # 2. Instanciar e avaliar
    expert = TechnicalNeuralExpert()
    result = expert.evaluate(ticker, data)
    result["ticker"] = ticker
    return result

async def run_technical_neural_analysis(ticker: str) -> Dict[str, Any]:
    """Wrapper assíncrono para ser chamado no grafo."""
    return await asyncio.to_thread(analyze_technical_neural_sync, ticker)
