"""Mangala Engine — caçador de oportunidades baratas do SuperEzio.

Baseado em Tim Sykes (penny stock breakout) + PUCK ALGO SCANNER (0-100 score)
+ Whale Accumulation V2.

Universe: stocks < $10, volume > 500K, price > $0.50
Score 0-100 baseado em:
  - Volume anomaly (atual / média 20d): 0-30 pontos
  - Whale prints detectados: 0-25 pontos
  - Price momentum (5d): 0-20 pontos
  - RSI (40-70 sweet spot): 0-15 pontos
  - Catalyst (news/social): 0-10 pontos

Sinais:
  >= 80: "MANGALA!" (high conviction flip)
  60-79: "WATCH" (potential setup)
  40-59: "MEH" (not ready)
  < 40:  "PASS" (ignore)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Universe filters ───────────────────────────────────────────────────────
MAX_PRICE = 10.0
MIN_VOLUME = 500_000
MIN_PRICE = 0.50
TOP_N = 10
TOP_N_FOR_BOB = 5

# ── DNA gene loader (optional — legacy-safe fallback) ──────────────────────


def _load_gene(name: str, default: float) -> float:
    """Load a gene from the DNA engine if available, else return *default*.

    This allows the Mangala engine to run in legacy mode (standalone without
    the CORPO DNA layer) while still benefiting from evolutionary tuning when
    the full stack is deployed.
    """
    try:
        from core.body.dna import get_dna

        dna = get_dna()
        return dna.get_gene(name)
    except (ImportError, AttributeError, KeyError):
        return default


# ── Score thresholds (from DNA genes, with fallback defaults) ─────────────
HIGH_CONVICTION = _load_gene("mangala.high_conviction", 80)  # "MANGALA!"
WATCH_THRESHOLD = _load_gene("mangala.watch_threshold", 60)  # "WATCH"
MEH_THRESHOLD = 40  # "MEH" (not in DNA — kept as fixed)

# ── Weight maximums (from DNA genes, with fallback defaults) ──────────────
MAX_VOLUME_SCORE = int(_load_gene("mangala.volume_weight", 30))
MAX_WHALE_SCORE = int(_load_gene("mangala.whale_weight", 25))
MAX_MOMENTUM_SCORE = int(_load_gene("mangala.momentum_weight", 20))
MAX_RSI_SCORE = int(_load_gene("mangala.rsi_weight", 15))
MAX_CATALYST_SCORE = int(_load_gene("mangala.catalyst_weight", 10))


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════


def scan_mangala_opportunities(
    data_hub: Any,
    scanner: Any | None = None,
) -> list[dict[str, Any]]:
    """Scan for Mangala (high-conviction penny stock) opportunities.

    Args:
        data_hub: DataHub instance for routing data collection (quotes, candles,
                  news, sentiment).
        scanner: Optional scanner. Can be:
            - An object with a ``scan_equities(max_price=...)`` method
              (e.g. OpenBBScanner).
            - A callable ``fn(max_price=..., min_volume=...)``
              (e.g. ``scan_penny_stocks``).
            - If None, falls back to ``scan_penny_stocks`` internally.

    Returns:
        Top 10 opportunities sorted by Mangala Score descending. Each item:
            ticker, price, volume, name, score, signal, factors, flip_plan
    """
    candidates = _get_candidates(scanner)
    if not candidates:
        logger.info("Mangala: no candidates found")
        return []

    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            ticker = candidate.get("ticker", "")
            if not ticker:
                continue
            price = candidate.get("price", 0) or 0
            if price < MIN_PRICE:
                continue

            stock_data = _collect_stock_data(data_hub, ticker, candidate)
            result = calculate_mangala_score(stock_data)
            scored.append(
                {
                    "ticker": ticker,
                    "price": round(price, 2),
                    "volume": candidate.get("volume", 0) or 0,
                    "name": candidate.get("name", "") or ticker,
                    **result,
                }
            )
        except Exception as exc:
            logger.debug("Mangala score failed for %s: %s", candidate.get("ticker"), exc)
            continue

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = scored[:TOP_N]
    logger.info("Mangala: %d candidates scored, %d high-conviction", len(scored), _count_high(top))
    return top


def calculate_mangala_score(stock_data: dict[str, Any]) -> dict[str, Any]:
    """Calculate Mangala Score 0-100 for a single stock.

    Args:
        stock_data: Dict with keys: price, volume, avg_volume_20d, closes,
                    momentum_5d, rsi, whale_print, news_count, sentiment,
                    news_headlines, etc.

    Returns:
        dict with:
            score (int): 0-100
            signal (str): "MANGALA!"|"WATCH"|"MEH"|"PASS"
            factors (dict): per-component scores
            flip_plan (dict): entry, target_5pct, stop_3pct, max_hold_days
    """
    factors: dict[str, int] = {
        "volume": _score_volume_anomaly(stock_data),
        "whale": _score_whale_prints(stock_data),
        "momentum": _score_momentum(stock_data),
        "rsi": _score_rsi(stock_data),
        "catalyst": _score_catalyst(stock_data),
    }

    total = sum(factors.values())
    total = max(0, min(100, total))

    signal = _determine_signal(total)
    flip_plan = _build_flip_plan(stock_data)

    return {
        "score": total,
        "signal": signal,
        "factors": factors,
        "flip_plan": flip_plan,
    }


def format_mangala_for_bob(opportunities: list[dict[str, Any]]) -> str:
    """Format top 5 Mangala opportunities for Bob's explanation.

    Args:
        opportunities: Output from scan_mangala_opportunities().

    Returns:
        Formatted string ready for Bob's system prompt.
    """
    if not opportunities:
        return ""

    top = opportunities[:TOP_N_FOR_BOB]
    lines = [
        "## MANGALA ENGINE — Oportunidades de Alta Conviccao",
        "",
        "| Score | Ticker | Preco | Sinal | Fatores (V/W/M/R/C) |",
        "|-------|--------|-------|-------|---------------------|",
    ]

    for opp in top:
        ticker = opp.get("ticker", "?")
        price = opp.get("price", 0)
        score = opp.get("score", 0)
        signal = opp.get("signal", "?")
        factors = opp.get("factors", {})

        factor_str = (
            f"V:{factors.get('volume', 0)} "
            f"W:{factors.get('whale', 0)} "
            f"M:{factors.get('momentum', 0)} "
            f"R:{factors.get('rsi', 0)} "
            f"C:{factors.get('catalyst', 0)}"
        )

        lines.append(f"| {score:>3} | {ticker:<6} | ${price:<6.2f} | {signal:<8} | {factor_str} |")

    high_conviction = [o for o in top if o.get("signal") == "MANGALA!"]
    if high_conviction:
        lines.append("")
        lines.append("### Planos de Entrada (MANGALA!)")
        for opp in high_conviction:
            ticker = opp.get("ticker", "?")
            flip = opp.get("flip_plan", {})
            lines.append(
                f"- **{ticker}**:"
                f" Entry ${flip.get('entry', 0):.2f}"
                f" | Target ${flip.get('target_5pct', 0):.2f}"
                f" | Stop ${flip.get('stop_3pct', 0):.2f}"
                f" | Max {flip.get('max_hold_days', 5)} dias"
            )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════


def _get_candidates(scanner: Any) -> list[dict[str, Any]]:
    """Get stock candidates under $10 with sufficient volume."""
    if scanner is not None:
        if hasattr(scanner, "scan_equities"):
            try:
                return scanner.scan_equities(max_price=MAX_PRICE) or []
            except Exception:
                pass
        if callable(scanner):
            try:
                return scanner(max_price=MAX_PRICE, min_volume=MIN_VOLUME) or []
            except Exception:
                pass

    # Fallback: use penny_scanner
    try:
        from core.scanner.penny_scanner import scan_penny_stocks

        return scan_penny_stocks(max_price=MAX_PRICE, min_volume=MIN_VOLUME)
    except Exception:
        logger.warning("Mangala: no scanner available")
        return []


def _collect_stock_data(
    data_hub: Any,
    ticker: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Collect technical, whale, and news data for a single ticker."""
    result: dict[str, Any] = {
        "ticker": ticker,
        "price": candidate.get("price", 0) or 0,
        "volume": candidate.get("volume", 0) or 0,
    }

    # ── Quote data (price, volume, prev_close) ──
    try:
        if hasattr(data_hub, "get_quote"):
            quote = data_hub.get_quote(ticker)
            if isinstance(quote, dict) and "error" not in quote:
                result["price"] = float(quote.get("price", result["price"]) or result["price"])
                result["volume"] = int(quote.get("volume", result["volume"]) or result["volume"])
                if quote.get("previous_close") is not None:
                    result["prev_close"] = float(quote["previous_close"])
                if quote.get("percent_change") is not None:
                    result["change_pct"] = float(quote["percent_change"])
    except Exception:
        pass

    # ── Candles (technicals + momentum) ──
    try:
        if hasattr(data_hub, "get_candles"):
            candles_resp = data_hub.get_candles(ticker, timeframe="1M")
            candles = (
                candles_resp.get("candles")
                if isinstance(candles_resp, dict)
                else candles_resp
                if isinstance(candles_resp, list)
                else []
            )
            if candles and len(candles) >= 5:
                closes = [
                    float(c.get("close") or c.get("price", 0))
                    for c in candles
                    if c.get("close") or c.get("price")
                ]
                volumes_raw = [float(c.get("volume", 0)) for c in candles]

                if closes:
                    result["closes"] = closes

                    # 20-day average volume
                    lookback = min(len(volumes_raw), 20)
                    if lookback > 0:
                        result["avg_volume_20d"] = sum(volumes_raw[-lookback:]) / lookback

                    # 5-day price momentum
                    if len(closes) >= 5:
                        prev = closes[-5]
                        if prev > 0:
                            result["momentum_5d"] = (closes[-1] - prev) / prev * 100.0

                    # RSI
                    from core.math.indicators import rsi

                    rsi_val = rsi(closes)
                    if rsi_val is not None:
                        result["rsi"] = round(rsi_val, 1)
    except Exception:
        pass

    # ── News & catalyst ──
    try:
        if hasattr(data_hub, "get_news"):
            news = data_hub.get_news(ticker, limit=5)
            if isinstance(news, list):
                result["news_count"] = len(news)
                result["news_headlines"] = [
                    str(n.get("title", n.get("headline", ""))) for n in news[:3]
                ]
    except Exception:
        pass

    # ── Sentiment ──
    try:
        if hasattr(data_hub, "get_sentiment_summary"):
            sentiment = data_hub.get_sentiment_summary(ticker)
            if isinstance(sentiment, dict) and "error" not in sentiment:
                result["sentiment"] = sentiment
    except Exception:
        pass

    return result


def _determine_signal(score: int) -> str:
    if score >= HIGH_CONVICTION:
        return "MANGALA!"
    if score >= WATCH_THRESHOLD:
        return "WATCH"
    if score >= MEH_THRESHOLD:
        return "MEH"
    return "PASS"


def _build_flip_plan(stock_data: dict[str, Any]) -> dict[str, Any]:
    """Build entry/exit plan based on current price."""
    price = stock_data.get("price", 0) or 0
    return {
        "entry": round(price, 2),
        "target_5pct": round(price * 1.05, 2),
        "stop_3pct": round(price * 0.97, 2),
        "max_hold_days": 5,
    }


def _count_high(opportunities: list[dict[str, Any]]) -> int:
    return sum(1 for o in opportunities if o.get("signal") == "MANGALA!")


# ═══════════════════════════════════════════════════════════════════════════
# Scoring functions
# ═══════════════════════════════════════════════════════════════════════════


def _score_volume_anomaly(data: dict[str, Any]) -> int:
    """Score volume anomaly 0-30 based on current / 20d average volume."""
    volume = data.get("volume", 0) or 0
    avg_vol = data.get("avg_volume_20d", 0) or 0
    if avg_vol <= 0 or volume <= 0:
        return 0

    ratio = volume / avg_vol
    if ratio >= 5.0:
        return 30
    if ratio >= 3.0:
        return 25
    if ratio >= 2.0:
        return 20
    if ratio >= 1.5:
        return 15
    if ratio >= 1.2:
        return 10
    if ratio >= 0.8:
        return 5
    return 0


def _score_whale_prints(data: dict[str, Any]) -> int:
    """Score whale prints 0-25 based on whale detection signals.

    Uses explicit whale_print data when available, otherwise falls back to
    a volume/price heuristic.
    """
    score = 0

    # Explicit pennylab whale detection data
    whale_info = data.get("whale_print") or {}
    if whale_info:
        label = str(whale_info.get("label", "")).upper()
        confidence = float(whale_info.get("confidence", 0) or 0)

        if label == "FORTE" and confidence > 0.7:
            score = 25
        elif label == "PROVAVEL" or label == "PROVÁVEL":
            score = 20
        elif label == "MODERADO":
            score = 12
        elif label == "FRACO":
            score = 5

    # Fallback heuristic: high volume ratio + low price
    if score == 0:
        volume = data.get("volume", 0) or 0
        price = data.get("price", 0) or 0
        avg_vol = data.get("avg_volume_20d", 0) or 0

        if volume > 0 and avg_vol > 0 and price > 0:
            ratio = volume / avg_vol
            if ratio > 4.0 and price < 5:
                score = 15
            elif ratio > 2.5:
                score = 8

    return score


def _score_momentum(data: dict[str, Any]) -> int:
    """Score price momentum 0-20 based on 5-day price change."""
    momentum = data.get("momentum_5d")
    if momentum is None:
        return 0

    if momentum >= 15:
        return 20
    if momentum >= 10:
        return 18
    if momentum >= 7:
        return 15
    if momentum >= 5:
        return 12
    if momentum >= 3:
        return 10
    if momentum >= 1:
        return 5
    if momentum >= -1:
        return 3
    return 0


def _score_rsi(data: dict[str, Any]) -> int:
    """Score RSI 0-15. Sweet spot: 40-70."""
    rsi_val = data.get("rsi")
    if rsi_val is None:
        return 0

    if 55 <= rsi_val <= 65:
        return 15
    if 50 <= rsi_val <= 70:
        return 12
    if 45 <= rsi_val <= 75:
        return 8
    if 40 <= rsi_val <= 78:
        return 5
    if 30 <= rsi_val <= 80:
        return 3
    return 0


def _score_catalyst(data: dict[str, Any]) -> int:
    """Score catalyst/news 0-10 based on recent news and social signals."""
    score = 0

    news_count = data.get("news_count", 0) or 0
    if news_count >= 5:
        score += 5
    elif news_count >= 3:
        score += 3
    elif news_count >= 1:
        score += 2

    sentiment = data.get("sentiment") or {}
    if sentiment:
        sent_label = str(sentiment.get("sentiment_label", "")).lower()
        sent_score = float(sentiment.get("sentiment_score", 0) or 0)

        if "bullish" in sent_label or sent_score > 0.3:
            score += 3
        elif sent_score > 0:
            score += 1

    headlines = data.get("news_headlines") or []
    catalyst_keywords = [
        "earnings",
        "guidance",
        "upgrade",
        "outperform",
        "breakthrough",
        "contract",
        "partnership",
        "approval",
    ]
    for headline in headlines:
        h = str(headline).lower()
        if any(kw in h for kw in catalyst_keywords):
            score += 2
            break

    return min(score, MAX_CATALYST_SCORE)
