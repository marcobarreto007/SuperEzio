"""
Pipeline Cache — LRU Cache + TTL para operações caras
=======================================================
Cache para:
  - Resultados de detect_ticker() (TTL curto, pois mensagens são únicas)
  - Resultados de infer_scan_filters()
  - Dados de mercado (TTL médio, 30s-60s)
  - Resultados de company profile (TTL longo, 5min)
  - Resultados de macro data (TTL longo, 10min)
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar
from functools import wraps
from collections import OrderedDict

from ..observability.neural_log import log_event
from ..observability.debug_logger import debug_logger, MODULE_CACHE

F = TypeVar("F", bound=Callable[..., Any])

# ── LRU Cache with TTL ───────────────────────────────────────────────────


class LRUCache:
    """
    Cache LRU (Least Recently Used) com TTL (Time-To-Live).

    Args:
        maxsize: Número máximo de itens no cache
        ttl: Tempo de vida em segundos (default: 60)

    Uso:
        cache = LRUCache(maxsize=100, ttl=60)
        cache.put("key", value)
        value = cache.get("key")  # None se expirado ou não existente
    """

    def __init__(self, maxsize: int = 100, ttl: float = 60.0) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Optional[Any]:
        """Retorna valor do cache, ou None se ausente/expirado."""
        if key not in self._cache:
            self._misses += 1
            debug_logger.trace(MODULE_CACHE, "Cache MISS", key=key[:50])
            return None

        timestamp, value = self._cache[key]
        if time.time() - timestamp > self._ttl:
            # Expirado
            del self._cache[key]
            self._misses += 1
            self._evictions += 1
            debug_logger.trace(MODULE_CACHE, "Cache EXPIRED", key=key[:50])
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        debug_logger.trace(MODULE_CACHE, "Cache HIT", key=key[:50])
        return value

    def put(self, key: str, value: Any) -> None:
        """Insere/atualiza valor no cache."""
        if key in self._cache:
            self._cache.move_to_end(key)
            debug_logger.trace(MODULE_CACHE, "Cache UPDATE", key=key[:50])
        elif len(self._cache) >= self._maxsize:
            removed_key, _ = self._cache.popitem(last=False)  # Remove LRU
            self._evictions += 1
            debug_logger.trace(
                MODULE_CACHE, "Cache EVICTION", removed_key=str(removed_key)[:50]
            )
        else:
            debug_logger.trace(MODULE_CACHE, "Cache INSERT", key=key[:50])

        self._cache[key] = (time.time(), value)

    def invalidate(self, key: str) -> None:
        """Remove item específico do cache."""
        self._cache.pop(key, None)
        debug_logger.trace(MODULE_CACHE, "Cache INVALIDATE", key=key[:50])

    def clear(self) -> None:
        """Limpa cache inteiro."""
        self._cache.clear()
        debug_logger.info(MODULE_CACHE, "Cache CLEARED")

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": self.size,
            "maxsize": self._maxsize,
            "ttl": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
            "evictions": self._evictions,
        }


# ── Cached function decorator ───────────────────────────────────────────


def cached(
    cache: LRUCache,
    key_func: Optional[Callable[..., str]] = None,
) -> Callable[[F], F]:
    """
    Decorator que cacheia resultados de função usando LRUCache.

    Args:
        cache: Instância de LRUCache
        key_func: Função para gerar chave do cache (default: str(args) + str(kwargs))

    Uso:
        @cached(my_cache)
        def expensive_function(x: int) -> str:
            return expensive_computation(x)
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"

            result = cache.get(key)
            if result is not None:
                return result

            result = func(*args, **kwargs)
            cache.put(key, result)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


# ── Global Cache Instances ───────────────────────────────────────────────

# Ticker detection cache (TTL curto porque mensagens são únicas, mas repetições ocorrem)
ticker_cache = LRUCache(maxsize=200, ttl=30.0)

# Scan filters cache (TTL curto)
scan_filters_cache = LRUCache(maxsize=100, ttl=30.0)

# Market data cache (TTL médio — preços mudam)
market_data_cache = LRUCache(maxsize=50, ttl=30.0)

# Company profile cache (TTL longo — dados fundamentalistas mudam pouco)
company_profile_cache = LRUCache(maxsize=100, ttl=300.0)  # 5 min

# Macro data cache (TTL muito longo — dados macro mudam semanalmente)
macro_data_cache = LRUCache(maxsize=20, ttl=600.0)  # 10 min

# Quant analysis cache (TTL médio)
quant_cache = LRUCache(maxsize=50, ttl=60.0)

# Risk metrics cache (TTL médio)
risk_cache = LRUCache(maxsize=50, ttl=60.0)

# News/sentiment cache (TTL curto)
sentiment_cache = LRUCache(maxsize=30, ttl=20.0)

# Reddit signal cache (TTL médio)
reddit_cache = LRUCache(maxsize=30, ttl=120.0)


def get_all_cache_stats() -> Dict[str, Any]:
    """Retorna estatísticas de todos os caches para monitoramento."""
    return {
        "ticker": ticker_cache.stats,
        "scan_filters": scan_filters_cache.stats,
        "market_data": market_data_cache.stats,
        "company_profile": company_profile_cache.stats,
        "macro_data": macro_data_cache.stats,
        "quant": quant_cache.stats,
        "risk": risk_cache.stats,
        "sentiment": sentiment_cache.stats,
        "reddit": reddit_cache.stats,
    }


def clear_all_caches() -> None:
    """Limpa todos os caches (útil para testes ou reset)."""
    ticker_cache.clear()
    scan_filters_cache.clear()
    market_data_cache.clear()
    company_profile_cache.clear()
    macro_data_cache.clear()
    quant_cache.clear()
    risk_cache.clear()
    sentiment_cache.clear()
    reddit_cache.clear()
    log_event("CACHE", "ALL_CLEARED", {})
