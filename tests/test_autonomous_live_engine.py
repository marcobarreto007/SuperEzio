from __future__ import annotations

import json
from types import SimpleNamespace


def test_autonomous_loop_defaults_to_live_engine(monkeypatch, tmp_path):
    import core.trading.autonomous_loop as loop_module

    fake_engine = SimpleNamespace(
        get_status=lambda: {"session": False, "engine": {}, "positions": {}},
        start_session=lambda: {"started_at": "pytest"},
        run_one_cycle=lambda: {
            "trades_executed": 0,
            "positions_closed": 0,
            "total_pnl": 0.0,
            "opportunities_found": 0,
        },
        check_and_update_positions=lambda: [],
        end_session=lambda: None,
    )

    monkeypatch.setattr(
        loop_module,
        "get_live_trading_engine",
        lambda use_ibkr, equity: fake_engine,
    )

    loop = loop_module.AutonomousLoop(
        equity=12345,
        scan_interval_seconds=1,
        persistence_path=tmp_path / "loop.json",
    )

    assert loop._engine is fake_engine
    assert loop._engine_mode == "live_ibkr"


def test_ibkr_adapter_subprocess_uses_order_cli_contract_for_limit_orders(monkeypatch):
    import subprocess

    from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter
    from core.trading.broker import Order, OrderSide, OrderStatus, OrderType

    captured = {}

    def fake_run(args, **_kwargs):
        captured["args"] = args
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"order_id": "ibkr-42", "status": "Submitted"}),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    order = Order(
        id="pytest-order",
        symbol="nvda",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=5,
        status=OrderStatus.PENDING,
        limit_price=132.6,
    )

    result = InteractiveBrokersAdapter().submit_order(order)

    assert captured["args"][-4:] == ["BUY", "NVDA", "5", "132.6"]
    assert result.status == OrderStatus.SUBMITTED
    assert result.limit_price == 132.6


def test_ibkr_adapter_blocks_market_orders_by_default(monkeypatch):
    import subprocess

    from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter
    from core.trading.broker import Order, OrderSide, OrderStatus, OrderType

    def fail_run(*_args, **_kwargs):
        raise AssertionError("market order must not reach _ibkr_order.py by default")

    monkeypatch.delenv("SUPEREZIO_IBKR_ALLOW_MARKET_ORDER", raising=False)
    monkeypatch.setattr(subprocess, "run", fail_run)

    result = InteractiveBrokersAdapter().submit_order(
        Order(
            id="pytest-market",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty=1,
            status=OrderStatus.PENDING,
        )
    )

    assert result.status == OrderStatus.REJECTED
    assert result.id == "ibkr-blocked-market-order"


def test_live_trading_engine_submits_limit_order(monkeypatch, tmp_path):
    import adapters.broker.ibkr_adapter as ibkr_module

    from core.trading.auto_executor import ExecutionStatus
    from core.trading.broker import Order, OrderStatus, OrderType
    from core.trading.trading_engine_live import (
        LiveTradingEngine,
        MarketSentiment,
        TradingOpportunity,
    )

    captured = {}

    class FakeAdapter:
        def submit_order(self, order: Order) -> Order:
            captured["order"] = order
            return Order(
                id="ibkr-submitted",
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                status=OrderStatus.SUBMITTED,
                limit_price=order.limit_price,
            )

    monkeypatch.setattr(ibkr_module, "InteractiveBrokersAdapter", FakeAdapter)

    engine = LiveTradingEngine(
        use_ibkr=True,
        equity=100000,
        journal_path=tmp_path / "paper_journal.jsonl",
        persistence_path=tmp_path / "live_engine_state.json",
    )
    engine._executor.prepare_order = lambda **_kwargs: SimpleNamespace(
        status=ExecutionStatus.APPROVED,
        rejection_reason="",
    )
    engine._position_manager.open_position = lambda **_kwargs: SimpleNamespace(
        position_id="pos-1",
    )
    engine._journal.add_trade = lambda _trade: None

    result = engine.execute_trade_real(
        TradingOpportunity(
            symbol="NVDA",
            sentiment=MarketSentiment.BULLISH,
            confidence=0.8,
            entry_price=132.64,
            stop_loss=128.0,
            take_profit=140.0,
            thesis="pytest live LMT",
            expected_move_pct=0.05,
            liquidity_score=1.0,
            market_data={"avg_daily_volume": 10_000_000, "change_pct": 1.0},
        ),
        quantity=5,
    )

    assert result["position_id"] == "pos-1"
    assert captured["order"].order_type == OrderType.LIMIT
    assert captured["order"].limit_price == 132.64
    assert captured["order"].status == OrderStatus.PENDING
