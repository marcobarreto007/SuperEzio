"""Contrato para coleta de dados.

O pipeline depende deste port para obter dados de ticker e scans,
sem conhecer subprocessos, HTTP ou providers externos.
"""

from __future__ import annotations

from typing import Any, Protocol


class DataCollectorPort(Protocol):
    """Coletor de dados financeiros e macro."""

    async def collect_all(self, ticker: str, timeout: float) -> dict[str, Any]:
        """Coleta todos os dados disponíveis para um ticker.

        Retorna dict com:
        - data_quality: "provider_or_computed" | "partial" | "timeout" | "error"
        - source_errors: list[str]
        - technicals, fundamentals, realtime_price, news, sentiment, macro, reddit
        """
        ...

    async def run_scan(self, message: str, filters: dict[str, Any]) -> dict[str, Any]:
        """Executa market scan baseado em filtros e query do usuário.

        Retorna dict com candidates, filters, data_quality, source_errors.
        """
        ...
