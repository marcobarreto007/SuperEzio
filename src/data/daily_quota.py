"""Cota diária por provedor — o eixo que o pacing por intervalo não cobre.

O free tier do Alpha Vantage é **25 requisições por DIA**, não "5 por minuto"
(fonte primária: https://www.alphavantage.co/support/ — "25 API requests per
day", conferido 2026-09-14; a página não menciona nenhum limite por minuto).
Intervalo mínimo entre chamadas não limita um total diário: com o pacing de
12 s que o hub usava, um scan podia disparar 300 chamadas/hora e queimar a
cota do dia em minutos sem que nenhum CircuitBreaker abrisse — o provedor
responde bem às primeiras 25 e devolve "rate limit" nas seguintes, o que o
fluxo tratava como falha transitória e tentava de novo.

Este módulo guarda data + contagem por provedor num arquivo de estado e
responde "ainda cabe?" antes de cada requisição. A virada de dia é UTC — o
mesmo eixo em que a Alpha Vantage conta a cota.

Estado: ``data/cache/provider_daily_quota.json`` (ou ``$SUPEREZIO_DATA_DIR``),
formato ``{"alpha_vantage": {"date": "2026-09-14", "count": 7}}``. O caminho
fica sob ``data/cache/`` — já coberto pelo ``.gitignore`` — para que o estado
de runtime não apareça como arquivo novo no ``git status``.

Escrita atômica (tmp + replace) e contador sob lock: o hub roda as chamadas
em worker threads e dois scans concorrentes não podem contar a mesma cota duas
vezes. Falha de I/O **não** derruba a chamada de dados (best-effort, com log):
o pior caso é voltar ao comportamento antigo — queimar a cota —, nunca
inventar dado nem travar o scan.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_STATE_FILENAME = "provider_daily_quota.json"
_DEFAULT_DIR = os.path.join("data", "cache")


def _quota_dir() -> Path:
    """Diretório do arquivo de estado (``SUPEREZIO_DATA_DIR`` quando definido)."""
    raw = os.getenv("SUPEREZIO_DATA_DIR") or _DEFAULT_DIR
    path = Path(raw)
    if path.is_absolute():
        return path
    from core.paths import resolve_project_path

    return resolve_project_path(path)


def state_path() -> Path:
    """Caminho absoluto do arquivo de estado da cota diária."""
    return _quota_dir() / _STATE_FILENAME


def _today() -> str:
    """Data corrente em UTC, ISO (``2026-09-14``)."""
    return datetime.now(UTC).date().isoformat()


def _load() -> dict[str, Any]:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(state: dict[str, Any]) -> None:
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        # Best-effort: estado ilegível significa "sem cota registrada", não
        # erro de dados. Loga para o operador ver o contador degradado.
        logger.warning("[DAILY_QUOTA] falha ao gravar %s: %s", path, exc)


def _entry(state: dict[str, Any], provider: str) -> tuple[str, int]:
    """Devolve ``(data, contagem)`` da entrada, zerando na virada de dia."""
    raw = state.get(provider)
    today = _today()
    if not isinstance(raw, dict) or raw.get("date") != today:
        return today, 0
    try:
        return today, int(raw.get("count") or 0)
    except (TypeError, ValueError):
        return today, 0


def used(provider: str) -> int:
    """Requisições já contadas hoje para *provider*."""
    with _LOCK:
        _, count = _entry(_load(), provider)
        return count


def remaining(provider: str, limit: int) -> int:
    """Requisições que ainda cabem hoje para *provider* (nunca negativo)."""
    return max(0, int(limit) - used(provider))


def is_exhausted(provider: str, limit: int) -> bool:
    """True quando a cota diária de *provider* já foi consumida.

    O chamador deve pular a rota e cair para o próximo provedor — não chamar
    e apostar que vem erro. Uma requisição que a Alpha Vantage recusa por
    cota **já foi consumida** do lado dela; tentar de novo só piora.
    """
    return used(provider) >= int(limit)


def consume(provider: str) -> int:
    """Registra uma requisição real e devolve a contagem do dia.

    Chamar **apenas** quando a requisição HTTP vai de fato acontecer — hit de
    cache não pode consumir cota.
    """
    with _LOCK:
        state = _load()
        date, count = _entry(state, provider)
        count += 1
        state[provider] = {"date": date, "count": count}
        _write(state)
        return count


def snapshot() -> dict[str, Any]:
    """Estado bruto por provedor, para diagnóstico e health."""
    with _LOCK:
        state = _load()
    today = _today()
    out: dict[str, Any] = {}
    for provider in sorted(state):
        date, count = _entry(state, provider)
        out[provider] = {"date": date, "count": count, "stale": date != today}
    return out
