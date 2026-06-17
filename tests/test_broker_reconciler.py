from __future__ import annotations

from core.trading.broker_reconciler import BrokerReconciler
from core.trading.paper_journal import PaperJournal


def test_reconciler_accepts_matching_broker_open_order(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    journal.record_broker_order(
        broker_order_id="perm-100",
        broker_perm_id="perm-100",
        broker_tws_order_id="4",
        ticker="NVDA",
        action="buy",
        qty=5,
        limit_price=132.6,
        status="submitted",
        thesis="pytest",
        verdict_at_entry="approved",
        risk_assessment="low",
    )

    report = BrokerReconciler(journal).reconcile(
        positions=[],
        open_orders=[
            {
                "order_id": "4",
                "perm_id": "perm-100",
                "ticker": "NVDA",
                "status": "Submitted",
                "quantity": 5,
            }
        ],
    )

    assert report.blocking is False
    assert report.open_orders_count == 1
    assert [issue.code for issue in report.issues] == []


def test_reconciler_warns_when_broker_order_is_missing_from_journal(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")

    report = BrokerReconciler(journal).reconcile(
        positions=[],
        open_orders=[
            {
                "order_id": "4",
                "perm_id": "perm-101",
                "ticker": "NOK",
                "status": "Submitted",
                "quantity": 10,
            }
        ],
    )

    assert report.blocking is False
    assert [issue.code for issue in report.issues] == ["broker_order_missing_journal"]


def test_reconciler_blocks_unverified_local_broker_ticket(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    journal.record_broker_order(
        broker_order_id="perm-102",
        broker_perm_id="perm-102",
        ticker="PLUG",
        action="buy",
        qty=10,
        limit_price=2.7,
        status="submitted",
        thesis="pytest",
        verdict_at_entry="approved",
        risk_assessment="low",
    )

    report = BrokerReconciler(journal).reconcile(positions=[], open_orders=[])

    assert report.blocking is True
    assert [issue.code for issue in report.issues] == ["journal_broker_ticket_unverified"]


def test_reconciler_blocks_confirmed_local_position_absent_from_broker(tmp_path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    journal.add_trade(
        {
            "trade_id": "confirmed-local",
            "ticker": "SNDL",
            "direction": "long",
            "shares": 100,
            "entry_price": 1.44,
            "status": "filled",
            "broker_fill_confirmed": True,
            "tags": ["broker_filled"],
            "thesis": "pytest",
        }
    )

    report = BrokerReconciler(journal).reconcile(positions=[], open_orders=[])

    assert report.blocking is True
    assert [issue.code for issue in report.issues] == ["journal_position_not_in_broker"]
