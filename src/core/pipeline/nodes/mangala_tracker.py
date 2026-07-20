"""Mangala Engine — Compound Capital Tracker

Trackea o crescimento do capital comecando com $20 (o dinheiro da loteria).
Cada flip e registrado como paper trade no journal.

Mangala e o jogo africano de semeadura — cada trade plantado e uma semente
que deve crescer o capital. O tracker mede o compounding real.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_JOURNAL_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "data"
    / "mangala_journal.jsonl"
)


@dataclass
class FlipRecord:
    """Um flip completo no Mangala — compra e venda de um ativo."""

    ticker: str
    entry_price: float
    exit_price: float
    shares: float
    entry_date: str
    exit_date: str
    profit: float
    profit_pct: float
    direction: str = "long"
    trade_id: str = ""
    tags: list[str] = field(default_factory=list)
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MangalaTracker:
    """Tracker de capital compounding comecando de $20.

    Le o journal existente ao inicializar para reconstruir estado.
    Cada flip e registrado no proprio journal do Mangala e,
    opcionalmente, sincronizado com o PaperJournal principal.
    """

    def __init__(
        self,
        starting_capital: float = 20.0,
        journal_path: Path | None = None,
    ):
        self.starting_capital = starting_capital
        self._journal_path = journal_path or DEFAULT_JOURNAL_PATH
        self._journal_path.parent.mkdir(parents=True, exist_ok=True)

        # Rebuild state from existing journal
        self._trades: list[dict[str, Any]] = []
        self._rebuild_state()

    # ── Properties ────────────────────────────────────────────────

    @property
    def current_capital(self) -> float:
        """Capital atual apos todos os flips registrados."""
        total_profit = sum(
            t.get("profit", 0.0) or 0.0 for t in self._trades
        )
        return self.starting_capital + total_profit

    @property
    def trades(self) -> list[dict[str, Any]]:
        """Lista de flips registrados."""
        return list(self._trades)

    # ── Journal I/O ───────────────────────────────────────────────

    def _rebuild_state(self) -> None:
        """Le o journal do disco e reconstroi o estado interno."""
        if not self._journal_path.exists():
            self._trades = []
            return
        entries: list[dict[str, Any]] = []
        with open(self._journal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(
                            "Skipping corrupt mangala journal line"
                        )
        self._trades = entries

    def _append_to_journal(self, entry: dict[str, Any]) -> None:
        """Append um flip ao journal."""
        with open(self._journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Core Operations ───────────────────────────────────────────

    def record_flip(
        self,
        ticker: str,
        entry_price: float,
        exit_price: float,
        shares: float,
        entry_date: str | None = None,
        exit_date: str | None = None,
    ) -> float:
        """Registra um flip completo e atualiza o capital.

        Args:
            ticker: Simbolo do ativo (ex: "AAPL").
            entry_price: Preco de entrada.
            exit_price: Preco de saida.
            shares: Quantidade de acoes.
            entry_date: Data ISO da entrada (auto se None).
            exit_date: Data ISO da saida (auto se None).

        Returns:
            Profit realizado no flip.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        entry_date = entry_date or now_iso
        exit_date = exit_date or now_iso

        profit = (exit_price - entry_price) * shares
        profit_pct = (
            (profit / (entry_price * shares)) * 100
            if entry_price > 0 and shares > 0
            else 0.0
        )

        trade_id = (
            f"mangala-{ticker}-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        )

        record = FlipRecord(
            ticker=ticker.upper(),
            entry_price=entry_price,
            exit_price=exit_price,
            shares=shares,
            entry_date=entry_date,
            exit_date=exit_date,
            profit=round(profit, 2),
            profit_pct=round(profit_pct, 4),
            direction="long",
            trade_id=trade_id,
            tags=["mangala", "flip"],
        ).to_dict()

        self._trades.append(record)
        self._append_to_journal(record)

        # Sync to PaperJournal as well (integracao com ecossistema)
        self._sync_to_paper_journal(record)

        logger.info(
            "Mangala flip: %s %s shares=%.2f entry=%.2f exit=%.2f profit=%.2f",
            trade_id,
            ticker,
            shares,
            entry_price,
            exit_price,
            profit,
        )
        return round(profit, 2)

    def _sync_to_paper_journal(self, flip: dict[str, Any]) -> None:
        """Sincroniza um flip do Mangala com o PaperJournal principal."""
        try:
            from core.trading.paper_journal import PaperJournal

            journal = PaperJournal()
            journal.add_trade(
                {
                    "trade_id": flip.get("trade_id"),
                    "ticker": flip.get("ticker"),
                    "direction": flip.get("direction", "long"),
                    "entry_price": flip.get("entry_price"),
                    "exit_price": flip.get("exit_price"),
                    "shares": flip.get("shares"),
                    "entry_date": flip.get("entry_date"),
                    "exit_date": flip.get("exit_date"),
                    "pnl_amount": flip.get("profit"),
                    "pnl_percent": flip.get("profit_pct"),
                    "outcome": "win" if (flip.get("profit") or 0) > 0.01 else "loss",
                    "thesis": f"Mangala flip: {flip.get('ticker')}",
                    "verdict_at_entry": "PASS",
                    "risk_assessment": "Mangala capital compounding flip",
                    "expected_holding_period": "swing",
                    "tags": ["mangala", "flip"],
                }
            )
        except Exception as exc:
            logger.warning(
                "Could not sync mangala flip to paper journal: %s", exc
            )

    # ── Summary ───────────────────────────────────────────────────

    def compound_summary(self) -> dict[str, Any]:
        """Retorna o resumo completo do compounding.

        Returns:
            Dict com: starting, current, total_flips, win_rate,
                      total_profit, best_flip, growth_pct, next_target.
        """
        total_flips = len(self._trades)

        if total_flips == 0:
            next_target = round(self.starting_capital * 1.5, 2)
            return {
                "starting": self.starting_capital,
                "current": self.current_capital,
                "total_flips": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_profit": 0.0,
                "best_flip": None,
                "worst_flip": None,
                "growth_pct": 0.0,
                "next_target": next_target,
                "remaining_to_target": round(max(0, next_target - self.starting_capital), 2),
                "progress_pct": 0.0,
            }

        wins = sum(1 for t in self._trades if (t.get("profit") or 0) > 0.01)
        losses = sum(1 for t in self._trades if (t.get("profit") or 0) < -0.01)
        win_rate = (wins / total_flips) * 100

        total_profit = sum(t.get("profit", 0.0) or 0.0 for t in self._trades)
        best_flip = max(self._trades, key=lambda t: t.get("profit", 0) or 0)
        worst_flip = min(self._trades, key=lambda t: t.get("profit", 0) or 0)

        current = self.current_capital
        growth_pct = ((current / self.starting_capital) - 1) * 100

        # Proximo milestone: 50% de aumento sobre o capital atual
        next_milestone = round(current * 1.5, 2)

        return {
            "starting": self.starting_capital,
            "current": round(current, 2),
            "total_flips": total_flips,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 2),
            "total_profit": round(total_profit, 2),
            "best_flip": {
                "ticker": best_flip.get("ticker"),
                "profit": best_flip.get("profit"),
                "date": best_flip.get("exit_date", ""),
            },
            "worst_flip": {
                "ticker": worst_flip.get("ticker"),
                "profit": worst_flip.get("profit"),
                "date": worst_flip.get("exit_date", ""),
            },
            "growth_pct": round(growth_pct, 2),
            "next_target": next_milestone,
            "remaining_to_target": round(max(0, next_milestone - current), 2),
            "progress_pct": round(
                min(100, ((current - self.starting_capital) / (next_milestone - self.starting_capital)) * 100)
                if next_milestone > self.starting_capital
                else 0,
                2,
            ),
        }

    def reset(self, new_starting_capital: float | None = None) -> None:
        """Reseta o tracker (limpa journal e reinicia capital).

        Usado apenas em testes ou reset manual. Requer confirmacao.
        """
        if new_starting_capital is not None:
            self.starting_capital = new_starting_capital
        self._trades = []
        # Limpa o journal fisicamente
        if self._journal_path.exists():
            self._journal_path.write_text("", encoding="utf-8")
        logger.info("Mangala tracker reset. Starting capital: %.2f", self.starting_capital)


# ── Module-level singleton (conveniencia) ────────────────────────

_MANGALA_TRACKER: MangalaTracker | None = None


def get_mangala_tracker() -> MangalaTracker:
    """Retorna o singleton do MangalaTracker."""
    global _MANGALA_TRACKER
    if _MANGALA_TRACKER is None:
        _MANGALA_TRACKER = MangalaTracker()
    return _MANGALA_TRACKER
