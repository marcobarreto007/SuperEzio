"""
F51 BODY HEARTBEAT — Ciclo Vital do Sistema
============================================
Loop de heartbeat com 3 modos de ciclo:
  - FULL:   todos os 7 estágios, a cada 5 minutos
  - LIGHT:  scan -> track -> learn, a cada 60 segundos
  - DEEP:   FULL + cristalização de memória, a cada 60 minutos

Cada estágio é uma async Task que publica no event_bus.
Erro em qualquer estágio -> registra dor, não quebra o loop.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.body.event_bus import BodyEventBus, EventSeverity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cycle types
# ---------------------------------------------------------------------------


class HeartbeatCycle(str, Enum):
    FULL = "full"  # 7 estágios, 5min
    LIGHT = "light"  # scan->track->learn, 60s
    DEEP = "deep"  # FULL + cristalização, 60min


# ---------------------------------------------------------------------------
# Stage types
# ---------------------------------------------------------------------------


class HeartbeatStage(str, Enum):
    SCAN = "scan"
    TRACK = "track"
    LEARN = "learn"
    DECIDE = "decide"
    ACT = "act"
    REFLECT = "reflect"
    CRYSTALLIZE = "crystallize"


# ---------------------------------------------------------------------------
# Stage definitions per cycle
# ---------------------------------------------------------------------------

FULL_STAGES: List[HeartbeatStage] = [
    HeartbeatStage.SCAN,
    HeartbeatStage.TRACK,
    HeartbeatStage.LEARN,
    HeartbeatStage.DECIDE,
    HeartbeatStage.ACT,
    HeartbeatStage.REFLECT,
]

LIGHT_STAGES: List[HeartbeatStage] = [
    HeartbeatStage.SCAN,
    HeartbeatStage.TRACK,
    HeartbeatStage.LEARN,
]

DEEP_STAGES: List[HeartbeatStage] = FULL_STAGES + [HeartbeatStage.CRYSTALLIZE]

# Intervalos em segundos
INTERVAL_FULL: int = 300  # 5 minutos
INTERVAL_LIGHT: int = 60  # 60 segundos
INTERVAL_DEEP: int = 3600  # 60 minutos


# ---------------------------------------------------------------------------
# Stage callback type
# ---------------------------------------------------------------------------

StageCallback = Callable[[HeartbeatStage, HeartbeatCycle], Any]

# ---------------------------------------------------------------------------
# HeartbeatLoop
# ---------------------------------------------------------------------------


class HeartbeatLoop:
    """
    Loop principal de heartbeat do corpo F51.

    Uso:
        hb = HeartbeatLoop(event_bus=bus)
        await hb.start()       # inicia o loop principal
        await hb.stop()        # para graciosamente
        await hb.beat(cycle)   # executa um ciclo manual
        status = hb.health()   # estado atual
    """

    def __init__(
        self,
        event_bus: BodyEventBus,
        stage_callbacks: Optional[Dict[HeartbeatStage, StageCallback]] = None,
    ):
        self._bus = event_bus
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._current_cycle: Optional[HeartbeatCycle] = None
        self._current_stage: Optional[HeartbeatStage] = None
        self._last_full: float = 0.0
        self._last_light: float = 0.0
        self._last_deep: float = 0.0
        self._beat_count: int = 0
        self._pain_log: List[Dict[str, Any]] = []
        self._stage_callbacks = stage_callbacks or {}

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Inicia o loop principal de heartbeat em background."""
        if self._running:
            logger.warning("HeartbeatLoop já está rodando.")
            return

        self._running = True
        now = time.time()
        self._last_full = now
        self._last_light = now
        self._last_deep = now

        # Spawn the main loop task
        task = asyncio.create_task(self._main_loop())
        self._tasks.append(task)
        logger.info("HeartbeatLoop iniciado.")

    async def stop(self) -> None:
        """Para o loop de heartbeat graciosamente."""
        self._running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._tasks.clear()
        logger.info("HeartbeatLoop parado.")

    # ------------------------------------------------------------------
    # Manual beat
    # ------------------------------------------------------------------

    async def beat(
        self,
        cycle: HeartbeatCycle = HeartbeatCycle.LIGHT,
    ) -> Dict[str, Any]:
        """
        Executa um ciclo de heartbeat manualmente.
        Útil para testes ou sob demanda.

        Returns:
            dict com cycle, stages_executed, errors
        """
        stages = self._stages_for_cycle(cycle)
        errors: List[str] = []
        executed: List[str] = []

        self._current_cycle = cycle

        for stage in stages:
            self._current_stage = stage
            try:
                await self._execute_stage(stage, cycle)
                executed.append(stage.value)
            except Exception as e:
                error_msg = f"{stage.value}: {e}"
                errors.append(error_msg)
                await self._register_pain(stage, str(e))

        self._beat_count += 1
        self._current_cycle = None
        self._current_stage = None

        return {
            "cycle": cycle.value,
            "stages_executed": executed,
            "errors": errors,
            "beat_count": self._beat_count,
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> Dict[str, Any]:
        """Retorna estado atual do ciclo de heartbeat."""
        now = time.time()
        return {
            "running": self._running,
            "current_cycle": self._current_cycle.value if self._current_cycle else None,
            "current_stage": self._current_stage.value if self._current_stage else None,
            "beat_count": self._beat_count,
            "seconds_since_full": now - self._last_full,
            "seconds_since_light": now - self._last_light,
            "seconds_since_deep": now - self._last_deep,
            "pain_count": len(self._pain_log),
            "recent_pains": self._pain_log[-5:] if self._pain_log else [],
        }

    # ------------------------------------------------------------------
    # Internal: main loop
    # ------------------------------------------------------------------

    async def _main_loop(self) -> None:
        """Loop principal que decide qual ciclo executar."""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Erro no _main_loop: %s", e)
                await self._register_pain(HeartbeatStage.SCAN, str(e))

            await asyncio.sleep(1)

    async def _tick(self) -> None:
        """Decide qual ciclo executar baseado nos intervalos."""
        now = time.time()

        # DEEP: a cada 60min
        if now - self._last_deep >= INTERVAL_DEEP:
            await self.beat(HeartbeatCycle.DEEP)
            self._last_deep = now
            self._last_full = now
            self._last_light = now

        # FULL: a cada 5min
        elif now - self._last_full >= INTERVAL_FULL:
            await self.beat(HeartbeatCycle.FULL)
            self._last_full = now
            self._last_light = now

        # LIGHT: a cada 60s
        elif now - self._last_light >= INTERVAL_LIGHT:
            await self.beat(HeartbeatCycle.LIGHT)
            self._last_light = now

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------

    def _stages_for_cycle(self, cycle: HeartbeatCycle) -> List[HeartbeatStage]:
        if cycle == HeartbeatCycle.LIGHT:
            return LIGHT_STAGES
        elif cycle == HeartbeatCycle.DEEP:
            return DEEP_STAGES
        return FULL_STAGES

    async def _execute_stage(self, stage: HeartbeatStage, cycle: HeartbeatCycle) -> None:
        """Executa um estágio individual e publica no event_bus."""
        event_type_map = {
            HeartbeatCycle.FULL: "event:body.heartbeat.full",
            HeartbeatCycle.LIGHT: "event:body.heartbeat.light",
            HeartbeatCycle.DEEP: "event:body.heartbeat.deep",
        }
        event_type = event_type_map.get(cycle, "event:body.heartbeat.light")

        # Call custom callback if registered
        cb = self._stage_callbacks.get(stage)
        if cb is not None:
            result = cb(stage, cycle)
            if hasattr(result, "__await__"):
                await result

        # Publish stage event
        await self._bus.publish(
            event_type=event_type,
            payload={
                "stage": stage.value,
                "cycle": cycle.value,
                "beat_count": self._beat_count,
            },
            source="f51-heartbeat",
            severity=EventSeverity.INFO,
        )

        logger.debug("Heartbeat stage=%s cycle=%s OK", stage.value, cycle.value)

    # ------------------------------------------------------------------
    # Pain registration
    # ------------------------------------------------------------------

    async def _register_pain(self, stage: HeartbeatStage, error: str) -> None:
        """Registra dor no sistema (não quebra o loop)."""
        pain_entry = {
            "stage": stage.value,
            "error": error,
            "timestamp": time.time(),
        }
        self._pain_log.append(pain_entry)

        # Publica dor no event_bus
        try:
            await self._bus.publish(
                event_type="event:body.pain.heartbeat",
                payload=pain_entry,
                source="f51-heartbeat",
                severity=EventSeverity.ERROR,
            )
        except Exception:
            logger.exception("Falha ao publicar dor no event_bus")
