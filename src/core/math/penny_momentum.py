"""Penny-stock momentum backtest primitives.

This module is intentionally pure: no model calls, no pipeline state, no I/O.
The runtime tool can fetch or inject OHLCV data, then this module computes the
strategy result deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Sequence

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


@dataclass(frozen=True)
class Trade:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    return_pct: float
    exit_reason: str
    hold_days: int


def simulate_penny_momentum_backtest(
    ohlcv_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    config: PennyMomentumConfig | None = None,
) -> dict[str, Any]:
    """Run the long-only penny momentum breakout strategy.

    Data format per bar:
    {"date": "YYYY-MM-DD", "open": float, "high": float, "low": float,
     "close": float, "volume": float}
    """

    cfg = config or PennyMomentumConfig()
    series = {
        symbol.upper(): _normalize_bars(bars) for symbol, bars in ohlcv_by_symbol.items() if bars
    }
    if not series:
        return _empty_result(cfg, "missing_ohlcv")

    calendar = sorted({bar["date"] for bars in series.values() for bar in bars})
    if not calendar:
        return _empty_result(cfg, "missing_calendar")

    by_date = {
        symbol: {bar["date"]: idx for idx, bar in enumerate(bars)}
        for symbol, bars in series.items()
    }
    cash = float(cfg.starting_capital)
    positions: dict[str, dict[str, Any]] = {}
    trades: list[Trade] = []
    equity_curve: list[float] = []

    for current_date in calendar:
        # Mark to market before exits/entries for a stable daily equity curve.
        equity = cash + sum(
            pos["qty"] * _close_on_or_before(series[symbol], by_date[symbol], current_date)
            for symbol, pos in positions.items()
        )
        equity_curve.append(equity)

        # Exits first.
        for symbol in list(positions):
            idx = by_date.get(symbol, {}).get(current_date)
            if idx is None:
                continue
            bar = series[symbol][idx]
            pos = positions[symbol]
            held = int(pos["held_days"]) + 1
            stop_price = pos["entry_price"] * (1.0 + cfg.stop_loss_pct)
            exit_reason = ""
            exit_price = 0.0
            if bar["low"] <= stop_price:
                exit_reason = "stop_loss"
                exit_price = stop_price
            elif held >= cfg.hold_days:
                exit_reason = "time_exit"
                exit_price = bar["close"]

            if exit_reason:
                qty = pos["qty"]
                proceeds = qty * exit_price
                cash += proceeds
                pnl = proceeds - pos["cost"]
                trades.append(
                    Trade(
                        symbol=symbol,
                        entry_date=pos["entry_date"],
                        exit_date=_date_to_str(current_date),
                        entry_price=round(pos["entry_price"], 4),
                        exit_price=round(exit_price, 4),
                        qty=round(qty, 6),
                        pnl=round(pnl, 4),
                        return_pct=round((exit_price - pos["entry_price"]) / pos["entry_price"], 6),
                        exit_reason=exit_reason,
                        hold_days=held,
                    )
                )
                del positions[symbol]
            else:
                pos["held_days"] = held

        # Entries after exits, using close-to-close simulation.
        slots = cfg.max_positions - len(positions)
        if slots <= 0:
            continue
        candidates = []
        for symbol, bars in series.items():
            if symbol in positions:
                continue
            idx = by_date.get(symbol, {}).get(current_date)
            if idx is None:
                continue
            signal = _entry_signal(bars, idx, cfg)
            if signal["entry"]:
                candidates.append((symbol, signal["rank"]))
        candidates.sort(key=lambda item: item[1], reverse=True)

        for symbol, _rank in candidates[:slots]:
            idx = by_date[symbol][current_date]
            close = series[symbol][idx]["close"]
            equity = cash + sum(
                pos["qty"] * _close_on_or_before(series[s], by_date[s], current_date)
                for s, pos in positions.items()
            )
            allocation = min(cash, equity * cfg.target_weight)
            if allocation <= 0 or close <= 0:
                continue
            qty = allocation / close
            cash -= allocation
            positions[symbol] = {
                "entry_date": _date_to_str(current_date),
                "entry_price": close,
                "qty": qty,
                "cost": allocation,
                "held_days": 0,
            }

    # Liquidate open positions at the last available close.
    final_date = calendar[-1]
    for symbol in list(positions):
        pos = positions[symbol]
        exit_price = _close_on_or_before(series[symbol], by_date[symbol], final_date)
        proceeds = pos["qty"] * exit_price
        cash += proceeds
        pnl = proceeds - pos["cost"]
        trades.append(
            Trade(
                symbol=symbol,
                entry_date=pos["entry_date"],
                exit_date=_date_to_str(final_date),
                entry_price=round(pos["entry_price"], 4),
                exit_price=round(exit_price, 4),
                qty=round(pos["qty"], 6),
                pnl=round(pnl, 4),
                return_pct=round((exit_price - pos["entry_price"]) / pos["entry_price"], 6),
                exit_reason="final_liquidation",
                hold_days=int(pos["held_days"]),
            )
        )
        del positions[symbol]

    final_equity = cash
    equity_curve.append(final_equity)
    daily_returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] > 0
    ]
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    total_return = (final_equity - cfg.starting_capital) / cfg.starting_capital
    drawdown = max_drawdown(equity_curve)
    result = {
        "strategy": "penny_momentum_breakout",
        "starting_capital": round(cfg.starting_capital, 2),
        "final_equity": round(final_equity, 2),
        "total_return": round(total_return, 6),
        "total_return_pct": round(total_return * 100.0, 2),
        "sharpe": round(sharpe_ratio(daily_returns), 4),
        "max_drawdown": round(drawdown, 6),
        "max_drawdown_pct": round(drawdown * 100.0, 2),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "win_rate_pct": round((len(wins) / len(trades)) * 100.0, 2) if trades else 0.0,
        "trade_count": len(trades),
        "avg_win_pct": round(_avg([t.return_pct for t in wins]) * 100.0, 2),
        "avg_loss_pct": round(_avg([t.return_pct for t in losses]) * 100.0, 2),
        "verdict": _verdict(total_return, drawdown, trades),
        "trades": [t.__dict__ for t in trades],
        "equity_curve": [round(v, 2) for v in equity_curve],
    }
    result["mathcore_verdict"] = _mathcore_verdict(result)
    return result


def _entry_signal(
    bars: Sequence[dict[str, Any]],
    idx: int,
    cfg: PennyMomentumConfig,
) -> dict[str, Any]:
    min_history = max(
        cfg.avg_dollar_volume_period,
        cfg.volume_slow_period,
        cfg.breakout_lookback,
    )
    if idx < min_history:
        return {"entry": False, "reason": "insufficient_history", "rank": 0.0}
    bar = bars[idx]
    close = bar["close"]
    if close < cfg.min_price or close > cfg.max_price:
        return {"entry": False, "reason": "price_filter", "rank": 0.0}

    slow_window = bars[idx - cfg.volume_slow_period + 1 : idx + 1]
    fast_window = bars[idx - cfg.volume_fast_period + 1 : idx + 1]
    dollar_window = bars[idx - cfg.avg_dollar_volume_period + 1 : idx + 1]
    avg_dollar_volume = _avg([b["close"] * b["volume"] for b in dollar_window])
    if avg_dollar_volume < cfg.min_avg_dollar_volume:
        return {"entry": False, "reason": "liquidity_filter", "rank": 0.0}

    fast_volume = _avg([b["volume"] for b in fast_window])
    slow_volume = _avg([b["volume"] for b in slow_window])
    if slow_volume <= 0 or fast_volume <= cfg.volume_spike_ratio * slow_volume:
        return {"entry": False, "reason": "volume_filter", "rank": 0.0}

    breakout_window = bars[idx - cfg.breakout_lookback : idx]
    previous_high = max(b["close"] for b in breakout_window)
    if close <= previous_high:
        return {"entry": False, "reason": "breakout_filter", "rank": 0.0}

    rank = (fast_volume / slow_volume) * (close / previous_high)
    return {"entry": True, "reason": "momentum_breakout", "rank": rank}


def _normalize_bars(bars: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for raw in bars:
        close = _float(raw.get("close") or raw.get("price"))
        high = _float(raw.get("high"), close)
        low = _float(raw.get("low"), close)
        volume = _float(raw.get("volume"))
        if close <= 0 or volume < 0:
            continue
        normalized.append(
            {
                "date": _parse_date(raw.get("date") or raw.get("time") or raw.get("timestamp")),
                "open": _float(raw.get("open"), close),
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    normalized.sort(key=lambda item: item["date"])
    return normalized


def _close_on_or_before(
    bars: Sequence[dict[str, Any]],
    by_date: Mapping[date, int],
    current_date: date,
) -> float:
    idx = by_date.get(current_date)
    if idx is not None:
        return bars[idx]["close"]
    previous = [bar for bar in bars if bar["date"] <= current_date]
    return previous[-1]["close"] if previous else bars[0]["close"]


def _empty_result(cfg: PennyMomentumConfig, reason: str) -> dict[str, Any]:
    result = {
        "strategy": "penny_momentum_breakout",
        "starting_capital": round(cfg.starting_capital, 2),
        "final_equity": round(cfg.starting_capital, 2),
        "total_return": 0.0,
        "total_return_pct": 0.0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "max_drawdown_pct": 0.0,
        "win_rate": 0.0,
        "win_rate_pct": 0.0,
        "trade_count": 0,
        "avg_win_pct": 0.0,
        "avg_loss_pct": 0.0,
        "verdict": "NO_DATA",
        "reason": reason,
        "trades": [],
        "equity_curve": [round(cfg.starting_capital, 2)],
    }
    result["mathcore_verdict"] = _mathcore_verdict(result)
    return result


def _mathcore_verdict(result: Mapping[str, Any]) -> str:
    return (
        "[mathcore/penny_momentum] "
        f"verdict={result.get('verdict')} "
        f"total_return={result.get('total_return_pct')}% "
        f"sharpe={result.get('sharpe')} "
        f"max_drawdown={result.get('max_drawdown_pct')}% "
        f"win_rate={result.get('win_rate_pct')}% "
        f"trades={result.get('trade_count')}"
    )


def _verdict(total_return: float, drawdown: float, trades: Sequence[Trade]) -> str:
    if not trades:
        return "NO_TRADE"
    if drawdown <= -0.50:
        return "REJECT_DRAWDOWN"
    if total_return <= -0.10:
        return "REJECT_NEGATIVE_EDGE"
    if total_return > 0.10 and drawdown > -0.25:
        return "PASS_EXPERIMENTAL"
    return "WATCH_ONLY"


def _avg(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        raise ValueError("bar date is required")
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text[:10]).date()


def _date_to_str(value: date) -> str:
    return value.isoformat()
