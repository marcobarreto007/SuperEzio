"""Daily Standup - Relatório diário do Bob.

Bob gera um relatório diário automático:
- Resumo do dia (trades, PnL, XP)
- O que aprendeu
- O que vai fazer amanhã
- Nível atual, próximo objetivo
- Lições recentes
- Métricas de saúde
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_STANDUP_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "daily_standup_log.jsonl"
)


@dataclass
class DailyStandup:
    """Relatório diário do Bob."""

    date: str  # YYYY-MM-DD
    timestamp: str
    # Performance
    trades_today: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    pnl_total: float = 0.0
    pnl_avg: float = 0.0
    # XP
    xp_start: int = 0
    xp_end: int = 0
    xp_gained: int = 0
    level_start: str = ""
    level_end: str = ""
    # Learning
    lessons_learned: int = 0
    patterns_found: int = 0
    top_lessons: list[str] = field(default_factory=list)
    # State
    market_hours_active: float = 6.5  # Horas mercado esteve aberto (default US market)
    learning_cycles: int = 0
    committee_deliberations: int = 0
    # Plans
    tomorrow_focus: list[str] = field(default_factory=list)
    tomorrow_goals: list[str] = field(default_factory=list)
    # Health
    health_score: float = 0.0  # 0-100
    health_status: str = "healthy"  # healthy | caution | danger
    concerns: list[str] = field(default_factory=list)
    # Notes
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "timestamp": self.timestamp,
            "performance": {
                "trades_today": self.trades_today,
                "wins": self.wins,
                "losses": self.losses,
                "win_rate": round(self.win_rate, 3),
                "pnl_total": round(self.pnl_total, 2),
                "pnl_avg": round(self.pnl_avg, 2),
            },
            "xp": {
                "start": self.xp_start,
                "end": self.xp_end,
                "gained": self.xp_gained,
                "level_start": self.level_start,
                "level_end": self.level_end,
            },
            "learning": {
                "lessons_learned": self.lessons_learned,
                "patterns_found": self.patterns_found,
                "top_lessons": self.top_lessons,
            },
            "activity": {
                "market_hours_active": round(self.market_hours_active, 2),
                "learning_cycles": self.learning_cycles,
                "committee_deliberations": self.committee_deliberations,
            },
            "plans": {
                "tomorrow_focus": self.tomorrow_focus,
                "tomorrow_goals": self.tomorrow_goals,
            },
            "health": {
                "score": round(self.health_score, 1),
                "status": self.health_status,
                "concerns": self.concerns,
            },
            "notes": self.notes,
        }


class DailyStandupGenerator:
    """Gerador de relatórios diários."""

    def __init__(
        self,
        log_path: Path | None = None,
    ):
        self._log_path = log_path or DEFAULT_STANDUP_LOG_PATH
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def _save_standup(self, standup: DailyStandup) -> None:
        """Salva standup no disco (append-only)."""
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(standup.to_dict(), ensure_ascii=False) + "\n")

    def _load_journal_trades(self, date_str: str) -> list[dict]:
        """Carrega trades do journal para uma data."""
        try:
            from .paper_journal import PaperJournal

            journal = PaperJournal()
            all_trades = journal.list_all()

            # Filtrar trades da data
            date_trades = []
            for trade in all_trades:
                exit_date = trade.get("exit_date")
                if not exit_date:
                    continue

                try:
                    exit_dt = datetime.fromisoformat(exit_date.replace("Z", "+00:00"))
                    if exit_dt.tzinfo is None:
                        exit_dt = exit_dt.replace(tzinfo=timezone.utc)

                    if exit_dt.date().isoformat() == date_str:
                        date_trades.append(trade)
                except (ValueError, TypeError):
                    continue

            return date_trades
        except ImportError:
            logger.warning("PaperJournal not available for standup")
            return []

    def _load_xp_progress(self, date_str: str) -> tuple[int, int, str, str]:
        """Carrega progresso de XP (start, end, level_start, level_end)."""
        try:
            from .xp_system import get_xp_system

            xp = get_xp_system()
            stats = xp.get_stats()

            # Simplificado: não temos histórico por data
            # Retorna valores atuais como "end"
            return (
                0,  # Start (placeholder)
                stats.total_xp,
                "Novice",  # Start (placeholder)
                stats.level.title,
            )
        except ImportError:
            return 0, 1, "Novice", "Novice"

    def _load_learning_metrics(self, date_str: str) -> tuple[int, int, list[str]]:
        """Carrega métricas de aprendizado."""
        try:
            from .learning_log import LearningLog

            # Buscar lições da data
            learning_log = LearningLog()
            lessons = learning_log.get_recent_lessons(days=1)

            top_lessons = [f"{lesson.get('title', '?')}" for lesson in lessons[:3]]

            # Padrões (placeholder)
            patterns = 0

            return len(lessons), patterns, top_lessons
        except ImportError:
            return 0, 0, []

    def _calculate_health_score(
        self,
        win_rate: float,
        pnl_total: float,
        losses: int,
        consecutive_losses: int = 0,
    ) -> tuple[float, str, list[str]]:
        """Calcula health score (0-100)."""
        score = 100.0
        concerns = []

        # Win rate impact
        if win_rate >= 0.6:
            score += 10
        elif win_rate >= 0.5:
            score += 0
        elif win_rate >= 0.4:
            score -= 10
            concerns.append("Win rate abaixo de 50%")
        else:
            score -= 20
            concerns.append("Win rate crítico")

        # PnL impact
        if pnl_total > 0:
            score += min(10, pnl_total / 100)
        elif pnl_total < -100:
            score -= 20
            concerns.append("Perda diária > $100")
        elif pnl_total < -50:
            score -= 10
            concerns.append("Perda diária > $50")

        # Loss streak impact
        if consecutive_losses >= 5:
            score -= 30
            concerns.append("Loss streak severo")
        elif consecutive_losses >= 3:
            score -= 15
            concerns.append("Loss streak ativo")

        # Clamp
        score = max(0, min(100, score))

        # Status
        if score >= 70:
            status = "healthy"
        elif score >= 50:
            status = "caution"
        else:
            status = "danger"

        return score, status, concerns

    def generate(
        self,
        date_str: str | None = None,
    ) -> DailyStandup:
        """Gera relatório diário.

        Args:
            date_str: Data no formato YYYY-MM-DD (hoje se None)

        Returns:
            Standup completo
        """
        if date_str is None:
            date_str = datetime.now(timezone.utc).date().isoformat()

        # Carregar trades do dia
        trades = self._load_journal_trades(date_str)

        # Métricas de performance
        trades_today = len(trades)
        wins = sum(1 for t in trades if t.get("outcome") == "win")
        losses = sum(1 for t in trades if t.get("outcome") == "loss")
        win_rate = wins / trades_today if trades_today > 0 else 0.5

        pnl_total = sum(t.get("pnl_amount", 0) for t in trades)
        pnl_avg = pnl_total / trades_today if trades_today > 0 else 0

        # XP progress
        xp_start, xp_end, level_start, level_end = self._load_xp_progress(date_str)
        xp_gained = xp_end - xp_start

        # Learning metrics
        lessons_count, patterns_count, top_lessons = self._load_learning_metrics(date_str)

        # Health score
        consecutive_losses = 0  # Placeholder (requer cálculo real)
        health_score, health_status, concerns = self._calculate_health_score(
            win_rate, pnl_total, losses, consecutive_losses
        )

        # Plans para amanhã
        tomorrow_focus = []
        tomorrow_goals = []

        if health_status == "danger":
            tomorrow_focus = ["Focar em preservar capital", "Reduzir tamanho de posições"]
            tomorrow_goals = ["Zero trades por 24h", "Revisar todas as lições recentes"]
        elif health_status == "caution":
            tomorrow_focus = ["Aumentar seletividade", "Focar em setups de alta confiança"]
            tomorrow_goals = ["Máximo 3 trades", "Revisar pain memory antes de cada entrada"]
        else:
            tomorrow_focus = ["Continuar estratégia atual", "Aumentar tamanho em setups validados"]
            tomorrow_goals = [
                "Buscar setups similares aos wins recentes",
                "Aplicar lições aprendidas",
            ]

        # Criar standup
        standup = DailyStandup(
            date=date_str,
            timestamp=datetime.now(timezone.utc).isoformat(),
            trades_today=trades_today,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            pnl_total=pnl_total,
            pnl_avg=pnl_avg,
            xp_start=xp_start,
            xp_end=xp_end,
            xp_gained=xp_gained,
            level_start=level_start,
            level_end=level_end,
            lessons_learned=lessons_count,
            patterns_found=patterns_count,
            top_lessons=top_lessons,
            market_hours_active=6.5,  # Placeholder (horas padrão US market)
            learning_cycles=1 if lessons_count > 0 else 0,
            committee_deliberations=trades_today,  # Um por trade
            tomorrow_focus=tomorrow_focus,
            tomorrow_goals=tomorrow_goals,
            health_score=health_score,
            health_status=health_status,
            concerns=concerns,
            notes="" if pnl_total >= 0 else "Dia de perdas - focar em aprendizado.",
        )

        self._save_standup(standup)
        logger.info(
            "Daily standup generated for %s: health=%s pnl=%.2f", date_str, health_status, pnl_total
        )

        return standup

    def render(
        self,
        standup: DailyStandup | None = None,
        max_chars: int = 1500,
    ) -> str:
        """Renderiza standup como texto.

        Args:
            standup: Standup para renderizar (gera novo se None)
            max_chars: Máximo de caracteres

        Returns:
            Texto do standup
        """
        if standup is None:
            standup = self.generate()

        lines = [
            f"\n{'=' * 60}",
            f"BOB DAILY STANDUP - {standup.date}",
            f"{'=' * 60}",
            "",
            "📊 PERFORMANCE",
            f"  Trades: {standup.trades_today}",
            f"  Wins: {standup.wins} | Losses: {standup.losses}",
            f"  Win Rate: {standup.win_rate:.1%}",
            f"  PnL Total: ${standup.pnl_total:+.2f}",
            f"  PnL Avg: ${standup.pnl_avg:+.2f}",
            "",
            "⭐ XP & LEVEL",
            f"  XP: {standup.xp_start} → {standup.xp_end} (+{standup.xp_gained})",
            f"  Level: {standup.level_start} → {standup.level_end}",
            "",
            "🧠 LEARNING",
            f"  Lessons learned: {standup.lessons_learned}",
            f"  Patterns found: {standup.patterns_found}",
        ]

        if standup.top_lessons:
            lines.append("  Top lessons:")
            for lesson in standup.top_lessons:
                lines.append(f"    - {lesson}")

        lines.extend(
            [
                "",
                f"⚠️ HEALTH: {standup.health_status.upper()} (Score: {standup.health_score:.0f}/100)",
            ]
        )

        if standup.concerns:
            lines.append("  Concerns:")
            for concern in standup.concerns:
                lines.append(f"    - {concern}")

        lines.extend(
            [
                "",
                "📅 PLANS FOR TOMORROW",
                "  Focus:",
            ]
        )

        for focus in standup.tomorrow_focus:
            lines.append(f"    - {focus}")

        lines.append("  Goals:")
        for goal in standup.tomorrow_goals:
            lines.append(f"    - {goal}")

        if standup.notes:
            lines.extend(["", f"📝 Notes: {standup.notes}"])

        lines.append(f"\n{'=' * 60}\n")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n..."

        return result


# Singleton
_daily_standup: DailyStandupGenerator | None = None


def get_daily_standup() -> DailyStandupGenerator:
    """Retorna singleton de DailyStandupGenerator."""
    global _daily_standup
    if _daily_standup is None:
        _daily_standup = DailyStandupGenerator()
        logger.info("DailyStandupGenerator initialized")
    return _daily_standup


if __name__ == "__main__":
    # Test mode
    generator = get_daily_standup()

    standup = generator.generate()

    print(f"\nStandup for {standup.date}:")
    print(f"Health: {standup.health_status} ({standup.health_score:.0f}/100)")
    print(f"PnL: ${standup.pnl_total:+.2f}")
    print(f"XP gained: {standup.xp_gained}")

    print("\n" + generator.render(standup))
