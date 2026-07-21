"""
CORPO — Camada de corpo do SuperEzio F51.
===========================================
Event bus + Heartbeat + DNA + Memory Lattice + Immune + Emotion.
"""

from .dna import DNAEngine, Gene
from .emotion import EMOTION_LABELS, EmotionalState, PADEngine
from .event_bus import BodyEvent, BodyEventBus
from .heartbeat import HeartbeatLoop
from .immune import ImmuneSystem
from .memory_lattice import LAYER_NAMES, MemoryLattice


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
    "DNAEngine",
    "Gene",
    "EmotionalState",
    "PADEngine",
    "EMOTION_LABELS",
    "ImmuneSystem",
    "MemoryLattice",
    "LAYER_NAMES",
]
