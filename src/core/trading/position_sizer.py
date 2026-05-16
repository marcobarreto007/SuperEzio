"""Position sizer — risk-based position sizing for SuperEzio trades."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionSize:
    shares: int
    notional_value: float
    risk_per_share: float
    stop_loss_price: float
    size_reason: str


class PositionSizer:
    """Calculates position size based on account equity and risk parameters.

    Rules:
    - Max 1-2% of equity risked per trade
    - Max 3 concurrent open positions
    - Min position notional to avoid dust trades
    - Stop-loss distance determines share count
    """

    def __init__(
        self,
        equity: float,
        max_risk_pct: float = 0.02,
        max_open_positions: int = 3,
        min_notional: float = 50.0,
        default_stop_pct: float = 0.05,
    ):
        if equity <= 0:
            raise ValueError(f"Equity must be positive, got {equity}")
        if not 0 < max_risk_pct <= 0.1:
            raise ValueError(f"max_risk_pct must be in (0, 0.1], got {max_risk_pct}")
        if max_open_positions < 1:
            raise ValueError(f"max_open_positions must be >= 1, got {max_open_positions}")

        self.equity = equity
        self.max_risk_pct = max_risk_pct
        self.max_open_positions = max_open_positions
        self.min_notional = min_notional
        self.default_stop_pct = default_stop_pct

    @property
    def max_risk_amount(self) -> float:
        return self.equity * self.max_risk_pct

    def can_open(self, open_positions: int) -> bool:
        return open_positions < self.max_open_positions

    def size(
        self,
        entry_price: float,
        stop_loss_price: float | None = None,
        open_positions: int = 0,
    ) -> PositionSize:
        if entry_price <= 0:
            raise ValueError(f"entry_price must be positive, got {entry_price}")

        if not self.can_open(open_positions):
            return PositionSize(
                shares=0,
                notional_value=0.0,
                risk_per_share=0.0,
                stop_loss_price=0.0,
                size_reason=f"max_open_positions={self.max_open_positions} reached",
            )

        if stop_loss_price is None:
            stop_loss_price = entry_price * (1 - self.default_stop_pct)

        if stop_loss_price >= entry_price:
            raise ValueError(
                f"stop_loss_price ({stop_loss_price}) must be below entry_price ({entry_price})"
            )

        risk_per_share = entry_price - stop_loss_price
        max_shares_by_risk = int(self.max_risk_amount / risk_per_share)
        shares = max(0, max_shares_by_risk)

        notional = shares * entry_price

        if notional < self.min_notional:
            return PositionSize(
                shares=0,
                notional_value=0.0,
                risk_per_share=risk_per_share,
                stop_loss_price=stop_loss_price,
                size_reason=f"notional {notional:.2f} below min {self.min_notional}",
            )

        return PositionSize(
            shares=shares,
            notional_value=notional,
            risk_per_share=risk_per_share,
            stop_loss_price=stop_loss_price,
            size_reason=f"{self.max_risk_pct*100:.1f}% risk = R${self.max_risk_amount:.2f} / R${risk_per_share:.2f} risk/share",
        )
