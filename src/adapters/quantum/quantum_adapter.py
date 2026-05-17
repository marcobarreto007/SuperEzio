"""Factory para QuantumWalkBias — desacopla data_hub de experts."""

from __future__ import annotations

from typing import Any


def make_quantum_walk() -> Any:
    from experts.crisis.quantum_expert import QuantumWalkBias

    return QuantumWalkBias()
