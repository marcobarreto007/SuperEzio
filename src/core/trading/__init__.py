"""SuperEzio trading module: risk management, order execution, position control.

This module is isolated from automatic execution. Any integration with a
broker requires an explicit Money Gate decision.
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
from .expert_weights import ExpertRecord, ExpertWeightRouter
from .kill_switch import KillSwitch, KillSwitchReason, KillSwitchState
from .order_builder import BracketOrder, OrderBuilder
from .position_sizer import PositionSize, PositionSizer
from .reward import RewardComponents, RewardFunction, TradeOutcome

__all__ = [
    "AlpacaPaperAdapter",
    "ApprovalGate",
    "ApprovalRequest",
    "ApprovalStatus",
    "BracketOrder",
    "BrokerAdapter",
    "EmailAlerter",
    "EmailConfig",
    "ExpertRecord",
    "ExpertWeightRouter",
    "GateConfig",
    "KillSwitch",
    "KillSwitchReason",
    "KillSwitchState",
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
    "SimulatedBroker",
    "TradeOutcome",
]
