"""NewsAPI Circuit Breaker — cache, quota state, fallback limpo.
429 nao pode spammar log nem travar analise.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 min
COOLDOWN_AFTER_429_SECONDS = 900  # 15 min
FALLBACK_SOURCES = ["news_scout", "reddit_pulse", "finnhub"]


@dataclass
class NewsCircuitState:
    quota_exhausted: bool = False
    cooldown_until: float = 0.0
    consecutive_429s: int = 0
    requests_today: int = 0
    last_success: float = 0.0

    def record_429(self) -> None:
        self.consecutive_429s += 1
        if self.consecutive_429s >= 3:
            self.quota_exhausted = True
            self.cooldown_until = time.time() + COOLDOWN_AFTER_429_SECONDS
            logger.warning("[news_circuit] NewsAPI quota exhausted — cooling down for %ds", COOLDOWN_AFTER_429_SECONDS)

    def record_success(self) -> None:
        self.consecutive_429s = 0
        self.requests_today += 1
        self.last_success = time.time()

    @property
    def available(self) -> bool:
        if self.quota_exhausted and time.time() < self.cooldown_until:
            return False
        if self.quota_exhausted and time.time() >= self.cooldown_until:
            self.quota_exhausted = False
            self.consecutive_429s = 0
            logger.info("[news_circuit] NewsAPI cooldown ended — re-enabled")
        return True


class NewsCircuitBreaker:
    """Circuit breaker com cache e fallback para NewsAPI."""

    def __init__(self):
        self._state = NewsCircuitState()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}  # ticker → (timestamp, data)

    def get(self, ticker: str) -> dict[str, Any] | None:
        """Retorna dados cacheados se disponíveis e não expirados."""
        if ticker in self._cache:
            ts, data = self._cache[ticker]
            if time.time() - ts < CACHE_TTL_SECONDS:
                return data
        return None

    def set(self, ticker: str, data: dict[str, Any]) -> None:
        self._cache[ticker] = (time.time(), data)
        self._state.record_success()

    def handle_429(self) -> None:
        self._state.record_429()

    @property
    def available(self) -> bool:
        return self._state.available

    @property
    def fallback_sources(self) -> list[str]:
        return list(FALLBACK_SOURCES)

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "quota_exhausted": self._state.quota_exhausted,
            "consecutive_429s": self._state.consecutive_429s,
            "requests_today": self._state.requests_today,
            "cache_entries": len(self._cache),
        }


# Singleton
_news_circuit: NewsCircuitBreaker | None = None


def get_news_circuit() -> NewsCircuitBreaker:
    global _news_circuit
    if _news_circuit is None:
        _news_circuit = NewsCircuitBreaker()
    return _news_circuit
