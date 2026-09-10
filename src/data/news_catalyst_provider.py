"""Catalisador keyless derivado das rotas de noticia gratuitas.

A capability short_term_catalyst so tinha o Finnhub (exige chave valida); sem
ela, TODO candidato do scan morre em missing_catalyst (incidente 2026-09-10:
`short_term_catalyst: all providers exhausted []`). Aqui derivamos catalisador
de manchetes recentes das rotas keyless (google_news_ca / yahoo_conversation),
aceitando apenas termos CONCRETOS que o gate de qualidade reconhece
(core/pipeline/trade_order.py, contrato de catalyst). Sem manchete dentro da
janela com termo concreto -> {} — nunca inventamos catalisador.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

logger = logging.getLogger(__name__)

# Mesmos termos aceitos pelo contrato de catalyst do gate (trade_order.py).
# O texto final precisa conter um deles para nao virar missing_catalyst.
_CATALYST_TERMS = (
    "earnings",
    "guidance",
    "filing",
    "approval",
    "contract",
    "merger",
    "acquisition",
    "launch",
    "investor day",
    "fy results",
    "results on",
)


def _parse_published(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _match_term(title: str) -> str:
    lowered = title.lower()
    for term in _CATALYST_TERMS:
        if term in lowered:
            return term
    return ""


class NewsCatalystProvider:
    """Deriva um catalisador verificavel da manchete recente mais forte."""

    provider_name = "news_catalyst"

    def __init__(
        self,
        news_loader: Callable[[str], list[dict[str, Any]]],
        *,
        window_days: int = 14,
    ) -> None:
        self._news = news_loader
        self._window_days = window_days

    def get_short_term_catalyst(self, symbol: str, **_: Any) -> dict[str, Any]:
        try:
            items = self._news(symbol) or []
        # Fronteira de melhor esforco: falha de noticia nao derruba o scan.
        except Exception as exc:  # noqa: BLE001
            logger.warning("news_catalyst: news loader failed for %s: %s", symbol, exc)
            return {}

        cutoff = datetime.now(UTC) - timedelta(days=self._window_days)
        best: tuple[datetime, str, str, str] | None = None
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            published = _parse_published(item.get("published_date") or item.get("published_at"))
            if not title or published is None or published < cutoff:
                continue
            term = _match_term(title)
            if not term:
                continue
            source = str(item.get("source") or item.get("provider") or "")
            if best is None or published > best[0]:
                best = (published, term, title, source)

        if best is None:
            return {}
        published, term, title, source = best
        return {
            "catalyst": f"{term}: {title}"[:300],
            "event_date": published.date().isoformat(),
            "headline": title[:200],
            "news_source": source[:80],
            "window_days": self._window_days,
            "provider": self.provider_name,
        }
