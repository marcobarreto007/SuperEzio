"""SuperEzio trading module — risk management, order execution, position control.

.. deprecated::
    This entire module is disconnected from the production pipeline.
    Used only by tests/test_trading_loop{1-5}.py.
    Integration planned for Money Gate F4.
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
