"""Factory para QuantumExpert — desacopla data_hub de experts."""

from __future__ import annotations

from typing import Any


def make_quantum_expert() -> Any:
    from experts.crisis.quantum_expert import QuantumExpert

    return QuantumExpert()
