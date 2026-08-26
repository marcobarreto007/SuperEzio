"""
LabJournal — Storage JSONL para trades experimentais e postmortems
===================================================================
Armazenamento simples em JSONL (uma entrada JSON por linha).
Sem SQLite para manter dependências zero além de stdlib + pydantic.

Operações:
  - append(entry)        → adiciona TradeLog
  - load_ticker(ticker)  → filtra entradas por ticker
  - all_entries()        → carrega tudo
  - postmortem(ticker)   → resumo de PnL e lições
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import LAB_JOURNAL_PATH
from .schemas import TradeLog


class LabJournal:
    """
    Diário de trades experimentais em formato JSONL.
    Thread-safety: não garantida (uso pessoal/local, single-process).
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path: Path = path or LAB_JOURNAL_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def append(self, entry: TradeLog) -> None:
        """Salva uma entrada de trade no journal."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    def append_dict(self, data: dict[str, Any]) -> None:
        """Salva dicionário genérico (para snapshots de report, etc.)."""
        data.setdefault("logged_at", datetime.now(UTC).isoformat())
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def all_entries(self) -> list[dict[str, Any]]:
        """Carrega todas as entradas do journal."""
        if not self.path.exists():
            return []
        entries = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # linha corrompida — ignora silenciosamente
        return entries

    def load_ticker(self, ticker: str) -> list[dict[str, Any]]:
        """Filtra entradas por ticker (case-insensitive)."""
        t = ticker.upper()
        return [e for e in self.all_entries() if e.get("ticker", "").upper() == t]

    # ------------------------------------------------------------------
    # Postmortem
    # ------------------------------------------------------------------

    def postmortem(self, ticker: str) -> dict[str, Any]:
        """
        Gera resumo de PnL e estatísticas para um ticker.
        Não faz análise LLM — apenas matemática simples.
        """
        entries = self.load_ticker(ticker)
        if not entries:
            return {
                "ticker": ticker,
                "status": "sem_registros",
                "message": f"Nenhuma entrada encontrada no journal para {ticker}",
            }

        completed = [e for e in entries if e.get("exit_price") and e.get("entry_price")]
        open_positions = [e for e in entries if not e.get("exit_price")]

        pnl_list = []
        for e in completed:
            entry_p = e.get("entry_price", 0)
            exit_p = e.get("exit_price", 0)
            if entry_p and entry_p > 0:
                pnl_pct = (exit_p - entry_p) / entry_p * 100
                pnl_list.append(pnl_pct)

        total_size = sum(e.get("size_usd", 0) for e in entries)
        avg_pnl = sum(pnl_list) / len(pnl_list) if pnl_list else None
        wins = sum(1 for p in pnl_list if p > 0)
        losses = len(pnl_list) - wins

        return {
            "ticker": ticker,
            "total_trades": len(entries),
            "completed": len(completed),
            "open": len(open_positions),
            "total_size_usd": round(total_size, 2),
            "avg_pnl_pct": round(avg_pnl, 2) if avg_pnl is not None else None,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(pnl_list), 3) if pnl_list else None,
            "best_pnl_pct": round(max(pnl_list), 2) if pnl_list else None,
            "worst_pnl_pct": round(min(pnl_list), 2) if pnl_list else None,
            "notes": [e.get("note", "") for e in entries if e.get("note")],
        }


# Instância singleton para uso direto via import
journal = LabJournal()
