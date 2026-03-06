"""
PennyLab Config — Thresholds e Paths
======================================
Centraliza constantes de decisão para facilitar ajuste sem mexer em lógica.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths de armazenamento
# ---------------------------------------------------------------------------
_BASE = Path(__file__).resolve().parent.parent.parent.parent  # raiz do repo

LAB_JOURNAL_PATH: Path = Path(
    os.environ.get("PENNYLAB_JOURNAL", str(_BASE / "data" / "pennylab_journal.jsonl"))
)


# ---------------------------------------------------------------------------
# Thresholds de decisão
# (ajuste sem mexer em scoring.py ou experts/)
# ---------------------------------------------------------------------------


class Thresholds:
    """Escala unificada: 0-1 (não 0-100)."""

    # ── Bloqueios (NO_TRADE) ──
    LIQUIDITY_NO_TRADE: float = 0.80
    TRAP_NO_TRADE: float = 0.80
    PUMP_NO_TRADE: float = 0.70

    # ── Sinal de compra (BULLISH) ──
    BULLISH_MAX_WHALE: float = 0.35
    BULLISH_MAX_PUMP: float = 0.25
    BULLISH_MAX_TRAP: float = 0.25
    BULLISH_MAX_LIQUIDITY: float = 0.25
    BULLISH_MAX_EXPECTED_LOSS: float = 0.15
    BULLISH_MIN_CONFIDENCE: float = 0.40

    # ── Sinal de venda/alerta (BEARISH) ──
    BEARISH_MIN_TRAP: float = 0.50
    BEARISH_MIN_EXPECTED_LOSS: float = 0.40

    # ── Seguir baleia (PAPER/MICRO) ──
    WHALE_PAPER: float = 0.70
    TRAP_SAFE: float = 0.60
    LIQUIDITY_SAFE: float = 0.60

    # ── Confidence mínima para não ser WATCH_ONLY ──
    MIN_REPORT_CONFIDENCE: float = 0.25


THRESHOLDS = Thresholds()


# ---------------------------------------------------------------------------
# Limites de tamanho de posição (APENAS referência de log, sem execução)
# ---------------------------------------------------------------------------
MAX_POSITION_USD: float = float(os.environ.get("PENNYLAB_MAX_USD", "50.0"))
MAX_PRICE_PENNY: float = float(os.environ.get("PENNYLAB_MAX_PRICE", "5.0"))
MIN_VOLUME_PENNY: int = int(os.environ.get("PENNYLAB_MIN_VOLUME", "500000"))
