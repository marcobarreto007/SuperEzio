"""
Tests for BodyEventBus — Fase 1 (Event Bus) da arquitetura CORPO.
"""

import pytest

from core.body import BodyEvent, BodyEventBus, create_body


class TestBodyEvent:
    """BodyEvent model validation."""

    def test_default_construction(self):
        event = BodyEvent(event_type="event:body.pain.liver")
        assert event.event_type == "event:body.pain.liver"
        assert event.source == "f51-body"
        assert event.severity.value == "info"
        assert isinstance(event.correlation_id, str)
        assert len(event.correlation_id) > 0

    def test_custom_fields(self):
        event = BodyEvent(
            event_type="event:pipeline.math.completed",
            source="test-math",
            payload={"result": 42},
            severity="critical",
        )
        assert event.event_type == "event:pipeline.math.completed"
        assert event.source == "test-math"
        assert event.payload["result"] == 42
        assert event.severity.value == "critical"

    def test_to_envelope_roundtrip(self):
        original = BodyEvent(
            event_type="event:body.dna.mutated",
            payload={"gene": "FOXO3"},
            source="test",
        )
        envelope = original.to_envelope()
        assert envelope.event_type == original.event_type

        reconstructed = BodyEvent.from_envelope(envelope)
        assert reconstructed.event_type == original.event_type
        assert reconstructed.payload["gene"] == "FOXO3"

    def test_event_type_validation(self):
        """Verifica que qualquer string é aceita como event_type (sem validação rígida)."""
        event = BodyEvent(event_type="custom:test.event")
        assert event.event_type == "custom:test.event"


class TestBodyEventBus:
    """BodyEventBus publish/subscribe/health."""

    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self):
        bus = BodyEventBus(hub_type="memory")
        received = []

        async def handler(event: BodyEvent):
            received.append(event)

        await bus.subscribe("event:test.alpha", handler)
        await bus.publish("event:test.alpha", payload={"msg": "hello"})

        assert len(received) == 1
        assert received[0].event_type == "event:test.alpha"
        assert received[0].payload["msg"] == "hello"

    @pytest.mark.asyncio
    async def test_list_topics(self):
        bus = BodyEventBus(hub_type="memory")

        async def handler(event: BodyEvent):
            pass

        assert bus.list_topics() == []

        await bus.subscribe("event:pipeline.math.completed", handler)
        await bus.subscribe("event:body.pain.liver", handler)

        topics = bus.list_topics()
        assert "event:pipeline.math.completed" in topics
        assert "event:body.pain.liver" in topics
        assert len(topics) == 2

    @pytest.mark.asyncio
    async def test_health_check(self):
        bus = BodyEventBus(hub_type="memory")
        result = await bus.health_check()

        assert result["status"] == "ok"
        assert result["hub_type"] == "memory"
        assert "active_topics_count" in result

    @pytest.mark.asyncio
    async def test_create_body_factory(self):
        body = create_body(event_bus_type="memory")
        assert "event_bus" in body
        assert "heartbeat" in body
        assert isinstance(body["event_bus"], BodyEventBus)
