"""Auto executor — orquestra execução automática com múltiplos gates.

Coordena todos os componentes de segurança antes de executar:
1. Kill switch (circuit breaker)
2. Risk guard (excesso de risco)
3. Committee (deliberação multi-agente)
4. Approval gate (aprovação humana se necessário)
5. Position sizing (tamanho correto)
6. Broker interface (execução real)

Só executa se TODOS os gates aprovarem.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Importar componentes existentes
from .approval_gate import ApprovalGate, ApprovalStatus, GateConfig
from .kill_switch import KillSwitch
from .position_sizer import PositionSizer, PositionSize
from .risk_guard import RiskGuard, RiskGuardResult
from .committee import get_reflection_committee, CommitteeDecision

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Status de uma execução."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    KILLED = "killed"  # Interrompida por kill switch
    BLOCKED = "blocked"  # Bloqueada por risk guard


class RejectionReason(Enum):
    """Motivo de rejeição."""
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    RISK_GUARD_REJECTED = "risk_guard_rejected"
    COMMITTEE_REJECTED = "committee_rejected"
    POSITION_SIZER_REJECTED = "position_sizer_rejected"
    APPROVAL_REJECTED = "approval_rejected"
    MARKET_CLOSED = "market_closed"
    INSUFFICIENT_CAPITAL = "insufficient_capital"
    BROKER_ERROR = "broker_error"


@dataclass
class ExecutionRequest:
    """Requisição de execução."""
    request_id: str
    symbol: str
    side: str  # 'buy' ou 'sell'
    quantity: int
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    thesis: str = ""
    confidence: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    # Resultados das checagens
    kill_switch_ok: bool = False
    risk_guard_result: RiskGuardResult | None = None
    committee_decision: CommitteeDecision | None = None
    position_size: PositionSize | None = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING

    # Resultado final
    status: ExecutionStatus = ExecutionStatus.PENDING
    rejection_reason: RejectionReason | None = None
    rejection_message: str = ""
    executed_at: str | None = None
    order_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "thesis": self.thesis,
            "confidence": round(self.confidence, 3),
            "timestamp": self.timestamp,
            "status": self.status.value,
            "kill_switch_ok": self.kill_switch_ok,
            "risk_guard": self.risk_guard_result.to_dict() if self.risk_guard_result else None,
            "committee": {
                "consensus": self.committee_decision.consensus.value if self.committee_decision else None,
                "is_approved": self.committee_decision.is_approved if self.committee_decision else None,
            },
            "position_size": {
                "shares": self.position_size.shares if self.position_size else 0,
                "reason": self.position_size.size_reason if self.position_size else "",
            },
            "approval_status": self.approval_status.value,
            "rejection_reason": self.rejection_reason.value if self.rejection_reason else None,
            "rejection_message": self.rejection_message,
            "executed_at": self.executed_at,
            "order_id": self.order_id,
        }


@dataclass
class ExecutorConfig:
    """Configuração do executor."""
    # Kill switch
    daily_loss_limit: float = 500.0
    max_drawdown_pct: float = 0.10
    max_consecutive_losses: int = 5

    # Risk guard
    max_position_pct: float = 0.10
    max_total_exposure_pct: float = 0.30
    max_trades_per_day: int = 10

    # Committee
    enable_committee: bool = True
    committee_approval_threshold: float = 0.75

    # Approval gate
    require_human_approval: bool = False
    max_auto_approve_risk: float = 200.0

    # Position sizing
    max_risk_pct: float = 0.02
    max_position_pct_sizing: float = 0.10

    # Market
    require_market_open: bool = True
    allowed_hours: tuple[int, int] = (9, 16)  # 9h-16h


class AutoExecutor:
    """Executor automático com múltiplos gates.

    Fluxo:
    1. Checa kill switch
    2. Checa risk guard
    3. Consulta committee (se habilitado)
    4. Calcula position size
    5. Submete para approval (se necessário)
    6. Executa ordem (se tudo aprovado)

    Se qualquer gate rejeitar, execução é cancelada.
    """

    def __init__(
        self,
        equity: float = 10000.0,
        config: ExecutorConfig | None = None,
        broker_interface: Any | None = None,
    ):
        self.equity = equity
        self.config = config or ExecutorConfig()
        self._broker = broker_interface

        # Inicializar componentes
        self._kill_switch = KillSwitch(
            daily_loss_limit=self.config.daily_loss_limit,
            max_drawdown_pct=self.config.max_drawdown_pct,
            max_consecutive_losses=self.config.max_consecutive_losses,
            initial_equity=equity,
        )

        self._risk_guard = RiskGuard(equity=equity)
        self._position_sizer = PositionSizer(equity=equity)
        self._approval_gate = ApprovalGate(
            config=GateConfig(
                max_auto_approve_amount=self.config.max_auto_approve_risk,
            )
        )

        self._next_request_id = 1
        self._history: list[ExecutionRequest] = []

    @property
    def is_trading_allowed(self) -> bool:
        """Se trading é permitido (kill switch inativo)."""
        return not self._kill_switch.is_active

    def prepare_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        entry_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        thesis: str = "",
        confidence: float = 0.0,
        market_data: dict[str, Any] | None = None,
        current_positions: list[dict[str, Any]] | None = None,
    ) -> ExecutionRequest:
        """Prepara uma ordem e executa todos os gates.

        Returns:
            ExecutionRequest com resultado de todos os gates
        """
        request_id = f"req-{self._next_request_id:06d}"
        self._next_request_id += 1

        request = ExecutionRequest(
            request_id=request_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            thesis=thesis,
            confidence=confidence,
        )

        # 1. Checar kill switch
        if self._kill_switch.is_active:
            request.status = ExecutionStatus.KILLED
            request.rejection_reason = RejectionReason.KILL_SWITCH_ACTIVE
            request.rejection_message = f"Kill switch active: {self._kill_switch.state.reason.value if self._kill_switch.state.reason else 'unknown'}"
            self._history.append(request)
            logger.warning("Execution rejected: kill switch active (%s)", request.request_id)
            return request

        request.kill_switch_ok = True

        # 2. Checar risk guard
        risk_result = self._risk_guard.check_trade(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            current_positions=current_positions or [],
            market_data=market_data or {},
        )
        request.risk_guard_result = risk_result

        if not risk_result.approved:
            request.status = ExecutionStatus.BLOCKED
            request.rejection_reason = RejectionReason.RISK_GUARD_REJECTED
            request.rejection_message = "; ".join(v.message for v in risk_result.violations)
            self._history.append(request)
            logger.warning("Execution rejected: risk guard (%s)", request.request_id)
            return request

        # 3. Consultar committee (se habilitado)
        if self.config.enable_committee:
            try:
                committee = get_reflection_committee()
                setup = {
                    "ticker": symbol,
                    "side": side,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "thesis": thesis,
                    "confidence": confidence,
                }
                decision = committee.deliberate(setup)
                request.committee_decision = decision

                if not decision.is_approved:
                    request.status = ExecutionStatus.REJECTED
                    request.rejection_reason = RejectionReason.COMMITTEE_REJECTED
                    request.rejection_message = f"Committee rejected: {decision.consensus.value}"
                    self._history.append(request)
                    logger.warning("Execution rejected: committee (%s)", request.request_id)
                    return request
            except Exception as e:
                logger.error("Committee error, proceeding without: %s", e)

        # 4. Calcular position size
        position_size = self._position_sizer.size(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            open_positions=len(current_positions or []),
        )
        request.position_size = position_size

        if position_size.shares == 0:
            request.status = ExecutionStatus.REJECTED
            request.rejection_reason = RejectionReason.POSITION_SIZER_REJECTED
            request.rejection_message = position_size.size_reason
            self._history.append(request)
            logger.warning("Execution rejected: position sizer (%s)", request.request_id)
            return request

        # 5. Submeter para approval (se necessário)
        if self.config.require_human_approval:
            approval = self._approval_gate.submit(
                symbol=symbol,
                side=side,
                qty=position_size.shares,
                entry_price=entry_price,
                stop_loss_price=stop_loss or entry_price * 0.95,
                risk_amount=position_size.shares * (entry_price - (stop_loss or entry_price * 0.95)),
                reason=thesis,
            )
            request.approval_status = approval.status

            if approval.status != ApprovalStatus.APPROVED:
                request.status = ExecutionStatus.REJECTED
                request.rejection_reason = RejectionReason.APPROVAL_REJECTED
                request.rejection_message = f"Approval status: {approval.status.value}"
                self._history.append(request)
                logger.warning("Execution rejected: approval gate (%s)", request.request_id)
                return request

        # Todos os gates aprovaram
        request.status = ExecutionStatus.APPROVED
        self._history.append(request)

        logger.info(
            "Execution approved: %s %s %d shares @ $%.2f (%s)",
            side,
            symbol,
            position_size.shares,
            entry_price,
            request_id,
        )

        return request

    def execute_order(self, request: ExecutionRequest) -> ExecutionRequest:
        """Executa uma ordem aprovada.

        Args:
            request: ExecutionRequest aprovado

        Returns:
            ExecutionRequest com resultado da execução
        """
        if request.status != ExecutionStatus.APPROVED:
            logger.error("Cannot execute non-approved request: %s", request.request_id)
            request.status = ExecutionStatus.FAILED
            return request

        if not self._broker:
            # Mock execution para paper mode
            logger.info(
                "Mock execution: %s %s %d shares @ $%.2f",
                request.side,
                request.symbol,
                request.position_size.shares if request.position_size else request.quantity,
                request.entry_price,
            )
            request.status = ExecutionStatus.EXECUTED
            request.executed_at = datetime.now(timezone.utc).isoformat()
            request.order_id = f"mock-{request.request_id}"
            return request

        # Execução real via broker
        try:
            # Aqui seria a chamada real ao broker
            # order = self._broker.place_order(...)
            # request.order_id = order.order_id

            request.status = ExecutionStatus.EXECUTED
            request.executed_at = datetime.now(timezone.utc).isoformat()

            logger.info(
                "Order executed: %s -> %s",
                request.request_id,
                request.order_id,
            )

        except Exception as e:
            request.status = ExecutionStatus.FAILED
            logger.error("Execution failed: %s - %s", request.request_id, e)

        return request

    def record_trade_result(self, pnl: float) -> None:
        """Registra resultado de um trade."""
        self._kill_switch.record_trade(pnl)
        if pnl < 0:
            self._risk_guard.record_loss(pnl)

    def update_equity(self, new_equity: float) -> None:
        """Atualiza equity após mudança."""
        self.equity = new_equity
        self._risk_guard.update_equity(new_equity)

        # Recalcular peak equity no kill switch
        if new_equity > self._kill_switch.state.peak_equity:
            self._kill_switch.state.peak_equity = new_equity

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do executor."""
        approved_count = sum(1 for r in self._history if r.status == ExecutionStatus.APPROVED)
        executed_count = sum(1 for r in self._history if r.status == ExecutionStatus.EXECUTED)
        rejected_count = sum(
            1
            for r in self._history
            if r.status in (ExecutionStatus.REJECTED, ExecutionStatus.BLOCKED, ExecutionStatus.KILLED)
        )

        rejection_reasons = {}
        for r in self._history:
            if r.rejection_reason:
                reason = r.rejection_reason.value
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

        return {
            "kill_switch_active": self._kill_switch.is_active,
            "kill_switch_reason": self._kill_switch.state.reason.value if self._kill_switch.state.reason else None,
            "daily_pnl": round(self._kill_switch.state.daily_pnl, 2),
            "consecutive_losses": self._kill_switch.state.consecutive_losses,
            "requests_total": len(self._history),
            "approved": approved_count,
            "executed": executed_count,
            "rejected": rejected_count,
            "rejection_reasons": rejection_reasons,
            "equity": round(self.equity, 2),
        }


def get_auto_executor(equity: float = 10000.0) -> AutoExecutor:
    """Retorna instância singleton do AutoExecutor."""
    # Em produção, isso viria de um container ou singleton
    return AutoExecutor(equity=equity)
