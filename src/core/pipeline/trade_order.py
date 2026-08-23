"""DECISIVE_TRADE_ORDER quality gates, liquidity normalization, and confidence."""

from __future__ import annotations

import os
from typing import Any

# Short-term trade order thresholds (configurable via env).
MIN_AVG_DAILY_VOLUME_SHARES = int(os.getenv("SUPEREZIO_MIN_AVG_DAILY_VOLUME_SHARES", "500000"))
MIN_AVG_DAILY_DOLLAR_VOLUME_USD = float(
    os.getenv("SUPEREZIO_MIN_AVG_DAILY_DOLLAR_VOLUME_USD", "10000000")
)
BUY_CONFIDENCE_THRESHOLD = int(os.getenv("SUPEREZIO_BUY_CONFIDENCE_THRESHOLD", "65"))
STRONG_CONFIDENCE_THRESHOLD = int(os.getenv("SUPEREZIO_STRONG_CONFIDENCE_THRESHOLD", "80"))
MAX_CONFIDENCE_WITH_GATE_FAILURE = int(os.getenv("SUPEREZIO_MAX_CONFIDENCE_GATE_FAILURE", "55"))

_EMPTY_RISK_VALUES = frozenset({"—", "-", "", "see risk controls", "ver controles de risco"})
_GENERIC_EVIDENCE_VALUES = frozenset(
    {
        "broad market / sector risk; position size 0.5% of capital",
        "macro tape risk and sector rotation pressure",
        "market risk",
        "volatility risk",
        "technical setup",
        "short-term opportunity",
        "liquid equity on major exchange",
        "suitable for short-term tactical allocation",
    }
)
_UNTRUSTED_PROVENANCE_SOURCES = frozenset(
    {"", "fallback", "fallback_empty", "generic", "generated", "unknown", "no_data"}
)


def volume_shares_from_raw(volume: Any) -> float | None:
    """Normalize a volume field to share count."""
    if volume is None:
        return None
    if isinstance(volume, str):
        text = volume.strip().lower()
        if not text or text in _EMPTY_RISK_VALUES:
            return None
        multiplier = 1.0
        cleaned = text.replace(",", "").replace(" shares", "").replace(" shares/day", "")
        cleaned = cleaned.replace("/day", "").strip()
        if cleaned.endswith("b"):
            multiplier = 1_000_000_000.0
            cleaned = cleaned[:-1]
        elif cleaned.endswith("m"):
            multiplier = 1_000_000.0
            cleaned = cleaned[:-1]
        elif cleaned.endswith("k"):
            multiplier = 1_000.0
            cleaned = cleaned[:-1]
        try:
            return float(cleaned) * multiplier
        except ValueError:
            return None
    if isinstance(volume, (int, float)):
        if volume <= 0:
            return None
        return float(volume)
    return None


def normalize_liquidity_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    """Attach explicit liquidity fields to a candidate dict (in-place)."""
    raw = (
        candidate.get("avg_daily_volume_shares")
        or candidate.get("volume")
        or candidate.get("avg_volume")
        or candidate.get("liquidity")
    )
    shares = volume_shares_from_raw(raw)
    if shares is not None:
        candidate["avg_daily_volume_shares"] = shares
        price = candidate.get("price")
        if isinstance(price, (int, float)) and price > 0:
            candidate["avg_daily_dollar_volume"] = float(price) * shares
    return candidate


def format_liquidity_display(candidate: dict[str, Any]) -> str:
    """Render liquidity with explicit units — never a misleading raw float."""
    shares = candidate.get("avg_daily_volume_shares")
    if shares is None:
        shares = volume_shares_from_raw(
            candidate.get("volume") or candidate.get("avg_volume") or candidate.get("liquidity")
        )
    if shares is None or shares <= 0:
        return "—"

    if shares >= 1_000_000_000:
        vol_text = f"{shares / 1_000_000_000:.2f}B shares/day"
    elif shares >= 1_000_000:
        vol_text = f"{shares / 1_000_000:.2f}M shares/day"
    elif shares >= 1_000:
        vol_text = f"{shares / 1_000:.1f}K shares/day"
    else:
        vol_text = f"{int(shares)} shares/day"

    dollar = candidate.get("avg_daily_dollar_volume")
    if isinstance(dollar, (int, float)) and dollar >= 1_000_000:
        if dollar >= 1_000_000_000:
            dollar_text = f"${dollar / 1_000_000_000:.2f}B/day"
        else:
            dollar_text = f"${dollar / 1_000_000:.1f}M/day"
        return f"{vol_text} ({dollar_text})"
    return vol_text


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in _EMPTY_RISK_VALUES
    return True


def _is_actionable_evidence(value: Any, field: str) -> bool:
    """Return whether text is concrete enough to support an investment gate."""
    if not _is_present(value):
        return False
    if not isinstance(value, str):
        return True
    normalized = " ".join(value.strip().lower().split())
    if normalized in _GENERIC_EVIDENCE_VALUES or len(normalized) < 20:
        return False
    has_number = bool(any(character.isdigit() for character in normalized))
    concrete_terms = {
        "catalyst": (
            "earnings",
            "guidance",
            "filing",
            "approval",
            "contract",
            "merger",
            "acquisition",
            "launch",
            "investor day",
        ),
        "risk": (
            "earnings",
            "guidance",
            "revenue",
            "margin",
            "debt",
            "dilution",
            "regulatory",
            "currency",
            "consensus",
            "moving average",
        ),
        "invalidation": (
            "close below",
            "close above",
            "prior-week",
            "prior day",
            "cancelled",
            "guidance",
            "moving average",
        ),
    }
    return has_number or any(term in normalized for term in concrete_terms.get(field, ()))


def _provenance(candidate: dict[str, Any]) -> dict[str, Any]:
    value = candidate.get("provenance") or candidate.get("evidence_provenance")
    return value if isinstance(value, dict) else {}


def _has_field_provenance(
    candidate: dict[str, Any], field: str, *, _visited: frozenset[str] = frozenset()
) -> bool:
    """Require an attributable source for every field that can authorize a trade."""
    provenance = _provenance(candidate)
    if field in _visited:
        return False
    visited = _visited | {field}
    entry = provenance.get(field)
    if isinstance(entry, str):
        source = entry.strip().lower()
        return source not in _UNTRUSTED_PROVENANCE_SOURCES and not any(
            token in source for token in ("fallback", "generic", "generated", "unknown", "no_data")
        )
    if not isinstance(entry, dict):
        return False
    source = str(entry.get("source") or entry.get("provider") or "").strip().lower()
    if source in _UNTRUSTED_PROVENANCE_SOURCES:
        return False
    if source.startswith("computed:"):
        inputs = entry.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            return False
        return all(
            _has_field_provenance(candidate, str(input_field), _visited=visited)
            for input_field in inputs
        )
    return not any(
        token in source for token in ("fallback", "generic", "generated", "unknown", "no_data")
    )


def evaluate_quality_gates(candidate: dict[str, Any]) -> tuple[bool, list[str]]:
    """Hard gates for short-term DECISIVE_TRADE_ORDER eligibility."""
    normalize_liquidity_fields(candidate)
    failures: list[str] = []

    ticker = str(candidate.get("ticker") or "").strip()
    if not ticker:
        failures.append("missing_ticker")
    elif not _has_field_provenance(candidate, "ticker"):
        failures.append("missing_ticker_provenance")

    price = candidate.get("price")
    if not isinstance(price, (int, float)) or price <= 0:
        failures.append("missing_price")
    elif not _has_field_provenance(candidate, "price"):
        failures.append("missing_price_provenance")

    allow_penny = bool(
        candidate.get("allow_penny_otc")
        or candidate.get("allow_microcap")
        or (isinstance(price, (int, float)) and price < 5.0)
    )
    min_shares = 50_000 if allow_penny else MIN_AVG_DAILY_VOLUME_SHARES
    min_dollar = 100_000 if allow_penny else MIN_AVG_DAILY_DOLLAR_VOLUME_USD

    shares = candidate.get("avg_daily_volume_shares")
    if shares is None or shares <= 0:
        failures.append("missing_liquidity")
    elif shares < min_shares:
        failures.append("liquidity_below_minimum")
    elif not (
        _has_field_provenance(candidate, "avg_daily_volume_shares")
        or _has_field_provenance(candidate, "volume")
        or _has_field_provenance(candidate, "avg_volume")
        or _has_field_provenance(candidate, "liquidity")
    ):
        failures.append("missing_liquidity_provenance")

    dollar = candidate.get("avg_daily_dollar_volume")
    if dollar is not None and dollar < min_dollar:
        failures.append("dollar_volume_below_minimum")

    catalyst = (
        candidate.get("catalyst")
        or candidate.get("thesis")
        or candidate.get("short_term_thesis")
        or candidate.get("reason")
    )
    if not _is_actionable_evidence(catalyst, "catalyst"):
        failures.append("missing_catalyst")
    elif not any(
        _has_field_provenance(candidate, field)
        for field in ("catalyst", "thesis", "short_term_thesis", "reason")
        if candidate.get(field) == catalyst
    ):
        failures.append("missing_catalyst_provenance")

    risk = candidate.get("risk") or candidate.get("downside_risk")
    if not _is_actionable_evidence(risk, "risk"):
        failures.append("missing_risk")
    elif not any(
        _has_field_provenance(candidate, field)
        for field in ("risk", "downside_risk")
        if candidate.get(field) == risk
    ):
        failures.append("missing_risk_provenance")

    invalidation = candidate.get("invalidation") or candidate.get("invalidation_condition")
    if not _is_actionable_evidence(invalidation, "invalidation"):
        failures.append("missing_invalidation")
    elif not any(
        _has_field_provenance(candidate, field)
        for field in ("invalidation", "invalidation_condition")
        if candidate.get(field) == invalidation
    ):
        failures.append("missing_invalidation_provenance")

    if candidate.get("price_error") or candidate.get("provider_error"):
        failures.append("provider_error")

    market = str(candidate.get("market") or candidate.get("exchange") or "").lower()
    currency = str(candidate.get("currency") or "").upper()
    if (
        currency
        and currency != "USD"
        and any(token in market for token in ("united states", "nasdaq", "nyse", "usa", "us"))
    ):
        failures.append("currency_market_mismatch")

    return (len(failures) == 0, failures)


def compute_model_confidence(
    candidate: dict[str, Any],
    *,
    gate_failures: list[str] | None = None,
    source_errors: list[str] | None = None,
    weak_universe: bool = False,
) -> int:
    """Deterministic 0-100 confidence from data quality (not profit probability)."""
    normalize_liquidity_fields(candidate)
    failures = gate_failures if gate_failures is not None else evaluate_quality_gates(candidate)[1]

    score = 25
    if not failures:
        score += 20

    catalyst = (
        candidate.get("catalyst") or candidate.get("thesis") or candidate.get("short_term_thesis")
    )
    if _is_present(catalyst):
        score += 10
        if len(str(catalyst)) > 40:
            score += 5

    shares = candidate.get("avg_daily_volume_shares") or 0
    if isinstance(shares, (int, float)):
        if shares >= 5_000_000:
            score += 12
        elif shares >= MIN_AVG_DAILY_VOLUME_SHARES:
            score += 8
        elif shares >= 100_000:
            score += 3

    dollar = candidate.get("avg_daily_dollar_volume")
    if isinstance(dollar, (int, float)) and dollar >= MIN_AVG_DAILY_DOLLAR_VOLUME_USD:
        score += 8

    price = candidate.get("price")
    if isinstance(price, (int, float)) and price > 0:
        score += 5

    if _is_present(candidate.get("risk") or candidate.get("downside_risk")):
        score += 8
    if _is_present(candidate.get("invalidation") or candidate.get("invalidation_condition")):
        score += 8

    if candidate.get("name") or candidate.get("company"):
        score += 3

    provider = str(candidate.get("provider") or candidate.get("source") or "")
    if provider and "finnhub" in provider.lower():
        score += 2

    # Penalties
    if failures:
        score = min(score, MAX_CONFIDENCE_WITH_GATE_FAILURE)
        for failure in failures:
            if failure in {"missing_liquidity", "liquidity_below_minimum"}:
                score -= 15
            elif failure == "missing_risk":
                score -= 12
            elif failure == "missing_invalidation":
                score -= 8
            elif failure == "missing_catalyst":
                score -= 10
            elif failure in {"provider_error", "currency_market_mismatch"}:
                score -= 10

    if source_errors:
        score -= min(15, 5 * len(source_errors))

    if candidate.get("price_error"):
        score -= 10

    if weak_universe:
        score -= 5

    score = max(0, min(100, score))

    if failures and score >= STRONG_CONFIDENCE_THRESHOLD:
        score = MAX_CONFIDENCE_WITH_GATE_FAILURE

    if failures and score > MAX_CONFIDENCE_WITH_GATE_FAILURE:
        score = MAX_CONFIDENCE_WITH_GATE_FAILURE

    return score


def decide_final_action(confidence: int, gate_failures: list[str]) -> str:
    """Map confidence + gates to BUY_CANDIDATE / WAIT / REJECT_ALL."""
    if gate_failures:
        hard_reject = {
            "missing_catalyst",
            "missing_catalyst_provenance",
            "missing_liquidity",
            "missing_liquidity_provenance",
            "missing_price",
            "missing_price_provenance",
            "missing_risk_provenance",
            "missing_invalidation_provenance",
            "missing_ticker_provenance",
            "provider_error",
            "currency_market_mismatch",
        }
        if any(failure in hard_reject for failure in gate_failures):
            return "REJECT_ALL"
        return "WAIT"
    if confidence >= BUY_CONFIDENCE_THRESHOLD:
        return "BUY_CANDIDATE"
    return "WAIT"


def rank_candidates(
    candidates: list[dict[str, Any]],
    *,
    source_errors: list[str] | None = None,
    weak_universe: bool = False,
) -> list[dict[str, Any]]:
    """Score and rank candidates; each entry includes confidence and gate metadata."""
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        normalize_liquidity_fields(candidate)
        eligible, failures = evaluate_quality_gates(candidate)
        confidence = compute_model_confidence(
            candidate,
            gate_failures=failures,
            source_errors=source_errors,
            weak_universe=weak_universe,
        )
        ranked.append(
            {
                "candidate": candidate,
                "confidence": confidence,
                "gate_failures": failures,
                "eligible": eligible,
                "decision": decide_final_action(confidence, failures),
            }
        )
    ranked.sort(key=lambda item: item["confidence"], reverse=True)
    return ranked


def pick_candidate(
    ranked: list[dict[str, Any]],
    *,
    excluded_tickers: set[str] | list[str] | None = None,
    require_buy: bool = False,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Pick the next best candidate, skipping excluded tickers."""
    excluded = {str(t).upper() for t in (excluded_tickers or []) if t}
    for entry in ranked:
        candidate = entry.get("candidate") or {}
        ticker = str(candidate.get("ticker") or "").upper()
        if not ticker or ticker in excluded:
            continue
        if require_buy and entry.get("decision") != "BUY_CANDIDATE":
            continue
        return entry, ranked
    return None, ranked
