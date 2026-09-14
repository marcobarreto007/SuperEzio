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
    requested_shares: int = 0
    capped: bool = False
    max_notional_value: float = 0.0


class PositionSizer:
    """Calculates position size based on account equity and risk parameters.

    Rules:
    - Default 1.5% of equity risked per trade (max_risk_pct=0.015), the top of
      the operator's mandate range of 1.0-1.5% per trade (CLAUDE.md rule 7,
      "Risco Maximo por Trade: 1.0% a 1.5% do equity" = $10-$15 CAD on $1,000).
      Subir de 2% para 1.5% alinha o dimensionamento ao teto do protocolo.
    - NOTE: this is NOT the Canada Money Gate limit. The gate uses
      settings.superezio_money_gate_max_risk_pct (default 0.5%, hard cap 2%)
      — see src/core/config/settings.py.
    - Max 3 concurrent open positions
    - Min position notional to avoid dust trades
    - Stop-loss distance determines share count
    """

    def __init__(
        self,
        equity: float,
        max_risk_pct: float = 0.015,
        max_position_pct: float = 0.10,
        max_open_positions: int = 3,
        min_notional: float = 50.0,
        default_stop_pct: float = 0.05,
    ):
        if equity <= 0:
            raise ValueError(f"Equity must be positive, got {equity}")
        if not 0 < max_risk_pct <= 0.1:
            raise ValueError(f"max_risk_pct must be in (0, 0.1], got {max_risk_pct}")
        if not 0 < max_position_pct <= 1.0:
            raise ValueError(f"max_position_pct must be in (0, 1.0], got {max_position_pct}")
        if max_open_positions < 1:
            raise ValueError(f"max_open_positions must be >= 1, got {max_open_positions}")

        self.equity = equity
        self.max_risk_pct = max_risk_pct
        self.max_position_pct = max_position_pct
        self.max_open_positions = max_open_positions
        self.min_notional = min_notional
        self.default_stop_pct = default_stop_pct

    @property
    def max_risk_amount(self) -> float:
        return self.equity * self.max_risk_pct

    @property
    def max_position_value(self) -> float:
        return self.equity * self.max_position_pct

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
                max_notional_value=self.max_position_value,
            )

        if stop_loss_price is None:
            stop_loss_price = entry_price * (1 - self.default_stop_pct)

        if stop_loss_price >= entry_price:
            raise ValueError(
                f"stop_loss_price ({stop_loss_price}) must be below entry_price ({entry_price})"
            )

        risk_per_share = entry_price - stop_loss_price
        max_shares_by_risk = int(self.max_risk_amount / risk_per_share)
        max_shares_by_position = int(self.max_position_value / entry_price)
        shares = max(0, min(max_shares_by_risk, max_shares_by_position))

        notional = shares * entry_price

        if notional < self.min_notional:
            return PositionSize(
                shares=0,
                notional_value=0.0,
                risk_per_share=risk_per_share,
                stop_loss_price=stop_loss_price,
                size_reason=f"notional {notional:.2f} below min {self.min_notional}",
                capped=max_shares_by_position < max_shares_by_risk,
                max_notional_value=self.max_position_value,
            )

        capped = max_shares_by_position < max_shares_by_risk
        cap_reason = (
            f"; capped by {self.max_position_pct * 100:.1f}% max position" if capped else ""
        )
        return PositionSize(
            shares=shares,
            notional_value=notional,
            risk_per_share=risk_per_share,
            stop_loss_price=stop_loss_price,
            size_reason=(
                f"{self.max_risk_pct * 100:.1f}% risk = R${self.max_risk_amount:.2f} "
                f"/ R${risk_per_share:.2f} risk/share{cap_reason}"
            ),
            capped=capped,
            max_notional_value=self.max_position_value,
        )
