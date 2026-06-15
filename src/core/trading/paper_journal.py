"""Paper Trading Journal - C6: Acompanhar resultado.

Armazena teses de trades paper, registra entradas/saidas, e permite
revisitacao periodica para comparar expectativa com realidade.

Funciona offline - nao depende de IBKR conectado.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_JOURNAL_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "paper_journal.jsonl"
)

# Production guard: the real journal must never be silently truncated.
# Tests use tempfile.NamedTemporaryFile, never this path.
_PRODUCTION_JOURNAL = DEFAULT_JOURNAL_PATH.resolve()


def _parse_utc_datetime(value: Any) -> datetime | None:
    """Parse ISO timestamps used by the journal, accepting both Z and offsets."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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

    def review_aged_closed_theses(
        self,
        min_age_days: int = 14,
        now: datetime | None = None,
        *,
        record_memory: bool = True,
        memory: Any | None = None,
        session_id: str = "paper_journal",
    ) -> list[dict[str, Any]]:
        """Close C6 for trades old enough: thesis vs reality, post-mortem, memory.

        The operation is idempotent. A trade tagged with ``thesis_closed`` is not
        reviewed again, which avoids duplicate conversation-memory entries.
        """
        if min_age_days < 0:
            raise ValueError("min_age_days must be >= 0")

        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        reference = reference.astimezone(timezone.utc)
        cutoff = reference - timedelta(days=min_age_days)

        entries = self._read_all()
        reviewed: list[dict[str, Any]] = []
        updated_at = datetime.now(timezone.utc).isoformat()

        for entry in entries:
            if not entry.get("exit_date") or not entry.get("outcome"):
                continue

            tags = list(entry.get("tags") or [])
            if "thesis_closed" in tags:
                continue

            entry_dt = _parse_utc_datetime(entry.get("entry_date"))
            if entry_dt is None or entry_dt > cutoff:
                continue

            outcome = str(entry.get("outcome") or "")
            inferred_thesis_correct = outcome == "win"
            thesis_correct = entry.get("thesis_correct")
            if thesis_correct is None:
                thesis_correct = inferred_thesis_correct
                entry["thesis_correct"] = thesis_correct

            if thesis_correct:
                entry["what_went_right"] = entry.get("what_went_right") or (
                    "Outcome confirmed the original paper thesis after the review window."
                )
                entry["what_went_wrong"] = entry.get("what_went_wrong") or None
            else:
                entry["what_went_wrong"] = entry.get("what_went_wrong") or (
                    "Outcome did not confirm the original paper thesis after the review window."
                )
                entry["what_went_right"] = entry.get("what_went_right") or None

            if not entry.get("lesson_learned"):
                entry["lesson_learned"] = (
                    f"C6 post-mortem: {entry.get('ticker', 'UNKNOWN')} thesis "
                    f"{'confirmed' if thesis_correct else 'failed'}; "
                    f"outcome={outcome}; pnl=${float(entry.get('pnl_amount') or 0):.2f}."
                )

            tags.append("thesis_closed")
            entry["tags"] = tags
            entry["updated_at"] = updated_at

            entry_age = reference - entry_dt
            reviewed.append(
                {
                    "trade_id": entry.get("trade_id"),
                    "ticker": entry.get("ticker"),
                    "age_days": int(entry_age.total_seconds() // 86400),
                    "outcome": outcome,
                    "pnl_amount": entry.get("pnl_amount"),
                    "thesis_correct": bool(thesis_correct),
                    "memory_recorded": False,
                }
            )

        if not reviewed:
            return []

        self._rewrite(entries)

        if record_memory:
            memory_client = memory
            if memory_client is None:
                try:
                    from core.memory.conversation_memory import get_conversation_memory

                    memory_client = get_conversation_memory()
                except Exception as exc:
                    logger.warning("Could not load conversation memory for thesis close: %s", exc)
                    memory_client = None

            if memory_client is not None and hasattr(memory_client, "add_turn"):
                reviewed_by_id = {item["trade_id"]: item for item in reviewed}
                for entry in entries:
                    trade_id = entry.get("trade_id")
                    review = reviewed_by_id.get(trade_id)
                    if review is None:
                        continue
                    try:
                        memory_client.add_turn(
                            session_id=session_id,
                            user_message=f"C6 thesis close: {entry.get('ticker', '')} {trade_id}",
                            bob_response=(
                                f"Thesis closed for {entry.get('ticker', '')}: "
                                f"outcome={entry.get('outcome')}, "
                                f"thesis_correct={entry.get('thesis_correct')}, "
                                f"pnl={entry.get('pnl_amount')}"
                            ),
                            context_summary="Automated 14-day paper trade post-mortem.",
                            ticker_discussed=str(entry.get("ticker") or ""),
                            thesis_formed=str(entry.get("thesis") or ""),
                            verdict=str(entry.get("outcome") or ""),
                            confidence=1.0,
                            tags=["thesis_closed", "paper_trade", "c6"],
                            category="thesis_closed",
                        )
                        review["memory_recorded"] = True
                    except Exception as exc:
                        logger.warning(
                            "Could not record thesis close for %s in memory: %s",
                            trade_id,
                            exc,
                        )

        return reviewed

    def count(self) -> int:
        """Numero total de trades no journal."""
        return len(self._read_all())
