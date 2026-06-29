"""Autonomous Learning Daemon — 24/7 market intelligence worker.

Runs continuously, collecting data, running experts, and learning.
No timeouts. No rush. Bob works while you sleep.

Architecture:
- Cycle 1 (every 5 min): Update prices for watchlist tickers
- Cycle 2 (every 15 min): Run market scans for opportunities
- Cycle 3 (every 60 min): Run full expert analysis on top movers
- Cycle 4 (every 6 hours): Rebuild OHLCV cache for all 391 tickers
- Cycle 5 (every 24 hours): Learning cycle — review closed trades, update pain memory

All results stored in SQLite (historical_cache.db, expert_analyses.db).
Pipeline can query these instantly — no wait time for users.

Usage:
    python -m core.trading.autonomous_learner
    # Runs forever. Ctrl+C to stop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Configuration — NO TIMEOUTS, NO RUSH
# ═══════════════════════════════════════════════════════════

PRICE_UPDATE_INTERVAL = int(os.getenv("LEARNER_PRICE_INTERVAL_SEC", "300"))  # 5 min
SCAN_INTERVAL = int(os.getenv("LEARNER_SCAN_INTERVAL_SEC", "900"))  # 15 min
EXPERT_INTERVAL = int(os.getenv("LEARNER_EXPERT_INTERVAL_SEC", "3600"))  # 60 min
OHLCV_REBUILD_INTERVAL = int(os.getenv("LEARNER_OHLCV_INTERVAL_SEC", "21600"))  # 6 hours
LEARNING_INTERVAL = int(os.getenv("LEARNER_LEARNING_INTERVAL_SEC", "86400"))  # 24 hours

_shutdown_flag = False


def _handle_signal(signum, frame):
    global _shutdown_flag
    logger.info("shutdown_signal_received", signal=signum)
    _shutdown_flag = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ═══════════════════════════════════════════════════════════
# Core Loop
# ═══════════════════════════════════════════════════════════


async def _cycle_update_prices(watchlist: list[str]):
    """Fetch current prices for all watchlist tickers."""
    logger.info("cycle_price_update_start", tickers=len(watchlist))
    from core.trading.historical_cache import fetch_and_cache_ticker

    updated = 0
    for ticker in watchlist:
        if _shutdown_flag:
            break
        try:
            candles = fetch_and_cache_ticker(ticker)
            if candles > 0:
                updated += 1
        except Exception as e:
            logger.debug("price_update_error", ticker=ticker, error=str(e)[:80])
        await asyncio.sleep(0.5)  # Be nice to APIs

    logger.info("cycle_price_update_done", updated=updated, total=len(watchlist))


async def _cycle_scan_market(watchlist: list[str]):
    """Run market scans on top movers from the watchlist."""
    logger.info("cycle_scan_start")

    # Find top volume movers from cached data
    from core.trading.historical_cache import _get_db

    conn = _get_db()

    try:
        # Top 20 by recent volume
        rows = conn.execute("""
            SELECT ticker, close, volume, date FROM ohlcv_cache
            WHERE date >= date('now', '-5 days')
            ORDER BY volume DESC LIMIT 50
        """).fetchall()

        if rows:
            # Run experts on top movers
            from core.trading.batch_expert_runner import run_experts_on_ticker

            seen = set()
            for row in rows:
                ticker = row[0]
                if ticker in seen or _shutdown_flag:
                    continue
                seen.add(ticker)
                try:
                    run_experts_on_ticker(ticker)
                except Exception as e:
                    logger.debug("scan_expert_error", ticker=ticker, error=str(e)[:80])

            logger.info("cycle_scan_done", tickers_analyzed=len(seen))
        else:
            logger.info("cycle_scan_no_data")
    finally:
        conn.close()


async def _cycle_full_experts(watchlist: list[str]):
    """Run full 6-expert analysis on all watchlist tickers."""
    logger.info("cycle_experts_start", tickers=len(watchlist))
    from core.trading.batch_expert_runner import run_experts_on_ticker

    completed = 0
    for ticker in watchlist:
        if _shutdown_flag:
            break
        try:
            analysis = run_experts_on_ticker(ticker)
            if analysis:
                completed += 1
        except Exception as e:
            logger.debug("expert_error", ticker=ticker, error=str(e)[:80])
        await asyncio.sleep(0.1)

    logger.info("cycle_experts_done", completed=completed, total=len(watchlist))


async def _cycle_rebuild_ohlcv(watchlist: list[str]):
    """Rebuild full 6-month OHLCV for all tickers."""
    logger.info("cycle_ohlcv_rebuild_start", tickers=len(watchlist))
    from core.trading.historical_cache import fetch_and_cache_ticker

    rebuilt = 0
    for ticker in watchlist:
        if _shutdown_flag:
            break
        try:
            candles = fetch_and_cache_ticker(ticker, force=True)
            if candles > 0:
                rebuilt += 1
        except Exception as e:
            logger.debug("ohlcv_error", ticker=ticker, error=str(e)[:80])
        await asyncio.sleep(1)  # Slower — full rebuild is heavy

    logger.info("cycle_ohlcv_rebuild_done", rebuilt=rebuilt, total=len(watchlist))


async def _cycle_learn():
    """Run learning cycle — review closed trades, update pain memory."""
    logger.info("cycle_learning_start")
    try:
        from core.trading.feedback_loop import get_feedback_loop

        fb = get_feedback_loop()

        # Review aged theses
        journal_path = Path("data/paper_journal.jsonl")
        if journal_path.exists():
            trades = []
            for line in journal_path.read_text().splitlines():
                if line.strip():
                    try:
                        import json

                        trades.append(json.loads(line))
                    except:
                        pass

            closed = [t for t in trades if t.get("outcome") in ("win", "loss")]
            logger.info("learning_review", closed_trades=len(closed))

        fb.run_learning_cycle()
        stats = fb.get_stats()
        logger.info("cycle_learning_done", stats=stats)
    except Exception as e:
        logger.error("learning_error", error=str(e)[:200])


# ═══════════════════════════════════════════════════════════
# Main Daemon
# ═══════════════════════════════════════════════════════════


async def run_forever():
    """Run the autonomous learner forever. Never stops. Never times out."""
    from core.trading.dynamic_watchlist import get_dynamic_watchlist

    watchlist = get_dynamic_watchlist(use_universe_400=True)
    logger.info("learner_boot", tickers=len(watchlist), mode="24/7")

    last_price = 0.0
    last_scan = 0.0
    last_expert = 0.0
    last_ohlcv = 0.0
    last_learn = 0.0

    cycle = 0

    while not _shutdown_flag:
        cycle += 1
        now = time.time()
        logger.info("learner_cycle", cycle=cycle, tickers=len(watchlist))

        try:
            # Price updates (every 5 min)
            if now - last_price >= PRICE_UPDATE_INTERVAL:
                await _cycle_update_prices(watchlist)
                last_price = now

            # Market scans (every 15 min)
            if now - last_scan >= SCAN_INTERVAL:
                await _cycle_scan_market(watchlist)
                last_scan = now

            # Full experts (every 60 min)
            if now - last_expert >= EXPERT_INTERVAL:
                await _cycle_full_experts(watchlist)
                last_expert = now

            # OHLCV rebuild (every 6 hours)
            if now - last_ohlcv >= OHLCV_REBUILD_INTERVAL:
                await _cycle_rebuild_ohlcv(watchlist)
                last_ohlcv = now

            # Learning cycle (every 24 hours)
            if now - last_learn >= LEARNING_INTERVAL:
                await _cycle_learn()
                last_learn = now

        except Exception as e:
            logger.error("learner_cycle_error", cycle=cycle, error=str(e)[:200])

        # Sleep between cycles — no rush
        next_check = min(
            last_price + PRICE_UPDATE_INTERVAL,
            last_scan + SCAN_INTERVAL,
            last_expert + EXPERT_INTERVAL,
            last_ohlcv + OHLCV_REBUILD_INTERVAL,
            last_learn + LEARNING_INTERVAL,
        )
        wait = max(30, next_check - time.time())
        logger.debug("learner_sleep", seconds=int(wait))
        await asyncio.sleep(min(wait, 300))  # Max 5 min sleep chunks (check shutdown)

    logger.info("learner_shutdown_complete", total_cycles=cycle)


def main():
    """Entry point: python -m core.trading.autonomous_learner"""
    print("=" * 60)
    print("  SuperEzio Autonomous Learner — 24/7 Market Intelligence")
    print("=" * 60)
    print(f"  Price updates:  every {PRICE_UPDATE_INTERVAL}s")
    print(f"  Market scans:   every {SCAN_INTERVAL}s")
    print(f"  Expert analysis: every {EXPERT_INTERVAL}s")
    print(f"  OHLCV rebuild:  every {OHLCV_REBUILD_INTERVAL}s")
    print(f"  Learning cycle: every {LEARNING_INTERVAL}s")
    print(f"  Ctrl+C to stop")
    print("=" * 60)
    print()

    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
