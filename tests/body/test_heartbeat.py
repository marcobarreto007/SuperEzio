"""
Tests for HeartbeatLoop — Fase 2 (Heartbeat) da arquitetura CORPO.
"""

import pytest
from core.body import BodyEventBus, HeartbeatLoop
from core.body.heartbeat import (
    HeartbeatCycle,
    HeartbeatStage,
    FULL_STAGES,
    LIGHT_STAGES,
    DEEP_STAGES,
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
        assert len(result["stages_executed"]) == 6
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_beat_deep(self):
        bus = BodyEventBus(hub_type="memory")
        hb = HeartbeatLoop(event_bus=bus)
        result = await hb.beat(HeartbeatCycle.DEEP)

        assert result["cycle"] == "deep"
        assert len(result["stages_executed"]) == 7  # 6 FULL + Crystallize
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
