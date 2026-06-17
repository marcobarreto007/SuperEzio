"""Bob Lifecycle 24/7 - Organismo Vivo.

Loop principal que gerencia estados do Bob:
- MARKET_CLOSED: Estudar histórico, refletir, preparar setups
- PRE_MARKET: Scan pré-market, identificar oportunidades
- MARKET_OPEN: Trading ativo com gates
- POST_MARKET: Análise pós-close, feedback loop
- SLEEPING: Dormir fora de horas US (economizar recursos)

O Bob nunca desliga — ele muda de comportamento conforme o mercado.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# Importar dependências do projeto
try:
    from .market_hours import get_market_state, get_market_phase
    from .xp_system import get_xp_system, XPSystem
    from .feedback_loop import get_feedback_loop, FeedbackLoop
    from .paper_journal import PaperJournal
    from .daily_cycle import DailyCycle
except ImportError:
    # Fallback para testes standalone
    pass


class LifecycleState(Enum):
    """Estados do ciclo de vida do Bob."""
    MARKET_CLOSED = "MARKET_CLOSED"
    PRE_MARKET = "PRE_MARKET"
    MARKET_OPEN = "MARKET_OPEN"
    POST_MARKET = "POST_MARKET"
    SLEEPING = "SLEEPING"
    LEARNING = "LEARNING"
    RECOVERING = "RECOVERING"
    STOPPED = "STOPPED"


@dataclass
class StateTransition:
    """Registro de transição de estado."""
    from_state: LifecycleState
    to_state: LifecycleState
    timestamp: str
    reason: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_state.value,
            "to": self.to_state.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "context": self.context,
        }


@dataclass
class LifecycleContext:
    """Contexto compartilhado entre estados."""
    xp_system: XPSystem | None = None
    feedback_loop: FeedbackLoop | None = None
    journal: PaperJournal | None = None
    daily_cycle: DailyCycle | None = None

    # Estado interno
    current_phase: str = "INITIALIZING"
    last_market_phase: str = ""
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    trades_today: int = 0
    last_learning_cycle: str | None = None

    # Limites
    max_trades_per_day: int = 10
    max_consecutive_losses: int = 3
    daily_loss_limit_usd: float = 500.0

    # Flags
    kill_switch_active: bool = False
    manual_override: bool = False
    force_learning: bool = False


class BobLifecycle:
    """Gerenciador do ciclo de vida 24/7 do Bob."""

    def __init__(
        self,
        context: LifecycleContext | None = None,
        on_state_change: Callable[[StateTransition], None] | None = None,
        sleep_interval_seconds: int = 30,
    ):
        self._context = context or LifecycleContext()
        self._on_state_change = on_state_change
        self._sleep_interval = sleep_interval_seconds

        self._state = LifecycleState.STOPPED
        self._running = False
        self._task: asyncio.Task | None = None
        self._transitions: list[StateTransition] = []

        # Inicializar dependências
        self._init_dependencies()

    def _init_dependencies(self) -> None:
        """Inicializa dependências do contexto."""
        try:
            if self._context.xp_system is None:
                self._context.xp_system = get_xp_system()
            if self._context.feedback_loop is None:
                self._context.feedback_loop = get_feedback_loop()
            if self._context.journal is None:
                self._context.journal = PaperJournal()
            if self._context.daily_cycle is None:
                self._context.daily_cycle = DailyCycle(
                    journal=self._context.journal,
                )
        except Exception as e:
            logger.warning("Failed to initialize some dependencies: %s", e)

    def _record_transition(
        self,
        to_state: LifecycleState,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Registra transição de estado."""
        transition = StateTransition(
            from_state=self._state,
            to_state=to_state,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            context=context or {},
        )
        self._transitions.append(transition)
        self._state = to_state

        logger.info(
            "State transition: %s → %s (%s)",
            transition.from_state.value,
            transition.to_state.value,
            reason,
        )

        if self._on_state_change:
            try:
                self._on_state_change(transition)
            except Exception as e:
                logger.error("Error in state change callback: %s", e)

    def _should_enter_recovery(self) -> bool:
        """Verifica se Bob deve entrar em modo recuperação."""
        return (
            self._context.consecutive_losses >= self._context.max_consecutive_losses
            or self._context.kill_switch_active
        )

    def _should_wake_up(self) -> bool:
        """Verifica se Bob deve acordar (está em SLEEPING mas tem trabalho)."""
        market_state = get_market_state(cached=False)
        market_phase = market_state["phase"]

        # Acordar 30min antes do mercado abrir
        if market_phase == "PRE_MARKET":
            return True

        # Acordar se houver tarefa manual
        if self._context.manual_override or self._context.force_learning:
            return True

        return False

    async def _state_market_closed(self) -> LifecycleState:
        """Estado: Mercado fechado.

        Bob estuda histórico, reflete, prepara setups.
        """
        logger.info("Bob está estudando histórico e refletindo...")

        # Executar ciclo de aprendizado
        try:
            if self._context.feedback_loop:
                results = await asyncio.to_thread(
                    self._context.feedback_loop.run_learning_cycle
                )
                self._context.last_learning_cycle = results.get("timestamp")
                logger.info("Learning cycle completed: %d lessons", results.get("lessons_extracted", 0))
        except Exception as e:
            logger.warning("Learning cycle failed: %s", e)

        # Esperar próxima transição
        market_state = get_market_state(cached=False)
        next_open_seconds = market_state["time_until_open_seconds"]

        # Se faltam menos de 1h para abrir, ir para PRE_MARKET
        if next_open_seconds < 3600:
            return LifecycleState.PRE_MARKET

        # Senão, dormir um pouco
        await asyncio.sleep(min(self._sleep_interval, next_open_seconds))

        # Reavaliar estado
        return LifecycleState.MARKET_CLOSED

    async def _state_pre_market(self) -> LifecycleState:
        """Estado: Pré-market.

        Bob scania oportunidades, prepara setups.
        """
        logger.info("Bob está scaniando pré-market...")

        # Executar morning routine
        try:
            if self._context.daily_cycle:
                morning = await asyncio.to_thread(
                    self._context.daily_cycle.morning_routine
                )
                logger.info("Morning routine: %s", morning.get("phase"))
        except Exception as e:
            logger.warning("Morning routine failed: %s", e)

        # Esperar mercado abrir
        while True:
            market_state = get_market_state(cached=False)
            if market_state["is_open"]:
                return LifecycleState.MARKET_OPEN

            # Check kill switch
            if self._context.kill_switch_active:
                return LifecycleState.RECOVERING

            await asyncio.sleep(10)  # Check frequentemente

    async def _state_market_open(self) -> LifecycleState:
        """Estado: Mercado aberto.

        Bob trada ativamente com gates.
        """
        logger.info("Bob está tradando...")

        # Executar trading session
        try:
            if self._context.daily_cycle and hasattr(self._context.daily_cycle, "trading_session"):
                # O trading session precisa ser chamado com uma mensagem
                # Por agora, apenas log
                logger.info("Trading session ativo")
        except Exception as e:
            logger.warning("Trading session setup failed: %s", e)

        # Loop enquanto mercado estiver aberto
        while True:
            market_state = get_market_state(cached=False)

            if not market_state["is_open"]:
                return LifecycleState.POST_MARKET

            # Check kill switch
            if self._context.kill_switch_active:
                return LifecycleState.RECOVERING

            # Check recovery mode
            if self._should_enter_recovery():
                return LifecycleState.RECOVERING

            # Check max trades
            if self._context.trades_today >= self._context.max_trades_per_day:
                logger.info("Max trades reached for today")
                return LifecycleState.POST_MARKET

            await asyncio.sleep(self._sleep_interval)

    async def _state_post_market(self) -> LifecycleState:
        """Estado: Pós-market.

        Bob analisa o dia, roda feedback loop.
        """
        logger.info("Bob está analisando o dia...")

        # Executar evening routine
        try:
            if self._context.daily_cycle:
                evening = await asyncio.to_thread(
                    self._context.daily_cycle.evening_routine
                )
                logger.info("Evening routine: %d closed trades", evening.get("open_trades", 0))
        except Exception as e:
            logger.warning("Evening routine failed: %s", e)

        # Executar learning cycle
        try:
            if self._context.feedback_loop:
                results = await asyncio.to_thread(
                    self._context.feedback_loop.run_learning_cycle
                )
                self._context.last_learning_cycle = results.get("timestamp")
                logger.info("Learning cycle: %d patterns", results.get("patterns_found", 0))
        except Exception as e:
            logger.warning("Learning cycle failed: %s", e)

        # Resetar contadores diários
        self._context.trades_today = 0
        self._context.consecutive_losses = 0
        self._context.consecutive_wins = 0

        # Ir para SLEEPING
        return LifecycleState.SLEEPING

    async def _state_sleeping(self) -> LifecycleState:
        """Estado: Dormindo.

        Bob economiza recursos fora de horas.
        """
        logger.info("Bob está dormindo...")

        # Dormir até próximo evento
        while True:
            if self._should_wake_up():
                market_state = get_market_state(cached=False)
                if market_state["phase"] == "PRE_MARKET":
                    return LifecycleState.PRE_MARKET
                if self._context.force_learning:
                    return LifecycleState.LEARNING
                return LifecycleState.MARKET_CLOSED

            # Dormir por mais tempo
            await asyncio.sleep(self._sleep_interval * 2)

    async def _state_learning(self) -> LifecycleState:
        """Estado: Aprendendo forçado.

        Bob executa learning cycle por solicitação manual.
        """
        logger.info("Bob está aprendendo (forçado)...")

        try:
            if self._context.feedback_loop:
                results = await asyncio.to_thread(
                    self._context.feedback_loop.run_learning_cycle
                )
                self._context.last_learning_cycle = results.get("timestamp")
                logger.info("Forced learning completed")
        except Exception as e:
            logger.warning("Forced learning failed: %s", e)

        self._context.force_learning = False

        # Voltar ao estado normal
        market_state = get_market_state(cached=False)
        market_phase = market_state["phase"]

        if market_phase == "MARKET_OPEN":
            return LifecycleState.MARKET_OPEN
        elif market_phase == "PRE_MARKET":
            return LifecycleState.PRE_MARKET
        elif market_phase == "POST_MARKET":
            return LifecycleState.POST_MARKET
        else:
            return LifecycleState.SLEEPING

    async def _state_recovering(self) -> LifecycleState:
        """Estado: Recuperação.

        Bob está em recuperação após perdas consecutivas ou kill switch.
        """
        logger.warning("Bob está em recuperação...")

        # Executar learning cycle intensivo
        try:
            if self._context.feedback_loop:
                results = await asyncio.to_thread(
                    self._context.feedback_loop.run_learning_cycle
                )
                logger.info("Recovery learning completed")
        except Exception as e:
            logger.warning("Recovery learning failed: %s", e)

        # Esperar intervenção manual ou timeout
        for _ in range(10):  # Max ~5min
            if not self._context.kill_switch_active:
                break
            await asyncio.sleep(30)

        if self._context.kill_switch_active:
            return LifecycleState.STOPPED

        # Reset consecutive losses
        self._context.consecutive_losses = 0

        # Voltar ao mercado se aberto
        market_state = get_market_state(cached=False)
        if market_state["is_open"]:
            return LifecycleState.MARKET_OPEN

        return LifecycleState.MARKET_CLOSED

    async def _run(self) -> None:
        """Loop principal do ciclo de vida."""
        self._running = True
        self._record_transition(
            LifecycleState.MARKET_CLOSED,
            "Lifecycle started",
            {"timestamp": datetime.now(timezone.utc).isoformat()},
        )

        state_handlers = {
            LifecycleState.MARKET_CLOSED: self._state_market_closed,
            LifecycleState.PRE_MARKET: self._state_pre_market,
            LifecycleState.MARKET_OPEN: self._state_market_open,
            LifecycleState.POST_MARKET: self._state_post_market,
            LifecycleState.SLEEPING: self._state_sleeping,
            LifecycleState.LEARNING: self._state_learning,
            LifecycleState.RECOVERING: self._state_recovering,
        }

        while self._running:
            try:
                handler = state_handlers.get(self._state)
                if not handler:
                    logger.error("No handler for state: %s", self._state)
                    break

                next_state = await handler()

                if next_state != self._state:
                    self._record_transition(
                        next_state,
                        f"Transition from {self._state.value}",
                    )

            except asyncio.CancelledError:
                logger.info("Lifecycle cancelled")
                break
            except Exception as e:
                logger.error("Error in lifecycle loop: %s", e)
                await asyncio.sleep(self._sleep_interval)

    def start(self) -> asyncio.Task:
        """Inicia o ciclo de vida do Bob.

        Returns:
            Task do loop
        """
        if self._running:
            logger.warning("Lifecycle already running")
            return self._task  # type: ignore

        logger.info("Starting Bob 24/7 lifecycle...")
        self._task = asyncio.create_task(self._run())
        return self._task

    async def stop(self) -> None:
        """Para o ciclo de vida do Bob."""
        logger.info("Stopping Bob lifecycle...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._record_transition(
            LifecycleState.STOPPED,
            "Lifecycle stopped",
        )

    def get_state(self) -> LifecycleState:
        """Retorna estado atual."""
        return self._state

    def get_status(self) -> dict[str, Any]:
        """Retorna status completo do ciclo de vida."""
        market_state = get_market_state(cached=False)

        xp_stats = None
        if self._context.xp_system:
            xp_stats = self._context.xp_system.get_stats().to_dict()

        return {
            "lifecycle": {
                "state": self._state.value,
                "running": self._running,
                "transitions_count": len(self._transitions),
                "last_transition": (
                    self._transitions[-1].to_dict() if self._transitions else None
                ),
            },
            "market": market_state,
            "xp": xp_stats,
            "context": {
                "consecutive_losses": self._context.consecutive_losses,
                "consecutive_wins": self._context.consecutive_wins,
                "trades_today": self._context.trades_today,
                "kill_switch_active": self._context.kill_switch_active,
                "manual_override": self._context.manual_override,
            },
        }

    def trigger_learning(self) -> None:
        """Força execução de learning cycle."""
        self._context.force_learning = True
        logger.info("Forced learning triggered")

    def set_kill_switch(self, active: bool) -> None:
        """Ativa/desativa kill switch."""
        self._context.kill_switch_active = active
        logger.info("Kill switch: %s", "ACTIVE" if active else "inactive")

    def set_manual_override(self, active: bool) -> None:
        """Ativa/desativa override manual."""
        self._context.manual_override = active
        logger.info("Manual override: %s", "ACTIVE" if active else "inactive")


# Singleton
_lifecycle: BobLifecycle | None = None


def get_lifecycle() -> BobLifecycle:
    """Retorna singleton de BobLifecycle."""
    global _lifecycle
    if _lifecycle is None:
        _lifecycle = BobLifecycle()
        logger.info("BobLifecycle initialized")
    return _lifecycle


if __name__ == "__main__":
    # Test mode
    async def test():
        lifecycle = get_lifecycle()
        print("Starting lifecycle for 10 seconds...")
        task = lifecycle.start()

        await asyncio.sleep(10)

        print("\nStatus:")
        import json
        print(json.dumps(lifecycle.get_status(), indent=2, default=str))

        await lifecycle.stop()

    asyncio.run(test())
