"""Mangala Daily Scan — Engine de scan proativo de oportunidades.

Torna o Mangala Engine PROATIVO:
- Roda scan a cada 15 min em horario de mercado (9:30-16:00 ET)
- Fora do mercado: a cada 60 min
- Usa DataHub (14 providers) para coleta de dados fundamentalistas
- Usa SocialWhaleProvider para sinais de whale + pump detection
- Reusa o scoring engine do mangala.py (score 0-100)
- Salva top 5 em data/mangala_daily.json
- Log "MANGALA! AAPL score=87 whale=FORTE pump=CLEAN"
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Auto-detect src/ no sys.path
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "mangala_daily.json"

# ── Universe filters (mesmos do mangala.py) ──────────────────────────────────
MAX_PRICE = 10.0
MIN_VOLUME = 500_000
MIN_PRICE = 0.50
TOP_N = 5

# ── Market hours (ET) ────────────────────────────────────────────────────────
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
# Weekdays: Monday=0, Sunday=6
WEEKEND_DAYS = {5, 6}

# ── Scan intervals ───────────────────────────────────────────────────────────
MARKET_HOURS_INTERVAL_SECONDS = 15 * 60  # 15 min
OFF_HOURS_INTERVAL_SECONDS = 60 * 60  # 60 min

# ── Whale status labels ──────────────────────────────────────────────────────
WHALE_FORTE_THRESHOLD = 70
WHALE_PROVAVEL_THRESHOLD = 50
WHALE_MODERADO_THRESHOLD = 30

# ── Pump risk labels ─────────────────────────────────────────────────────────
PUMP_ALERT_THRESHOLD = 60
PUMP_RISK_THRESHOLD = 30


# ═══════════════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class MangalaOpportunity:
    """Uma oportunidade scanneada pelo Mangala Engine."""

    ticker: str
    price: float
    volume: int
    name: str
    score: int
    signal: str
    factors: dict[str, int]
    whale_status: str
    whale_score: int
    pump_risk: str
    pump_score: int
    flip_plan: dict[str, Any]
    scanned_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════════
# Market hours helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _now_et() -> datetime:
    """Return current time approximated as US Eastern (UTC-4 EDT / UTC-5 EST)."""
    now = datetime.now(UTC)
    # Simplificacao: EDT = UTC-4 (marco a novembro)
    # Para o proposito do scan, usar UTC-4 é suficiente
    et_hour = (now.hour - 4) % 24
    return now.replace(hour=et_hour, minute=now.minute)


def is_market_hours(dt: datetime | None = None) -> bool:
    """Check if current time (ET) is within market hours (9:30-16:00, weekdays)."""
    if dt is None:
        dt = _now_et()

    # Weekend check
    if dt.weekday() in WEEKEND_DAYS:
        return False

    hour = dt.hour
    minute = dt.minute

    if hour < MARKET_OPEN_HOUR or hour > MARKET_CLOSE_HOUR:
        return False
    if hour == MARKET_OPEN_HOUR and minute < MARKET_OPEN_MINUTE:
        return False
    if hour == MARKET_CLOSE_HOUR and minute > MARKET_CLOSE_MINUTE:
        return False
    return True


def get_scan_interval() -> int:
    """Return scan interval in seconds based on current market hours."""
    return MARKET_HOURS_INTERVAL_SECONDS if is_market_hours() else OFF_HOURS_INTERVAL_SECONDS


# ═══════════════════════════════════════════════════════════════════════════════
# Whale & Pump mapping
# ═══════════════════════════════════════════════════════════════════════════════


def _map_whale_status(whale_score: int) -> str:
    """Map whale score 0-100 to label: FORTE, PROVAVEL, MODERADO, FRACO."""
    if whale_score >= WHALE_FORTE_THRESHOLD:
        return "FORTE"
    if whale_score >= WHALE_PROVAVEL_THRESHOLD:
        return "PROVAVEL"
    if whale_score >= WHALE_MODERADO_THRESHOLD:
        return "MODERADO"
    return "FRACO"


def _map_pump_risk(pump_score: int) -> str:
    """Map pump risk 0-100 to label: ALERT, RISK, CLEAN."""
    if pump_score >= PUMP_ALERT_THRESHOLD:
        return "ALERT"
    if pump_score >= PUMP_RISK_THRESHOLD:
        return "RISK"
    return "CLEAN"


# ═══════════════════════════════════════════════════════════════════════════════
# Core scan
# ═══════════════════════════════════════════════════════════════════════════════


def _get_data_hub():
    """Get or create the DataHub singleton."""
    try:
        from data.data_hub import hub

        return hub
    except Exception as exc:
        logger.warning("MangalaScan: DataHub unavailable: %s", exc)
        return None


def _get_social_whale(data_hub: Any) -> Any | None:
    """Get SocialWhaleProvider from DataHub."""
    if data_hub is None:
        return None
    try:
        return data_hub.get_provider("social_whale")
    except Exception:
        return None


def _get_pennylab_data(social_whale: Any, ticker: str) -> dict[str, Any]:
    """Collect whale signals and pump detection for a ticker.

    Returns:
        Dict with whale_score, whale_signal, pump_risk, pump_signal.
    """
    result: dict[str, Any] = {
        "whale_score": 0,
        "whale_signal": "CLEAN",
        "pump_score": 0,
        "pump_signal": "CLEAN",
    }

    if social_whale is None:
        return result

    # ── Whale signals ──
    try:
        whale_data = social_whale.get_whale_signals(ticker)
        if isinstance(whale_data, dict) and "error" not in whale_data:
            result["whale_score"] = int(whale_data.get("whale_score", 0) or 0)
            result["whale_signal"] = str(whale_data.get("signal", "CLEAN"))
    except Exception as exc:
        logger.debug("MangalaScan: whale signal failed for %s: %s", ticker, exc)

    # ── Pump detection ──
    try:
        pump_data = social_whale.get_pump_detection(ticker)
        if isinstance(pump_data, dict) and "error" not in pump_data:
            result["pump_score"] = int(pump_data.get("pump_risk", 0) or 0)
            result["pump_signal"] = str(pump_data.get("signal", "CLEAN"))
    except Exception as exc:
        logger.debug("MangalaScan: pump detection failed for %s: %s", ticker, exc)

    return result


def _get_candidates(data_hub: Any) -> list[dict[str, Any]]:
    """Get stock candidates under $10 with sufficient volume.

    Reuses the same logic as mangala.py's _get_candidates.
    """
    # Try penny_scanner first
    try:
        from core.scanner.penny_scanner import scan_penny_stocks

        candidates = scan_penny_stocks(max_price=MAX_PRICE, min_volume=MIN_VOLUME)
        if candidates:
            return candidates
    except Exception:
        pass

    # Fallback: use DataHub to build a candidate list
    # Try trending stocks from ApeWisdom or SocialWhale
    try:
        if data_hub is not None:
            ape = data_hub.get_provider("apewisdom")
            if ape is not None:
                trending = ape.get_trending_stocks(limit=20)
                if isinstance(trending, list):
                    candidates = []
                    for item in trending:
                        ticker = str(item.get("ticker", item.get("symbol", ""))).upper()
                        price = float(item.get("price", 0) or 0)
                        volume = int(item.get("volume", 0) or 0)
                        if ticker and MIN_PRICE <= price <= MAX_PRICE and volume >= MIN_VOLUME:
                            candidates.append(
                                {
                                    "ticker": ticker,
                                    "price": price,
                                    "volume": volume,
                                    "name": str(item.get("name", ticker)),
                                }
                            )
                    if candidates:
                        return candidates
    except Exception:
        pass

    logger.warning("MangalaScan: no scanner available")
    return []


def _collect_stock_data(data_hub: Any, ticker: str, candidate: dict[str, Any]) -> dict[str, Any]:
    """Collect technical data for a ticker via DataHub.

    Reuses the same pattern as mangala.py's _collect_stock_data.
    """
    result: dict[str, Any] = {
        "ticker": ticker,
        "price": candidate.get("price", 0) or 0,
        "volume": candidate.get("volume", 0) or 0,
    }

    if data_hub is None:
        return result

    # ── Quote data ──
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

    # ── Candles (technicals) ──
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
                    try:
                        from core.math.indicators import rsi

                        rsi_val = rsi(closes)
                        if rsi_val is not None:
                            result["rsi"] = round(rsi_val, 1)
                    except Exception:
                        pass
    except Exception:
        pass

    # ── News ──
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


def _calculate_mangala_score(stock_data: dict[str, Any]) -> dict[str, Any]:
    """Calculate Mangala Score 0-100 for a single stock.

    Reuses mangala.py's calculate_mangala_score when available,
    otherwise does inline calculation.
    """
    try:
        from core.pipeline.nodes.mangala import calculate_mangala_score as _calc

        return _calc(stock_data)
    except Exception:
        pass

    # Inline fallback scoring
    factors: dict[str, int] = {
        "volume": _inline_score_volume(stock_data),
        "whale": _inline_score_whale(stock_data),
        "momentum": _inline_score_momentum(stock_data),
        "rsi": _inline_score_rsi(stock_data),
        "catalyst": _inline_score_catalyst(stock_data),
    }

    total = sum(factors.values())
    total = max(0, min(100, total))

    signal = (
        "MANGALA!"
        if total >= 80
        else ("WATCH" if total >= 60 else ("MEH" if total >= 40 else "PASS"))
    )

    price = stock_data.get("price", 0) or 0
    flip_plan = {
        "entry": round(price, 2),
        "target_5pct": round(price * 1.05, 2),
        "stop_3pct": round(price * 0.97, 2),
        "max_hold_days": 5,
    }

    return {
        "score": total,
        "signal": signal,
        "factors": factors,
        "flip_plan": flip_plan,
    }


def _inline_score_volume(data: dict[str, Any]) -> int:
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


def _inline_score_whale(data: dict[str, Any]) -> int:
    whale_info = data.get("whale_print") or {}
    if whale_info:
        label = str(whale_info.get("label", "")).upper()
        confidence = float(whale_info.get("confidence", 0) or 0)
        if label == "FORTE" and confidence > 0.7:
            return 25
        if label in ("PROVAVEL", "PROVÁVEL"):
            return 20
        if label == "MODERADO":
            return 12
        if label == "FRACO":
            return 5
    # Heuristic fallback
    volume = data.get("volume", 0) or 0
    price = data.get("price", 0) or 0
    avg_vol = data.get("avg_volume_20d", 0) or 0
    if volume > 0 and avg_vol > 0 and price > 0:
        ratio = volume / avg_vol
        if ratio > 4.0 and price < 5:
            return 15
        if ratio > 2.5:
            return 8
    return 0


def _inline_score_momentum(data: dict[str, Any]) -> int:
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


def _inline_score_rsi(data: dict[str, Any]) -> int:
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


def _inline_score_catalyst(data: dict[str, Any]) -> int:
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

    return min(score, 10)


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def run_daily_scan() -> list[dict[str, Any]]:
    """Execute Mangala scan and return top 5 opportunities.

    Returns:
        List of top 5 opportunities, each containing:
            ticker, price, volume, name, score, signal, factors,
            whale_status, whale_score, pump_risk, pump_score,
            flip_plan, scanned_at
    """
    data_hub = _get_data_hub()
    social_whale = _get_social_whale(data_hub)

    candidates = _get_candidates(data_hub)
    if not candidates:
        logger.info("MangalaScan: no candidates found")
        return []

    logger.info("MangalaScan: scanning %d candidates", len(candidates))

    opportunities: list[MangalaOpportunity] = []
    for candidate in candidates:
        try:
            ticker = candidate.get("ticker", "")
            if not ticker:
                continue
            price = candidate.get("price", 0) or 0
            if price < MIN_PRICE:
                continue

            # Collect fundamental + technical data via DataHub
            stock_data = _collect_stock_data(data_hub, ticker, candidate)

            # Collect Pennylab data (whale + pump) via SocialWhaleProvider
            pennylab = _get_pennylab_data(social_whale, ticker)
            stock_data["whale_print"] = {
                "label": _map_whale_status(pennylab["whale_score"]),
                "confidence": min(1.0, pennylab["whale_score"] / 100.0),
                "score": pennylab["whale_score"],
            }

            # Calculate Mangala Score (reusing mangala.py's engine)
            scored = _calculate_mangala_score(stock_data)

            whale_status = _map_whale_status(pennylab["whale_score"])
            pump_risk = _map_pump_risk(pennylab["pump_score"])

            opp = MangalaOpportunity(
                ticker=ticker,
                price=round(price, 2),
                volume=int(candidate.get("volume", 0) or 0),
                name=str(candidate.get("name", ticker)),
                score=scored["score"],
                signal=scored["signal"],
                factors=scored["factors"],
                whale_status=whale_status,
                whale_score=pennylab["whale_score"],
                pump_risk=pump_risk,
                pump_score=pennylab["pump_score"],
                flip_plan=scored["flip_plan"],
            )
            opportunities.append(opp)

            logger.info(
                "MANGALA! %s score=%d whale=%s pump=%s",
                ticker,
                scored["score"],
                whale_status,
                pump_risk,
            )

        except Exception as exc:
            logger.debug("MangalaScan: failed for %s: %s", candidate.get("ticker"), exc)
            continue

    # Sort by score descending, take top N
    opportunities.sort(key=lambda o: o.score, reverse=True)
    top = opportunities[:TOP_N]

    # Save to disk
    _save_scan_results(top)

    logger.info(
        "MangalaScan: complete — %d scored, top %d, high-conviction=%d",
        len(opportunities),
        len(top),
        sum(1 for o in top if o.signal == "MANGALA!"),
    )

    return [o.to_dict() for o in top]


def _save_scan_results(opportunities: list[MangalaOpportunity]) -> None:
    """Save scan results to data/mangala_daily.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "scanned_at": datetime.now(UTC).isoformat(),
        "count": len(opportunities),
        "opportunities": [o.to_dict() for o in opportunities],
    }

    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info("MangalaScan: saved %d opportunities to %s", len(opportunities), DATA_FILE)
    except Exception as exc:
        logger.warning("MangalaScan: failed to save results: %s", exc)


def load_latest_scan() -> dict[str, Any]:
    """Load the latest scan results from disk.

    Returns:
        Dict with scanned_at, count, and opportunities list.
        Returns empty dict if no scan data exists.
    """
    if not DATA_FILE.exists():
        return {}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as exc:
        logger.warning("MangalaScan: failed to load scan data: %s", exc)
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# Background loop (for server integration)
# ═══════════════════════════════════════════════════════════════════════════════

_scan_task: asyncio.Task | None = None
_running = False


async def background_scan_loop() -> None:
    """Background loop that runs scans at market-aware intervals."""
    global _running
    _running = True

    logger.info("MangalaScan: background loop started — first scan deferred to first interval")

    while _running:
        interval = get_scan_interval()
        logger.debug("MangalaScan: next scan in %d seconds", interval)

        await asyncio.sleep(interval)

        if not _running:
            break

        try:
            await asyncio.to_thread(run_daily_scan)
        except Exception as exc:
            logger.warning("MangalaScan: scan cycle failed: %s", exc)


def start_background_scan() -> None:
    """Start the background scan loop.

    Called from the server lifespan startup.
    """
    global _scan_task
    if _scan_task is not None and not _scan_task.done():
        logger.info("MangalaScan: background loop already running")
        return

    _scan_task = asyncio.create_task(background_scan_loop())
    logger.info("MangalaScan: background loop started as task")


def stop_background_scan() -> None:
    """Stop the background scan loop.

    Called from the server lifespan shutdown.
    """
    global _running, _scan_task
    _running = False

    if _scan_task is not None and not _scan_task.done():
        _scan_task.cancel()
        _scan_task = None
        logger.info("MangalaScan: background loop stopped")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    """CLI entry point — runs a single scan and prints results."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("Mangala Daily Scan — running...")
    results = run_daily_scan()

    if not results:
        print("No opportunities found.")
        return

    print(f"\nTop {len(results)} Mangala Opportunities:")
    print("-" * 80)
    for opp in results:
        print(
            f"  {opp['ticker']:6s} | "
            f"${opp['price']:>6.2f} | "
            f"Score {opp['score']:>3d} | "
            f"{opp['signal']:8s} | "
            f"Whale {opp['whale_status']:8s} | "
            f"Pump {opp['pump_risk']:5s}"
        )
    print("-" * 80)

    high = [o for o in results if o.get("signal") == "MANGALA!"]
    if high:
        print(f"\nHigh-conviction flips ({len(high)}):")
        for opp in high:
            fp = opp.get("flip_plan", {})
            print(
                f"  {opp['ticker']}: entry=${fp.get('entry', 0):.2f} "
                f"target=${fp.get('target_5pct', 0):.2f} "
                f"stop=${fp.get('stop_3pct', 0):.2f}"
            )


if __name__ == "__main__":
    main()
