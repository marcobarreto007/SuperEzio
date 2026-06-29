"""Market Hours Detection - US Equity Markets (NYSE/NASDAQ).

Detecta horários de trading para ações US considerando timezone US/Eastern
e feriados da Bolsa de Valores de Nova York.

Regras:
- Pre-market: 04:00-09:30 ET
- Regular hours: 09:30-16:00 ET
- After-hours: 16:00-20:00 ET
- Closed: Weekends e feriados
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# US Eastern Time (UTC-5 standard, UTC-4 DST)
_EASTERN_STANDARD = timezone(timedelta(hours=-5))
_EASTERN_DAYLIGHT = timezone(timedelta(hours=-4))


def _get_eastern_timezone(now: datetime | None = None) -> timezone:
    """Retorna timezone US Eastern ajustado para DST."""
    reference = now or datetime.now(timezone.utc)

    # DST nos EUA: segundo domingo de março às 02:00 local
    # até primeiro domingo de novembro às 02:00 local
    def is_dst(dt: datetime) -> bool:
        """Simplificado: DST entre março e novembro."""
        # Na prática, usar pytz ou zoneinfo seria melhor
        # Este é um fallback simplificado
        march_start = datetime(dt.year, 3, 8, tzinfo=timezone.utc)  # Aprox 2o domingo
        november_start = datetime(dt.year, 11, 1, tzinfo=timezone.utc)
        return march_start <= dt < november_start

    if is_dst(reference.astimezone(timezone.utc)):
        return _EASTERN_DAYLIGHT
    return _EASTERN_STANDARD


def _to_eastern(dt: datetime | None = None) -> datetime:
    """Converte datetime para US Eastern timezone."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_get_eastern_timezone(dt))


def _is_us_holiday(dt: datetime) -> bool:
    """Verifica se data é feriado da Bolsa de NY (simplificado).

    Feriados observados pela NYSE:
    - New Year's Day (Jan 1)
    - Martin Luther King Jr. Day (3a segunda de janeiro)
    - Washington's Birthday (3a segunda de fevereiro)
    - Good Friday (sexta antes da Páscoa)
    - Memorial Day (última segunda de maio)
    - Juneteenth (Jun 19)
    - Independence Day (Jul 4)
    - Labor Day (1a segunda de setembro)
    - Thanksgiving (4a quinta de novembro)
    - Christmas Day (Dec 25)
    """
    eastern = _to_eastern(dt)
    month, day, weekday = eastern.month, eastern.day, eastern.weekday()

    # New Year's Day
    if month == 1 and day == 1:
        return True

    # Juneteenth (observed Jun 19 or closest weekday)
    if month == 6 and day == 19:
        return True
    if month == 6 and day == 20 and weekday == 0:  # Monday obs
        return True

    # Independence Day
    if month == 7 and day == 4:
        return True

    # Christmas Day
    if month == 12 and day == 25:
        return True

    # Memorial Day (última segunda de maio)
    if month == 5 and weekday == 0:  # Monday
        if day >= 25:  # Last week
            return True

    # Labor Day (1a segunda de setembro)
    if month == 9 and weekday == 0 and day <= 7:
        return True

    # Thanksgiving (4a quinta de novembro)
    if month == 11 and weekday == 3:  # Thursday
        if 22 <= day <= 28:  # 4th Thursday
            return True

    # MLK Day (3a segunda de janeiro) - simplificado
    if month == 1 and weekday == 0 and 14 <= day <= 21:
        return True

    # Washington's Birthday (3a segunda de fevereiro) - simplificado
    if month == 2 and weekday == 0 and 14 <= day <= 21:
        return True

    return False


def is_weekend(dt: datetime | None = None) -> bool:
    """Verifica se é sábado ou domingo em Eastern Time."""
    eastern = _to_eastern(dt)
    return eastern.weekday() >= 5  # 5=Saturday, 6=Sunday


def is_market_open(dt: datetime | None = None) -> bool:
    """Verifica se mercado está aberto (09:30-16:00 ET)."""
    if is_weekend(dt):
        return False

    if _is_us_holiday(dt):
        return False

    eastern = _to_eastern(dt)
    market_open = time(9, 30)
    market_close = time(16, 0)

    current_time = eastern.time()
    return market_open <= current_time < market_close


def is_pre_market(dt: datetime | None = None) -> bool:
    """Verifica se é pre-market (04:00-09:30 ET)."""
    if is_weekend(dt):
        return False

    if _is_us_holiday(dt):
        return False

    eastern = _to_eastern(dt)
    pre_start = time(4, 0)
    market_open = time(9, 30)

    current_time = eastern.time()
    return pre_start <= current_time < market_open


def is_after_hours(dt: datetime | None = None) -> bool:
    """Verifica se é after-hours (16:00-20:00 ET)."""
    if is_weekend(dt):
        return False

    if _is_us_holiday(dt):
        return False

    eastern = _to_eastern(dt)
    market_close = time(16, 0)
    after_end = time(20, 0)

    current_time = eastern.time()
    return market_close <= current_time < after_end


def is_market_closed(dt: datetime | None = None) -> bool:
    """Verifica se mercado está fechado."""
    return not (is_market_open(dt) or is_pre_market(dt) or is_after_hours(dt))


def get_market_phase(dt: datetime | None = None) -> str:
    """Retorna fase atual do mercado.

    Retorna:
        "MARKET_OPEN" - 09:30-16:00 ET dia útil
        "PRE_MARKET" - 04:00-09:30 ET dia útil
        "POST_MARKET" - 16:00-20:00 ET dia útil
        "CLOSED" - fora de horas, weekend ou feriado
    """
    if is_market_open(dt):
        return "MARKET_OPEN"
    if is_pre_market(dt):
        return "PRE_MARKET"
    if is_after_hours(dt):
        return "POST_MARKET"
    return "CLOSED"


def next_market_open(dt: datetime | None = None) -> datetime:
    """Retorna próximo horário de abertura do mercado."""
    reference = dt or datetime.now(timezone.utc)
    eastern = _to_eastern(reference)

    # Se já passou do fechamento, próxima abertura é amanhã
    if eastern.hour >= 16 or (eastern.hour == 16 and eastern.minute >= 0):
        eastern = eastern.replace(hour=0, minute=0, second=0, microsecond=0)
        eastern += timedelta(days=1)

    # Avançar até dia útil
    while is_weekend(eastern) or _is_us_holiday(eastern):
        eastern += timedelta(days=1)

    # Setar 09:30 ET
    eastern = eastern.replace(hour=9, minute=30, second=0, microsecond=0)

    # Converter de volta para UTC
    return eastern.astimezone(timezone.utc)


def next_market_close(dt: datetime | None = None) -> datetime:
    """Retorna próximo horário de fechamento do mercado."""
    reference = dt or datetime.now(timezone.utc)
    eastern = _to_eastern(reference)

    # Se já passou do fechamento, próximo fechamento é amanhã
    if eastern.hour >= 16 or (eastern.hour == 16 and eastern.minute >= 0):
        eastern = eastern.replace(hour=0, minute=0, second=0, microsecond=0)
        eastern += timedelta(days=1)

    # Avançar até dia útil
    while is_weekend(eastern) or _is_us_holiday(eastern):
        eastern += timedelta(days=1)

    # Setar 16:00 ET
    eastern = eastern.replace(hour=16, minute=0, second=0, microsecond=0)

    # Converter de volta para UTC
    return eastern.astimezone(timezone.utc)


def time_until_open(dt: datetime | None = None) -> timedelta:
    """Retorna tempo até próxima abertura."""
    now = dt or datetime.now(timezone.utc)
    target = next_market_open(now)
    return target - now


def time_until_close(dt: datetime | None = None) -> timedelta:
    """Retorna tempo até próximo fechamento."""
    now = dt or datetime.now(timezone.utc)
    target = next_market_close(now)
    return target - now


def get_market_day_progress(dt: datetime | None = None) -> dict[str, Any]:
    """Retorna progresso do dia de trading (0-100%).

    Útil para saber quão avançado está o dia de trading.
    """
    if not is_market_open(dt):
        return {"progress": 0.0, "phase": get_market_phase(dt)}

    eastern = _to_eastern(dt)

    # Dia de trading: 09:30-16:00 = 6.5 horas = 390 minutos
    day_start = eastern.replace(hour=9, minute=30, second=0, microsecond=0)
    day_end = eastern.replace(hour=16, minute=0, second=0, microsecond=0)

    total_minutes = 390
    elapsed_minutes = (eastern - day_start).total_seconds() / 60

    progress = min(100.0, max(0.0, (elapsed_minutes / total_minutes) * 100))

    return {
        "progress": round(progress, 2),
        "phase": "MARKET_OPEN",
        "minutes_elapsed": int(elapsed_minutes),
        "minutes_remaining": int(total_minutes - elapsed_minutes),
        "day_start_utc": day_start.astimezone(timezone.utc).isoformat(),
        "day_end_utc": day_end.astimezone(timezone.utc).isoformat(),
    }


# Singleton para cache de estado
_market_state_cache: dict[str, Any] = {"last_check": None, "state": None}


def get_market_state(cached: bool = True, cache_ttl_seconds: int = 60) -> dict[str, Any]:
    """Retorna estado completo do mercado.

    Args:
        cached: Se True, usa cache com TTL de cache_ttl_seconds
        cache_ttl_seconds: Tempo de vida do cache em segundos

    Returns:
        Dict com:
        - phase: MARKET_OPEN, PRE_MARKET, POST_MARKET, CLOSED
        - is_open: bool
        - is_pre_market: bool
        - is_after_hours: bool
        - next_open: ISO timestamp UTC
        - next_close: ISO timestamp UTC
        - time_until_open: segundos
        - time_until_close: segundos
        - day_progress: dict se market open
    """

    now = datetime.now(timezone.utc)

    if cached:
        last_check = _market_state_cache.get("last_check")
        if last_check:
            elapsed = (now - last_check).total_seconds()
            if elapsed < cache_ttl_seconds and _market_state_cache.get("state"):
                return _market_state_cache["state"]

    phase = get_market_phase(now)
    state = {
        "phase": phase,
        "is_open": is_market_open(now),
        "is_pre_market": is_pre_market(now),
        "is_after_hours": is_after_hours(now),
        "next_open_utc": next_market_open(now).isoformat(),
        "next_close_utc": next_market_close(now).isoformat(),
        "time_until_open_seconds": int(time_until_open(now).total_seconds()),
        "time_until_close_seconds": int(time_until_close(now).total_seconds()),
        "timestamp_utc": now.isoformat(),
    }

    if phase == "MARKET_OPEN":
        state["day_progress"] = get_market_day_progress(now)

    _market_state_cache["last_check"] = now
    _market_state_cache["state"] = state

    return state


if __name__ == "__main__":
    # Test mode
    state = get_market_state(cached=False)
    print(f"Phase: {state['phase']}")
    print(f"Is Open: {state['is_open']}")
    print(f"Next Open: {state['next_open_utc']}")
    print(f"Time Until Open: {state['time_until_open_seconds'] / 60:.1f} minutes")
