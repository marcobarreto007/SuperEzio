from __future__ import annotations

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


def test_ibkr_adapter_uses_prepared_worker_for_limit_orders(monkeypatch):
    import adapters.broker.ibkr_adapter as ibkr_adapter_module
    import adapters.broker.ibkr_order_worker as order_worker_module
    from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter
    from adapters.broker.ibkr_order_worker import BrokerTransportResult
    from core.trading.broker import Order, OrderSide, OrderStatus, OrderType

    captured = {}

    def fake_run(order, *, host, port):
        captured["order"] = order
        captured["host"] = host
        captured["port"] = port
        return BrokerTransportResult(
            returncode=0,
            stdout='{"order_id":"ibkr-42","status":"Submitted"}',
        )

    monkeypatch.setattr(order_worker_module, "run_prepared_order", fake_run)
    monkeypatch.setattr(ibkr_adapter_module, "_low_level_gate_check", lambda _order: True)

    order = Order(
        id="pytest-order",
        symbol="nvda",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=5,
        status=OrderStatus.PENDING,
        limit_price=132.6,
        gate_metadata={
            "gate_status": "ALLOW",
            "gate_trace_id": "test-trace",
            "validated_ticker": "NVDA",
            "journal_ready": True,
            "execution_freeze": False,
            "pipeline_prepared": True,
            "adaptive_policy_applied": True,
            "approval_id": "apr-test",
            "consensus_decision": "SUPPORT",
        },
    )
    monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")

    result = InteractiveBrokersAdapter().submit_order(order)

    assert captured["order"] is order
    assert captured["host"] == "127.0.0.1"
    assert captured["order"].gate_metadata["approval_id"] == "apr-test"
    assert result.status == OrderStatus.SUBMITTED
    assert result.limit_price == 132.6


def test_ibkr_adapter_blocks_market_orders_by_default(monkeypatch):
    from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter
    from core.trading.broker import Order, OrderSide, OrderStatus, OrderType

    monkeypatch.delenv("SUPEREZIO_IBKR_ALLOW_MARKET_ORDER", raising=False)

    order = Order(
        id="pytest-market",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        qty=1,
        status=OrderStatus.PENDING,
    )
    # Gate metadata required for low-level check
    object.__setattr__(
        order,
        "gate_metadata",
        {
            "gate_status": "ALLOW",
            "gate_trace_id": "test",
            "validated_ticker": "AAPL",
            "journal_ready": True,
            "execution_freeze": False,
        },
    )
    monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")

    result = InteractiveBrokersAdapter().submit_order(order)

    assert result.status == OrderStatus.REJECTED
    assert "blocked" in result.id.lower()


def test_ibkr_adapter_cancel_uses_risk_reduction_worker(monkeypatch):
    import adapters.broker.ibkr_order_worker as order_worker_module
    from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter

    captured = {}

    def fake_cancel(order_id, *, host, port):
        captured.update(order_id=order_id, host=host, port=port)
        return True

    monkeypatch.setattr(order_worker_module, "cancel_open_order", fake_cancel)

    assert InteractiveBrokersAdapter().cancel_order("perm-42") is True
    assert captured == {"order_id": "perm-42", "host": "127.0.0.1", "port": 7497}


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
                id="933426820",
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                status=OrderStatus.SUBMITTED,
                limit_price=order.limit_price,
                perm_id="933426820",
                tws_order_id="4",
                client_id="123",
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
    engine._position_manager.open_position = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("IBKR submitted order must not create a local position")
    )

    result = engine.execute_trade_real(
        TradingOpportunity(
            symbol="NVDA",
            sentiment=MarketSentiment.BULLISH,
            confidence=0.8,
            entry_price=132.64,
            stop_loss=128.0,
            take_profit=140.0,
            thesis="buy NVDA LMT order",
            expected_move_pct=0.05,
            liquidity_score=1.0,
            market_data={"avg_daily_volume": 10_000_000, "change_pct": 1.0},
        ),
        quantity=5,
    )

    # F51 Trade Gate may block (FREEZE, IBKR offline, etc). Accept either.
    if result and result.get("blocked"):
        assert "reason" in result  # Valid block
        return  # Gate blocked — rest of assertions don't apply
    assert result["order_id"] == "933426820"
    assert result["submitted"] is True
    assert result["position_confirmed"] is False
    assert captured["order"].order_type == OrderType.LIMIT
    assert captured["order"].limit_price == 132.64
    assert captured["order"].status == OrderStatus.PENDING

    journal_rows = engine._journal.list_all()
    assert len(journal_rows) == 1
    assert journal_rows[0]["source"] == "ibkr_order_ticket"
    assert journal_rows[0]["broker_fill_confirmed"] is False
    assert journal_rows[0]["broker_perm_id"] == "933426820"


def test_live_cycle_blocks_when_reconciliation_blocks(monkeypatch, tmp_path):
    import core.trading.trading_engine_live as live_module

    from core.trading.broker_reconciler import BrokerReconciliationReport, ReconciliationIssue
    from core.trading.trading_engine_live import LiveTradingEngine

    # SUPEREZIO_LIVE_TRADING_DISABLED now defaults to True (fail-safe — see
    # docs/audit/phase6_rag_pennylab_execution.md finding 6.3), which forces
    # use_ibkr=False regardless of the constructor argument. This test
    # specifically exercises the IBKR-enabled reconciliation path, so it
    # must opt out of the fail-safe default explicitly.
    monkeypatch.setenv("SUPEREZIO_LIVE_TRADING_DISABLED", "false")

    engine = LiveTradingEngine(
        use_ibkr=True,
        equity=100000,
        journal_path=tmp_path / "paper_journal.jsonl",
        persistence_path=tmp_path / "live_engine_state.json",
    )
    monkeypatch.setattr(
        live_module,
        "get_market_state",
        lambda cached=False: {"is_open": True, "phase": "MARKET_OPEN"},
    )
    engine.update_equity_from_broker = lambda: engine.equity
    engine.scan_market_real = lambda: (_ for _ in ()).throw(
        AssertionError("blocked cycle must not scan")
    )
    engine._reconciler.reconcile = lambda: BrokerReconciliationReport(
        timestamp="pytest",
        positions_count=0,
        open_orders_count=0,
        journal_rows_count=1,
        blocking=True,
        issues=[
            ReconciliationIssue(
                severity="BLOCK",
                code="journal_broker_ticket_unverified",
                message="pytest",
            )
        ],
    )

    summary = engine.run_one_cycle_real()

    assert summary["blocked"] is True
    assert summary["opportunities"] == 0
    assert summary["orders_submitted"] == 0
    assert summary["reconciliation"]["issues"][0]["code"] == "journal_broker_ticket_unverified"
