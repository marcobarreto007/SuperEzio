"""Paper Trading Journal - C6: Acompanhar resultado.

Armazena teses de trades paper, registra entradas/saidas, e permite
revisitacao periodica para comparar expectativa com realidade.

Funciona offline - nao depende de IBKR conectado.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_JOURNAL_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "paper_journal.jsonl"
)

# Production guard: the real journal must never be silently truncated.
# Tests use tempfile.NamedTemporaryFile, never this path.
_PRODUCTION_JOURNAL = DEFAULT_JOURNAL_PATH.resolve()


@dataclass
class PaperTrade:
    """Um trade paper completo - da tese ao resultado."""

    trade_id: str
    ticker: str
    thesis: str  # Por que entrou
    direction: str  # "long" | "short"
    entry_date: str  # ISO 8601
    entry_price: float
    shares: float
    entry_reasoning: str  # Dados usados na decisao
    verdict_at_entry: str  # Veredito F51 no momento da entrada
    risk_assessment: str  # Riscos identificados
    expected_holding_period: str  # "day_trade" | "swing" | "position" | "long_term"

    # Saida (preenchida no fechamento)
    exit_date: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = (
        None  # "take_profit" | "stop_loss" | "thesis_broken" | "time_exit" | "manual"
    )

    # Resultado
    pnl_amount: float | None = None
    pnl_percent: float | None = None
    outcome: str | None = None  # "win" | "loss" | "breakeven" | "abandoned"

    # Reflexao post-mortem
    thesis_correct: bool | None = None  # A tese se confirmou?
    what_went_right: str | None = None
    what_went_wrong: str | None = None
    lesson_learned: str | None = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)

    def close_trade(
        self,
        exit_price: float,
        exit_date: str | None = None,
        exit_reason: str = "manual",
    ) -> None:
        """Fecha o trade e calcula PnL."""
        self.exit_price = exit_price
        self.exit_date = exit_date or datetime.now(timezone.utc).isoformat()
        self.exit_reason = exit_reason

        if self.direction == "long":
            self.pnl_amount = (exit_price - self.entry_price) * self.shares
        else:
            self.pnl_amount = (self.entry_price - exit_price) * self.shares

        if self.entry_price > 0:
            self.pnl_percent = (self.pnl_amount / (self.entry_price * self.shares)) * 100

        if self.pnl_amount is not None:
            if self.pnl_amount > 0.01:
                self.outcome = "win"
            elif self.pnl_amount < -0.01:
                self.outcome = "loss"
            else:
                self.outcome = "breakeven"

        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_reflection(
        self,
        thesis_correct: bool,
        what_went_right: str = "",
        what_went_wrong: str = "",
        lesson_learned: str = "",
    ) -> None:
        """Registra reflexao post-mortem."""
        self.thesis_correct = thesis_correct
        self.what_went_right = what_went_right or None
        self.what_went_wrong = what_went_wrong or None
        self.lesson_learned = lesson_learned or None
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PaperJournal:
    """Journal de trades paper - append-only JSONL."""

    def __init__(self, path: Path | None = None):
        self._path = path or DEFAULT_JOURNAL_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def _read_all(self) -> list[dict[str, Any]]:
        """Le todas as entradas do journal."""
        if not self._path.exists():
            return []
        entries = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping corrupt journal line")
        return entries

    def _append(self, entry: dict[str, Any]) -> None:
        """Adiciona uma entrada ao journal."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _rewrite(self, entries: list[dict[str, Any]]) -> None:
        """Reescreve o journal inteiro (usado para updates).

        Guard: recusa truncar o journal de producao (escrever zero entradas).
        Isso impede que um bug ou rm -f acidental silencie o trilho de auditoria.
        """
        resolved = self._path.resolve()
        if resolved == _PRODUCTION_JOURNAL and len(entries) == 0:
            raise RuntimeError(
                f"Refusing to truncate production journal at {resolved}. "
                f"The production journal is append-only. "
                f"To reset it, delete the file manually with explicit intent."
            )
        with open(self._path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def open_trade(self, trade: PaperTrade) -> str:
        """Abre um novo trade paper. Retorna o trade_id."""
        self._append(trade.to_dict())
        logger.info(
            "Paper trade opened: %s %s %s @ %.2f",
            trade.trade_id,
            trade.ticker,
            trade.direction,
            trade.entry_price,
        )
        return trade.trade_id

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str = "manual",
        exit_date: str | None = None,
    ) -> PaperTrade | None:
        """Fecha um trade existente e registra o resultado."""
        entries = self._read_all()
        for i, entry in enumerate(entries):
            if entry.get("trade_id") == trade_id:
                trade = PaperTrade(
                    **{k: v for k, v in entry.items() if k != "created_at" and k != "updated_at"}
                )
                trade.created_at = entry.get("created_at", "")
                trade.updated_at = entry.get("updated_at", "")
                trade.close_trade(
                    exit_price=exit_price, exit_date=exit_date, exit_reason=exit_reason
                )
                entries[i] = trade.to_dict()
                self._rewrite(entries)
                logger.info(
                    "Paper trade closed: %s outcome=%s pnl=%.2f",
                    trade_id,
                    trade.outcome,
                    trade.pnl_amount or 0,
                )
                return trade
        logger.warning("Trade not found: %s", trade_id)
        return None

    def add_reflection(
        self,
        trade_id: str,
        thesis_correct: bool,
        what_went_right: str = "",
        what_went_wrong: str = "",
        lesson_learned: str = "",
    ) -> PaperTrade | None:
        """Adiciona reflexao post-mortem a um trade fechado."""
        entries = self._read_all()
        for i, entry in enumerate(entries):
            if entry.get("trade_id") == trade_id:
                trade = PaperTrade(
                    **{k: v for k, v in entry.items() if k not in ("created_at", "updated_at")}
                )
                trade.created_at = entry.get("created_at", "")
                trade.updated_at = entry.get("updated_at", "")
                trade.add_reflection(
                    thesis_correct=thesis_correct,
                    what_went_right=what_went_right,
                    what_went_wrong=what_went_wrong,
                    lesson_learned=lesson_learned,
                )
                entries[i] = trade.to_dict()
                self._rewrite(entries)
                logger.info(
                    "Reflection added to trade: %s thesis_correct=%s", trade_id, thesis_correct
                )
                return trade
        logger.warning("Trade not found for reflection: %s", trade_id)
        return None

    def get_trade(self, trade_id: str) -> dict[str, Any] | None:
        """Busca um trade especifico pelo ID."""
        for entry in self._read_all():
            if entry.get("trade_id") == trade_id:
                return entry
        return None

    def list_open(self) -> list[dict[str, Any]]:
        """Lista trades abertos (sem saida)."""
        return [e for e in self._read_all() if e.get("exit_date") is None]

    def list_closed(self) -> list[dict[str, Any]]:
        """Lista trades fechados (com saida e resultado)."""
        return [e for e in self._read_all() if e.get("exit_date") is not None]

    def list_all(self) -> list[dict[str, Any]]:
        """Lista todos os trades."""
        return self._read_all()

    def get_stats(self) -> dict[str, Any]:
        """Estatisticas agregadas do journal."""
        closed = self.list_closed()
        total = len(closed)
        wins = sum(1 for t in closed if t.get("outcome") == "win")
        losses = sum(1 for t in closed if t.get("outcome") == "loss")
        breakeven = sum(1 for t in closed if t.get("outcome") == "breakeven")

        total_pnl = sum(t.get("pnl_amount", 0) or 0 for t in closed)
        avg_pnl_pct = sum(t.get("pnl_percent", 0) or 0 for t in closed) / total if total > 0 else 0
        win_rate = (wins / total * 100) if total > 0 else 0

        thesis_correct_count = sum(1 for t in closed if t.get("thesis_correct") is True)
        thesis_wrong_count = sum(1 for t in closed if t.get("thesis_correct") is False)
        thesis_accuracy = (
            thesis_correct_count / (thesis_correct_count + thesis_wrong_count) * 100
            if (thesis_correct_count + thesis_wrong_count) > 0
            else 0
        )

        return {
            "total_trades": len(self._read_all()),
            "open_trades": len(self.list_open()),
            "closed_trades": total,
            "wins": wins,
            "losses": losses,
            "breakeven": breakeven,
            "win_rate_pct": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_percent": round(avg_pnl_pct, 4),
            "thesis_accuracy_pct": round(thesis_accuracy, 2),
            "has_reflections": sum(1 for t in closed if t.get("lesson_learned")),
            "path": str(self._path),
        }

    def count(self) -> int:
        """Numero total de trades no journal."""
        return len(self._read_all())
