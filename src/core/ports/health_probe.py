"""Contrato para health check de providers externos/locais.

Isola o pipeline de saber se a verificação é via HTTP, socket,
arquivo de PID, ou qualquer outro mecanismo.
"""

from __future__ import annotations

from typing import Any, Protocol


class HealthProbePort(Protocol):
    """Verifica disponibilidade de um provider."""

    async def is_ready(self, provider: Any) -> bool:
        """Retorna True se o provider está disponível para requisições."""
        ...
