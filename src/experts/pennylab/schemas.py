"""
PennyLab / WhaleTrap Lab — Schemas
===================================
Contratos de dados para o módulo. Nenhum dado é fabricado aqui;
todos os campos opcionais refletem ausência de provedor real conectado.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Decision(str, Enum):
    BULLISH = "BULLISH"  # setup limpo, risco controlado — sinal verde
    BEARISH = "BEARISH"  # risco elevado, evitar entrada
    WATCH_ONLY = "WATCH_ONLY"  # dados insuficientes ou neutro
    PAPER_TRADE = "PAPER_TRADE"  # baleia suspeita, testar em paper
    MICRO_ENTRY = "MICRO_ENTRY"  # seguir baleia com posição mínima
    NO_TRADE = "NO_TRADE"  # armadilha, liquidez ou gate bloqueou
    EXIT_NOW = "EXIT_NOW"  # posição existente: sair imediatamente
    POST_MORTEM = "POST_MORTEM"  # análise post mortem


class DataQuality(str, Enum):
    REAL = "real"  # dado real de provedor conectado
    MANUAL = "manual"  # entrada manual via --input JSON
    UNAVAILABLE = "unavailable"  # sem dado — não fabrica nada


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


class SignalInput(BaseModel):
    """Dados de mercado para um ticker. Todos os campos são opcionais
    para refletir provedores não conectados. O sistema decide com o que tem."""

    ticker: str = Field(..., description="Símbolo do ativo (ex: ABCD, SNDL)")

    # Preço / volume
    price: Optional[float] = None  # último preço
    prev_close: Optional[float] = None
    volume: Optional[int] = None  # volume do dia
    avg_volume_10d: Optional[int] = None  # média 10 dias
    market_cap: Optional[float] = None  # em USD

    # Spread / liquidez
    bid: Optional[float] = None
    ask: Optional[float] = None
    shares_float: Optional[int] = None  # ações em circulação

    # Técnicos simples
    rsi_14: Optional[float] = None
    ema_20: Optional[float] = None

    # Metadados de origem
    data_quality: DataQuality = DataQuality.UNAVAILABLE
    source: str = "manual"
    as_of: Optional[str] = None  # ISO timestamp

    # Evidências adicionais (mensagens de fórum, alertas, etc.)
    external_signals: List[str] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------


class PennylabScores(BaseModel):
    """Scores normalizados 0-1."""

    whale_suspicion: float = Field(0.0, ge=0.0, le=1.0)
    pump_probability: float = Field(0.0, ge=0.0, le=1.0)
    trap_risk: float = Field(0.0, ge=0.0, le=1.0)
    liquidity_risk: float = Field(0.0, ge=0.0, le=1.0)
    expected_loss: float = Field(0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Report principal
# ---------------------------------------------------------------------------


class PennylabReport(BaseModel):
    ticker: str
    decision: Decision
    scores: PennylabScores
    mathcore_verdict: str = ""
    evidence: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    entry_conditions: List[str] = Field(default_factory=list)
    exit_conditions: List[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    data_quality: DataQuality = DataQuality.UNAVAILABLE
    veracity_passed: bool = True
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = ConfigDict(use_enum_values=True)


# ---------------------------------------------------------------------------
# Lab Journal (log de trades experimentais)
# ---------------------------------------------------------------------------


class TradeLog(BaseModel):
    """Registro de trade experimental — apenas paper/micro, nunca execução real."""

    ticker: str
    entry_price: float
    exit_price: Optional[float] = None
    size_usd: float = Field(..., description="Tamanho em USD")
    pnl_pct: Optional[float] = None
    note: str = ""
    is_paper: bool = True  # sempre True inicialmente
    logged_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    report_snapshot: Optional[Dict[str, Any]] = None  # snapshot do PennylabReport


# ---------------------------------------------------------------------------
# Scan request / result
# ---------------------------------------------------------------------------


class ScanFilter(BaseModel):
    max_price: Optional[float] = None
    min_volume: Optional[int] = None
    max_spread_pct: float = 5.0  # descarta se spread > X%


class ScanResult(BaseModel):
    filters: ScanFilter
    candidates: List[str] = Field(default_factory=list)
    skipped: int = 0
    note: str = "Nenhum provedor de scan conectado. Passe tickers manualmente."
