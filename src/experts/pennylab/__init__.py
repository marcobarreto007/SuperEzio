"""
PennyLab / WhaleTrap Lab
=========================
F51 — Laboratório CLI para penny stocks e detecção de baleias.

Uso pessoal/laboratório. NÃO executa ordens.
Python calcula. RAG lembra. Experts investigam. LLM orquestra. Marco decide.
"""

from .schemas import SignalInput, PennylabReport, PennylabScores, TradeLog, Decision
from .scoring import analyze
from .lab_journal import journal

__all__ = [
    "SignalInput",
    "PennylabReport",
    "PennylabScores",
    "TradeLog",
    "Decision",
    "analyze",
    "journal",
]

__version__ = "0.1.0"
