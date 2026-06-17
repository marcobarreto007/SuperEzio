"""Position manager — gerenciamento de posições abertas.

Rastreia, gerencia e toma decisões sobre posições abertas:
- Entry e exit tracking
- Stop loss e take profit
- Trailing stops
- Position sizing dinâmico
- Decisões de exit baseadas em regras e mercado
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PositionSide(Enum):
    """Lado da posição."""
    LONG = "long"
    SHORT = "short"


class PositionStatus(Enum):
    """Status da posição."""
    PENDING_ENTRY = "pending_entry"
    OPEN = "open"
    PENDING_EXIT = "pending_exit"
    CLOSED = "closed"
    STOPPED = "stopped"  # Parado por stop loss
    TAKEN = "taken"  # Alvo atingido


class ExitReason(Enum):
    """Motivo de exit."""
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    MANUAL = "manual"
    TRAILING_STOP = "trailing_stop"
    SIGNAL_REVERSAL = "signal_reversal"
    RISK_LIMIT = "risk_limit"
    TIME_EXIT = "time_exit"


@dataclass
class Position:
    """Uma posição aberta."""
    position_id: str
    symbol: str
    side: PositionSide
    quantity: int
    entry_price: float
    entry_date: str
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop_pct: float = 0.0
    current_price: float = 0.0
    status: PositionStatus = PositionStatus.OPEN

    # Métricas
    entry_value: float = field(init=False)
    current_value: float = field(init=False)
    unrealized_pnl: float = field(init=False)
    unrealized_pnl_pct: float = field(init=False)

    # Exit
    exit_price: float | None = None
    exit_date: str | None = None
    exit_reason: ExitReason | None = None
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0

    # Metadados
    thesis: str = ""
    confidence_at_entry: float = 0.0
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.entry_value = self.quantity * self.entry_price
        self._update_metrics()

    def _update_metrics(self) -> None:
        """Atualiza métricas baseadas no preço atual."""
        self.current_value = self.quantity * self.current_price
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (self.current_price - self.entry_price) * self.quantity
            self.unrealized_pnl_pct = (
                (self.current_price - self.entry_price) / self.entry_price
                if self.entry_price > 0
                else 0
            )
        else:
            self.unrealized_pnl = (self.entry_price - self.current_price) * self.quantity
            self.unrealized_pnl_pct = (
                (self.entry_price - self.current_price) / self.entry_price
                if self.entry_price > 0
                else 0
            )

    def update_price(self, price: float) -> None:
        """Atualiza preço atual e recalcula métricas."""
        self.current_price = price
        self._update_metrics()

    def update_trailing_stop(self, high_water_mark: float) -> None:
        """Atualiza stop loss trailing."""
        if self.trailing_stop_pct > 0 and self.side == PositionSide.LONG:
            new_stop = high_water_mark * (1 - self.trailing_stop_pct)
            if self.stop_loss is None or new_stop > self.stop_loss:
                self.stop_loss = new_stop
                logger.debug(
                    "Trailing stop updated for %s: $%.2f -> $%.2f",
                    self.symbol,
                    self.stop_loss if self.stop_loss else 0,
                    new_stop,
                )

    def should_exit_stop_loss(self) -> bool:
        """Checa se deve sair por stop loss."""
        if self.stop_loss is None:
            return False
        if self.side == PositionSide.LONG:
            return self.current_price <= self.stop_loss
        else:
            return self.current_price >= self.stop_loss

    def should_exit_take_profit(self) -> bool:
        """Checa se deve sair por take profit."""
        if self.take_profit is None:
            return False
        if self.side == PositionSide.LONG:
            return self.current_price >= self.take_profit
        else:
            return self.current_price <= self.take_profit

    def close(
        self,
        exit_price: float,
        reason: ExitReason,
        timestamp: str | None = None,
    ) -> None:
        """Fecha a posição."""
        self.exit_price = exit_price
        self.exit_date = timestamp or datetime.now(timezone.utc).isoformat()
        self.exit_reason = reason

        # Calcular PnL realizado
        if self.side == PositionSide.LONG:
            self.realized_pnl = (exit_price - self.entry_price) * self.quantity
        else:
            self.realized_pnl = (self.entry_price - exit_price) * self.quantity

        self.realized_pnl_pct = (
            (exit_price - self.entry_price) / self.entry_price
            if self.entry_price > 0
            else 0
        )

        # Atualizar status
        if reason == ExitReason.STOP_LOSS:
            self.status = PositionStatus.STOPPED
        elif reason == ExitReason.TAKE_PROFIT:
            self.status = PositionStatus.TAKEN
        else:
            self.status = PositionStatus.CLOSED

        logger.info(
            "Position closed: %s %s %d shares @ $%.2f -> $%.2f (%s) PnL: $%.2f (%.1f%%)",
            self.side.value,
            self.symbol,
            self.quantity,
            self.entry_price,
            exit_price,
            reason.value,
            self.realized_pnl,
            self.realized_pnl_pct * 100,
        )

    def to_dict(self) -> dict[str, Any]:
        """Converte para dict."""
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "entry_date": self.entry_date,
            "current_price": self.current_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trailing_stop_pct": self.trailing_stop_pct,
            "status": self.status.value,
            "entry_value": self.entry_value,
            "current_value": self.current_value,
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct * 100, 2),
            "exit_price": self.exit_price,
            "exit_date": self.exit_date,
            "exit_reason": self.exit_reason.value if self.exit_reason else None,
            "realized_pnl": round(self.realized_pnl, 2),
            "realized_pnl_pct": round(self.realized_pnl_pct * 100, 2),
            "thesis": self.thesis,
            "confidence_at_entry": self.confidence_at_entry,
            "tags": self.tags,
        }


@dataclass
class PositionSummary:
    """Resumo de todas as posições."""
    total_positions: int
    total_value: float
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float
    largest_position_pct: float
    most_profitable: Position | None
    least_profitable: Position | None
    symbols: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_positions": self.total_positions,
            "total_value": round(self.total_value, 2),
            "total_unrealized_pnl": round(self.total_unrealized_pnl, 2),
            "total_unrealized_pnl_pct": round(self.total_unrealized_pnl_pct * 100, 2),
            "largest_position_pct": round(self.largest_position_pct * 100, 2),
            "most_profitable": {
                "symbol": self.most_profitable.symbol if self.most_profitable else "",
                "pnl": round(self.most_profitable.unrealized_pnl, 2) if self.most_profitable else 0,
            },
            "least_profitable": {
                "symbol": self.least_profitable.symbol if self.least_profitable else "",
                "pnl": round(self.least_profitable.unrealized_pnl, 2) if self.least_profitable else 0,
            },
            "symbols": self.symbols,
        }


class PositionManager:
    """Gerenciador de posições abertas.

    Funções:
    - Abrir novas posições
    - Atualizar preços
    - Checar stops (stop loss, take profit, trailing)
    - Fechar posições
    - Gerar resumos
    """

    def __init__(self, equity: float = 10000.0):
        self.equity = equity
        self._positions: dict[str, Position] = {}
        self._next_id = 1
        self._closed_positions: list[Position] = []

    @property
    def open_positions(self) -> list[Position]:
        """Retorna posições abertas."""
        return [p for p in self._positions.values() if p.status == PositionStatus.OPEN]

    @property
    def closed_positions(self) -> list[Position]:
        """Retorna posições fechadas."""
        return self._closed_positions.copy()

    def open_position(
        self,
        symbol: str,
        side: PositionSide,
        quantity: int,
        entry_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trailing_stop_pct: float = 0.0,
        thesis: str = "",
        confidence: float = 0.0,
        tags: list[str] | None = None,
    ) -> Position:
        """Abre uma nova posição."""
        position_id = f"pos-{self._next_id:06d}"
        self._next_id += 1

        position = Position(
            position_id=position_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            entry_date=datetime.now(timezone.utc).isoformat(),
            current_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_pct=trailing_stop_pct,
            thesis=thesis,
            confidence_at_entry=confidence,
            tags=tags or [],
        )

        self._positions[position_id] = position
        logger.info(
            "Position opened: %s %s %d shares @ $%.2f (ID: %s)",
            side.value,
            symbol,
            quantity,
            entry_price,
            position_id,
        )

        return position

    def get_position(self, position_id: str) -> Position | None:
        """Retorna posição por ID."""
        return self._positions.get(position_id)

    def get_positions_by_symbol(self, symbol: str) -> list[Position]:
        """Retorna posições por símbolo."""
        return [p for p in self._positions.values() if p.symbol == symbol]

    def update_position_price(
        self,
        position_id: str,
        current_price: float,
        update_trailing_stop: bool = True,
    ) -> None:
        """Atualiza preço de uma posição."""
        position = self._positions.get(position_id)
        if not position:
            logger.warning("Position not found: %s", position_id)
            return

        old_price = position.current_price
        position.update_price(current_price)

        # Atualizar trailing stop
        if update_trailing_stop and position.trailing_stop_pct > 0:
            if position.side == PositionSide.LONG and current_price > old_price:
                position.update_trailing_stop(current_price)
            elif position.side == PositionSide.SHORT and current_price < old_price:
                # Trailing stop para short (inverte a lógica)
                new_stop = current_price * (1 + position.trailing_stop_pct)
                if position.stop_loss is None or new_stop < position.stop_loss:
                    position.stop_loss = new_stop

    def check_exit_signals(self, position_id: str) -> list[str]:
        """Checa sinais de exit para uma posição. Retorna motivos de exit detectados."""
        position = self._positions.get(position_id)
        if not position:
            return []

        signals = []

        if position.should_exit_stop_loss():
            signals.append("stop_loss")

        if position.should_exit_take_profit():
            signals.append("take_profit")

        return signals

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: ExitReason,
    ) -> Position | None:
        """Fecha uma posição."""
        position = self._positions.get(position_id)
        if not position:
            logger.warning("Position not found: %s", position_id)
            return None

        position.close(exit_price, reason)
        self._closed_positions.append(position)

        logger.info(
            "Position %s closed at $%.2f (%s): PnL $%.2f (%.1f%%)",
            position_id,
            exit_price,
            reason.value,
            position.realized_pnl,
            position.realized_pnl_pct * 100,
        )

        return position

    def get_summary(self, equity: float | None = None) -> PositionSummary:
        """Retorna resumo das posições abertas."""
        equity = equity or self.equity
        open_pos = self.open_positions

        if not open_pos:
            return PositionSummary(
                total_positions=0,
                total_value=0.0,
                total_unrealized_pnl=0.0,
                total_unrealized_pnl_pct=0.0,
                largest_position_pct=0.0,
                most_profitable=None,
                least_profitable=None,
                symbols=[],
            )

        total_value = sum(p.current_value for p in open_pos)
        total_pnl = sum(p.unrealized_pnl for p in open_pos)

        most_profitable = max(open_pos, key=lambda p: p.unrealized_pnl)
        least_profitable = min(open_pos, key=lambda p: p.unrealized_pnl)

        largest_pos = max(open_pos, key=lambda p: p.current_value)
        largest_pct = largest_pos.current_value / equity if equity > 0 else 0

        symbols = sorted(set(p.symbol for p in open_pos))

        return PositionSummary(
            total_positions=len(open_pos),
            total_value=total_value,
            total_unrealized_pnl=total_pnl,
            total_unrealized_pnl_pct=total_pnl / equity if equity > 0 else 0,
            largest_position_pct=largest_pct,
            most_profitable=most_profitable,
            least_profitable=least_profitable,
            symbols=symbols,
        )

    def get_position_count_by_symbol(self, symbol: str) -> int:
        """Retorna número de posições para um símbolo."""
        return len([p for p in self.open_positions if p.symbol == symbol])

    def get_exposure_by_symbol(self, symbol: str) -> float:
        """Retorna exposição total para um símbolo."""
        positions = self.get_positions_by_symbol(symbol)
        return sum(p.current_value for p in positions if p.status == PositionStatus.OPEN)

    def to_dict(self) -> dict[str, Any]:
        """Converte estado para dict."""
        return {
            "open_positions": [p.to_dict() for p in self.open_positions],
            "closed_count": len(self._closed_positions),
            "summary": self.get_summary().to_dict(),
        }


def get_position_manager(equity: float = 10000.0) -> PositionManager:
    """Retorna instância singleton do PositionManager."""
    # Em produção, isso viria de um container ou singleton
    return PositionManager(equity=equity)
