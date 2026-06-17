"""Risk guard — protection against excesses and dangerous patterns.

Previne:
- Exposição excessiva a um único ativo
- Alavancagem excessiva
- Trades muito grandes
- Padrões perigosos (overtrading, revenge trading)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Níveis de risco."""
    SAFE = "safe"
    CAUTION = "caution"
    DANGER = "danger"
    BLOCKED = "blocked"


class ViolationType(Enum):
    """Tipos de violação."""
    POSITION_SIZE_EXCEEDED = "position_size_exceeded"
    EXPOSURE_LIMIT_EXCEEDED = "exposure_limit_exceeded"
    LEVERAGE_TOO_HIGH = "leverage_too_high"
    OVERTRADING = "overtrading"
    REVENGE_TRADING = "revenge_trading"
    LIQUIDITY_TOO_LOW = "liquidity_too_low"
    GAP_RISK = "gap_risk"
    CONCENTRATION_RISK = "concentration_risk"


@dataclass
class RiskViolation:
    """Uma violação de risco detectada."""
    violation_type: ViolationType
    risk_level: RiskLevel
    message: str
    current_value: float | None = None
    limit_value: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    can_override: bool = False  # Se pode ser sobreposto manualmente

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_type": self.violation_type.value,
            "risk_level": self.risk_level.value,
            "message": self.message,
            "current_value": self.current_value,
            "limit_value": self.limit_value,
            "timestamp": self.timestamp,
            "can_override": self.can_override,
        }


@dataclass
class RiskLimits:
    """Limites de risco configuráveis."""
    # Tamanho de posição
    max_position_pct: float = 0.10  # Max 10% do equity em uma posição
    max_notional_per_trade: float = 5000.0  # Max notional por trade

    # Exposição
    max_total_exposure_pct: float = 0.30  # Max 30% do equity exposto
    max_same_asset_exposure_pct: float = 0.15  # Max 15% em um mesmo ativo

    # Alavancagem
    max_leverage: float = 1.0  # 1.0 = sem alavancagem

    # Liquidez
    min_avg_daily_volume: float = 1_000_000.0  # Min $1M volume diário

    # Padrões perigosos
    max_trades_per_day: int = 10
    max_trades_per_hour: int = 3
    revenge_trading_loss_threshold: float = -200.0  # Depois de perder $200, bloquear novos trades
    revenge_trading_cooldown_min: int = 30  # Minutos de cooldown

    # Gap risk
    max_gap_risk_pct: float = 0.03  # Max 3% gap risk (pre-market / after-hours)


@dataclass
class RiskGuardResult:
    """Resultado de uma checagem de risco."""
    approved: bool
    violations: list[RiskViolation] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.SAFE
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "risk_level": self.risk_level.value,
            "violations": [v.to_dict() for v in self.violations],
            "warnings": self.warnings,
        }


class RiskGuard:
    """Guarda de risco — protege contra excessos e padrões perigosos.

    Checa antes de cada trade:
    - Tamanho da posição
    - Exposição total
    - Concentração
    - Liquidez
    - Padrões perigosos (overtrading, revenge trading)
    """

    def __init__(
        self,
        limits: RiskLimits | None = None,
        equity: float = 10000.0,
    ):
        self.limits = limits or RiskLimits()
        self.equity = equity
        self._trade_history: list[dict[str, Any]] = []
        self._hourly_trade_counts: dict[str, int] = {}
        self._revenge_cooldown_until: float = 0.0

    def update_equity(self, new_equity: float) -> None:
        """Atualiza equity base."""
        if new_equity <= 0:
            raise ValueError(f"Equity must be positive, got {new_equity}")
        self.equity = new_equity

    def check_trade(
        self,
        symbol: str,
        side: str,
        quantity: int,
        entry_price: float,
        stop_loss: float | None = None,
        current_positions: list[dict[str, Any]] | None = None,
        market_data: dict[str, Any] | None = None,
    ) -> RiskGuardResult:
        """Checa se um trade é seguro.

        Args:
            symbol: Ticker
            side: 'buy' ou 'sell'
            quantity: Quantidade de ações
            entry_price: Preço de entrada
            stop_loss: Preço do stop loss
            current_positions: Posições abertas atuais
            market_data: Dados de mercado (volume, etc)

        Returns:
            RiskGuardResult com aprovação e violações
        """
        result = RiskGuardResult(approved=True)

        if quantity <= 0:
            result.approved = False
            result.violations.append(
                RiskViolation(
                    violation_type=ViolationType.POSITION_SIZE_EXCEEDED,
                    risk_level=RiskLevel.BLOCKED,
                    message=f"Quantity must be positive, got {quantity}",
                )
            )
            return result

        if entry_price <= 0:
            result.approved = False
            result.violations.append(
                RiskViolation(
                    violation_type=ViolationType.POSITION_SIZE_EXCEEDED,
                    risk_level=RiskLevel.BLOCKED,
                    message=f"Entry price must be positive, got {entry_price}",
                )
            )
            return result

        notional = quantity * entry_price
        position_pct = notional / self.equity if self.equity > 0 else 0

        # 1. Checar tamanho de posição
        if position_pct > self.limits.max_position_pct:
            result.approved = False
            result.risk_level = RiskLevel.DANGER
            result.violations.append(
                RiskViolation(
                    violation_type=ViolationType.POSITION_SIZE_EXCEEDED,
                    risk_level=RiskLevel.DANGER,
                    message=f"Position size {position_pct:.1%} exceeds limit {self.limits.max_position_pct:.1%}",
                    current_value=position_pct,
                    limit_value=self.limits.max_position_pct,
                    can_override=False,
                )
            )

        if notional > self.limits.max_notional_per_trade:
            result.approved = False
            result.risk_level = RiskLevel.DANGER
            result.violations.append(
                RiskViolation(
                    violation_type=ViolationType.POSITION_SIZE_EXCEEDED,
                    risk_level=RiskLevel.DANGER,
                    message=f"Notional ${notional:.2f} exceeds limit ${self.limits.max_notional_per_trade:.2f}",
                    current_value=notional,
                    limit_value=self.limits.max_notional_per_trade,
                    can_override=False,
                )
            )

        # 2. Checar exposição total
        current_positions = current_positions or []
        total_exposure = sum(p.get("quantity", 0) * p.get("avg_price", 0) for p in current_positions)
        total_exposure_with_new = total_exposure + notional
        total_exposure_pct = total_exposure_with_new / self.equity if self.equity > 0 else 0

        if total_exposure_pct > self.limits.max_total_exposure_pct:
            result.approved = False
            result.risk_level = RiskLevel.DANGER
            result.violations.append(
                RiskViolation(
                    violation_type=ViolationType.EXPOSURE_LIMIT_EXCEEDED,
                    risk_level=RiskLevel.DANGER,
                    message=f"Total exposure {total_exposure_pct:.1%} exceeds limit {self.limits.max_total_exposure_pct:.1%}",
                    current_value=total_exposure_pct,
                    limit_value=self.limits.max_total_exposure_pct,
                    can_override=False,
                )
            )

        # 3. Checar concentração
        same_asset_exposure = sum(
            p.get("quantity", 0) * p.get("avg_price", 0)
            for p in current_positions
            if p.get("symbol") == symbol
        )
        same_asset_exposure_with_new = same_asset_exposure + notional
        same_asset_pct = same_asset_exposure_with_new / self.equity if self.equity > 0 else 0

        if same_asset_pct > self.limits.max_same_asset_exposure_pct:
            result.approved = False
            result.risk_level = RiskLevel.DANGER
            result.violations.append(
                RiskViolation(
                    violation_type=ViolationType.CONCENTRATION_RISK,
                    risk_level=RiskLevel.DANGER,
                    message=f"Same asset exposure {same_asset_pct:.1%} for {symbol} exceeds limit {self.limits.max_same_asset_exposure_pct:.1%}",
                    current_value=same_asset_pct,
                    limit_value=self.limits.max_same_asset_exposure_pct,
                    can_override=False,
                )
            )

        # 4. Checar liquidez
        if market_data:
            avg_volume = market_data.get("avg_daily_volume", 0)
            if avg_volume < self.limits.min_avg_daily_volume:
                result.approved = False
                result.risk_level = RiskLevel.BLOCKED
                result.violations.append(
                    RiskViolation(
                        violation_type=ViolationType.LIQUIDITY_TOO_LOW,
                        risk_level=RiskLevel.BLOCKED,
                        message=f"Liquidity too low: avg daily volume ${avg_volume:,.0f} < ${self.limits.min_avg_daily_volume:,.0f}",
                        current_value=avg_volume,
                        limit_value=self.limits.min_avg_daily_volume,
                        can_override=False,
                    )
                )

        # 5. Checar overtrading
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%d-%H")
        day_key = now.strftime("%Y-%m-%d")

        self._hourly_trade_counts[hour_key] = self._hourly_trade_counts.get(hour_key, 0) + 1
        hourly_count = self._hourly_trade_counts[hour_key]

        daily_count = sum(
            count for key, count in self._hourly_trade_counts.items()
            if key.startswith(day_key)
        )

        if hourly_count > self.limits.max_trades_per_hour:
            result.approved = False
            result.risk_level = RiskLevel.CAUTION
            result.violations.append(
                RiskViolation(
                    violation_type=ViolationType.OVERTRADING,
                    risk_level=RiskLevel.CAUTION,
                    message=f"Overtrading: {hourly_count} trades in last hour (max {self.limits.max_trades_per_hour})",
                    current_value=hourly_count,
                    limit_value=self.limits.max_trades_per_hour,
                    can_override=True,
                )
            )

        if daily_count > self.limits.max_trades_per_day:
            result.approved = False
            result.risk_level = RiskLevel.DANGER
            result.violations.append(
                RiskViolation(
                    violation_type=ViolationType.OVERTRADING,
                    risk_level=RiskLevel.DANGER,
                    message=f"Overtrading: {daily_count} trades today (max {self.limits.max_trades_per_day})",
                    current_value=daily_count,
                    limit_value=self.limits.max_trades_per_day,
                    can_override=False,
                )
            )

        # 6. Checar revenge trading
        import time

        if time.time() < self._revenge_cooldown_until:
            result.approved = False
            result.risk_level = RiskLevel.BLOCKED
            result.violations.append(
                RiskViolation(
                    violation_type=ViolationType.REVENGE_TRADING,
                    risk_level=RiskLevel.BLOCKED,
                    message="Revenge trading cooldown active - wait before trading again",
                    can_override=False,
                )
            )

        # Atualizar nível de risco
        if result.approved and result.violations:
            result.risk_level = RiskLevel.CAUTION

        logger.info(
            "Risk guard check: %s %s %d shares @ $%.2f -> %s (%s)",
            side,
            symbol,
            quantity,
            entry_price,
            result.risk_level.value,
            len(result.violations),
        )

        return result

    def record_loss(self, pnl: float) -> None:
        """Registra uma perda para checar revenge trading."""
        if pnl < self.limits.revenge_trading_loss_threshold:
            import time

            cooldown_seconds = self.limits.revenge_trading_cooldown_min * 60
            self._revenge_cooldown_until = time.time() + cooldown_seconds
            logger.warning(
                "Revenge trading cooldown activated for %d minutes after loss of $%.2f",
                self.limits.revenge_trading_cooldown_min,
                pnl,
            )

    def reset_daily_counts(self) -> None:
        """Reseta contadores diários."""
        self._hourly_trade_counts.clear()
        logger.info("Daily trade counts reset")

    def get_current_risk_level(self, current_positions: list[dict[str, Any]]) -> RiskLevel:
        """Retorna o nível de risco atual baseado nas posições."""
        total_exposure = sum(p.get("quantity", 0) * p.get("avg_price", 0) for p in current_positions)
        exposure_pct = total_exposure / self.equity if self.equity > 0 else 0

        if exposure_pct > self.limits.max_total_exposure_pct * 0.8:
            return RiskLevel.DANGER
        elif exposure_pct > self.limits.max_total_exposure_pct * 0.5:
            return RiskLevel.CAUTION
        return RiskLevel.SAFE


def get_risk_guard(equity: float = 10000.0) -> RiskGuard:
    """Retorna instância singleton do RiskGuard."""
    # Em produção, isso viria de um container ou singleton
    return RiskGuard(equity=equity)
