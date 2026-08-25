"""Paper Trading Journal - C6: Acompanhar resultado.

Armazena teses de trades paper, registra entradas/saidas, e permite
revisitacao periodica para comparar expectativa com realidade.

Funciona offline - nao depende de IBKR conectado.
"""

from __future__ import annotations

import json
import logging
import os
import threading
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

    # Immutable decision snapshot used only after a terminal outcome.
    # Legacy compatibility field. New learning uses only a calibrated
    # prediction_probability_at_entry with its provenance below.
    confidence_at_entry: float | None = None
    prediction_probability_at_entry: float | None = None
    prediction_class_at_entry: str | None = None
    calibration_status: str = "unknown"
    model_id: str = ""
    forecast_as_of: str = ""
    forecast_horizon: str | int | None = None
    risk_at_entry: float | None = None
    fees: float = 0.0
    slippage: float = 0.0
    expert_attribution: dict[str, float] = field(default_factory=dict)
    expert_predictions: dict[str, dict[str, Any]] = field(default_factory=dict)

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
        configured = str(os.getenv("SUPEREZIO_PAPER_JOURNAL_PATH") or "").strip()
        self._path = path or (Path(configured) if configured else DEFAULT_JOURNAL_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_environment = (
            "operator" if self._path.resolve() == _PRODUCTION_JOURNAL else "isolated"
        )
        # Reentrant so the read-modify-write methods can hold the lock across
        # their own calls to _read_all/_rewrite (same pattern as
        # TradeWorkflowStore._lock).
        #
        # SCOPE: this closes the intra-process race only. Writers also live in
        # separate processes (agent_server and the Mangala scan both reach this
        # journal), and a cross-process lost update remains possible. Closing
        # that needs an OS file lock and is tracked separately.
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def storage_environment(self) -> str:
        """Environment stamped onto new rows written by this journal."""

        return self._storage_environment

    def _assert_write_allowed(self) -> None:
        """Prevent pytest from ever mutating the operator's journal."""

        if self._path.resolve() == _PRODUCTION_JOURNAL and os.getenv("PYTEST_CURRENT_TEST"):
            raise RuntimeError(
                "Tests may not write to the operator paper journal; inject a temporary path"
            )

    def _prepare_new_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(entry)
        claimed_environment = str(
            prepared.get("storage_environment") or self._storage_environment
        ).strip()
        if claimed_environment != self._storage_environment:
            raise RuntimeError(
                f"Journal environment mismatch: row={claimed_environment} "
                f"storage={self._storage_environment}"
            )
        prepared["storage_environment"] = self._storage_environment
        prepared["provenance"] = str(prepared.get("provenance") or "paper_journal").strip()
        if not prepared["provenance"]:
            raise RuntimeError("Journal provenance is required")
        return prepared

    def _quarantine_raw_line(self, raw_line: str) -> None:
        """Preserva uma linha corrompida antes que um _rewrite a apague.

        Append puro num arquivo-irmao: nunca trunca e nunca levanta para o
        chamador. A leitura precede o _rewrite em todos os caminhos de escrita,
        entao a linha e salva antes de poder ser destruida.
        """
        try:
            quarantine_path = self._path.with_name(self._path.name + ".quarantine")
            with open(quarantine_path, "a", encoding="utf-8") as f:
                f.write(raw_line.rstrip("\n") + "\n")
        except OSError:
            logger.exception("Could not quarantine corrupt journal line")

    def _read_all(self) -> list[dict[str, Any]]:
        """Le todas as entradas do journal."""
        if not self._path.exists():
            return []
        entries = []
        with self._lock, open(self._path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        self._quarantine_raw_line(raw_line)
                        logger.warning("Quarantined corrupt journal line")
        return entries

    def _append(self, entry: dict[str, Any]) -> None:
        """Adiciona uma entrada ao journal."""
        self._assert_write_allowed()
        prepared = self._prepare_new_entry(entry)
        with self._lock, open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(prepared, ensure_ascii=False) + "\n")

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
        self._assert_write_allowed()
        # Escrita atomica: grava num temporario no mesmo diretorio e troca com
        # os.replace. open(path, "w") truncava o journal ANTES de escrever, entao
        # um crash no meio da gravacao deixava o arquivo vazio ou pela metade.
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        with self._lock:
            with open(tmp_path, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)

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

    def add_trade(self, trade: dict[str, Any]) -> str:
        """Append a trade/ticket dict using the journal's canonical schema.

        Engines historically passed lightweight dicts here. Keep the method
        strict enough for audit while preserving extra broker metadata.
        """
        now = datetime.now(timezone.utc).isoformat()
        ticker = str(trade.get("ticker") or trade.get("symbol") or "").strip().upper()
        if not ticker:
            raise ValueError("trade ticker/symbol is required")

        direction = (
            str(trade.get("direction") or trade.get("side") or trade.get("action") or "long")
            .strip()
            .lower()
        )
        if direction == "buy":
            direction = "long"
        elif direction == "sell":
            direction = "short"
        if direction not in {"long", "short"}:
            direction = "long"

        trade_id = str(
            trade.get("trade_id")
            or trade.get("order_id")
            or f"paper-{ticker}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        )
        entry_price = float(
            trade.get("entry_price") or trade.get("limit_price") or trade.get("price") or 0.0
        )
        shares = float(trade.get("shares") or trade.get("qty") or trade.get("quantity") or 0.0)

        canonical = PaperTrade(
            trade_id=trade_id,
            ticker=ticker,
            thesis=str(trade.get("thesis") or trade.get("message") or ""),
            direction=direction,
            entry_date=str(trade.get("entry_date") or trade.get("timestamp") or now),
            entry_price=entry_price,
            shares=shares,
            entry_reasoning=str(
                trade.get("entry_reasoning") or trade.get("reasoning") or trade.get("thesis") or ""
            ),
            verdict_at_entry=str(trade.get("verdict_at_entry") or trade.get("verdict") or ""),
            risk_assessment=str(trade.get("risk_assessment") or trade.get("risk") or ""),
            expected_holding_period=str(
                trade.get("expected_holding_period") or trade.get("horizon") or "unknown"
            ),
            confidence_at_entry=trade.get("confidence_at_entry"),
            prediction_probability_at_entry=trade.get("prediction_probability_at_entry"),
            prediction_class_at_entry=trade.get("prediction_class_at_entry"),
            calibration_status=str(trade.get("calibration_status") or "unknown"),
            model_id=str(trade.get("model_id") or ""),
            forecast_as_of=str(trade.get("forecast_as_of") or ""),
            forecast_horizon=trade.get("forecast_horizon"),
            risk_at_entry=trade.get("risk_at_entry"),
            fees=float(trade.get("fees") or 0.0),
            slippage=float(trade.get("slippage") or 0.0),
            expert_attribution=dict(trade.get("expert_attribution") or {}),
            expert_predictions=dict(trade.get("expert_predictions") or {}),
            tags=list(trade.get("tags") or []),
        ).to_dict()

        for key, value in trade.items():
            if key not in canonical:
                canonical[key] = value
        canonical["updated_at"] = now
        self._append(canonical)
        logger.info("Paper journal row added: %s %s", trade_id, ticker)
        return trade_id

    def record_broker_order(
        self,
        *,
        broker_order_id: str,
        ticker: str,
        action: str,
        qty: float,
        limit_price: float | None,
        status: str,
        thesis: str,
        verdict_at_entry: str,
        risk_assessment: str,
        expected_holding_period: str = "unknown",
        broker_perm_id: str | None = None,
        broker_tws_order_id: str | None = None,
        broker_client_id: str | None = None,
        market_data: dict[str, Any] | None = None,
    ) -> str:
        """Record an IBKR submitted order without claiming a fill."""
        clean_ticker = str(ticker).strip().upper()
        trade_id = f"broker-{broker_order_id or broker_perm_id or clean_ticker}"
        tags = ["broker_submitted", "awaiting_fill", "ibkr"]
        return self.add_trade(
            {
                "trade_id": trade_id,
                "ticker": clean_ticker,
                "action": action.upper(),
                "direction": "long" if action.lower() == "buy" else "short",
                "qty": qty,
                "shares": qty,
                "entry_price": limit_price or 0.0,
                "limit_price": limit_price,
                "thesis": thesis,
                "entry_reasoning": thesis,
                "verdict_at_entry": verdict_at_entry,
                "risk_assessment": risk_assessment,
                "expected_holding_period": expected_holding_period,
                "status": "submitted",
                "broker": "IBKR",
                "broker_order_id": broker_order_id,
                "broker_perm_id": broker_perm_id,
                "broker_tws_order_id": broker_tws_order_id,
                "broker_client_id": broker_client_id,
                "broker_order_status": status,
                "broker_fill_confirmed": False,
                "source": "ibkr_order_ticket",
                "market_data": market_data or {},
                "tags": tags,
            }
        )

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str = "manual",
        exit_date: str | None = None,
    ) -> PaperTrade | None:
        """Fecha um trade existente e registra o resultado.

        O lock cobre leitura E escrita: sem ele, dois fechamentos concorrentes
        leem a mesma lista, cada um aplica a sua mudanca e o segundo _rewrite
        sobrescreve o primeiro — um fechamento perdido em silencio.
        """
        with self._lock:
            entries = self._read_all()
            for i, entry in enumerate(entries):
                if entry.get("trade_id") == trade_id:
                    paper_fields = set(PaperTrade.__dataclass_fields__)
                    trade = PaperTrade(
                        **{
                            k: v
                            for k, v in entry.items()
                            if k in paper_fields and k not in ("created_at", "updated_at")
                        }
                    )
                    trade.created_at = entry.get("created_at", "")
                    trade.updated_at = entry.get("updated_at", "")
                    trade.close_trade(
                        exit_price=exit_price, exit_date=exit_date, exit_reason=exit_reason
                    )
                    updated = entry.copy()
                    updated.update(trade.to_dict())
                    entries[i] = updated
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
        """Adiciona reflexao post-mortem a um trade fechado.

        Mesmo motivo do close_trade: o lock precisa cobrir leitura e escrita.
        """
        with self._lock:
            entries = self._read_all()
            for i, entry in enumerate(entries):
                if entry.get("trade_id") == trade_id:
                    paper_fields = set(PaperTrade.__dataclass_fields__)
                    trade = PaperTrade(
                        **{
                            k: v
                            for k, v in entry.items()
                            if k in paper_fields and k not in ("created_at", "updated_at")
                        }
                    )
                    trade.created_at = entry.get("created_at", "")
                    trade.updated_at = entry.get("updated_at", "")
                    trade.add_reflection(
                        thesis_correct=thesis_correct,
                        what_went_right=what_went_right,
                        what_went_wrong=what_went_wrong,
                        lesson_learned=lesson_learned,
                    )
                    updated = entry.copy()
                    updated.update(trade.to_dict())
                    entries[i] = updated
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
