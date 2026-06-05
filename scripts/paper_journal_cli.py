#!/usr/bin/env python
"""Paper Journal CLI - gerencia trades paper e metricas de performance.

Usage:
  python scripts/paper_journal_cli.py open <ticker> <direction> <entry_price> <shares> <thesis> [--holding swing]
  python scripts/paper_journal_cli.py close <trade_id> <exit_price> [--reason take_profit]
  python scripts/paper_journal_cli.py reflect <trade_id> --correct/--wrong [--right "..."] [--wrong "..." ] [--lesson "..."]
  python scripts/paper_journal_cli.py list [--open|--closed]
  python scripts/paper_journal_cli.py stats
  python scripts/paper_journal_cli.py performance [--equity 100000]
  python scripts/paper_journal_cli.py show <trade_id>

Exemplos:
  python scripts/paper_journal_cli.py open AAPL long 185.50 100 "AAPL undervalued after pullback, strong earnings catalyst"
  python scripts/paper_journal_cli.py close bob-20260605-001 192.00 --reason take_profit
  python scripts/paper_journal_cli.py reflect bob-20260605-001 --correct --right "Catalyst confirmed" --lesson "Wait for volume confirmation"
  python scripts/paper_journal_cli.py stats
  python scripts/paper_journal_cli.py performance --equity 100000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Garante src/ no path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from core.trading.paper_journal import PaperJournal, PaperTrade  # noqa: E402
from core.trading.performance_metrics import PerformanceEngine  # noqa: E402


def _trade_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"bob-{ts}"


def cmd_open(args: argparse.Namespace) -> None:
    journal = PaperJournal()
    trade = PaperTrade(
        trade_id=args.id or _trade_id(),
        ticker=args.ticker.upper(),
        direction=args.direction,
        entry_price=args.entry_price,
        shares=args.shares,
        thesis=args.thesis,
        entry_reasoning=args.thesis,
        verdict_at_entry="manual_entry",
        risk_assessment="Manual entry - verificar com Bob para risk assessment completo.",
        expected_holding_period=args.holding,
        entry_date=datetime.now(timezone.utc).isoformat(),
    )
    journal.open_trade(trade)
    print(json.dumps({"status": "opened", "trade_id": trade.trade_id, "ticker": trade.ticker}, indent=2))


def cmd_close(args: argparse.Namespace) -> None:
    journal = PaperJournal()
    trade = journal.close_trade(
        trade_id=args.trade_id,
        exit_price=args.exit_price,
        exit_reason=args.reason,
    )
    if trade:
        print(json.dumps({
            "status": "closed",
            "trade_id": trade.trade_id,
            "outcome": trade.outcome,
            "pnl_amount": round(trade.pnl_amount or 0, 2),
            "pnl_percent": round(trade.pnl_percent or 0, 4),
        }, indent=2))
    else:
        print(json.dumps({"status": "not_found", "trade_id": args.trade_id}))
        sys.exit(1)


def cmd_reflect(args: argparse.Namespace) -> None:
    journal = PaperJournal()
    trade = journal.add_reflection(
        trade_id=args.trade_id,
        thesis_correct=args.correct,
        what_went_right=args.right or "",
        what_went_wrong=args.wrong or "",
        lesson_learned=args.lesson or "",
    )
    if trade:
        print(json.dumps({
            "status": "reflected",
            "trade_id": trade.trade_id,
            "thesis_correct": trade.thesis_correct,
            "lesson_learned": trade.lesson_learned,
        }, indent=2))
    else:
        print(json.dumps({"status": "not_found", "trade_id": args.trade_id}))
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    journal = PaperJournal()
    if args.open_only:
        trades = journal.list_open()
    elif args.closed_only:
        trades = journal.list_closed()
    else:
        trades = journal.list_all()

    output = []
    for t in trades:
        output.append({
            "trade_id": t.get("trade_id"),
            "ticker": t.get("ticker"),
            "direction": t.get("direction"),
            "entry_price": t.get("entry_price"),
            "exit_price": t.get("exit_price"),
            "pnl_amount": round(t.get("pnl_amount", 0) or 0, 2) if t.get("exit_price") else None,
            "outcome": t.get("outcome"),
            "has_reflection": bool(t.get("lesson_learned")),
        })
    print(json.dumps({"count": len(output), "trades": output}, indent=2))


def cmd_show(args: argparse.Namespace) -> None:
    journal = PaperJournal()
    trade = journal.get_trade(args.trade_id)
    if trade:
        # Round floats for display
        for key in ("entry_price", "exit_price", "pnl_amount", "pnl_percent"):
            if trade.get(key) is not None:
                trade[key] = round(trade[key], 4)
        print(json.dumps(trade, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"status": "not_found", "trade_id": args.trade_id}))
        sys.exit(1)


def cmd_stats(args: argparse.Namespace) -> None:
    journal = PaperJournal()
    stats = journal.get_stats()
    print(json.dumps(stats, indent=2))


def cmd_performance(args: argparse.Namespace) -> None:
    journal = PaperJournal()
    engine = PerformanceEngine(journal, initial_equity=args.equity)
    report = engine.evaluate()
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper Journal CLI - Bob's trade journal and performance metrics")
    sub = parser.add_subparsers(dest="command")

    # open
    p_open = sub.add_parser("open", help="Abrir um novo trade paper")
    p_open.add_argument("ticker", help="Ticker (ex: AAPL)")
    p_open.add_argument("direction", choices=["long", "short"], help="Direcao")
    p_open.add_argument("entry_price", type=float, help="Preco de entrada")
    p_open.add_argument("shares", type=float, help="Quantidade")
    p_open.add_argument("thesis", help="Tese do trade")
    p_open.add_argument("--id", default=None, help="Trade ID customizado (default: auto-gerado)")
    p_open.add_argument("--holding", default="swing", choices=["day_trade", "swing", "position", "long_term"])

    # close
    p_close = sub.add_parser("close", help="Fechar um trade paper")
    p_close.add_argument("trade_id", help="ID do trade")
    p_close.add_argument("exit_price", type=float, help="Preco de saida")
    p_close.add_argument("--reason", default="manual", choices=["take_profit", "stop_loss", "thesis_broken", "time_exit", "manual"])

    # reflect
    p_reflect = sub.add_parser("reflect", help="Adicionar reflexao post-mortem")
    p_reflect.add_argument("trade_id", help="ID do trade")
    group = p_reflect.add_mutually_exclusive_group(required=True)
    group.add_argument("--correct", action="store_true", dest="correct", help="Tese estava correta")
    group.add_argument("--wrong", action="store_false", dest="correct", help="Tese estava errada")
    p_reflect.add_argument("--right", default="", help="O que deu certo")
    p_reflect.add_argument("--wrong-text", default="", dest="wrong", help="O que deu errado")
    p_reflect.add_argument("--lesson", default="", help="Licao aprendida")

    # list
    p_list = sub.add_parser("list", help="Listar trades")
    p_list.add_argument("--open", dest="open_only", action="store_true", help="Apenas abertos")
    p_list.add_argument("--closed", dest="closed_only", action="store_true", help="Apenas fechados")

    # show
    p_show = sub.add_parser("show", help="Mostrar detalhes de um trade")
    p_show.add_argument("trade_id", help="ID do trade")

    # stats
    sub.add_parser("stats", help="Estatisticas agregadas do journal")

    # performance
    p_perf = sub.add_parser("performance", help="Relatorio completo de performance (C7)")
    p_perf.add_argument("--equity", type=float, default=100_000.0, help="Equity inicial (default: 100000)")

    args = parser.parse_args()

    if args.command == "open":
        cmd_open(args)
    elif args.command == "close":
        cmd_close(args)
    elif args.command == "reflect":
        cmd_reflect(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "performance":
        cmd_performance(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
