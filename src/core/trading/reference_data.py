"""Reference data for Brazilian fixed income — tax and deposit insurance.

Structured, deterministic and source-carrying. Follows the pattern this repo
already proved twice:

  - ``config/td_direct_commission_free_etfs.json``: ``schema_version``,
    ``verified_at``, ``source_url`` per manifest.
  - ``src/core/trading/td_universe.py``: ``fresh``/``stale``/``missing``/
    ``invalid`` state with EXPLICIT degradation, never to "allow everything".

Every number here comes from an authoritative source consulted on its
``verified_at`` date — IR from Lei 11.033/2004, IOF from Decreto 6.306/2007
and the FGC limits from the guarantor itself. Each block carries its own
``source_url`` because they are different instruments from different issuers.

When the manifest is not ``fresh`` the lookups return ``None`` (fail-closed)
instead of guessing a tax rate or a coverage limit. A wrong tax number is
worse than an absent one, and silence is what the None forces.

Lookups are deliberately deterministic range lookups — no semantic search, no
embedding, no fuzzy match for a number that has to be exact.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.paths import project_path

REFERENCE_DIR = project_path("config", "reference")
BR_TAX_AND_FGC_PATH = REFERENCE_DIR / "br_tax_and_fgc.json"

_REFERENCE_SCHEMA_VERSION = 1
_DEFAULT_TTL_DAYS = 365


def _resolve_path(path: str | Path | None) -> Path:
    return Path(path) if path is not None else BR_TAX_AND_FGC_PATH


def _age_days(verified_at: object) -> float | None:
    """Age of the manifest in days, or None when ``verified_at`` is unusable."""
    raw = str(verified_at or "")
    if not raw:
        return None
    try:
        # fromisoformat aceita o sufixo "Z" desde o Python 3.11.
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return (datetime.now(UTC) - stamp).total_seconds() / 86400.0


def _load_manifest(path: str | Path | None = None) -> dict[str, Any] | None:
    """Parsed manifest, or None when missing / unreadable / wrong schema."""
    target = _resolve_path(path)
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    # Conjunto pequeno: leitura do arquivo (OSError) e JSON invalido (ValueError).
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != _REFERENCE_SCHEMA_VERSION:
        return None
    return data


def reference_state(path: str | Path | None = None) -> dict[str, Any]:
    """State of the reference manifest: fresh / stale / missing / invalid.

    Degrading is explicit and never silent: consumers must read this before
    trusting a lookup, and the lookups themselves refuse (None) unless the
    state is ``fresh``.
    """
    target = _resolve_path(path)
    if not target.exists():
        return {"state": "missing"}

    data = _load_manifest(path)
    if data is None:
        # Present but unreadable or wrong schema_version — invalid, not missing.
        return {"state": "invalid"}

    age_days = _age_days(data.get("verified_at"))
    if age_days is None:
        return {"state": "invalid"}

    try:
        ttl_days = int(data.get("ttl_days") or _DEFAULT_TTL_DAYS)
    except (TypeError, ValueError):
        ttl_days = _DEFAULT_TTL_DAYS

    blocks = [
        name
        for name in ("ir_renda_fixa", "iof_renda_fixa", "fgc")
        if isinstance(data.get(name), dict)
    ]
    return {
        "state": "fresh" if age_days <= ttl_days else "stale",
        "verified_at": data.get("verified_at"),
        "age_days": round(age_days, 2),
        "ttl_days": ttl_days,
        "blocks": blocks,
    }


def _fresh_manifest(path: str | Path | None = None) -> dict[str, Any] | None:
    """Manifest only when FRESH, else None — the fail-closed gate for lookups."""
    if reference_state(path).get("state") != "fresh":
        return None
    return _load_manifest(path)


def _as_fraction(percent: object) -> float | None:
    """Percentual (22.5) -> fracao (0.225). None quando nao for numero."""
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
        return None
    return float(percent) / 100.0


def _normalized_days(days: object) -> int | None:
    if isinstance(days, bool) or not isinstance(days, (int, float)):
        return None
    value = int(days)
    return value if value >= 0 else None


def ir_rate_for_days(days: object, path: str | Path | None = None) -> float | None:
    """Aliquota de IR (fracao) para uma aplicacao de renda fixa de N dias.

    Ex.: 180 dias -> 0.225; 181 -> 0.20; 720 -> 0.175; 721 -> 0.15.

    Devolve None quando o dado nao e utilizavel (manifest ausente, stale ou
    invalido; dias invalidos; faixa nao encontrada). Nunca devolve uma
    aliquota estimada: um IR errado e pior que um IR ausente.
    """
    data = _fresh_manifest(path)
    if data is None:
        return None
    normalized = _normalized_days(days)
    if normalized is None:
        return None

    block = data.get("ir_renda_fixa")
    if not isinstance(block, dict):
        return None
    faixas = block.get("faixas")
    if not isinstance(faixas, list):
        return None

    for faixa in faixas:
        if not isinstance(faixa, dict):
            continue
        low = faixa.get("prazo_dias_min")
        high = faixa.get("prazo_dias_max")
        if not isinstance(low, int) or isinstance(low, bool):
            continue
        if high is not None and (not isinstance(high, int) or isinstance(high, bool)):
            continue
        if normalized >= low and (high is None or normalized <= high):
            return _as_fraction(faixa.get("aliquota_pct"))
    return None


def iof_rate_for_days(days: object, path: str | Path | None = None) -> float | None:
    """Aliquota de IOF (fracao do rendimento) no dia N do resgate.

    Ex.: dia 1 -> 0.96; dia 15 -> 0.50; dia 29 -> 0.03; dia 30 em diante -> 0.0.

    A partir do 30o dia a aliquota e zero por forca do Anexo (dia 30 = 00), o
    que e um valor CONHECIDO e nao um chute. Dia 0 ou negativo e entrada
    invalida e devolve None. Sem manifest fresco, devolve None.
    """
    data = _fresh_manifest(path)
    if data is None:
        return None
    normalized = _normalized_days(days)
    if normalized is None:
        return None

    block = data.get("iof_renda_fixa")
    if not isinstance(block, dict):
        return None
    tabela = block.get("tabela")
    if not isinstance(tabela, list) or not tabela:
        return None

    zero_dia = block.get("aliquota_zero_dia")
    if not isinstance(zero_dia, int) or isinstance(zero_dia, bool):
        return None
    if normalized >= zero_dia:
        return 0.0

    for row in tabela:
        if not isinstance(row, dict):
            continue
        if row.get("dia") == normalized:
            return _as_fraction(row.get("aliquota_pct"))
    # Dentro da janela regressiva mas fora da tabela: dado incompleto, nao zero.
    return None


def fgc_limits(path: str | Path | None = None) -> dict[str, Any] | None:
    """Limites de cobertura do FGC, ou None quando o dado nao e utilizavel.

    Devolve o bloco inteiro (limite por CPF/instituicao, teto global por
    periodo, listas de cobertos e nao cobertos) com a fonte junto — o
    consumidor precisa poder citar de onde veio.
    """
    data = _fresh_manifest(path)
    if data is None:
        return None
    block = data.get("fgc")
    if not isinstance(block, dict):
        return None
    return dict(block)
