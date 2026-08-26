"""
Tests for HeartbeatLoop — Fase 2 (Heartbeat) da arquitetura CORPO.
"""

import pytest

from core.body import BodyEventBus, HeartbeatLoop
from core.body.heartbeat import (
    DEEP_STAGES,
    FULL_STAGES,
    LIGHT_STAGES,
    HeartbeatCycle,
    HeartbeatStage,
)


class TestHeartbeatStages:
    """Stage definitions per cycle."""

    def test_light_stages(self):
        assert LIGHT_STAGES == [
            HeartbeatStage.SCAN,
            HeartbeatStage.TRACK,
            HeartbeatStage.LEARN,
        ]

    def test_full_stages(self):
        assert FULL_STAGES == [
            HeartbeatStage.SCAN,
            HeartbeatStage.SCORE,
            HeartbeatStage.VERIFY,
            HeartbeatStage.TRACK,
            HeartbeatStage.LEARN,
            HeartbeatStage.DECIDE,
            HeartbeatStage.ACT,
            HeartbeatStage.REFLECT,
        ]

    def test_deep_stages(self):
        assert DEEP_STAGES == FULL_STAGES + [HeartbeatStage.CRYSTALLIZE]


class TestHeartbeatLoop:
    """HeartbeatLoop single-beat and health."""

    @pytest.mark.asyncio
    async def test_beat_light(self):
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)
        result = await hb.beat(HeartbeatCycle.LIGHT)

        assert result["cycle"] == "light"
        assert len(result["stages_executed"]) == 3
        assert result["errors"] == []
        assert result["beat_count"] == 1

    @pytest.mark.asyncio
    async def test_beat_full(self):
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)
        result = await hb.beat(HeartbeatCycle.FULL)

        assert result["cycle"] == "full"
        assert len(result["stages_executed"]) == 8
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_beat_deep(self):
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)
        result = await hb.beat(HeartbeatCycle.DEEP)

        assert result["cycle"] == "deep"
        assert len(result["stages_executed"]) == 9  # 8 FULL + Crystallize
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_health_status(self):
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)

        health = hb.health()
        assert health["running"] is False
        assert health["beat_count"] == 0
        assert health["pain_count"] == 0

        await hb.beat(HeartbeatCycle.LIGHT)
        health = hb.health()
        assert health["running"] is False
        assert health["beat_count"] == 1

    @pytest.mark.asyncio
    async def test_stage_callback(self):
        bus = BodyEventBus(hub_type="memory")
        called_stages = []

        def track_cb(stage: HeartbeatStage, cycle: HeartbeatCycle):
            called_stages.append((stage, cycle))

        cb_map = {HeartbeatStage.SCAN: track_cb}
        hb = HeartbeatLoop(event_bus=bus, stage_callbacks=cb_map)

        await hb.beat(HeartbeatCycle.LIGHT)
        assert len(called_stages) == 1
        assert called_stages[0][0] == HeartbeatStage.SCAN
        assert called_stages[0][1] == HeartbeatCycle.LIGHT

    @pytest.mark.asyncio
    async def test_stage_error_does_not_break_loop(self):
        bus = BodyEventBus(hub_type="memory")
        called_stages = []

        def failing_cb(stage, cycle):
            raise RuntimeError("stage failure")

        async def good_cb(stage, cycle):
            called_stages.append(stage)

        cb_map = {
            HeartbeatStage.SCAN: failing_cb,
            HeartbeatStage.TRACK: good_cb,
        }
        hb = HeartbeatLoop(event_bus=bus, stage_callbacks=cb_map)

        result = await hb.beat(HeartbeatCycle.LIGHT)

        # SCAN failed, error logged, but TRACK still ran
        assert len(result["errors"]) == 1
        assert "scan" in result["errors"][0]
        assert HeartbeatStage.TRACK in called_stages

        health = hb.health()
        assert health["pain_count"] >= 1

    @pytest.mark.asyncio
    async def test_start_stop(self):
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)

        assert hb.health()["running"] is False

        await hb.start()
        assert hb.health()["running"] is True

        await hb.stop()
        assert hb.health()["running"] is False

    # ------------------------------------------------------------------
    # Pipeline integration tests
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_beat_with_state(self):
        """beat() aceita e propaga state para os estagios reais."""
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)
        result = await hb.beat(HeartbeatCycle.LIGHT, state={"ticker": "TEST"})

        assert result["cycle"] == "light"
        assert len(result["stages_executed"]) == 3
        assert hb._state["ticker"] == "TEST"

    @pytest.mark.asyncio
    async def test_beat_publishes_pipeline_events(self):
        """FULL cycle publica eventos de pipeline reais no event_bus."""
        bus = BodyEventBus(hub_type="memory")
        received_events = []

        async def capture(event_type, **kwargs):
            received_events.append(event_type)

        hb = HeartbeatLoop(event_bus=bus)
        # Publish sync — capturamos os tipos de evento
        bus.publish = capture  # type: ignore[assignment]

        await hb.beat(HeartbeatCycle.FULL)

        # No FULL cycle, cada stage publica um evento body.heartbeat.full
        # E os stages SCORE e VERIFY publicam eventos adicionais
        full_events = [e for e in received_events if "body.heartbeat" in e]
        assert len(full_events) >= 8  # pelo menos 1 por stage

    @pytest.mark.asyncio
    async def test_score_stage_mathhub_empty_state(self):
        """SCORE com estado vazio nao quebra o loop."""
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)
        result = await hb.beat(HeartbeatCycle.FULL)

        # SCORE deve executar sem quebrar (estado vazio = partial)
        score_errors = [e for e in result["errors"] if "score" in e.lower()]
        assert len(score_errors) == 0

    @pytest.mark.asyncio
    async def test_verify_stage_fallback(self):
        """VERIFY com estado vazio usa fallback e nao quebra."""
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)
        result = await hb.beat(HeartbeatCycle.FULL)

        verify_errors = [e for e in result["errors"] if "verify" in e.lower()]
        assert len(verify_errors) == 0

    @pytest.mark.asyncio
    async def test_scan_skips_pennylab_without_ticker(self):
        """SCAN sem ticker skips Pennylab, tenta Mangala."""
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)
        result = await hb.beat(HeartbeatCycle.FULL)

        scan_errors = [e for e in result["errors"] if "scan" in e.lower()]
        assert len(scan_errors) == 0

    @pytest.mark.asyncio
    async def test_stage_execution_order(self):
        """Estagios executam na ordem correta no FULL cycle."""
        bus = BodyEventBus(hub_type="memory")
        executed_order = []

        def capture_cb(stage, cycle):
            executed_order.append(stage.value)

        cb_map = {s: capture_cb for s in FULL_STAGES}
        hb = HeartbeatLoop(event_bus=bus, stage_callbacks=cb_map)

        await hb.beat(HeartbeatCycle.FULL)

        expected_order = [s.value for s in FULL_STAGES]
        assert executed_order == expected_order
