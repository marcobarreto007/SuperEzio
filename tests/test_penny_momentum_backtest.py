from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from src.core.math.penny_momentum import PennyMomentumConfig, simulate_penny_momentum_backtest
from src.core.pipeline.contracts import AgentToolCall
from src.core.pipeline.nodes.tool_executor import node_tool_executor
from src.data.yfinance_provider import _utc_observed_at


def _bars(
    *,
    breakout: bool = True,
    spike: bool = True,
    liquid: bool = True,
    price: float = 2.0,
    stop: bool = False,
) -> list[dict]:
    start = date(2026, 1, 1)
    bars = []
    for i in range(40):
        close = price + min(i, 20) * 0.01
        volume = 300_000 if liquid else 50_000
        if spike and liquid and 21 <= i <= 25:
            volume = 3_000_000
        if i == 25:
            close = price + 0.85 if breakout else price + 0.05
        if i > 25:
            close = price + 1.05 + (i - 26) * 0.01
        low = close
        if stop and i == 27:
            low = (price + 0.85) * 0.80
            close = low
        bars.append(
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "open": close,
                "high": close,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    return bars


def test_scenario_1_valid_breakout_produces_mathcore_pass():
    result = simulate_penny_momentum_backtest({"GOOD": _bars()})

    assert result["trade_count"] == 1
    assert result["total_return_pct"] > 0
    assert result["verdict"] in {"WATCH_ONLY", "PASS_EXPERIMENTAL"}
    assert "mathcore/penny_momentum" in result["mathcore_verdict"]


def test_scenario_2_missing_volume_spike_rejects_entry():
    result = simulate_penny_momentum_backtest({"QUIET": _bars(spike=False)})

    assert result["trade_count"] == 0
    assert result["verdict"] == "NO_TRADE"


def test_scenario_3_missing_breakout_rejects_entry():
    result = simulate_penny_momentum_backtest({"FLAT": _bars(breakout=False)})

    assert result["trade_count"] == 0
    assert result["verdict"] == "NO_TRADE"


def test_scenario_4_illiquid_symbol_rejects_entry():
    result = simulate_penny_momentum_backtest({"THIN": _bars(liquid=False)})

    assert result["trade_count"] == 0
    assert result["verdict"] == "NO_TRADE"


def test_scenario_5_price_above_penny_range_rejects_entry():
    result = simulate_penny_momentum_backtest({"RICH": _bars(price=6.0)})

    assert result["trade_count"] == 0
    assert result["verdict"] == "NO_TRADE"


def test_scenario_6_stop_loss_exits_trade():
    result = simulate_penny_momentum_backtest({"STOP": _bars(stop=True)})

    assert result["trade_count"] == 1
    assert result["trades"][0]["exit_reason"] == "stop_loss"
    assert result["total_return_pct"] < 0


def test_scenario_7_max_positions_caps_same_day_signals():
    data = {f"S{i:02d}": _bars(price=2.0 + i * 0.01) for i in range(12)}
    result = simulate_penny_momentum_backtest(data)

    assert result["trade_count"] == 10


def test_scenario_8_mixed_universe_only_trades_valid_symbols():
    data = {
        "GOOD": _bars(),
        "QUIET": _bars(spike=False),
        "THIN": _bars(liquid=False),
        "RICH": _bars(price=6.0),
    }
    result = simulate_penny_momentum_backtest(data)

    assert result["trade_count"] == 1
    assert result["trades"][0]["symbol"] == "GOOD"


def test_scenario_dates_remain_iso_in_trade_ledger():
    result = simulate_penny_momentum_backtest({"GOOD": _bars()})

    assert date.fromisoformat(result["trades"][0]["entry_date"])
    assert date.fromisoformat(result["trades"][0]["exit_date"])


def test_scenario_9_contract_accepts_penny_momentum_tool():
    call = AgentToolCall.model_validate(
        {"tool": "penny_momentum_backtest", "args": {"tickers": ["GOOD"]}}
    )

    assert call.tool == "penny_momentum_backtest"


@pytest.mark.asyncio
async def test_scenario_10_tool_executor_returns_backtest_context(monkeypatch):
    monkeypatch.setattr(
        "src.core.pipeline.nodes.tool_executor.get_stream_writer",
        lambda: lambda _event: None,
    )

    state = {
        "agent_tool_call": {
            "tool": "penny_momentum_backtest",
            "args": {"ohlcv_by_symbol": {"GOOD": _bars()}},
        },
        "executed_tools": [],
        "executed_tool_counts": {},
    }
    result = await node_tool_executor(state, gateway=None, config=None)

    assert result["executed_tools"] == ["penny_momentum_backtest"]
    assert "[MATHCORE BACKTEST]" in result["data_context"]
    assert result["penny_momentum_backtest"]["trade_count"] == 1


@pytest.mark.asyncio
async def test_tool_executor_missing_data_feeds_error_context(monkeypatch):
    monkeypatch.setattr(
        "src.core.pipeline.nodes.tool_executor.get_stream_writer",
        lambda: lambda _event: None,
    )

    state = {
        "agent_tool_call": {"tool": "penny_momentum_backtest", "args": {}},
        "executed_tools": [],
        "executed_tool_counts": {},
        "errors": [],
    }
    result = await node_tool_executor(state, gateway=None, config=None)

    assert result["executed_tools"] == ["penny_momentum_backtest"]
    assert "missing_ohlcv" in result["data_context"]
    assert "penny_momentum_backtest:missing_ohlcv" in result["errors"]


def test_yfinance_datetime_payload_is_accepted_and_observation_is_preserved():
    bars = _bars()
    for index, bar in enumerate(bars):
        bar["datetime"] = datetime(2026, 1, 1, 14, 30, tzinfo=UTC) + timedelta(days=index)
        del bar["date"]

    result = simulate_penny_momentum_backtest({"REAL": bars})

    assert result["data_window"]["REAL"]["first_observed_at"] == "2026-01-01T14:30:00+00:00"
    assert result["trades"][0]["signal_observed_at"] == "2026-01-26T14:30:00+00:00"
    assert result["trades"][0]["entry_observed_at"] == "2026-01-27T14:30:00+00:00"


def test_yfinance_timestamp_converts_zone_without_relabelling_clock():
    eastern = timezone(-timedelta(hours=5))

    assert _utc_observed_at(datetime(2026, 1, 5, 9, 30, tzinfo=eastern)) == (
        "2026-01-05T14:30:00+00:00"
    )


def test_signal_at_close_executes_only_at_next_open():
    bars = _bars()
    signal_close = bars[25]["close"]
    bars[26]["open"] = 4.25
    bars[26]["high"] = 4.30
    bars[26]["low"] = 4.20
    bars[26]["close"] = 4.25
    cfg = PennyMomentumConfig(commission_bps=0.0, slippage_bps=0.0)

    result = simulate_penny_momentum_backtest({"CAUSAL": bars}, cfg)
    trade = result["trades"][0]

    assert trade["signal_date"] == "2026-01-26"
    assert trade["entry_date"] == "2026-01-27"
    assert trade["entry_price"] == 4.25
    assert trade["entry_price"] != signal_close
    assert result["execution_rule"] == "signal_on_close_t_execute_next_observed_open"


def test_fees_slippage_and_benchmarks_are_reported_and_reduce_equity():
    no_cost = simulate_penny_momentum_backtest(
        {"GOOD": _bars()}, PennyMomentumConfig(commission_bps=0.0, slippage_bps=0.0)
    )
    with_cost = simulate_penny_momentum_backtest(
        {"GOOD": _bars()}, PennyMomentumConfig(commission_bps=25.0, slippage_bps=50.0)
    )

    assert with_cost["final_equity"] < no_cost["final_equity"]
    assert with_cost["costs"]["total_fees"] > 0
    assert with_cost["benchmarks"]["cash"]["total_return"] == 0.0
    assert "total_return" in with_cost["benchmarks"]["buy_and_hold_equal_weight"]
    assert "excess_return_vs_buy_and_hold" in with_cost


@pytest.mark.parametrize(
    "payload, reason",
    [({}, "missing_ohlcv"), ({"EMPTY": []}, "missing_ohlcv:EMPTY")],
)
def test_absent_market_data_fails_explicitly(payload, reason):
    with pytest.raises(ValueError, match=reason):
        simulate_penny_momentum_backtest(payload)


@pytest.mark.asyncio
async def test_tool_executor_rejects_partial_requested_universe(monkeypatch):
    monkeypatch.setattr(
        "src.core.pipeline.nodes.tool_executor.get_stream_writer", lambda: lambda _event: None
    )
    monkeypatch.setattr(
        "src.core.pipeline.nodes.tool_executor._fetch_backtest_ohlcv",
        lambda tickers, timeframe: {"GOOD": _bars()},
    )
    state = {
        "agent_tool_call": {
            "tool": "penny_momentum_backtest",
            "args": {"tickers": ["GOOD", "MISSING"]},
        },
        "executed_tools": [],
        "executed_tool_counts": {},
        "errors": [],
    }

    result = await node_tool_executor(state, gateway=None, config=None)

    assert result["penny_momentum_backtest"]["error"] == (
        "missing_ohlcv_for_requested_tickers:MISSING"
    )
