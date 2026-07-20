"""SuperEzio trading module: risk management, order execution, position control.

This module is isolated from automatic execution. Any integration with a
broker requires an explicit Money Gate decision.

Wave 4 cleanup (2026-07-19): 23 dead modules removed (~8,500 LOC).
Only live modules re-exported below.
"""

from .alerter import EmailAlerter, EmailConfig, LogAlerter
from .approval_gate import (
    ApprovalGate,
    ApprovalRequest,
    ApprovalStatus,
    GateConfig,
    approval_request_to_dict,
    get_approval_gate,
)
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
from .position_sizer import PositionSize, PositionSizer
from .reward import RewardComponents, RewardFunction, TradeOutcome

__all__ = [
    "AlpacaPaperAdapter",
    "ApprovalGate",
    "ApprovalRequest",
    "ApprovalStatus",
    "approval_request_to_dict",
    "BrokerAdapter",
    "EmailAlerter",
    "EmailConfig",
    "ExpertRecord",
    "ExpertWeightRouter",
    "GateConfig",
    "get_approval_gate",
    "KillSwitch",
    "KillSwitchReason",
    "KillSwitchState",
    "LogAlerter",
    "Order",
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
