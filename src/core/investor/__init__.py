"""
core.investor — Family Investor Mode
=====================================
Submódulos:
  - committee      : InvestorCommittee (7 agentes com evidencias)
  - cost_guard     : CostGuard (orçamento diário)
  - storage        : InvestorStorage (SQLite)
  - prompts        : Prompts dos 7 agentes
  - fraud_memory   : FraudManipulationMemory (base local de padrões)
  - fraud_analyst  : FraudPatternAnalyst (detecção de red flags)

Nota: ``FakeDeepSeekProvider`` era um stub de teste e não faz parte da API
pública. Em testes, injete um stub local com método ``chat_completion``.
"""

from .committee import InvestorCommittee, AI_ANALYSIS_NOTICE
from .cost_guard import CostGuard, get_cost_guard
from .fraud_analyst import FraudPatternAnalyst
from .fraud_memory import FraudManipulationMemory, get_fraud_memory
from .storage import InvestorStorage, get_investor_storage

__all__ = [
    "InvestorCommittee",
    "AI_ANALYSIS_NOTICE",
    "CostGuard",
    "get_cost_guard",
    "FraudPatternAnalyst",
    "FraudManipulationMemory",
    "get_fraud_memory",
    "InvestorStorage",
    "get_investor_storage",
]
