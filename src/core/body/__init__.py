"""
CORPO — Camada de corpo do SuperEzio F51.
===========================================
Event bus + Heartbeat + ciclo vital do sistema.
"""

from .event_bus import BodyEvent, BodyEventBus
from .heartbeat import HeartbeatLoop


def create_body(event_bus_type: str = "memory") -> dict:
    """
    Factory para criar o corpo do SuperEzio.

    Args:
        event_bus_type: "memory" (default) ou "redis"

    Returns:
        dict com {"event_bus": BodyEventBus, "heartbeat": HeartbeatLoop}
    """
    bus = BodyEventBus(hub_type=event_bus_type)
    hb = HeartbeatLoop(event_bus=bus)
    return {"event_bus": bus, "heartbeat": hb}


__all__ = [
    "BodyEvent",
    "BodyEventBus",
    "HeartbeatLoop",
    "create_body",
]
