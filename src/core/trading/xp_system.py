"""XP System - Experience Points & Levels for Bob.

Bob ganha XP por trades bem-sucedidos e perde XP por perdas.
O "fator de dor" faz com que perdas grandes pesem mais na memória.

Níveis:
1-10:   Novice (Aprendiz)
11-25:  Junior
26-50:  Mid-Level
51-75:  Senior
76-90:  Expert
91-99:  Master
100:    Grandmaster (Bob máximo)

Dor:
- Perda <$100: peso 1x
- Perda $100-500: peso 2x
- Perda >$500: peso 5x, flag "trauma"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_XP_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "xp_log.jsonl"
)


class Level(Enum):
    """Níveis de experiência do Bob."""
    NOVICE = (1, 10, "Aprendiz")
    JUNIOR = (11, 25, "Junior")
    MID_LEVEL = (26, 50, "Mid-Level")
    SENIOR = (51, 75, "Senior")
    EXPERT = (76, 90, "Expert")
    MASTER = (91, 99, "Master")
    GRANDMASTER = (100, 100, "Grandmaster")

    @classmethod
    def from_xp(cls, xp: int) -> "Level":
        """Retorna nível baseado em XP."""
        for level in cls:
            min_xp, max_xp, _ = level.value
            if min_xp <= xp <= max_xp:
                return level
        return Level.NOVICE

    @property
    def title(self) -> str:
        return self.value[2]

    @property
    def min_xp(self) -> int:
        return self.value[0]

    @property
    def max_xp(self) -> int:
        return self.value[1]

    @property
    def range(self) -> tuple[int, int]:
        return (self.min_xp, self.max_xp)


@dataclass
class XPEvent:
    """Um evento de ganho ou perda de XP."""
    event_id: str
    timestamp: str
    type: str  # "gain" | "loss"
    amount: int
    source: str  # "trade_win", "trade_loss", "lesson", "streak", etc.
    context: dict[str, Any] = field(default_factory=dict)
    trade_id: str | None = None
    pain_factor: float = 1.0  # Multiplicador de dor
    trauma: bool = False  # Se True, evento marcado como trauma

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "amount": self.amount,
            "source": self.source,
            "context": self.context,
            "trade_id": self.trade_id,
            "pain_factor": self.pain_factor,
            "trauma": self.trauma,
        }


@dataclass
class XPStats:
    """Estatísticas atuais do XP."""
    total_xp: int
    level: Level
    progress: float  # 0-100 dentro do nível atual
    next_level_xp: int
    current_level_xp: int
    events_count: int
    gains_count: int
    losses_count: int
    traumas_count: int
    last_updated: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_xp": self.total_xp,
            "level": self.level.name,
            "level_title": self.level.title,
            "level_range": list(self.level.range),
            "progress": round(self.progress, 2),
            "next_level_xp": self.next_level_xp,
            "current_level_xp": self.current_level_xp,
            "events_count": self.events_count,
            "gains_count": self.gains_count,
            "losses_count": self.losses_count,
            "traumas_count": self.traumas_count,
            "last_updated": self.last_updated,
        }


class XPSystem:
    """Sistema de XP do Bob."""

    def __init__(self, path: Path | None = None, initial_xp: int = 1):
        self._path = path or DEFAULT_XP_LOG_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

        self._xp = initial_xp
        self._events: list[XPEvent] = []
        self._gains_count = 0
        self._losses_count = 0
        self._traumas_count = 0

        self._load()

    def _load(self) -> None:
        """Carrega eventos do disco."""
        if not self._path.exists():
            return

        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = XPEvent(**data)
                    self._events.append(event)

                    # Recalcular XP
                    if event.type == "gain":
                        self._xp += event.amount
                        self._gains_count += 1
                    else:
                        self._xp -= abs(event.amount)
                        self._losses_count += 1
                        if event.trauma:
                            self._traumas_count += 1
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Skipping corrupt XP event: %s", e)

        # XP não pode ser negativo
        self._xp = max(1, self._xp)

    def _save(self, event: XPEvent) -> None:
        """Salva evento no disco (append-only)."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def _generate_event_id(self) -> str:
        """Gera ID único para evento."""
        return f"xp_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{len(self._events)}"

    def get_level(self) -> Level:
        """Retorna nível atual do Bob."""
        return Level.from_xp(self._xp)

    def get_stats(self) -> XPStats:
        """Retorna estatísticas completas do XP."""
        level = self.get_level()
        min_xp, max_xp = level.range

        # Progresso dentro do nível (0-100)
        if level == Level.GRANDMASTER:
            progress = 100.0
        else:
            level_range = max_xp - min_xp
            xp_in_level = self._xp - min_xp
            progress = (xp_in_level / level_range) * 100 if level_range > 0 else 0

        return XPStats(
            total_xp=self._xp,
            level=level,
            progress=progress,
            next_level_xp=max_xp,
            current_level_xp=min_xp,
            events_count=len(self._events),
            gains_count=self._gains_count,
            losses_count=self._losses_count,
            traumas_count=self._traumas_count,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

    def _calculate_pain_factor(self, loss_amount: float, context: dict[str, Any]) -> tuple[float, bool]:
        """Calcula fator de dor baseado no valor da perda.

        Retorna:
            (pain_factor, is_trauma)
        """
        pnl = abs(context.get("pnl_amount", loss_amount))

        # Fator de dor baseado no valor
        if pnl < 100:
            return 1.0, False
        elif pnl < 500:
            return 2.0, False
        else:
            return 5.0, True  # Trauma

    def gain_xp(
        self,
        amount: int,
        source: str,
        context: dict[str, Any] | None = None,
        trade_id: str | None = None,
    ) -> XPEvent:
        """Adiciona XP ao Bob.

        Args:
            amount: Quantidade de XP ganho
            source: Fonte do ganho (trade_win, lesson, streak, etc.)
            context: Contexto adicional
            trade_id: ID do trade relacionado

        Returns:
            Evento criado
        """
        event = XPEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            type="gain",
            amount=max(1, amount),
            source=source,
            context=context or {},
            trade_id=trade_id,
            pain_factor=1.0,
            trauma=False,
        )

        self._events.append(event)
        self._xp += event.amount
        self._gains_count += 1
        self._save(event)

        logger.info("XP gained: +%d (%s) - Total: %d", amount, source, self._xp)
        return event

    def lose_xp(
        self,
        amount: int,
        source: str,
        context: dict[str, Any] | None = None,
        trade_id: str | None = None,
        pnl_amount: float | None = None,
    ) -> XPEvent:
        """Remove XP do Bob (aplica fator de dor).

        Args:
            amount: Quantidade base de XP perdido
            source: Fonte da perda (trade_loss, thesis_broken, etc.)
            context: Contexto adicional
            trade_id: ID do trade relacionado
            pnl_amount: Valor da perda em dólares (para calcular fator de dor)

        Returns:
            Evento criado
        """
        ctx = context or {}
        if pnl_amount is not None:
            ctx["pnl_amount"] = pnl_amount

        pain_factor, is_trauma = self._calculate_pain_factor(abs(amount), ctx)
        actual_loss = int(amount * pain_factor)

        event = XPEvent(
            event_id=self._generate_event_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            type="loss",
            amount=actual_loss,
            source=source,
            context=ctx,
            trade_id=trade_id,
            pain_factor=pain_factor,
            trauma=is_trauma,
        )

        self._events.append(event)
        self._xp = max(1, self._xp - actual_loss)  # XP nunca < 1
        self._losses_count += 1
        if is_trauma:
            self._traumas_count += 1
        self._save(event)

        logger.info(
            "XP lost: -%d (%s, pain_factor=%.1f, trauma=%s) - Total: %d",
            actual_loss,
            source,
            pain_factor,
            is_trauma,
            self._xp,
        )
        return event

    def record_trade_outcome(
        self,
        outcome: str,
        pnl_amount: float | None = None,
        thesis_correct: bool | None = None,
        trade_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> XPEvent | None:
        """Registra outcome de trade e ajusta XP automaticamente.

        Args:
            outcome: "win", "loss", "breakeven"
            pnl_amount: Valor PnL em dólares
            thesis_correct: Se a tese foi confirmada
            trade_id: ID do trade
            context: Contexto adicional

        Returns:
            Evento criado ou None (se breakeven)
        """
        ctx = context or {}
        if pnl_amount is not None:
            ctx["pnl_amount"] = pnl_amount
        if thesis_correct is not None:
            ctx["thesis_correct"] = thesis_correct

        if outcome == "win":
            # Base: +10 XP, bonus se tese correta
            amount = 10
            if thesis_correct:
                amount += 5
            return self.gain_xp(amount, "trade_win", ctx, trade_id)

        elif outcome == "loss":
            # Base: -10 XP, mais dor baseada no valor
            amount = 10
            if pnl_amount:
                amount += int(abs(pnl_amount) / 100)  # +1 XP por cada $100 perdido
            return self.lose_xp(amount, "trade_loss", ctx, trade_id, pnl_amount)

        elif outcome == "breakeven":
            # Sem XP, mas registra evento
            event = XPEvent(
                event_id=self._generate_event_id(),
                timestamp=datetime.now(timezone.utc).isoformat(),
                type="gain",
                amount=0,
                source="breakeven",
                context=ctx,
                trade_id=trade_id,
                pain_factor=1.0,
                trauma=False,
            )
            self._events.append(event)
            self._save(event)
            return event

        return None

    def record_streak(self, streak_type: str, count: int, context: dict[str, Any] | None = None) -> XPEvent:
        """Registra streak de wins ou losses.

        Args:
            streak_type: "win" | "loss"
            count: Quantidade de trades consecutivos
            context: Contexto adicional

        Returns:
            Evento criado
        """
        if streak_type == "win" and count >= 3:
            # Bonus de streak
            amount = count * 10
            return self.gain_xp(amount, "win_streak", context or {"streak_count": count})

        elif streak_type == "loss" and count >= 3:
            # Perda adicional por losing streak
            amount = count * 5
            return self.lose_xp(amount, "losing_streak", context or {"streak_count": count})

        # Streak pequeno, sem bonus
        return self.gain_xp(0, f"{streak_type}_streak_small", context or {"streak_count": count})

    def record_lesson_applied(self, lesson_id: str, context: dict[str, Any] | None = None) -> XPEvent:
        """Registra lição aprendida aplicada com sucesso.

        Args:
            lesson_id: ID da lição
            context: Contexto adicional

        Returns:
            Evento criado
        """
        ctx = context or {}
        ctx["lesson_id"] = lesson_id
        return self.gain_xp(30, "lesson_applied", ctx)

    def get_recent_events(self, limit: int = 20) -> list[XPEvent]:
        """Retorna eventos mais recentes."""
        return list(reversed(self._events[-limit:]))

    def get_traumas(self, limit: int = 10) -> list[XPEvent]:
        """Retorna eventos marcados como trauma."""
        traumas = [e for e in self._events if e.trauma]
        return list(reversed(traumas[-limit:]))

    def get_xp_by_source(self, source: str) -> int:
        """Retorna total de XP ganho/perdido por fonte."""
        total = 0
        for event in self._events:
            if event.source == source:
                if event.type == "gain":
                    total += event.amount
                else:
                    total -= event.amount
        return total

    def get_streak(self) -> dict[str, Any]:
        """Analisa último streak de wins/losses."""
        if not self._events:
            return {"type": None, "count": 0, "events": []}

        # Procurar streak de wins ou losses
        streak_events: list[XPEvent] = []
        streak_type = None

        for event in reversed(self._events):
            if event.source == "trade_win":
                if streak_type is None:
                    streak_type = "win"
                if streak_type == "win":
                    streak_events.append(event)
                else:
                    break
            elif event.source == "trade_loss":
                if streak_type is None:
                    streak_type = "loss"
                if streak_type == "loss":
                    streak_events.append(event)
                else:
                    break
            elif event.source in ("win_streak", "losing_streak"):
                # Streak events não quebram streak
                continue
            else:
                # Outros eventos quebram streak
                if streak_events:
                    break

        return {
            "type": streak_type,
            "count": len(streak_events),
            "events": [e.to_dict() for e in reversed(streak_events)],
        }

    def render_for_bob(self, max_chars: int = 1000) -> str:
        """Renderiza contexto de XP para o prompt do Bob."""
        stats = self.get_stats()
        streak = self.get_streak()

        lines = [
            "\n=== XP & LEVEL ===",
            f"Nível: {stats.level.title} (XP {stats.total_xp}/{stats.next_level_xp})",
            f"Progresso no nível: {stats.progress:.1f}%",
            f"Total de eventos: {stats.events_count}",
            f"Ganhos: {stats.gains_count} | Perdas: {stats.losses_count}",
        ]

        if stats.traumas_count > 0:
            lines.append(f"⚠️ Traumas: {stats.traumas_count} (perdas grandes)")

        if streak["type"]:
            lines.append(f"Streak atual: {streak['type'].upper()} ({streak['count']} consecutivos)")

        # Traumas recentes
        traumas = self.get_traumas(limit=3)
        if traumas:
            lines.append("\n⚠️ TRAUMAS RECENTES - EVITAR:")
            for trauma in traumas:
                pnl = trauma.context.get("pnl_amount", 0)
                lines.append(f"- {trauma.trade_id or '?'}: -${abs(pnl):.2f} ({trauma.source})")

        lines.append("=== FIM XP ===\n")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n..."

        return result


# Singleton
_xp_system: XPSystem | None = None


def get_xp_system() -> XPSystem:
    """Retorna singleton de XPSystem."""
    global _xp_system
    if _xp_system is None:
        _xp_system = XPSystem()
        logger.info("XPSystem initialized with %d XP", _xp_system._xp)
    return _xp_system


if __name__ == "__main__":
    # Test mode
    xp = get_xp_system()
    stats = xp.get_stats()
    print(f"Level: {stats.level.title}")
    print(f"XP: {stats.total_xp}/{stats.next_level_xp}")
    print(f"Progress: {stats.progress:.1f}%")
    print(f"Events: {stats.events_count}")
    print(f"\n{xp.render_for_bob()}")
