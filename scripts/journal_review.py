#!/usr/bin/env python
"""Journal review — checks C6 and C7 readiness.

Usage:
  python scripts/journal_review.py
  python scripts/journal_review.py --performance
"""

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from core.trading.paper_journal import PaperJournal  # noqa: E402
from core.trading.performance_metrics import PerformanceEngine  # noqa: E402


def main():
    journal = PaperJournal()
    all_trades = journal.list_all()
    open_trades = journal.list_open()
    closed_trades = journal.list_closed()

    print("=" * 60)
    print("JOURNAL REVIEW — C6/C7 Readiness")
    print("=" * 60)
    print(f"Total entries:    {len(all_trades)}")
    print(f"Open (buy only):  {len(open_trades)}")
    print(f"Closed (sold):    {len(closed_trades)}")
    print(f"With reflection:  {sum(1 for t in closed_trades if t.get('lesson_learned'))}")
    print()

    # ── C6: Track result ──
    print("── C6: Track result ──")
    print("Requires: ≥1 real thesis aged + closed + post-mortem")
    valid_c6 = [
        t
        for t in closed_trades
        if t.get("lesson_learned")
        and t.get("entry_date")
        and t.get("exit_date")
        and t.get("ticker") != "__CHECKPOINT__"
    ]
    if valid_c6:
        print(f"✅ {len(valid_c6)} closed trades with reflection — C6 READY for proof")
        for t in valid_c6:
            print(
                f"   {t['trade_id'][:30]} {t['ticker']} {t.get('outcome', '?')} pnl=${t.get('pnl_amount', 0):.2f}"
            )
    else:
        print("❌ 0 valid — need real trades (not checkpoint, not manual PLUG test)")
    print()

    # ── C7: Learn ──
    print("── C7: Learn ──")
    print("Requires: ≥10 real theses closed + ≥1 real bias detected")
    real_closed = [t for t in closed_trades if t.get("ticker") != "__CHECKPOINT__"]
    real_open = [t for t in open_trades if t.get("ticker") != "__CHECKPOINT__"]
    total_real = len(real_closed) + len(real_open)
    print(f"Real trades (open+closed): {total_real}/10 needed")
    if len(real_closed) >= 10:
        engine = PerformanceEngine(journal)
        report = engine.evaluate()
        biases = report.detected_biases
        if biases:
            print(f"✅ Biases detected: {len(biases)}")
            for b in biases:
                print(f"   - {b[:120]}")
        else:
            print("⚠️ 10+ closed but no biases detected — need more variety")
    else:
        print(f"❌ Only {len(real_closed)} closed — need {10 - len(real_closed)} more")
    print()

    # ── All entries ──
    print("── ALL ENTRIES ──")
    for t in all_trades:
        status = "CLOSED" if t.get("exit_date") else "OPEN"
        pnl = f"${t.get('pnl_amount', 0):.2f}" if t.get("pnl_amount") is not None else "-"
        ref = "📝" if t.get("lesson_learned") else ""
        print(
            f"  [{status}] {t['trade_id'][:30]:32s} {t['ticker']:16s} {t.get('direction', '?'):6s} x{t.get('shares', 0):5.0f} @ ${t.get('entry_price', 0):8.2f} pnl={pnl:>10s} {ref}"
        )


if __name__ == "__main__":
    main()
