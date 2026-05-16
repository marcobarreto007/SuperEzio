"""SuperEzio trading module — risk management, order execution, position control."""

from .alerter import EmailAlerter, EmailConfig, LogAlerter
from .approval_gate import ApprovalGate, ApprovalRequest, ApprovalStatus, GateConfig
from .broker import (
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

__all__ = [
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
    "SimulatedBroker",
]
