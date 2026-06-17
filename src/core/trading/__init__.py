"""SuperEzio trading module: risk management, order execution, position control.

This module is isolated from automatic execution. Any integration with a
broker requires an explicit Money Gate decision.

Autonomous trading (Phase 5):
- TradingEngine: Core autonomous trading brain
- AutonomousLoop: 24/7 continuous operation
- RiskGuard: Protects against excesses
- PositionManager: Tracks open/closed positions
- AutoExecutor: Orchestrates all gates
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
from .auto_executor import AutoExecutor, ExecutorConfig, ExecutionStatus, get_auto_executor
from .autonomous_loop import AutonomousLoop, run_autonomous_loop
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
from .broker_reconciler import BrokerReconciler, BrokerReconciliationReport, ReconciliationIssue
from .daily_cycle import DailyCycle
from .expert_weights import ExpertRecord, ExpertWeightRouter
from .kill_switch import KillSwitch, KillSwitchReason, KillSwitchState
from .order_builder import BracketOrder, OrderBuilder
from .position_manager import (
    ExitReason,
    PositionManager,
    PositionSide,
    PositionStatus,
    PositionSummary,
    get_position_manager,
)
from .position_sizer import PositionSize, PositionSizer
from .reward import RewardComponents, RewardFunction, TradeOutcome
from .risk_guard import (
    RiskGuard,
    RiskGuardResult,
    RiskLevel,
    RiskLimits,
    ViolationType,
    get_risk_guard,
)
from .trading_engine import MarketSentiment, TradingEngine, TradingOpportunity, TradingSession, get_trading_engine
from .trading_engine_live import LiveTradingEngine, get_live_trading_engine

__all__ = [
    # Autonomous trading (Phase 5)
    "TradingEngine",
    "get_trading_engine",
    "LiveTradingEngine",
    "get_live_trading_engine",
    "AutonomousLoop",
    "run_autonomous_loop",
    "MarketSentiment",
    "TradingOpportunity",
    "TradingSession",
    # Risk & Execution (Phase 4)
    "AutoExecutor",
    "get_auto_executor",
    "ExecutorConfig",
    "ExecutionStatus",
    "PositionManager",
    "get_position_manager",
    "PositionSide",
    "ExitReason",
    "PositionStatus",
    "PositionSummary",
    "RiskGuard",
    "get_risk_guard",
    "RiskGuardResult",
    "RiskLevel",
    "RiskLimits",
    "ViolationType",
    # Original components
    "AlpacaPaperAdapter",
    "ApprovalGate",
    "ApprovalRequest",
    "ApprovalStatus",
    "approval_request_to_dict",
    "BracketOrder",
    "BrokerAdapter",
    "BrokerReconciler",
    "BrokerReconciliationReport",
    "DailyCycle",
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
    "OrderBuilder",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionSize",
    "PositionSizer",
    "RewardComponents",
    "RewardFunction",
    "ReconciliationIssue",
    "SimulatedBroker",
    "TradeOutcome",
]
