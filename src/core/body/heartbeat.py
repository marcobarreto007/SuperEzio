"""
F51 BODY HEARTBEAT — Ciclo Vital do Sistema
============================================
Loop de heartbeat com 3 modos de ciclo:
  - FULL:   todos os 8 estágios, a cada 5 minutos
  - LIGHT:  scan -> track -> learn, a cada 60 segundos
  - DEEP:   FULL + cristalização de memória, a cada 60 minutos

Cada estágio é uma async Task que publica no event_bus.
Erro em qualquer estágio -> registra dor, não quebra o loop.

Estágios conectados ao pipeline REAL:
  - SCORE: MathHub.calculate_all() -> event:pipeline.math.completed
  - VERIFY: node_f51_verdict()     -> event:pipeline.f51.verdict
  - SCAN:   Pennylab + Mangala     -> event:pipeline.pennylab.whale / mangala.found
"""

import asyncio
import logging
import os
import time
from collections.abc import Callable
from enum import Enum
from functools import partial
from typing import Any

from core.body.event_bus import BodyEventBus, EventSeverity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cycle types
# ---------------------------------------------------------------------------


class HeartbeatCycle(str, Enum):
    FULL = "full"  # 8 estágios, 5min
    LIGHT = "light"  # scan->track->learn, 60s
    DEEP = "deep"  # FULL + cristalização, 60min


# ---------------------------------------------------------------------------
# Stage types
# ---------------------------------------------------------------------------


class HeartbeatStage(str, Enum):
    SCAN = "scan"
    SCORE = "score"
    VERIFY = "verify"
    TRACK = "track"
    LEARN = "learn"
    DECIDE = "decide"
    ACT = "act"
    REFLECT = "reflect"
    CRYSTALLIZE = "crystallize"


# ---------------------------------------------------------------------------
# Stage definitions per cycle
# ---------------------------------------------------------------------------

FULL_STAGES: list[HeartbeatStage] = [
    HeartbeatStage.SCAN,
    HeartbeatStage.SCORE,
    HeartbeatStage.VERIFY,
    HeartbeatStage.TRACK,
    HeartbeatStage.LEARN,
    HeartbeatStage.DECIDE,
    HeartbeatStage.ACT,
    HeartbeatStage.REFLECT,
]

LIGHT_STAGES: list[HeartbeatStage] = [
    HeartbeatStage.SCAN,
    HeartbeatStage.TRACK,
    HeartbeatStage.LEARN,
]

DEEP_STAGES: list[HeartbeatStage] = FULL_STAGES + [HeartbeatStage.CRYSTALLIZE]

# Intervalos em segundos
INTERVAL_FULL: int = 300  # 5 minutos
INTERVAL_LIGHT: int = 60  # 60 segundos
INTERVAL_DEEP: int = 3600  # 60 minutos

# Fechador de posicao (corpo do estagio TRACK). O ciclo LIGHT bate a cada 60s e cada
# trade aberto custa um fetch de candles; sem intervalo proprio isso viraria dezenas
# de chamadas por minuto no provider de dados. Default = mesmo passo do ciclo FULL.
INTERVAL_POSITION_CLOSER: int = 300
# Teto de tempo do ciclo. Passou disso, o fechador e abandonado ate o proximo -- o
# heartbeat nao pode ficar preso esperando provider de mercado.
POSITION_CLOSER_TIMEOUT: float = 30.0


# ---------------------------------------------------------------------------
# Stage callback type
# ---------------------------------------------------------------------------

StageCallback = Callable[[HeartbeatStage, HeartbeatCycle], Any]


def _position_closer_enabled() -> bool:
    """Liga o fechador no estagio TRACK. Default: LIGADO, mas em dry-run.

    O fechador roda em simulacao por padrao (`position_closer.dry_run_from_env`), entao
    liga-lo nao fecha nada sozinho -- so LOGA o que fecharia. Para desligar de vez,
    `SUPEREZIO_POSITION_CLOSER_ENABLED=0`.
    """
    return str(os.getenv("SUPEREZIO_POSITION_CLOSER_ENABLED", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


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
        stage_callbacks: dict[HeartbeatStage, StageCallback] | None = None,
        state: dict[str, Any] | None = None,
    ):
        self._bus = event_bus
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._current_cycle: HeartbeatCycle | None = None
        self._current_stage: HeartbeatStage | None = None
        self._last_full: float = 0.0
        self._last_light: float = 0.0
        self._last_deep: float = 0.0
        # Ultimo ciclo do fechador de posicao (estagio TRACK). Ver _execute_track.
        self._last_position_closer: float = 0.0
        self._beat_count: int = 0
        self._pain_log: list[dict[str, Any]] = []
        self._stage_callbacks = stage_callbacks or {}
        self._state: dict[str, Any] = state or {}

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
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Executa um ciclo de heartbeat manualmente.
        Útil para testes ou sob demanda.

        Args:
            cycle: Tipo de ciclo (LIGHT, FULL, DEEP).
            state: Estado opcional do sistema para os estágios reais.

        Returns:
            dict com cycle, stages_executed, errors
        """
        if state is not None:
            self._state = dict(state)

        stages = self._stages_for_cycle(cycle)
        errors: list[str] = []
        executed: list[str] = []

        self._current_cycle = cycle

        for stage in stages:
            self._current_stage = stage
            try:
                await self._execute_stage(stage, cycle)
                executed.append(stage.value)
            except Exception as e:  # noqa: BLE001 - deliberado: erro vira dor, não quebra o ciclo.
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

    def health(self) -> dict[str, Any]:
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
                logger.exception("Erro no _main_loop")
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

    def _stages_for_cycle(self, cycle: HeartbeatCycle) -> list[HeartbeatStage]:
        if cycle == HeartbeatCycle.LIGHT:
            return LIGHT_STAGES
        elif cycle == HeartbeatCycle.DEEP:
            return DEEP_STAGES
        return FULL_STAGES

    async def _execute_stage(self, stage: HeartbeatStage, cycle: HeartbeatCycle) -> None:
        """Executa um estágio individual e publica no event_bus."""
        # ── Real pipeline integration ──
        if stage == HeartbeatStage.SCORE:
            await self._execute_score()
        elif stage == HeartbeatStage.VERIFY:
            await self._execute_verify()
        elif stage == HeartbeatStage.SCAN:
            await self._execute_scan(cycle)
        elif stage == HeartbeatStage.TRACK:
            await self._execute_track()

        # Call custom callback if registered
        cb = self._stage_callbacks.get(stage)
        if cb is not None:
            result = cb(stage, cycle)
            if hasattr(result, "__await__"):
                await result

        # Publish stage event
        event_type_map = {
            HeartbeatCycle.FULL: "event:body.heartbeat.full",
            HeartbeatCycle.LIGHT: "event:body.heartbeat.light",
            HeartbeatCycle.DEEP: "event:body.heartbeat.deep",
        }
        event_type = event_type_map.get(cycle, "event:body.heartbeat.light")
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
    # Pipeline integration: SCORE -> MathHub
    # ------------------------------------------------------------------

    async def _execute_score(self) -> None:
        """SCORE stage: executa MathHub.calculate_all() no estado atual e publica resultado."""
        try:
            from core.math.math_hub import MathHub

            math_report = MathHub().calculate_all(self._state)
            await self._bus.publish(
                event_type="event:pipeline.math.completed",
                payload={"math_report": math_report},
                source="f51-heartbeat",
                severity=EventSeverity.INFO,
            )
        except Exception:
            logger.exception("Heartbeat SCORE (MathHub) failed")

    # ------------------------------------------------------------------
    # Pipeline integration: VERIFY -> F51 Verdict
    # ------------------------------------------------------------------

    async def _execute_verify(self) -> None:
        """VERIFY stage: executa F51 Verdict no estado atual e publica resultado."""
        try:
            from core.pipeline.nodes.f51 import node_f51_verdict

            try:
                f51_result = await asyncio.wait_for(
                    node_f51_verdict(self._state),
                    timeout=10.0,
                )
                await self._bus.publish(
                    event_type="event:pipeline.f51.verdict",
                    payload={"f51_verdict": f51_result},
                    source="f51-heartbeat",
                    severity=EventSeverity.INFO,
                )
            except TimeoutError:
                logger.debug("Heartbeat VERIFY (node_f51_verdict) timed out")
            except Exception as exc:  # noqa: BLE001 - deliberado: fora do contexto langgraph.
                logger.debug(
                    "Heartbeat VERIFY (node_f51_verdict) unavailable"
                    " (fora do contexto langgraph): %s",
                    exc,
                )
        except Exception:
            logger.exception("Heartbeat VERIFY (F51) failed to import")

    # ------------------------------------------------------------------
    # Pipeline integration: SCAN -> Pennylab + Mangala
    # ------------------------------------------------------------------

    async def _execute_scan(self, cycle: HeartbeatCycle = HeartbeatCycle.FULL) -> None:
        """SCAN stage: executa Pennylab + Mangala scanners quando disponiveis.

        Ambos requerem feature flag explicita e rede externa.
        Executados apenas em ciclos FULL ou DEEP (nao em LIGHT).
        """
        ticker = self._state.get("ticker", "")

        # ── Pennylab (feature flag + ticker + FULL/DEEP) ──
        if (
            ticker
            and os.getenv("SUPEREZIO_HEARTBEAT_PENNYLAB") == "1"
            and cycle in (HeartbeatCycle.FULL, HeartbeatCycle.DEEP)
        ):
            try:
                from experts.pennylab.pipeline_hook import run_pennylab_analysis

                pennylab_result = await run_pennylab_analysis(ticker)
                await self._bus.publish(
                    event_type="event:pipeline.pennylab.whale",
                    payload={"pennylab": pennylab_result, "ticker": ticker},
                    source="f51-heartbeat",
                    severity=EventSeverity.INFO,
                )
            except Exception:  # noqa: BLE001 - deliberado: scanner opcional; falha vira debug.
                logger.debug("Heartbeat SCAN (Pennylab) unavailable for ticker=%s", ticker)

        # ── Mangala (feature flag + FULL/DEEP) ──
        if os.getenv("SUPEREZIO_HEARTBEAT_MANGALA") == "1" and cycle in (
            HeartbeatCycle.FULL,
            HeartbeatCycle.DEEP,
        ):
            try:
                from core.pipeline.nodes.mangala import scan_mangala_opportunities
                from data.data_hub import hub as data_hub

                loop = asyncio.get_running_loop()
                opportunities = await asyncio.wait_for(
                    loop.run_in_executor(None, scan_mangala_opportunities, data_hub),
                    timeout=15.0,
                )
                if opportunities:
                    await self._bus.publish(
                        event_type="event:pipeline.mangala.found",
                        payload={"mangala": opportunities},
                        source="f51-heartbeat",
                        severity=EventSeverity.INFO,
                    )
            except TimeoutError:
                logger.debug("Heartbeat SCAN (Mangala) timed out after 15s")
            except Exception:  # noqa: BLE001 - deliberado: scanner opcional; falha vira debug.
                logger.debug("Heartbeat SCAN (Mangala) unavailable")

    # ------------------------------------------------------------------
    # Pipeline integration: TRACK -> fechador de posicao
    # ------------------------------------------------------------------

    async def _execute_track(self) -> None:
        """TRACK stage: fecha posicoes paper que bateram stop, alvo ou prazo.

        O fechador e o CORPO deste estagio: le `journal.list_open()`, busca candles e
        avalia as barreiras persistidas na abertura. Antes disso TRACK nao tinha
        executor -- so callback externo.

        Duas travas de custo, porque isto e I/O de rede dentro do loop de batimento:
          - intervalo proprio (INTERVAL_POSITION_CLOSER), senao o ciclo LIGHT de 60s
            faria um fetch de candles por trade aberto a cada minuto;
          - timeout, para o heartbeat nao ficar preso esperando provider de mercado.

        Falha aqui vira debug, nunca derruba o ciclo: e um dos estagios de melhor
        esforco, igual SCORE/VERIFY/SCAN.
        """
        if not _position_closer_enabled():
            logger.debug("Heartbeat TRACK (position closer) desligado por env")
            return

        now = time.monotonic()
        if now - self._last_position_closer < INTERVAL_POSITION_CLOSER:
            logger.debug("Heartbeat TRACK (position closer) em intervalo de throttle")
            return
        self._last_position_closer = now

        try:
            from core.trading.position_closer import close_positions, dry_run_from_env

            loop = asyncio.get_running_loop()
            report = await asyncio.wait_for(
                loop.run_in_executor(None, partial(close_positions, dry_run=dry_run_from_env())),
                timeout=POSITION_CLOSER_TIMEOUT,
            )
            # Sumario no barramento: as decisoes por trade ja vao para o log do
            # fechador, e publicar a lista inteira inflaria o evento sem leitor.
            summary = {k: v for k, v in report.to_dict().items() if k != "decisions"}
            await self._bus.publish(
                event_type="event:pipeline.position.closer",
                payload=summary,
                source="f51-heartbeat",
                severity=EventSeverity.INFO,
            )
        except TimeoutError:
            logger.debug(
                "Heartbeat TRACK (position closer) timed out after %ss", POSITION_CLOSER_TIMEOUT
            )
        except Exception:  # noqa: BLE001 - deliberado: estagio opcional; falha vira debug.
            logger.debug("Heartbeat TRACK (position closer) unavailable")

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
