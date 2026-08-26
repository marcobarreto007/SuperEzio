"""
core.investor â€” Family Investor Mode
=====================================
SubmÃ³dulos:
  - cost_guard     : CostGuard (orÃ§amento diÃ¡rio; used in agent_server)
  - storage        : InvestorStorage (SQLite)
  - fraud_memory   : FraudManipulationMemory (base local de padrÃµes)
  - fraud_analyst  : FraudPatternAnalyst (detecÃ§Ã£o de red flags)

Only CostGuard is wired into the default server path. The other investor`r`ncomponents remain explicit-import modules and do not execute automatically.

Nota: ``FakeDeepSeekProvider`` era um stub de teste e nÃ£o faz parte da API
pÃºblica. Em testes, injete um stub local com mÃ©todo ``chat_completion``.
"""

from .cost_guard import CostGuard, get_cost_guard
from .fraud_analyst import FraudPatternAnalyst
from .fraud_memory import FraudManipulationMemory, get_fraud_memory
from .storage import InvestorStorage, get_investor_storage

__all__ = [
    "CostGuard",
    "FraudManipulationMemory",
    "FraudPatternAnalyst",
    "InvestorStorage",
    "get_cost_guard",
    "get_fraud_memory",
    "get_investor_storage",
]
