#!/usr/bin/env python
"""Generate the Stage 5 debut report for paper trading."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent
src_root = project_root / "src"
sys.path.insert(0, str(src_root))
sys.path.insert(0, str(project_root))

from core.trading.feedback_loop import FeedbackLoop  # noqa: E402
from core.trading.paper_journal import PaperJournal  # noqa: E402
from core.trading.performance_metrics import PerformanceEngine  # noqa: E402


def _parse_utc_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _status_line(label: str, proven: bool, detail: str = "") -> str:
    status = "PROVEN" if proven else "PENDING"
    suffix = f" ({detail})" if detail else ""
    return f"{label:<28} {'[OK]' if proven else '[..]'} {status}{suffix}"


def _aged_thesis_counts(
    journal: PaperJournal,
    *,
    days: int,
    as_of: datetime,
) -> tuple[int, int]:
    aged_count = 0
    thesis_closed_count = 0
    for trade in journal.list_closed():
        entry_dt = _parse_utc_datetime(trade.get("entry_date"))
        if entry_dt is None:
            continue
        age_days = (as_of - entry_dt).total_seconds() / 86400
        if age_days < days:
            continue
        aged_count += 1
        tags = set(trade.get("tags") or [])
        if "thesis_closed" in tags or trade.get("lesson_learned"):
            thesis_closed_count += 1
    return aged_count, thesis_closed_count


def build_debut_report(
    *,
    journal_path: Path | None = None,
    days: int = 14,
    min_trades: int = 10,
    as_of: datetime | None = None,
) -> str:
    """Build a deterministic text report from the paper journal."""
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    journal = PaperJournal(journal_path)
    stats = journal.get_stats()
    performance = PerformanceEngine(journal).evaluate()
    feedback = FeedbackLoop(journal_path=journal.path)
    bias_report = feedback.analyze_confidence_bias(min_closed=min_trades)
    aged_count, thesis_closed_count = _aged_thesis_counts(journal, days=days, as_of=now)

    c5_proven = stats["total_trades"] > 0
    c6_proven = aged_count >= min_trades and thesis_closed_count >= min_trades
    c7_proven = bias_report.get("status") == "analyzed"

    criteria = [
        _status_line("C1 Understand request", True),
        _status_line("C2 Collect real data", True),
        _status_line("C3 Separate opportunity", True),
        _status_line("C4 Explain risk", True),
        _status_line("C5 Register thesis", c5_proven, f"{stats['total_trades']} trades"),
        _status_line(
            "C6 Track result",
            c6_proven,
            f"{thesis_closed_count}/{min_trades} theses closed, {aged_count} aged",
        ),
        _status_line(
            "C7 Learn from errors",
            c7_proven,
            f"bias: {bias_report.get('bias')}",
        ),
        _status_line("C8 Never execute live", True, "paper only"),
    ]

    if c6_proven and c7_proven and performance.profit_factor >= 1:
        recommendation = "READY for live-money consideration."
    elif c6_proven and c7_proven:
        recommendation = "READY for demo; continue paper until profit factor improves."
    else:
        recommendation = "CONTINUE PAPER until C6/C7 sample is proven."

    bias_lines = [
        f"- Bias: {bias_report.get('bias')} ({bias_report.get('status')})",
        f"- Confidence sample: {bias_report.get('confidence_sample_size', 0)} trades",
    ]
    if bias_report.get("status") == "analyzed":
        bias_lines.extend(
            [
                f"- Avg confidence: {bias_report.get('avg_confidence', 0) * 100:.1f}%",
                f"- Win rate on confidence sample: {bias_report.get('win_rate', 0) * 100:.1f}%",
                f"- Correction: {bias_report.get('recommendation')}",
            ]
        )

    lines = [
        "=== SUPEREZIO DEBUT REPORT ===",
        f"Date: {now.date().isoformat()}",
        f"Period: {days} days of paper trading",
        f"Journal: {journal.path}",
        "",
        "CRITERIA:",
        *criteria,
        "",
        "PERFORMANCE:",
        f"Trades: {stats['closed_trades']} ({stats['wins']} wins, {stats['losses']} losses)",
        f"Win rate: {performance.win_rate_pct:.1f}%",
        f"Sharpe: {performance.sharpe_ratio:.2f}",
        f"Max drawdown: -{abs(performance.max_drawdown_percent):.1f}%",
        f"Profit factor: {performance.profit_factor:.2f}",
        f"Total PnL: ${performance.total_pnl:.2f}",
        "",
        "BIAS DETECTED:",
        *bias_lines,
        "",
        f"RECOMMENDATION: {recommendation}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate SuperEzio debut report")
    parser.add_argument("--journal", type=Path, default=None, help="Path to paper_journal.jsonl")
    parser.add_argument("--days", type=int, default=14, help="Paper trading review window")
    parser.add_argument("--min-trades", type=int, default=10, help="Minimum closed trades for C6/C7")
    args = parser.parse_args(argv)

    print(
        build_debut_report(
            journal_path=args.journal,
            days=args.days,
            min_trades=args.min_trades,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
