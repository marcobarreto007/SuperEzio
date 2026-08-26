"""Tests for Approval Gate + Email Alerter — Loop 3."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── ApprovalGate ────────────────────────────────────────────────────────────


class TestApprovalGateSubmit:
    def test_submit_creates_pending_request(self):
        from core.trading.approval_gate import ApprovalGate, ApprovalStatus, GateConfig

        gate = ApprovalGate(config=GateConfig(max_auto_approve_amount=0.0))
        req = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        assert req.status == ApprovalStatus.PENDING
        assert req.symbol == "AAPL"
        assert req.side == "buy"
        assert req.qty == 100
        assert req.risk_amount == 500.0

    def test_auto_approve_below_threshold(self):
        from core.trading.approval_gate import ApprovalGate, ApprovalStatus, GateConfig

        config = GateConfig(max_auto_approve_amount=100.0)
        gate = ApprovalGate(config=config)
        req = gate.submit("AAPL", "buy", 10, 100.0, 99.0, 50.0)
        assert req.status == ApprovalStatus.APPROVED
        assert req.resolved_by == "auto"

    def test_default_auto_approve_below_threshold(self):
        from core.trading.approval_gate import ApprovalGate, ApprovalStatus

        gate = ApprovalGate()
        req = gate.submit("AAPL", "buy", 10, 100.0, 95.0, 5.0)
        assert req.status == ApprovalStatus.APPROVED
        assert req.resolved_by == "auto"

    def test_default_pending_above_threshold(self):
        from core.trading.approval_gate import ApprovalGate, ApprovalStatus

        gate = ApprovalGate()
        req = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 600.0)
        assert req.status == ApprovalStatus.PENDING
        assert gate.pending_count == 1

    def test_unique_request_ids(self):
        from core.trading.approval_gate import ApprovalGate

        gate = ApprovalGate()
        r1 = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        r2 = gate.submit("TSLA", "buy", 5, 200.0, 190.0, 500.0)
        assert r1.id != r2.id


class TestApprovalGateApproveReject:
    def test_approve_pending(self):
        from core.trading.approval_gate import ApprovalGate, ApprovalStatus, GateConfig

        gate = ApprovalGate(config=GateConfig(max_auto_approve_amount=0.0))
        req = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        result = gate.approve(req.id)
        assert result is not None
        assert result.status == ApprovalStatus.APPROVED
        assert result.resolved_by == "operator"

    def test_approve_with_custom_approver(self):
        from core.trading.approval_gate import ApprovalGate, GateConfig

        gate = ApprovalGate(config=GateConfig(max_auto_approve_amount=0.0))
        req = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        result = gate.approve(req.id, approver="marco")
        assert result is not None
        assert result.resolved_by == "marco"

    def test_reject_pending(self):
        from core.trading.approval_gate import ApprovalGate, ApprovalStatus, GateConfig

        gate = ApprovalGate(config=GateConfig(max_auto_approve_amount=0.0))
        req = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        result = gate.reject(req.id)
        assert result is not None
        assert result.status == ApprovalStatus.REJECTED

    def test_approve_nonexistent_returns_none(self):
        from core.trading.approval_gate import ApprovalGate

        gate = ApprovalGate()
        assert gate.approve("no-such-id") is None

    def test_double_approve_returns_none(self):
        from core.trading.approval_gate import ApprovalGate, GateConfig

        gate = ApprovalGate(config=GateConfig(max_auto_approve_amount=0.0))
        req = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        gate.approve(req.id)
        assert gate.approve(req.id) is None


class TestApprovalGateExpire:
    def test_expire_old_requests(self):
        from core.trading.approval_gate import ApprovalGate, ApprovalStatus, GateConfig

        config = GateConfig(ttl_seconds=0.01, max_auto_approve_amount=0.0)
        gate = ApprovalGate(config=config)
        req = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        time.sleep(0.02)
        expired = gate.expire_old()
        assert len(expired) == 1
        assert req.id in expired
        assert req.status == ApprovalStatus.EXPIRED

    def test_no_expire_recent(self):
        from core.trading.approval_gate import ApprovalGate, GateConfig

        config = GateConfig(ttl_seconds=3600, max_auto_approve_amount=0.0)
        gate = ApprovalGate(config=config)
        gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        expired = gate.expire_old()
        assert len(expired) == 0


class TestApprovalGateState:
    def test_pending_count(self):
        from core.trading.approval_gate import ApprovalGate, GateConfig

        gate = ApprovalGate(config=GateConfig(max_auto_approve_amount=0.0))
        gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        gate.submit("TSLA", "buy", 5, 200.0, 190.0, 500.0)
        assert gate.pending_count == 2

    def test_get_pending(self):
        from core.trading.approval_gate import ApprovalGate, GateConfig

        gate = ApprovalGate(config=GateConfig(max_auto_approve_amount=0.0))
        r1 = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        pending = gate.get_pending()
        assert len(pending) == 1
        assert pending[0].id == r1.id

    def test_get_history(self):
        from core.trading.approval_gate import ApprovalGate

        gate = ApprovalGate()
        gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        gate.submit("TSLA", "buy", 5, 200.0, 190.0, 500.0)
        assert len(gate.get_history()) == 2

    def test_history_includes_auto_approved(self):
        from core.trading.approval_gate import ApprovalGate, GateConfig

        config = GateConfig(max_auto_approve_amount=500.0)
        gate = ApprovalGate(config=config)
        gate.submit("AAPL", "buy", 10, 100.0, 95.0, 50.0)
        assert len(gate.get_history()) == 1
        assert gate.pending_count == 0

    def test_pending_approval_survives_store_restart(self, tmp_path):
        from core.trading.approval_gate import ApprovalGate, GateConfig
        from core.trading.workflow_store import TradeWorkflowStore

        db = tmp_path / "workflow.sqlite3"
        gate = ApprovalGate(
            config=GateConfig(max_auto_approve_amount=0.0),
            store=TradeWorkflowStore(db),
        )
        req = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)

        restored = ApprovalGate(
            config=GateConfig(max_auto_approve_amount=0.0),
            store=TradeWorkflowStore(db),
        )
        assert restored.get_pending()[0].id == req.id
        restored.approve(req.id, approver="marco")
        final = ApprovalGate(store=TradeWorkflowStore(db)).get_history()[0]
        assert final.status.value == "approved"
        assert final.resolved_by == "marco"

    def test_approval_is_bound_to_same_ticket_hash(self, tmp_path):
        from core.trading.approval_gate import ApprovalGate, GateConfig
        from core.trading.workflow_store import TradeWorkflowStore

        store = TradeWorkflowStore(tmp_path / "workflow.sqlite3")
        ticket = {
            "ticket_id": "ticket-approval",
            "fingerprint": "c" * 64,
            "broker": "TD_DIRECT_INVESTING_CANADA",
            "status": "AWAITING_HUMAN",
            "phase": "human_review",
            "submitted_to_broker": False,
        }
        store.create_ticket(ticket)
        gate = ApprovalGate(
            config=GateConfig(max_auto_approve_amount=0.0),
            store=store,
        )
        first = gate.submit(
            "TD",
            "buy",
            2,
            110.0,
            108.0,
            4.0,
            ticket_id="ticket-approval",
            ticket_fingerprint="c" * 64,
        )
        retry = ApprovalGate(store=TradeWorkflowStore(store.path)).submit(
            "TD",
            "buy",
            2,
            110.0,
            108.0,
            4.0,
            ticket_id="ticket-approval",
            ticket_fingerprint="c" * 64,
        )

        assert retry.id == first.id == f"apr-{'c' * 24}"
        assert retry.ticket_id == "ticket-approval"


# ── EmailAlerter ────────────────────────────────────────────────────────────


class TestEmailAlerter:
    def test_disabled_returns_false(self):
        from core.trading.alerter import EmailAlerter

        alerter = EmailAlerter()
        assert alerter.send_trade_alert("Test", "body") is False

    def test_no_recipients_returns_false(self):
        from core.trading.alerter import EmailAlerter, EmailConfig

        config = EmailConfig(enabled=True, smtp_host="localhost", to_addrs=[])
        alerter = EmailAlerter(config=config)
        assert alerter.send_trade_alert("Test", "body") is False

    def test_send_approval_request_format(self):
        from core.trading.alerter import EmailAlerter, EmailConfig

        config = EmailConfig(enabled=True, smtp_host="localhost", to_addrs=["test@test.com"])
        alerter = EmailAlerter(config=config)
        # Will fail to actually send (no SMTP server), but should try and return False
        result = alerter.send_approval_request(
            request_id="apr-1",
            symbol="AAPL",
            side="buy",
            qty=10,
            risk_amount=200.0,
            reason="test",
        )
        assert result is False  # no SMTP server running

    def test_send_kill_switch_alert(self):
        from core.trading.alerter import EmailAlerter, EmailConfig

        config = EmailConfig(enabled=True, smtp_host="localhost", to_addrs=["test@test.com"])
        alerter = EmailAlerter(config=config)
        result = alerter.send_kill_switch_alert("daily_loss_limit", -500.0)
        assert result is False  # no SMTP server


# ── LogAlerter ──────────────────────────────────────────────────────────────


class TestLogAlerter:
    def test_send_trade_alert(self):
        from core.trading.alerter import LogAlerter

        alerter = LogAlerter()
        assert alerter.send_trade_alert("Test Alert", "Test body") is True

    def test_send_approval_request(self):
        from core.trading.alerter import LogAlerter

        alerter = LogAlerter()
        assert (
            alerter.send_approval_request(
                "apr-1",
                "AAPL",
                "buy",
                10,
                200.0,
                "test",
            )
            is True
        )

    def test_send_kill_switch_alert(self):
        from core.trading.alerter import LogAlerter

        alerter = LogAlerter()
        assert alerter.send_kill_switch_alert("daily_loss", -500.0) is True


# ── Integration: ApprovalGate + LogAlerter ──────────────────────────────────


class TestApprovalGateAlerterIntegration:
    def test_submit_and_alert(self):
        from core.trading.alerter import LogAlerter
        from core.trading.approval_gate import ApprovalGate, ApprovalStatus, GateConfig

        gate = ApprovalGate(config=GateConfig(max_auto_approve_amount=0.0))
        alerter = LogAlerter()

        req = gate.submit("AAPL", "buy", 100, 100.0, 95.0, 500.0)
        assert req.status == ApprovalStatus.PENDING
        assert alerter.send_approval_request(
            req.id,
            req.symbol,
            req.side,
            req.qty,
            req.risk_amount,
            req.reason,
        )

    def test_kill_switch_triggers_alert(self):
        from core.trading.alerter import LogAlerter
        from core.trading.kill_switch import KillSwitch

        ks = KillSwitch(daily_loss_limit=100)
        alerter = LogAlerter()

        triggered = ks.record_trade(-150)
        assert triggered
        assert alerter.send_kill_switch_alert(
            ks.state.reason.value,
            ks.state.daily_pnl,
        )
