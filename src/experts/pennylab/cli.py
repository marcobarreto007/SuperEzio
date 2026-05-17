"""
PennyLab CLI — F51 WhaleTrap Lab
==================================
Uso pessoal/laboratório. NÃO executa ordens.
NÃO conecta broker. NÃO decide sozinho.
Marco decide com base nas informações aqui geradas.

Comandos:
  ticker   SYMBOL [--input FILE]    → análise completa
  scan     --max-price N [...]      → lista tickers candidatos (requer provedor)
  log      --ticker X ...           → registra trade experimental
  postmortem SYMBOL                 → resume histórico de trades

Execução:
  python -m experts.pennylab.cli ticker ABCD --input sample.json
  python -m experts.pennylab.cli log --ticker SNDL --entry 0.42 --exit 0.46 --size 5
  python -m experts.pennylab.cli postmortem SNDL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from experts.pennylab.config import MAX_PRICE_PENNY, MIN_VOLUME_PENNY
from experts.pennylab.data_provider import fetch_signal, scan_penny_stocks
from experts.pennylab.experts.veracity_gate import PennylabVeracityGate
from experts.pennylab.lab_journal import journal
from experts.pennylab.rag_hooks import enrich_with_rag
from experts.pennylab.schemas import (
    DataQuality,
    ScanFilter,
    SignalInput,
    TradeLog,
)
from experts.pennylab.scoring import analyze

# ---------------------------------------------------------------------------
# Formatação de saída
# ---------------------------------------------------------------------------


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _load_signal_file(path: str, ticker: str) -> SignalInput:
    """Carrega SignalInput de arquivo JSON (entrada manual para testes)."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw["ticker"] = raw.get("ticker", ticker).upper()
    raw["data_quality"] = DataQuality.MANUAL
    raw["source"] = f"file:{Path(path).name}"
    return SignalInput(**raw)


# ---------------------------------------------------------------------------
# Subcomando: ticker
# ---------------------------------------------------------------------------


def cmd_ticker(args: argparse.Namespace) -> int:
    ticker = args.symbol.upper()

    if args.input:
        try:
            signal = _load_signal_file(args.input, ticker)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            print(f"[ERRO] Não foi possível carregar --input: {e}", file=sys.stderr)
            return 1
    else:
        # Busca dados reais via DataHub
        print(f"[...] Buscando dados para {ticker}...", file=sys.stderr)
        signal = fetch_signal(ticker)

    # VeracityGate
    gate = PennylabVeracityGate()
    gate_result = gate.check(signal)
    if not gate_result.passed:
        out = {
            "ticker": ticker,
            "decision": "NO_TRADE",
            "veracity_violations": gate_result.violations,
            "message": "VeracityGate vetou — dados inválidos",
        }
        _print_json(out)
        return 0

    # Análise
    report = analyze(signal, veracity_passed=gate_result.passed)

    # Enriquece com RAG
    report.evidence = enrich_with_rag(ticker, report.evidence)

    # Adiciona warnings do gate
    if gate_result.warnings:
        report.risks = gate_result.warnings + report.risks

    _print_json(report.model_dump())
    return 0


# ---------------------------------------------------------------------------
# Subcomando: scan
# ---------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> int:
    filters = ScanFilter(
        max_price=args.max_price,
        min_volume=args.min_volume,
        max_spread_pct=args.max_spread_pct,
    )
    if args.tickers:
        watchlist = [t.strip().upper() for t in args.tickers.split(",")]
    else:
        watchlist = None

    print(f"[...] Escaneando {len(watchlist or [])} tickers...", file=sys.stderr)
    result = scan_penny_stocks(filters, watchlist=watchlist)
    _print_json(result.model_dump())
    return 0


# ---------------------------------------------------------------------------
# Subcomando: log
# ---------------------------------------------------------------------------


def cmd_log(args: argparse.Namespace) -> int:
    entry = TradeLog(
        ticker=args.ticker.upper(),
        entry_price=args.entry,
        exit_price=args.exit if args.exit else None,
        size_usd=args.size,
        note=args.note or "",
        is_paper=True,  # sempre paper/micro — sem execução real
    )
    journal.append(entry)
    out = {
        "status": "registrado",
        "entry": entry.model_dump(),
        "journal_path": str(journal.path),
    }
    _print_json(out)
    return 0


# ---------------------------------------------------------------------------
# Subcomando: postmortem
# ---------------------------------------------------------------------------


def cmd_postmortem(args: argparse.Namespace) -> int:
    ticker = args.symbol.upper()
    result = journal.postmortem(ticker)
    _print_json(result)
    return 0


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m experts.pennylab.cli",
        description=(
            "F51 WhaleTrap Lab / SuperEzio PennyLab\n"
            "Sistema de análise laboratorial de penny stocks.\n"
            "NÃO executa ordens. NÃO decide sozinho. Marco decide."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- ticker ---
    p_ticker = sub.add_parser("ticker", help="Análise completa de um ticker")
    p_ticker.add_argument("symbol", help="Símbolo do ativo (ex: ABCD, SNDL)")
    p_ticker.add_argument(
        "--input",
        "-i",
        metavar="FILE",
        help="Arquivo JSON com dados de sinal (para testes sem provedor real)",
    )

    # --- scan ---
    p_scan = sub.add_parser("scan", help="Listar tickers candidatos via DataHub")
    p_scan.add_argument(
        "--max-price",
        type=float,
        default=MAX_PRICE_PENNY,
        help=f"Preço máximo (padrão: {MAX_PRICE_PENNY})",
    )
    p_scan.add_argument(
        "--min-volume",
        type=int,
        default=MIN_VOLUME_PENNY,
        help=f"Volume mínimo (padrão: {MIN_VOLUME_PENNY:,})",
    )
    p_scan.add_argument(
        "--max-spread-pct",
        type=float,
        default=5.0,
        help="Spread máximo em %% (padrão: 5.0)",
    )
    p_scan.add_argument(
        "--tickers",
        default=None,
        help="Lista de tickers separados por vírgula (padrão: watchlist interna)",
    )

    # --- log ---
    p_log = sub.add_parser("log", help="Registrar trade experimental no journal")
    p_log.add_argument("--ticker", required=True)
    p_log.add_argument("--entry", type=float, required=True, help="Preço de entrada")
    p_log.add_argument(
        "--exit", type=float, default=None, help="Preço de saída (opcional)"
    )
    p_log.add_argument("--size", type=float, required=True, help="Tamanho em USD")
    p_log.add_argument("--note", default="", help="Nota livre")

    # --- postmortem ---
    p_pm = sub.add_parser("postmortem", help="Resumo de trades de um ticker")
    p_pm.add_argument("symbol", help="Símbolo do ativo")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "ticker": cmd_ticker,
        "scan": cmd_scan,
        "log": cmd_log,
        "postmortem": cmd_postmortem,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
