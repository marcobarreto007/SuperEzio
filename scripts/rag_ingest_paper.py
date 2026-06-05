#!/usr/bin/env python
"""Bridge: Paper Journal → ForensicRAG ingestion.

Converts paper trading journal entries into RAG-searchable documents
so Bob can query real paper trading history via rag_forensics tool.

Usage:
  python scripts/rag_ingest_paper.py              # ingest all closed trades
  python scripts/rag_ingest_paper.py --all         # ingest all trades (incl open)
  python scripts/rag_ingest_paper.py --stats       # show what's in the RAG
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from core.trading.paper_journal import PaperJournal  # noqa: E402

RAG_PAPER_DIR = _PROJECT_ROOT / "data" / "paper_trades_rag"


def _trade_to_rag_doc(trade: dict) -> dict:
    """Convert a paper trade entry to a RAG-searchable document."""
    entry_price = trade.get("entry_price", "?")
    exit_price = trade.get("exit_price")
    pnl = trade.get("pnl_amount")
    outcome = trade.get("outcome", "open")

    text_parts = [
        f"Paper trade: {trade.get('ticker', '?')} {trade.get('direction', '?')}.",
        f"Entry: ${entry_price} on {trade.get('entry_date', '?')[:10]}.",
        f"Thesis: {trade.get('thesis', 'No thesis recorded.')}",
    ]
    if exit_price:
        text_parts.append(
            f"Exit: ${exit_price} on {str(trade.get('exit_date', '?'))[:10]}. "
            f"Outcome: {outcome}. PnL: ${round(pnl, 2) if pnl else '?'}."
        )
    if trade.get("thesis_correct") is not None:
        text_parts.append(
            f"Thesis was {'CORRECT' if trade.get('thesis_correct') else 'WRONG'}."
        )
    if trade.get("lesson_learned"):
        text_parts.append(f"Lesson: {trade.get('lesson_learned')}")

    return {
        "id": trade.get("trade_id", ""),
        "title": f"Paper Trade: {trade.get('ticker', '?')} {trade.get('direction', '?').upper()} @ ${entry_price}",
        "content": " ".join(text_parts),
        "source": "paper_journal",
        "timestamp": trade.get("created_at", datetime.now(timezone.utc).isoformat()),
        "metadata": {
            "ticker": trade.get("ticker"),
            "direction": trade.get("direction"),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_amount": pnl,
            "outcome": outcome,
            "has_reflection": bool(trade.get("lesson_learned")),
        },
    }


def ingest(include_open: bool = False) -> int:
    """Ingest paper journal entries into RAG data directory.

    Returns number of documents ingested.
    """
    journal = PaperJournal()
    trades = journal.list_all() if include_open else journal.list_closed()

    if not trades:
        print("No trades to ingest.")
        return 0

    RAG_PAPER_DIR.mkdir(parents=True, exist_ok=True)

    docs = [_trade_to_rag_doc(t) for t in trades]

    # Write as JSONL for ForensicRAG ingestion
    output_path = RAG_PAPER_DIR / "paper_trades.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"Ingested {len(docs)} trades → {output_path}")
    return len(docs)


def stats() -> dict:
    """Show what's in the RAG paper trades directory."""
    output_path = RAG_PAPER_DIR / "paper_trades.jsonl"
    if not output_path.exists():
        return {"status": "empty", "documents": 0}

    docs = []
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))

    tickers = {}
    outcomes = {"win": 0, "loss": 0, "breakeven": 0, "open": 0}
    for d in docs:
        t = d.get("metadata", {}).get("ticker", "?")
        tickers[t] = tickers.get(t, 0) + 1
        o = d.get("metadata", {}).get("outcome", "open")
        outcomes[o] = outcomes.get(o, 0) + 1

    return {
        "status": "populated",
        "documents": len(docs),
        "tickers": tickers,
        "outcomes": outcomes,
        "path": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Paper Journal → RAG bridge")
    parser.add_argument("--all", action="store_true", help="Include open trades")
    parser.add_argument("--stats", action="store_true", help="Show RAG stats")
    args = parser.parse_args()

    if args.stats:
        print(json.dumps(stats(), indent=2))
    else:
        n = ingest(include_open=args.all)
        if n > 0:
            print(json.dumps(stats(), indent=2))


if __name__ == "__main__":
    main()
