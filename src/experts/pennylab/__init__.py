"""
PennyLab / WhaleTrap Lab
=========================
F51 — Laboratório CLI para penny stocks e detecção de baleias.

Uso pessoal/laboratório. NÃO executa ordens.
Python calcula. RAG lembra. Experts investigam. LLM orquestra. Marco decide.
"""

from .lab_journal import journal
from .schemas import Decision, PennylabReport, PennylabScores, SignalInput, TradeLog
from .scoring import analyze

__all__ = [
    "Decision",
    "PennylabReport",
    "PennylabScores",
    "SignalInput",
    "TradeLog",
    "analyze",
    "journal",
]

__version__ = "0.1.0"
