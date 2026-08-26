"""Pure, causal penny-stock momentum backtest primitives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

from .risk import max_drawdown, sharpe_ratio


@dataclass(frozen=True)
class PennyMomentumConfig:
    starting_capital: float = 10_000.0
    min_price: float = 1.0
    max_price: float = 5.0
    min_avg_dollar_volume: float = 1_000_000.0
    avg_dollar_volume_period: int = 20
    volume_fast_period: int = 5
    volume_slow_period: int = 20
    volume_spike_ratio: float = 3.0
    breakout_lookback: int = 10
    max_positions: int = 10
    target_weight: float = 0.10
    hold_days: int = 10
    stop_loss_pct: float = -0.15
    commission_bps: float = 5.0
    slippage_bps: float = 10.0


@dataclass(frozen=True)
class Trade:
    symbol: str
    signal_date: str
    signal_observed_at: str
    entry_date: str
    entry_observed_at: str
    exit_date: str
    exit_observed_at: str
    entry_price: float
    exit_price: float
    qty: float
    gross_pnl: float
    fees: float
    pnl: float
    return_pct: float
    exit_reason: str
    hold_days: int


def simulate_penny_momentum_backtest(
    ohlcv_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    config: PennyMomentumConfig | None = None,
) -> dict[str, Any]:
    """Simulate signals at close ``t`` with execution at the next bar open."""
    cfg = config or PennyMomentumConfig()
    _validate_config(cfg)
    if not ohlcv_by_symbol:
        raise ValueError("missing_ohlcv")

    series: dict[str, list[dict[str, Any]]] = {}
    for raw_symbol, raw_bars in ohlcv_by_symbol.items():
        symbol = str(raw_symbol).strip().upper()
        if not symbol or not raw_bars:
            raise ValueError(f"missing_ohlcv:{symbol or '<blank_symbol>'}")
        bars = _normalize_bars(raw_bars)
        if not bars:
            raise ValueError(f"invalid_ohlcv:{symbol}")
        series[symbol] = bars

    calendar = sorted({bar["date"] for bars in series.values() for bar in bars})
    by_date = {
        symbol: {bar["date"]: idx for idx, bar in enumerate(bars)}
        for symbol, bars in series.items()
    }
    cash = float(cfg.starting_capital)
    positions: dict[str, dict[str, Any]] = {}
    pending: dict[str, dict[str, Any]] = {}
    trades: list[Trade] = []
    equity_curve = [cash]

    for current_date in calendar:
        for symbol in list(positions):
            idx = by_date[symbol].get(current_date)
            if idx is None:
                continue
            bar, pos = series[symbol][idx], positions[symbol]
            held = int(pos["held_days"]) + 1
            stop = pos["entry_price"] * (1.0 + cfg.stop_loss_pct)
            if bar["low"] <= stop:
                cash += _exit(
                    symbol, pos, bar, min(bar["open"], stop), "stop_loss", held, cfg, trades
                )
                del positions[symbol]
            elif held >= cfg.hold_days:
                cash += _exit(symbol, pos, bar, bar["open"], "time_exit", held, cfg, trades)
                del positions[symbol]
            else:
                pos["held_days"] = held

        eligible = [
            (symbol, signal)
            for symbol, signal in pending.items()
            if symbol not in positions
            and current_date > signal["signal_date"]
            and current_date in by_date[symbol]
        ]
        eligible.sort(key=lambda item: item[1]["rank"], reverse=True)
        slots = max(0, cfg.max_positions - len(positions))
        for symbol, signal in eligible[:slots]:
            bar = series[symbol][by_date[symbol][current_date]]
            equity_at_open = cash + sum(
                pos["qty"] * _known_open_price(series[s], by_date[s], current_date)
                for s, pos in positions.items()
            )
            allocation = min(cash, equity_at_open * cfg.target_weight)
            entry_price = bar["open"] * (1.0 + cfg.slippage_bps / 10_000.0)
            fee_rate = cfg.commission_bps / 10_000.0
            qty = allocation / (entry_price * (1.0 + fee_rate)) if entry_price > 0 else 0.0
            if allocation <= 0 or qty <= 0:
                continue
            notional = qty * entry_price
            entry_fee = notional * fee_rate
            cost = notional + entry_fee
            cash -= cost
            positions[symbol] = {
                "signal_date": signal["signal_date"],
                "signal_observed_at": signal["signal_observed_at"],
                "entry_date": current_date,
                "entry_observed_at": bar["observed_at"],
                "entry_price": entry_price,
                "entry_fee": entry_fee,
                "qty": qty,
                "cost": cost,
                "held_days": 0,
            }
            del pending[symbol]

        # A next-open order is valid for that open only. Do not carry stale
        # signals forward merely because the portfolio had no free slot.
        for symbol, _signal in eligible[slots:]:
            del pending[symbol]

        # Only now, after the close, calculate signals for a future open.
        for symbol, bars in series.items():
            if symbol in positions or symbol in pending:
                continue
            idx = by_date[symbol].get(current_date)
            if idx is None:
                continue
            signal = _entry_signal(bars, idx, cfg)
            if signal["entry"]:
                pending[symbol] = {
                    "signal_date": current_date,
                    "signal_observed_at": bars[idx]["observed_at"],
                    "rank": signal["rank"],
                }

        equity_curve.append(
            cash
            + sum(
                pos["qty"] * _close_on_or_before(series[s], by_date[s], current_date)
                for s, pos in positions.items()
            )
        )

    for symbol in list(positions):
        pos, bar = positions[symbol], series[symbol][-1]
        cash += _exit(
            symbol, pos, bar, bar["close"], "final_liquidation", int(pos["held_days"]), cfg, trades
        )
        del positions[symbol]

    final_equity = cash
    equity_curve.append(final_equity)
    returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] > 0
    ]
    wins, losses = [t for t in trades if t.pnl > 0], [t for t in trades if t.pnl <= 0]
    total_return = (final_equity - cfg.starting_capital) / cfg.starting_capital
    drawdown = max_drawdown(equity_curve)
    buy_hold = _buy_hold(series, cfg)
    result = {
        "strategy": "penny_momentum_breakout",
        "execution_rule": "signal_on_close_t_execute_next_observed_open",
        "starting_capital": round(cfg.starting_capital, 2),
        "final_equity": round(final_equity, 2),
        "total_return": round(total_return, 6),
        "total_return_pct": round(total_return * 100.0, 2),
        "sharpe": round(sharpe_ratio(returns), 4),
        "max_drawdown": round(drawdown, 6),
        "max_drawdown_pct": round(drawdown * 100.0, 2),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
        "trade_count": len(trades),
        "avg_win_pct": round(_avg([t.return_pct for t in wins]) * 100.0, 2),
        "avg_loss_pct": round(_avg([t.return_pct for t in losses]) * 100.0, 2),
        "costs": {
            "commission_bps": cfg.commission_bps,
            "slippage_bps": cfg.slippage_bps,
            "total_fees": round(sum(t.fees for t in trades), 4),
        },
        "benchmarks": {
            "cash": {"final_equity": round(cfg.starting_capital, 2), "total_return": 0.0},
            "buy_and_hold_equal_weight": buy_hold,
        },
        "excess_return_vs_buy_and_hold": round(total_return - buy_hold["total_return"], 6),
        "data_window": {
            s: {
                "first_observed_at": bars[0]["observed_at"],
                "last_observed_at": bars[-1]["observed_at"],
                "bar_count": len(bars),
            }
            for s, bars in series.items()
        },
        "verdict": _verdict(total_return, drawdown, trades),
        "trades": [asdict(t) for t in trades],
        "equity_curve": [round(value, 2) for value in equity_curve],
    }
    result["mathcore_verdict"] = _mathcore_verdict(result)
    return result


def _exit(
    symbol: str,
    pos: Mapping[str, Any],
    bar: Mapping[str, Any],
    raw_price: float,
    reason: str,
    held: int,
    cfg: PennyMomentumConfig,
    trades: list[Trade],
) -> float:
    price = raw_price * (1.0 - cfg.slippage_bps / 10_000.0)
    gross_proceeds = pos["qty"] * price
    exit_fee = gross_proceeds * cfg.commission_bps / 10_000.0
    proceeds = gross_proceeds - exit_fee
    pnl = proceeds - pos["cost"]
    trades.append(
        Trade(
            symbol=symbol,
            signal_date=pos["signal_date"].isoformat(),
            signal_observed_at=pos["signal_observed_at"],
            entry_date=pos["entry_date"].isoformat(),
            entry_observed_at=pos["entry_observed_at"],
            exit_date=bar["date"].isoformat(),
            exit_observed_at=bar["observed_at"],
            entry_price=round(pos["entry_price"], 4),
            exit_price=round(price, 4),
            qty=round(pos["qty"], 6),
            gross_pnl=round(pos["qty"] * (price - pos["entry_price"]), 4),
            fees=round(pos["entry_fee"] + exit_fee, 4),
            pnl=round(pnl, 4),
            return_pct=round(pnl / pos["cost"], 6),
            exit_reason=reason,
            hold_days=held,
        )
    )
    return proceeds


def _buy_hold(
    series: Mapping[str, Sequence[Mapping[str, Any]]], cfg: PennyMomentumConfig
) -> dict[str, Any]:
    allocation = cfg.starting_capital / len(series)
    fee_rate = cfg.commission_bps / 10_000.0
    final_equity = 0.0
    for bars in series.values():
        entry = float(bars[0]["open"]) * (1.0 + cfg.slippage_bps / 10_000.0)
        qty = allocation / (entry * (1.0 + fee_rate))
        exit_price = float(bars[-1]["close"]) * (1.0 - cfg.slippage_bps / 10_000.0)
        final_equity += qty * exit_price * (1.0 - fee_rate)
    total_return = (final_equity - cfg.starting_capital) / cfg.starting_capital
    return {"final_equity": round(final_equity, 2), "total_return": round(total_return, 6)}


def _entry_signal(
    bars: Sequence[dict[str, Any]], idx: int, cfg: PennyMomentumConfig
) -> dict[str, Any]:
    minimum = max(cfg.avg_dollar_volume_period, cfg.volume_slow_period, cfg.breakout_lookback)
    if idx < minimum:
        return {"entry": False, "reason": "insufficient_history", "rank": 0.0}
    close = bars[idx]["close"]
    if not cfg.min_price <= close <= cfg.max_price:
        return {"entry": False, "reason": "price_filter", "rank": 0.0}
    slow = bars[idx - cfg.volume_slow_period + 1 : idx + 1]
    fast = bars[idx - cfg.volume_fast_period + 1 : idx + 1]
    liquid = bars[idx - cfg.avg_dollar_volume_period + 1 : idx + 1]
    if _avg([b["close"] * b["volume"] for b in liquid]) < cfg.min_avg_dollar_volume:
        return {"entry": False, "reason": "liquidity_filter", "rank": 0.0}
    fast_volume, slow_volume = _avg([b["volume"] for b in fast]), _avg([b["volume"] for b in slow])
    if slow_volume <= 0 or fast_volume <= cfg.volume_spike_ratio * slow_volume:
        return {"entry": False, "reason": "volume_filter", "rank": 0.0}
    previous_high = max(b["close"] for b in bars[idx - cfg.breakout_lookback : idx])
    if close <= previous_high:
        return {"entry": False, "reason": "breakout_filter", "rank": 0.0}
    return {
        "entry": True,
        "reason": "momentum_breakout",
        "rank": fast_volume / slow_volume * close / previous_high,
    }


def _normalize_bars(raw_bars: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    bars = []
    for raw in raw_bars:
        value = raw.get("datetime")
        if value is None:
            value = raw.get("date") or raw.get("time") or raw.get("timestamp")
        observed = _parse_observed_at(value)
        bar = {
            "date": observed.date(),
            "observed_at": observed.isoformat(),
            "open": _required_float(raw.get("open"), "open"),
            "high": _required_float(raw.get("high"), "high"),
            "low": _required_float(raw.get("low"), "low"),
            "close": _required_float(
                raw.get("close") if raw.get("close") is not None else raw.get("price"), "close"
            ),
            "volume": _required_float(raw.get("volume"), "volume"),
        }
        if min(bar["open"], bar["high"], bar["low"], bar["close"]) <= 0 or bar["volume"] < 0:
            raise ValueError("invalid_ohlcv_value")
        bars.append(bar)
    bars.sort(key=lambda item: item["observed_at"])
    if len({bar["date"] for bar in bars}) != len(bars):
        raise ValueError("duplicate_daily_candle")
    return bars


def _known_open_price(
    bars: Sequence[dict[str, Any]], by_date: Mapping[date, int], current: date
) -> float:
    idx = by_date.get(current)
    if idx is None:
        return _close_on_or_before(bars, by_date, current)
    return bars[idx - 1]["close"] if idx > 0 else bars[idx]["open"]


def _close_on_or_before(
    bars: Sequence[dict[str, Any]], by_date: Mapping[date, int], current: date
) -> float:
    idx = by_date.get(current)
    if idx is not None:
        return bars[idx]["close"]
    previous = [bar for bar in bars if bar["date"] <= current]
    return previous[-1]["close"] if previous else bars[0]["open"]


def _validate_config(cfg: PennyMomentumConfig) -> None:
    if cfg.starting_capital <= 0:
        raise ValueError("starting_capital_must_be_positive")
    if cfg.max_positions <= 0 or not 0 < cfg.target_weight <= 1:
        raise ValueError("invalid_position_limits")
    if cfg.hold_days <= 0:
        raise ValueError("hold_days_must_be_positive")
    if cfg.commission_bps < 0 or cfg.slippage_bps < 0:
        raise ValueError("costs_must_be_non_negative")


def _required_float(value: Any, field: str) -> float:
    if value is None:
        raise ValueError(f"missing_{field}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{field}") from exc


def _parse_observed_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        observed = value
    elif isinstance(value, date):
        observed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, (int, float)):
        observed = datetime.fromtimestamp(float(value), tz=UTC)
    elif value is None:
        raise ValueError("bar_datetime_is_required")
    else:
        try:
            observed = datetime.fromisoformat(str(value).strip())
        except ValueError as exc:
            raise ValueError("invalid_bar_datetime") from exc
    return observed.astimezone(UTC) if observed.tzinfo is not None else observed


def _mathcore_verdict(result: Mapping[str, Any]) -> str:
    return (
        "[mathcore/penny_momentum] "
        f"verdict={result.get('verdict')} total_return={result.get('total_return_pct')}% "
        f"sharpe={result.get('sharpe')} max_drawdown={result.get('max_drawdown_pct')}% "
        f"win_rate={result.get('win_rate_pct')}% trades={result.get('trade_count')}"
    )


def _verdict(total_return: float, drawdown: float, trades: Sequence[Trade]) -> str:
    if not trades:
        return "NO_TRADE"
    if drawdown <= -0.50:
        return "REJECT_DRAWDOWN"
    if total_return <= -0.10:
        return "REJECT_NEGATIVE_EDGE"
    return "PASS_EXPERIMENTAL" if total_return > 0.10 and drawdown > -0.25 else "WATCH_ONLY"


def _avg(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
