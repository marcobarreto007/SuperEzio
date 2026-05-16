"""Order builder — translates trade decisions into broker orders."""

from __future__ import annotations

from dataclasses import dataclass

from .broker import Order, OrderSide, OrderStatus, OrderType
from .position_sizer import PositionSize


@dataclass(frozen=True)
class BracketOrder:
    """A bracket order: entry + stop-loss + take-profit."""

    entry: Order
    stop_loss: Order | None = None
    take_profit: Order | None = None
    size: PositionSize | None = None
    reason: str = ""


class OrderBuilder:
    """Builds orders from trade signals and position sizes.

    Supports:
    - Market orders (immediate execution)
    - Bracket orders (entry + SL + TP)
    - Small position orders (conservative sizing)
    """

    def __init__(
        self,
        default_slippage_pct: float = 0.001,
        default_take_profit_ratio: float = 2.0,
    ):
        self.default_slippage_pct = default_slippage_pct
        self.default_take_profit_ratio = default_take_profit_ratio

    def build_market_order(
        self,
        symbol: str,
        side: OrderSide,
        size: PositionSize,
        reason: str = "",
    ) -> Order | None:
        if size.shares <= 0:
            return None

        return Order(
            id="pending",
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            qty=size.shares,
            status=OrderStatus.PENDING,
        )

    def build_bracket_order(
        self,
        symbol: str,
        side: OrderSide,
        size: PositionSize,
        take_profit_price: float | None = None,
        reason: str = "",
    ) -> BracketOrder | None:
        if size.shares <= 0:
            return None

        entry_price = size.notional_value / size.shares
        slippage = entry_price * self.default_slippage_pct

        if side == OrderSide.BUY:
            entry = Order(
                id="pending",
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                qty=size.shares,
                status=OrderStatus.PENDING,
            )
            stop_loss = Order(
                id="pending_sl",
                symbol=symbol,
                side=OrderSide.SELL,
                order_type=OrderType.STOP,
                qty=size.shares,
                status=OrderStatus.PENDING,
                stop_price=round(size.stop_loss_price - slippage, 4),
            )
            if take_profit_price is None:
                risk = entry_price - size.stop_loss_price
                take_profit_price = entry_price + risk * self.default_take_profit_ratio
            take_profit = Order(
                id="pending_tp",
                symbol=symbol,
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                qty=size.shares,
                status=OrderStatus.PENDING,
                limit_price=round(take_profit_price + slippage, 4),
            )
        else:
            entry = Order(
                id="pending",
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                qty=size.shares,
                status=OrderStatus.PENDING,
            )
            stop_loss = Order(
                id="pending_sl",
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.STOP,
                qty=size.shares,
                status=OrderStatus.PENDING,
                stop_price=round(size.stop_loss_price + slippage, 4),
            )
            if take_profit_price is None:
                risk = size.stop_loss_price - entry_price
                take_profit_price = entry_price - risk * self.default_take_profit_ratio
            take_profit = Order(
                id="pending_tp",
                symbol=symbol,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                qty=size.shares,
                status=OrderStatus.PENDING,
                limit_price=round(take_profit_price - slippage, 4),
            )

        return BracketOrder(
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size=size,
            reason=reason or size.size_reason,
        )
