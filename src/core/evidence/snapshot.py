"""C2 Frozen Snapshot — numbers with provenance. C3 binds Bob to them."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.storage.atomic import atomic_write_text

from .pack import canonical_json, pack_digest, sha256_hex

SCHEMA_VERSION = "c2.1"
SNAPSHOT_FILENAME = "snapshot.json"

_HASH_EXCLUDE = frozenset({"integrity", "as_of"})

# name -> (unit, formula_id, provenance fact keys)
_NUMBER_META: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "latest_price": ("quote", "math_hub.price_series", ("price",)),
    "annualized_return": ("fraction", "math_hub.annualized_return", ("ohlcv",)),
    "volatility": ("fraction", "math_hub.volatility", ("ohlcv",)),
    "sharpe": ("ratio", "math_hub.sharpe", ("ohlcv",)),
    "sortino": ("ratio", "math_hub.sortino", ("ohlcv",)),
    "max_drawdown": ("fraction", "math_hub.max_drawdown", ("ohlcv",)),
    "var_95": ("fraction", "math_hub.var_95", ("ohlcv",)),
    "cvar_95": ("fraction", "math_hub.cvar_95", ("ohlcv",)),
    "kelly_fraction": ("fraction", "math_hub.kelly", ("ohlcv",)),
    "crisis_score": ("score", "math_hub.crisis_aggregate", ("ohlcv",)),
    "bootstrap_expected_return": ("fraction", "math_hub.return_bootstrap", ("ohlcv",)),
    "f51_decision_score": ("score", "f51.decision_score", ("ohlcv", "price")),
    "rsi": ("index", "math_hub.rsi14", ("ohlcv",)),
    "macd": ("quote", "math_hub.macd", ("ohlcv",)),
    "sma20": ("quote", "math_hub.sma20", ("ohlcv",)),
    "sma50": ("quote", "math_hub.sma50", ("ohlcv",)),
    "ema20": ("quote", "math_hub.ema20", ("ohlcv",)),
    "vwap": ("quote", "math_hub.vwap", ("ohlcv",)),
}


def payload_for_snapshot_hash(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in snapshot.items() if key not in _HASH_EXCLUDE}
    price = payload.get("price")
    if isinstance(price, dict):
        payload["price"] = {key: value for key, value in price.items() if key != "as_of"}
    return payload


def seal_snapshot(snapshot: dict[str, Any], *, writer: str = "evidence.snapshot") -> dict[str, Any]:
    sealed = dict(snapshot)
    digest = sha256_hex(canonical_json(payload_for_snapshot_hash(sealed)))
    sealed["integrity"] = {
        "canonical_json_sha256": digest,
        "writer": writer,
        "schema_version": SCHEMA_VERSION,
    }
    return sealed


def verify_snapshot_seal(snapshot: dict[str, Any]) -> bool:
    integrity = snapshot.get("integrity") or {}
    digest = integrity.get("canonical_json_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        return False
    return digest == sha256_hex(canonical_json(payload_for_snapshot_hash(snapshot)))


def _scalar(value: Any) -> Any:
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return None


def _number(
    *,
    name: str,
    value: Any,
    unit: str,
    formula_id: str,
    provenance: tuple[str, ...],
    computed_by: str,
) -> dict[str, Any] | None:
    scalar = _scalar(value)
    if scalar is None:
        return None
    return {
        "name": name,
        "value": scalar,
        "unit": unit,
        "formula_id": formula_id,
        "provenance": list(provenance),
        "computed_by": computed_by,
    }


def freeze_snapshot(
    *,
    pack: dict[str, Any],
    math_report: dict[str, Any] | None,
    run_id: str,
    extra_numbers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project pack facts + MathHub numbers into an immutable snapshot.

    ``extra_numbers`` adds code-calculated values the pack does not carry
    (each ``{name, value, unit, formula_id, provenance, computed_by}``); they
    enter the ledger only when the name is not already taken.
    """
    facts = pack.get("facts") if isinstance(pack.get("facts"), dict) else {}
    ticker = str(pack.get("ticker") or "")
    as_of = str(pack.get("created_at") or "")
    report = math_report if isinstance(math_report, dict) else {}
    math_numbers = report.get("numbers") if isinstance(report.get("numbers"), dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}

    price_fact = facts.get("price") if isinstance(facts.get("price"), dict) else {}
    price_block: dict[str, Any] | None = None
    if price_fact.get("status") == "OK":
        price_block = {
            "value": price_fact.get("value"),
            "as_of": price_fact.get("as_of"),
            "provider": price_fact.get("provider") or "unknown",
            "fact_key": "price",
        }

    ohlcv_fact = facts.get("ohlcv") if isinstance(facts.get("ohlcv"), dict) else {}
    series_ref = None
    if ohlcv_fact.get("status") == "OK" and isinstance(ohlcv_fact.get("value"), dict):
        series_ref = dict(ohlcv_fact["value"])

    numbers: dict[str, Any] = {}
    if price_block is not None:
        entry = _number(
            name="price",
            value=price_block["value"],
            unit="quote",
            formula_id="fact.price",
            provenance=("price",),
            computed_by=str(price_block["provider"]),
        )
        if entry is not None:
            numbers["price"] = entry

    for name, (unit, formula_id, provenance) in _NUMBER_META.items():
        value = math_numbers.get(name)
        if value is None:
            value = summary.get(name)
        entry = _number(
            name=name,
            value=value,
            unit=unit,
            formula_id=formula_id,
            provenance=provenance,
            computed_by="math_hub",
        )
        if entry is not None:
            numbers[name] = entry

    # Numbers code calculated outside MathHub (execution policy ceilings, for
    # instance) that a trade answer legitimately cites in prose. Without them
    # in the ledger, "stop de 5%" reads as a model invention and the bind
    # rejects an answer that only repeated the house's own configuration.
    for extra in extra_numbers or ():
        if not isinstance(extra, dict):
            continue
        entry = _number(
            name=str(extra.get("name") or ""),
            value=extra.get("value"),
            unit=str(extra.get("unit") or ""),
            formula_id=str(extra.get("formula_id") or extra.get("name") or ""),
            provenance=tuple(extra.get("provenance") or ()),
            computed_by=str(extra.get("computed_by") or "pipeline"),
        )
        if entry is not None and entry["name"] and entry["name"] not in numbers:
            numbers[entry["name"]] = entry

    try:
        pack_sha = pack_digest(pack)
    except ValueError:
        pack_sha = ""

    body = {
        "snapshot_id": uuid.uuid5(uuid.NAMESPACE_OID, f"snapshot:{run_id}:{ticker}").hex,
        "pack_id": pack.get("pack_id"),
        "pack_sha256": pack_sha,
        "run_id": run_id,
        "ticker": ticker,
        "as_of": as_of,
        "currency": None,
        "frozen": True,
        "price": price_block,
        "series_ref": series_ref,
        "numbers": numbers,
        "schema_version": SCHEMA_VERSION,
    }
    return seal_snapshot(body, writer="core.evidence.snapshot")


def save_snapshot(snapshot: dict[str, Any], dest_dir: Path | str) -> Path:
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / SNAPSHOT_FILENAME
    atomic_write_text(path, canonical_json(snapshot) + "\n", encoding="utf-8")
    return path


def format_snapshot_binding(snapshot: dict[str, Any]) -> str:
    """Deterministic text listing frozen numbers Bob may cite."""
    lines = ["═══ SNAPSHOT FROZEN (cite only these numbers) ═══"]
    numbers = snapshot.get("numbers") if isinstance(snapshot.get("numbers"), dict) else {}
    for name in sorted(numbers):
        item = numbers[name]
        if not isinstance(item, dict):
            continue
        provenance = ",".join(str(part) for part in (item.get("provenance") or []))
        lines.append(
            f"{name}={item.get('value')} unit={item.get('unit')} "
            f"formula={item.get('formula_id')} provenance={provenance}"
        )
    return "\n".join(lines)


def _allowed_number_values(snapshot: dict[str, Any]) -> list[float]:
    numbers = snapshot.get("numbers") if isinstance(snapshot.get("numbers"), dict) else {}
    allowed: list[float] = []
    for item in numbers.values():
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        allowed.append(float(value))
    return allowed


# A material claim is money or a percentage — the shapes the answer uses to
# move capital. Until 2026-09-14 the extractor saw only "$190.50" and "1.23",
# so "alocar 8% do capital" and "3500 CAD" carried a model-written number
# through the bind untouched: the model computed it, nothing checked it.
#
# The token patterns, in priority order (money wins an overlapping span).
# The sign belongs to the claim: drawdown, VaR and CVaR are negative in the
# ledger and negative in prose ("drawdown -23,38%") — without the sign the
# extractor reads 23,38 and the code number looks like an invention.
_PERCENT_NUMBER = re.compile(
    r"(?<![\w.,])(?P<num>[-−]?\d+(?:[.,]\d+)?)\s*(?:%|por\s+cento|per\s+cent)", re.IGNORECASE
)
_MONEY_CODE_NUMBER = re.compile(
    r"(?<![\w.,])(?P<num>[-−]?\d+(?:[.,]\d+)?)\s*(?:CAD|USD|BRL|EUR)\b", re.IGNORECASE
)
_MONEY_NUMBER = re.compile(r"(?<![\w.,])(?P<sign>[-−]?)(?:R\$|\$)\s*(?P<num>[-−]?\d+(?:[.,]\d+)?)")
_DECIMAL_NUMBER = re.compile(r"(?<![\d.,])(?P<num>[-−]?\d+\.\d{2,})(?![\d])")

_TOKEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_MONEY_NUMBER, "money"),
    (_MONEY_CODE_NUMBER, "money"),
    (_PERCENT_NUMBER, "percent"),
    (_DECIMAL_NUMBER, "decimal"),
)

# Claim mirrors of a number: a percent cited from a fraction-unit number is
# the same code value the human reads — volatility=0.32 is "32%".
_FRACTION_UNITS = frozenset({"fraction"})

# "VaR 95%" names the confidence level of the formula, not a value the answer
# moves capital with: 95 is a parameter inside the ledger row name (var_95).
# It is skipped only when that row exists — otherwise "VaR 8%" would launder an
# invented number past the bind.
_CONFIDENCE_LABEL = re.compile(r"(?i)(?:^|[^\w])(var|cvar|es|ic|confidence|confian[cç]a)\s*$")


def _parse_number_token(token: str) -> float | None:
    raw = token.replace("R$", "").replace("$", "").replace(" ", "").replace(",", ".")
    raw = raw.replace("−", "-")  # typographic minus
    raw = re.sub(r"(?i)(?:%|por\s*cento|per\s*cent|cad|usd|brl|eur)$", "", raw).strip()
    try:
        return float(raw)
    except ValueError:
        return None


def _claimed_token(match: re.Match[str]) -> str:
    """The number as the text claims it, sign included."""
    raw = match.group("num")
    sign = match.groupdict().get("sign") or ""
    if sign and not raw.startswith(("-", "−")):
        return sign + raw
    return raw


def _decimals_of(raw: str) -> int:
    for separator in (".", ","):
        if separator in raw:
            return len(raw.split(separator, 1)[1])
    return 0


def _is_confidence_level(
    content: str, start: int, valor: float, ledger_names: frozenset[str]
) -> bool:
    """True for the "95" of "VaR 95%" when the ledger has the row that uses it."""
    if not ledger_names or valor != int(valor):
        return False
    match = _CONFIDENCE_LABEL.search(content[:start])
    if match is None:
        return False
    return f"{match.group(1).lower()}_{int(valor)}" in ledger_names


def _material_numbers(
    content: str, ledger_names: frozenset[str] = frozenset()
) -> list[tuple[int, str, float, str, int]]:
    """Material numbers in ``content`` as (offset, trecho, valor, unidade, casas)."""
    claimed: list[tuple[int, int]] = []
    found: list[tuple[int, str, float, str, int]] = []
    for pattern, unidade in _TOKEN_PATTERNS:
        for match in pattern.finditer(content or ""):
            if any(start < match.end() and match.start() < end for start, end in claimed):
                continue
            raw = _claimed_token(match)
            valor = _parse_number_token(raw)
            if valor is None:
                continue
            claimed.append((match.start(), match.end()))
            if unidade == "percent" and _is_confidence_level(
                content, match.start(), valor, ledger_names
            ):
                continue
            found.append((match.start(), match.group(0).strip(), valor, unidade, _decimals_of(raw)))
    found.sort(key=lambda item: item[0])
    return found


def number_ledger(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """``snapshot.numbers`` as ledger rows: each value plus where it came from."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("numbers"), dict):
        return []
    as_of = str(snapshot.get("as_of") or "")
    rows: list[dict[str, Any]] = []
    for name, item in snapshot["numbers"].items():
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        rows.append(
            {
                "numero": str(name),
                "valor": float(value),
                "unidade": str(item.get("unit") or ""),
                "fonte": str(item.get("formula_id") or item.get("computed_by") or name),
                "calculado_em": str(item.get("as_of") or as_of),
            }
        )
    return rows


@dataclass(frozen=True)
class NumberClaim:
    """A material number read from prose, bound to the code that calculated it.

    ``rastreado`` is the verdict: True means the value exists in
    ``snapshot.numbers`` (a code calculation); False means the model wrote it
    and no code source backs it.
    """

    valor: float
    trecho: str
    unidade: str  # "money" | "percent" | "decimal"
    rastreado: bool
    fonte: str  # formula_id of the backing ledger row, "" when untraced
    numero: str  # ledger row name, "" when untraced
    calculado_em: str  # snapshot as_of of the backing row
    motivo: str  # "" | "sem_fonte_de_codigo" | "sem_snapshot_congelado"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _match_ledger(
    valor: float, unidade: str, casas: int, ledger: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Find the ledger row a claim may be citing, or None.

    Tolerance comes from how the claim was written, not from a global epsilon:
    a claim rounds a code number at its own precision ("32%" may cite
    volatility=0.3187; "$190" may cite 190.5) and may not invent one. The
    fraction reading of a percentage carries two extra decimals of precision
    ("8%" is 0.08 — it may not stretch to 0.3187).
    """
    tolerance = max(1e-9, 0.5 * (10.0**-casas))
    for row in ledger:
        raw = row["valor"]
        if abs(valor - raw) <= tolerance:
            return row
        if unidade != "percent":
            continue
        if row["unidade"] in _FRACTION_UNITS and abs(valor - raw * 100.0) <= tolerance:
            return row
        if abs(valor / 100.0 - raw) <= tolerance / 100.0:
            return row
    return None


def number_claims(content: str, snapshot: dict[str, Any] | None = None) -> list[NumberClaim]:
    """Every material number in ``content`` with the code source behind it.

    The envelope the pipeline reads: numbers are code-calculated and
    provenance-tracked, the narrative only carries them. An untraced claim is
    never promoted to a fact — it comes back ``rastreado=False`` with a
    ``motivo``.
    """
    text = content if isinstance(content, str) else str(content or "")
    if not text.strip():
        return []
    frozen = isinstance(snapshot, dict) and bool(snapshot.get("frozen"))
    ledger = number_ledger(snapshot if frozen else None)
    ledger_names = frozenset(row["numero"] for row in ledger)
    claims: list[NumberClaim] = []
    for _offset, trecho, valor, unidade, casas in _material_numbers(text, ledger_names):
        row = _match_ledger(valor, unidade, casas, ledger) if ledger else None
        if row is not None:
            motivo = ""
        elif not frozen:
            motivo = "sem_snapshot_congelado"
        else:
            motivo = "sem_fonte_de_codigo"
        claims.append(
            NumberClaim(
                valor=valor,
                trecho=trecho,
                unidade=unidade,
                rastreado=row is not None,
                fonte=str(row["fonte"]) if row is not None else "",
                numero=str(row["numero"]) if row is not None else "",
                calculado_em=str(row["calculado_em"]) if row is not None else "",
                motivo=motivo,
            )
        )
    return claims


def unbound_number_claims(
    content: str, snapshot: dict[str, Any] | None = None
) -> list[NumberClaim]:
    """The claims the bind refuses: numbers no code calculation backs."""
    return [claim for claim in number_claims(content, snapshot) if not claim.rastreado]


def bind_answer_to_snapshot(content: str, snapshot: dict[str, Any] | None) -> str:
    """Replace answers that cite numbers absent from the frozen snapshot.

    Extraction is not the source of truth — snapshot.numbers is. Casual turns
    without a frozen snapshot pass through unchanged.
    """
    text = content if isinstance(content, str) else str(content or "")
    if not text.strip():
        return text
    if not isinstance(snapshot, dict) or not snapshot.get("frozen"):
        return text
    if not _allowed_number_values(snapshot):
        return text
    unbound = [claim.trecho for claim in unbound_number_claims(text, snapshot)]
    if not unbound:
        return text
    unique = list(dict.fromkeys(unbound))
    return (
        "SNAPSHOT BIND REJECTED. Números fora do snapshot: "
        + ", ".join(unique)
        + ".\nUse somente:\n"
        + format_snapshot_binding(snapshot)
    )
