"""Contrato para audit trail de decisões.

Toda decisão de roteamento, seleção e fallback deve ser registrada
com contexto suficiente para explicar *por que* algo aconteceu.
"""

from __future__ import annotations

from typing import Any, Protocol


class AuditLogPort(Protocol):
    """Registro imutável de decisões arquiteturais."""

    def record_decision(
        self,
        run_id: str,
        step: str,
        decision: str,
        rationale: dict[str, Any],
    ) -> None:
        """Registra uma decisão.

        Args:
            run_id: identificador da execução do pipeline.
            step: nome do step (ex: "ceo_primary", "gateway_fallback",
                  "agent_selector", "data_source").
            decision: o que foi decidido (ex: "primary_external",
                      "technical+ risk", "ticker_analysis").
            rationale: dicionário com os dados que justificam a decisão.
        """
        ...

    def flush(self) -> None:
        """Garante persistência dos registros pendentes."""
        ...
