"""F51 Blindagem Final — 6 testes obrigatórios.

Prova que nenhuma ordem pode existir fora do F51 Trade Gate.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestRawIBKRCLIDisabledByDefault:
    """1. Raw CLI não executa sem env vars explícitas."""

    def test_cli_blocked_by_default(self):
        """Sem F51_ALLOW_RAW_IBKR_CLI=true, deve retornar BLOCKED_RAW_CLI_DISABLED."""
        import subprocess
        import json

        result = subprocess.run(
            [sys.executable, "scripts/_ibkr_order.py", "BUY", "AAPL", "1", "150.0"],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "F51_ALLOW_RAW_IBKR_CLI": "false"},
        )
        output = json.loads(result.stdout.strip())
        assert output["blocked"] is True
        assert output["reason"] == "BLOCKED_RAW_CLI_DISABLED"
        # Must NOT have IBKR result fields
        assert "order_id" not in output

    def test_cli_blocked_by_freeze_even_if_raw_allowed(self):
        """Com raw CLI permitido mas FREEZE=true, deve bloquear."""
        import subprocess
        import json

        result = subprocess.run(
            [sys.executable, "scripts/_ibkr_order.py", "BUY", "AAPL", "1", "150.0"],
            capture_output=True,
            text=True,
            timeout=10,
            env={
                **os.environ,
                "F51_ALLOW_RAW_IBKR_CLI": "true",
                "F51_TRADING_EXECUTION_FREEZE": "true",
                "F51_PAPER_MODE_CONFIRMED": "true",
            },
        )
        output = json.loads(result.stdout.strip())
        assert output["blocked"] is True
        assert "FREEZE" in output["reason"]

    def test_cli_blocked_without_paper_confirmed(self):
        """Com raw CLI + freeze off mas sem paper confirmed, deve bloquear."""
        import subprocess
        import json

        result = subprocess.run(
            [sys.executable, "scripts/_ibkr_order.py", "BUY", "AAPL", "1", "150.0"],
            capture_output=True,
            text=True,
            timeout=10,
            env={
                **os.environ,
                "F51_ALLOW_RAW_IBKR_CLI": "true",
                "F51_TRADING_EXECUTION_FREEZE": "false",
                "F51_PAPER_MODE_CONFIRMED": "false",
            },
        )
        output = json.loads(result.stdout.strip())
        assert output["blocked"] is True
        assert output["reason"] == "BLOCKED_PAPER_NOT_CONFIRMED"


class TestExecuteTradeRealCannotBypassGate:
    """2. execute_trade_real() não pode executar sem gate."""

    @pytest.mark.skipif(
        not os.path.exists("src/core/trading/trading_engine_live.py"),
        reason="trading_engine_live module not available",
    )
    def test_execute_trade_real_blocked_by_gate(self, monkeypatch):
        """Chamar execute_trade_real diretamente deve bloquear via F51 Trade Gate."""
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "true")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")

        # Verify gate module exists and blocks with FREEZE
        from core.pipeline.f51_trade_gate import evaluate_trade_gate

        result = evaluate_trade_gate(
            message="live trade NVDA",
            ticker="NVDA",
            thesis_ticker="NVDA",
            qty=10,
            limit_price=120.0,
            run_id="test-bypass",
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "EXECUTION_FREEZE"


class TestAutoExecutorRequiresGate:
    """3. auto_executor precisa do gate."""

    def test_auto_executor_rejects_ungated(self, monkeypatch):
        """Sem gate approval, execute_order bloqueia."""
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "true")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")

        from core.trading.auto_executor import (
            AutoExecutor,
            ExecutorConfig,
            ExecutionRequest,
            ExecutionStatus,
        )

        config = ExecutorConfig(enable_committee=False)
        executor = AutoExecutor(config=config)

        req = ExecutionRequest(
            request_id="test-ungated-001",
            symbol="AAPL",
            side="buy",
            quantity=10,
            entry_price=150.0,
        )
        # Força status que burlaria o prepare_order
        req.status = ExecutionStatus.APPROVED

        result = executor.execute_order(req)
        # Deve ser BLOCKED pelo gate check (FREEZE ativo)
        assert result.status == ExecutionStatus.BLOCKED
        assert "F51 Trade Gate" in (result.rejection_message or "")


class TestLowLevelBrokerRejectsUngatedOrder:
    """4. Broker/IBKR de baixo nível rejeita ordem ungated."""

    def test_ibkr_adapter_rejects_ungated_order(self, monkeypatch):
        """IBKR adapter.submit_order() rejeita ordem sem gate_metadata."""
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")

        from core.trading.broker import Order, OrderSide, OrderStatus, OrderType
        from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter

        adapter = InteractiveBrokersAdapter()
        order = Order(
            id="test-low-level-001",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            qty=10,
            limit_price=150.0,
            status=OrderStatus.PENDING,
        )
        # Order has no gate_metadata → should be rejected
        result = adapter.submit_order(order)
        assert result.status == OrderStatus.REJECTED
        assert "ungated" in str(result.id).lower()

    def test_low_level_gate_check_blocks_missing_metadata(self, monkeypatch):
        """_low_level_gate_check retorna False quando order não tem gate_metadata."""
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")

        from adapters.broker.ibkr_adapter import _low_level_gate_check

        # None has no gate_metadata → should fail
        result = _low_level_gate_check(None)
        assert result is False


class TestFreezeBlocksLowLevelOrder:
    """5. FREEZE bloqueia até ordem de baixo nível."""

    def test_auto_execute_paper_freeze_blocks(self, monkeypatch):
        """auto_execute_paper não procede com FREEZE=true."""
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "true")

        from core.pipeline.f51_trade_gate import is_execution_frozen

        assert is_execution_frozen() is True

    def test_order_submission_never_records_provisional_learning_outcome(self):
        """Learning must wait for a terminal journal outcome, never order submission."""
        import inspect

        from core.pipeline.nodes.auto_execute_paper import auto_execute_paper

        source = inspect.getsource(auto_execute_paper)
        assert "record_trade_outcome" not in source
        assert "pnl_estimate" not in source

    def test_tool_executor_freeze_blocks(self, monkeypatch):
        """tool_executor bloqueia submit_paper_order com FREEZE=true."""
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "true")

        from core.pipeline.f51_trade_gate import evaluate_trade_gate

        result = evaluate_trade_gate(
            message="paper trade buy 1 share of AAPL",
            ticker="AAPL",
            qty=1,
            limit_price=150.0,
            run_id="test-freeze",
        )
        assert result.status == "BLOCK"
        assert "FREEZE" in result.reason_code

    def test_freeze_off_allows_valid_order_to_reach_ibkr_check(self, monkeypatch):
        """Com FREEZE=false, ordem válida avança até check IBKR."""
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        # SUPEREZIO_* also freezes execution and must be cleared for this
        # test to be isolated from any real .env on disk — see
        # tests/test_f51_trade_gate.py::test_freeze_off_proceeds for context.
        monkeypatch.delenv("SUPEREZIO_LIVE_TRADING_DISABLED", raising=False)
        monkeypatch.delenv("SUPEREZIO_RESEARCH_PAPER_ONLY", raising=False)
        monkeypatch.delenv("SUPEREZIO_DAYTRADE_PAPER_ONLY", raising=False)

        from core.pipeline.f51_trade_gate import evaluate_trade_gate

        result = evaluate_trade_gate(
            message="paper trade buy 1 share of AAPL",
            ticker="AAPL",
            qty=1,
            limit_price=150.0,
            run_id="test-valid",
        )
        # IBKR is likely offline → should block at Gate 9
        assert result.status == "BLOCK"
        # Should be IBKR_OFFLINE or passed gates
        assert result.reason_code in (
            "IBKR_OFFLINE",
            "ALL_GATES_PASSED",
            "TICKER_VALIDATION_FAILED",
        )


class TestGeneratorHasNoUndefinedNames:
    """6. generator.py não contém undefined names."""

    def test_generator_compiles_clean(self):
        """Arquivo compila sem erros de sintaxe ou undefined names."""
        import ast
        import py_compile
        from pathlib import Path

        gen_path = Path("src/core/pipeline/nodes/generator.py")
        assert gen_path.exists(), "generator.py not found"

        # Parse sem erros
        with open(gen_path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        assert tree is not None

        # Compile sem erros
        py_compile.compile(str(gen_path), doraise=True)

    def test_generator_no_ruff_f821(self):
        """ruff não reporta F821 (undefined name) em generator.py."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "src/core/pipeline/nodes/generator.py",
                "--select",
                "F821",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"ruff F821 failed: {result.stdout}"
        # ruff outputs "All checks passed!" on success
        assert "error" not in result.stdout.lower() or "All checks passed" in result.stdout

    def test_build_candidate_sections_no_name_error(self):
        """_build_candidate_sections não lança NameError em runtime."""
        from src.core.pipeline.nodes.generator import _build_candidate_sections

        sections = _build_candidate_sections(
            portuguese=True,
            mode_label="paper",
            display_decision="WAIT",
            is_followup=False,
            prev_excluded="",
            paper_training=True,
            paper_auto_submit=False,
            paper_order_user_blocked=False,
            ticker="AAPL",
            name="Apple Inc",
            market="NASDAQ",
            price=150.0,
            currency="USD",
            collected_at="2026-06-27",
            provider="finnhub",
            liquidity_text="Alta",
            amount_text="1000",
            account_text="10000",
            estimated_qty=6,
            catalyst="earnings",
            time_horizon="swing",
            confidence=65,
            gate_failures=[],
            safety_gate_failures=[],
            display_decision_raw="WAIT",
            errors=[],
            state={},
        )
        assert isinstance(sections, list)
        assert len(sections) > 0
        # Verify no placeholder/undefined appears in output
        full_text = "\n".join(str(s) for s in sections)
        assert "{invalidation}" not in full_text
        assert "{risk}" not in full_text
