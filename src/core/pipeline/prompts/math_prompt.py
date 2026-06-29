"""Compact math context for DeepSeek expert prompts."""

from __future__ import annotations

from typing import Any, Mapping


def _dig(mapping: Mapping[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _number(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_price(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "N/A"
    return f"${number:.2f}"


def _fmt_percent(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "N/A"
    return f"{number * 100:.1f}%"


def _fmt_decimal(value: Any, places: int = 1) -> str:
    number = _number(value)
    if number is None:
        return "N/A"
    return f"{number:.{places}f}"


def _fmt_var(var_value: Any, latest_price: Any) -> str:
    var_number = _number(var_value)
    if var_number is None:
        return "N/A"
    price = _number(latest_price)
    if price is None:
        return _fmt_percent(var_number)
    amount = var_number * price
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):.2f}"


def _crisis_level(score: float | None) -> str:
    if score is None:
        return "unknown risk"
    if score < 0.35:
        return "low risk"
    if score < 0.70:
        return "medium risk"
    return "high risk"


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def format_math_context(report: Mapping[str, Any]) -> str:
    """Return the <=8 line structured math context consumed by DeepSeek."""

    if not report:
        return ""

    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    modules = report.get("modules") if isinstance(report.get("modules"), Mapping) else {}
    numbers = report.get("numbers") if isinstance(report.get("numbers"), Mapping) else {}

    ticker = str(report.get("ticker") or "UNKNOWN").upper()
    price = _first_present(
        summary.get("latest_price"),
        numbers.get("latest_price"),
        _dig(modules, "price_series", "values", "latest_price"),
    )

    annualized = _first_present(summary.get("return_annualized"), numbers.get("annualized_return"))
    volatility = _first_present(summary.get("volatility_annualized"), numbers.get("volatility"))
    sharpe = _first_present(summary.get("sharpe"), numbers.get("sharpe"))

    var_95 = _first_present(summary.get("var_95"), numbers.get("var_95"))
    max_drawdown = _first_present(summary.get("max_drawdown"), numbers.get("max_drawdown"))
    kelly = _first_present(summary.get("kelly_fraction"), numbers.get("kelly_fraction"))

    crisis_values = _dig(modules, "crisis_aggregate", "values") or {}
    crisis_status = _dig(modules, "crisis_aggregate", "status")
    crisis_score = _number(
        _first_present(
            summary.get("crisis_score"),
            numbers.get("crisis_score"),
            crisis_values.get("aggregate_score"),
        )
        if isinstance(crisis_values, Mapping)
        else _first_present(summary.get("crisis_score"), numbers.get("crisis_score"))
    )
    crisis_regime = (
        crisis_values.get("regime")
        if isinstance(crisis_values, Mapping) and crisis_values.get("regime")
        else None
    )
    if not crisis_regime and crisis_status in {"skipped", "insufficient_data"}:
        crisis_regime = "skipped"
    crisis_regime = str(crisis_regime or "N/A").upper()

    technical_values = _dig(modules, "technical_indicators", "values") or {}
    rsi = _first_present(
        technical_values.get("rsi14") if isinstance(technical_values, Mapping) else None,
        technical_values.get("rsi") if isinstance(technical_values, Mapping) else None,
    )
    macd_value = _first_present(
        _dig(technical_values, "macd", "macd") if isinstance(technical_values, Mapping) else None,
        _dig(technical_values, "macd", "line") if isinstance(technical_values, Mapping) else None,
        technical_values.get("macd") if isinstance(technical_values, Mapping) else None,
    )
    vwap_value = technical_values.get("vwap") if isinstance(technical_values, Mapping) else None

    crisis_score_text = "N/A"
    if crisis_score is not None:
        crisis_score_text = f"{crisis_score * 100:.0f}/100 ({_crisis_level(crisis_score)})"

    return "\n".join(
        [
            "[MATH_CONTEXT]",
            f"Ticker: {ticker} | Price: {_fmt_price(price)}",
            (
                "Returns: "
                f"annualized={_fmt_percent(annualized)} | "
                f"volatility={_fmt_percent(volatility)} | "
                f"Sharpe={_fmt_decimal(sharpe)}"
            ),
            (
                "Risk: "
                f"VaR_95={_fmt_var(var_95, price)} | "
                f"max_drawdown={_fmt_percent(max_drawdown)} | "
                f"Kelly={_fmt_percent(kelly)}"
            ),
            f"Crisis: regime={crisis_regime} | score={crisis_score_text}",
            (
                "Technicals: "
                f"RSI={_fmt_decimal(rsi)} | "
                f"MACD={_fmt_decimal(macd_value, 2)} | "
                f"VWAP={_fmt_price(vwap_value)}"
            ),
            "[/MATH_CONTEXT]",
        ]
    )


__all__ = ["format_math_context"]
