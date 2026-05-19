"""
core.investor — Family Investor Mode
=====================================
Submódulos:
  - committee      : InvestorCommittee (7 agentes com evidencias) — DEPRECATED
  - cost_guard     : CostGuard (orçamento diário) — ACTIVE (used in agent_server)
  - storage        : InvestorStorage (SQLite) — DEPRECATED
  - prompts        : Prompts dos 7 agentes — DEPRECATED
  - fraud_memory   : FraudManipulationMemory (base local de padrões) — DEPRECATED
  - fraud_analyst  : FraudPatternAnalyst (detecção de red flags) — DEPRECATED

Deprecated items are disconnected from the production pipeline.
Only CostGuard remains active. Integration planned for Money Gate F4.

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
