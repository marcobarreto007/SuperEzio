"""SuperEzio trading module â€” risk management, order execution, position control.

Runtime note:`r`n    This module is exercised by tests/test_trading_loop{1-5}.py and remains`r`n    isolated from automatic execution. Integration requires an explicit Money`r`n    Gate decision.
"""

from .alerter import EmailAlerter, EmailConfig, LogAlerter
from .approval_gate import ApprovalGate, ApprovalRequest, ApprovalStatus, GateConfig
from .broker import (
    AlpacaPaperAdapter,
    BrokerAdapter,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    SimulatedBroker,
)
from .dataset import DatasetBuilder, SFTExample
from .expert_weights import ExpertRecord, ExpertWeightRouter
from .kill_switch import KillSwitch, KillSwitchReason, KillSwitchState
from .order_builder import BracketOrder, OrderBuilder
from .position_sizer import PositionSize, PositionSizer
from .reward import RewardComponents, RewardFunction, TradeOutcome
from .training import LoRATrainer, TrainingConfig, TrainingResult

__all__ = [
    "AlpacaPaperAdapter",
    "ApprovalGate",
    "ApprovalRequest",
    "ApprovalStatus",
    "BracketOrder",
    "BrokerAdapter",
    "DatasetBuilder",
    "EmailAlerter",
    "EmailConfig",
    "ExpertRecord",
    "ExpertWeightRouter",
    "GateConfig",
    "KillSwitch",
    "KillSwitchReason",
    "KillSwitchState",
    "LoRATrainer",
    "LogAlerter",
    "Order",
    "OrderBuilder",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionSize",
    "PositionSizer",
    "RewardComponents",
    "RewardFunction",
    "SFTExample",
    "SimulatedBroker",
    "TradeOutcome",
    "TrainingConfig",
    "TrainingResult",
]
