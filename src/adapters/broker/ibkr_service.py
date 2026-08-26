"""IBKR Boundary Service — isolates ib_insync from FastAPI's async loop.

Runs in its own daemon thread with a dedicated IB() instance, cache, and cooldown.
Follows patterns from LiveMonitor (daemon thread), finnhub_provider (TTL cache),
and gateway (cooldown dict).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration (env-driven with defaults) ────────────────────────────────────
_IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
_IBKR_PORT = int(os.getenv("IBKR_PORT", "7497"))
_IBKR_SERVICE_CLIENT_ID = int(os.getenv("IBKR_SERVICE_CLIENT_ID", "100"))
_IBKR_CACHE_TTL_SEC = int(os.getenv("IBKR_CACHE_TTL_SEC", "10"))
_IBKR_COOLDOWN_SEC = int(os.getenv("IBKR_COOLDOWN_SEC", "60"))
_IBKR_COOLDOWN_MAX_ERRORS = int(os.getenv("IBKR_COOLDOWN_MAX_ERRORS", "3"))
_IBKR_REFRESH_INTERVAL_SEC = int(os.getenv("IBKR_REFRESH_INTERVAL_SEC", "15"))

# ── Singleton factory (following fraud_memory.py pattern) ────────────────────────────
_ibkr_service_instance: IBKRService | None = None
_ibkr_service_lock = threading.Lock()


def get_ibkr_service() -> IBKRService:
    """Get the singleton IBKRService instance, creating it if needed."""
    global _ibkr_service_instance
    if _ibkr_service_instance is None:
        with _ibkr_service_lock:
            if _ibkr_service_instance is None:
                _ibkr_service_instance = IBKRService()
                _ibkr_service_instance.start()
                logger.info(
                    "[IBKRService] Started singleton service (clientId=%s, host=%s, port=%s)",
                    _IBKR_SERVICE_CLIENT_ID,
                    _IBKR_HOST,
                    _IBKR_PORT,
                )
    return _ibkr_service_instance


class IBKRService:
    """Isolated IBKR boundary service with cache and cooldown.

    Runs in a daemon thread with a dedicated IB() instance.
    Provides cached positions/equity and live orders.
    Implements cooldown when TWS is unavailable.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ):
        self._host = host or _IBKR_HOST
        self._port = port or _IBKR_PORT
        self._client_id = client_id or _IBKR_SERVICE_CLIENT_ID

        # Thread safety
        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        # IBKR connection (owned by this service only)
        self._ib: Any = None
        self._connected = False

        # Cache (positions + equity)
        self._positions_cache: list[dict] = []
        self._equity_cache: float = 0.0
        self._cache_time: float = 0.0  # time.monotonic()

        # Open orders (no cache, always live)
        self._open_orders_cache: list[dict] = []
        self._open_orders_cache_time: float = 0.0

        # Cooldown state
        self._consecutive_failures: int = 0
        self._cooldown_until: float = 0.0  # time.monotonic()
        self._last_error: str = ""

        # Daemon thread for background refresh
        self._thread: threading.Thread | None = None
        self._cache_ready_event = threading.Event()

        # Status tracking
        self._started_at: float = time.monotonic()
        self._last_refresh_attempt: float = 0.0
        self._last_refresh_success: float = 0.0

    def start(self) -> None:
        """Start the daemon thread and connect to IBKR."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("[IBKRService] Already started")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            name="superezio-ibkr-service",
            target=self._refresh_loop,
            daemon=True,
        )
        self._thread.start()
        logger.info("[IBKRService] Daemon thread started")

    def stop(self) -> None:
        """Stop the daemon thread and disconnect."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._disconnect()
        logger.info("[IBKRService] Stopped")

    def _connect(self) -> bool:
        """Connect to IBKR with retry logic. Returns True if successful."""
        if self._connected and self._ib is not None:
            return True

        try:
            self._ensure_thread_event_loop()
            from ib_insync import IB

            self._ib = IB()
            self._ib.connect(self._host, self._port, clientId=self._client_id, timeout=5.0)
            self._connected = True
            self._consecutive_failures = 0
            logger.info(
                "[IBKRService] Connected to %s:%s (client %s)",
                self._host,
                self._port,
                self._client_id,
            )
            return True
        except ImportError:
            self._last_error = "ib_insync not installed"
            logger.warning("[IBKRService] %s", self._last_error)
            return False
        except Exception as exc:
            self._last_error = str(exc)[:200]
            self._consecutive_failures += 1
            logger.warning("[IBKRService] Connection failed: %s", self._last_error)
            self._connected = False
            return False

    @staticmethod
    def _ensure_thread_event_loop() -> None:
        """Ensure ib_insync has an asyncio loop in daemon worker threads."""

        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

    def _disconnect(self) -> None:
        """Disconnect from IBKR."""
        try:
            if self._ib is not None and self._connected:
                self._ib.disconnect()
                logger.info("[IBKRService] Disconnected")
        except Exception:
            pass
        finally:
            self._connected = False
            self._ib = None

    def _refresh_loop(self) -> None:
        """Background refresh loop (runs in daemon thread)."""
        while not self._stop_event.is_set():
            try:
                self._refresh()
            except Exception as exc:
                logger.warning("[IBKRService] Refresh error: %s", exc)
                self._consecutive_failures += 1
                self._last_error = str(exc)[:200]

            # Wait for next refresh or stop event
            self._stop_event.wait(_IBKR_REFRESH_INTERVAL_SEC)

    def _refresh(self) -> None:
        """Refresh cache from IBKR."""
        self._last_refresh_attempt = time.monotonic()

        # Auto-recovery: after 100+ failures, reset counter and try fresh
        if self._consecutive_failures >= 100:
            logger.warning(
                "[IBKRService] Auto-recovery: %d consecutive failures, resetting counter",
                self._consecutive_failures,
            )
            self._consecutive_failures = 0
            self._cooldown_until = 0  # Clear cooldown
            self._disconnect()  # Force reconnect

        # Check cooldown
        if time.monotonic() < self._cooldown_until:
            logger.debug(
                "[IBKRService] In cooldown (until %.0f, failures=%d)",
                self._cooldown_until,
                self._consecutive_failures,
            )
            return

        # Try to connect if not connected
        if not self._connect():
            # Check if we should enter cooldown
            if self._consecutive_failures >= _IBKR_COOLDOWN_MAX_ERRORS:
                self._cooldown_until = time.monotonic() + _IBKR_COOLDOWN_SEC
                logger.warning(
                    "[IBKRService] Entering cooldown for %ds (%d consecutive failures) - TWS/Gateway may be down",
                    _IBKR_COOLDOWN_SEC,
                    self._consecutive_failures,
                )
            return

        # Fetch positions
        try:
            from ib_insync import Stock

            pos_list = self._ib.positions()
            positions = []

            if pos_list:
                contracts = [Stock(p.contract.symbol, "SMART", "USD") for p in pos_list]
                self._ib.qualifyContracts(*contracts)

                # Use delayed data (3) — free, no subscription required
                self._ib.reqMarketDataType(3)
                tickers = [self._ib.reqMktData(c) for c in contracts]
                self._ib.sleep(1.0)

                for c in contracts:
                    self._ib.cancelMktData(c)

                for p, ticker in zip(pos_list, tickers):
                    price = ticker.last or ticker.close or ticker.marketPrice() or float(p.avgCost)
                    positions.append(
                        {
                            "symbol": p.contract.symbol,
                            "ticker": p.contract.symbol,
                            "quantity": int(p.position),
                            "shares": int(p.position),
                            "avg_cost": round(float(p.avgCost), 2) if p.avgCost else 0.0,
                            "current_price": round(float(price), 2),
                            "market_value": round(float(p.position) * price, 2),
                        }
                    )

            with self._lock:
                self._positions_cache = positions
                self._cache_time = time.monotonic()
                self._cache_ready_event.set()

            logger.debug("[IBKRService] Refreshed positions: %d items", len(positions))

        except Exception as exc:
            logger.warning("[IBKRService] Positions refresh failed: %s", exc)
            self._consecutive_failures += 1
            return  # Don't fetch equity if positions failed

        # Fetch account equity
        try:
            equity = 0.0
            for v in self._ib.accountSummary():
                if v.tag == "NetLiquidation":
                    equity = float(v.value)
                    break

            with self._lock:
                self._equity_cache = equity
                self._cache_ready_event.set()

            logger.debug("[IBKRService] Refreshed equity: $%s", equity)

        except Exception as exc:
            logger.warning("[IBKRService] Equity refresh failed: %s", exc)

        # Reset failure counter on success
        self._consecutive_failures = 0
        self._last_refresh_success = time.monotonic()

    def get_positions(self, force_refresh: bool = False, wait_timeout: float = 2.0) -> list[dict]:
        """Get cached positions, optionally forcing a refresh.

        Args:
            force_refresh: If True, bypass cache and trigger a refresh (with timeout)
            wait_timeout: Max seconds to wait for a forced refresh

        Returns:
            List of position dicts (empty list if service is down)
        """
        if not force_refresh:
            with self._lock:
                if (
                    time.monotonic() - self._cache_time < _IBKR_CACHE_TTL_SEC
                    or self._positions_cache
                ):
                    return list(self._positions_cache)

        # Force refresh
        if self._stop_event.is_set():
            return []

        if not force_refresh and threading.current_thread() is not self._thread:
            self._cache_ready_event.wait(timeout=max(0.0, wait_timeout))
            with self._lock:
                return list(self._positions_cache)

        # Trigger refresh and wait
        self._refresh()
        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            with self._lock:
                if time.monotonic() - self._cache_time < _IBKR_CACHE_TTL_SEC:
                    return list(self._positions_cache)
            time.sleep(0.1)

        # Timeout — return whatever we have
        with self._lock:
            return list(self._positions_cache)

    def get_account_equity(self, force_refresh: bool = False, wait_timeout: float = 2.0) -> float:
        """Get cached account equity.

        Args:
            force_refresh: If True, bypass cache and trigger a refresh
            wait_timeout: Max seconds to wait for a forced refresh

        Returns:
            Account equity (0.0 if service is down)
        """
        if not force_refresh:
            with self._lock:
                if (
                    time.monotonic() - self._cache_time < _IBKR_CACHE_TTL_SEC
                    or self._equity_cache > 0
                ):
                    return self._equity_cache

        # Force refresh
        if self._stop_event.is_set():
            return 0.0

        if not force_refresh and threading.current_thread() is not self._thread:
            self._cache_ready_event.wait(timeout=max(0.0, wait_timeout))
            with self._lock:
                return self._equity_cache

        self._refresh()
        deadline = time.monotonic() + wait_timeout
        while time.monotonic() < deadline:
            with self._lock:
                if time.monotonic() - self._cache_time < _IBKR_CACHE_TTL_SEC:
                    return self._equity_cache
            time.sleep(0.1)

        with self._lock:
            return self._equity_cache

    def get_open_orders(self, timeout: float = 3.0) -> list[dict]:
        """Get open orders (live call, no cache).

        Args:
            timeout: Max seconds to wait for the request

        Returns:
            List of order dicts (empty list if service is down)
        """
        if not self._connect():
            return []

        try:
            orders: list[dict] = []
            seen: set[str] = set()

            def add_trade(trade: Any) -> None:
                order = getattr(trade, "order", None)
                contract = getattr(trade, "contract", None)
                order_status = getattr(trade, "orderStatus", None)

                if order is None:
                    return

                raw_order_id = str(getattr(order, "orderId", "") or "")
                perm_id = str(getattr(order, "permId", "") or "")
                client_id = str(getattr(order, "clientId", "") or "")
                symbol = str(
                    getattr(contract, "symbol", "") or getattr(contract, "localSymbol", "") or ""
                ).upper()
                status = str(getattr(order_status, "status", "") or "submitted")
                order_id = perm_id if perm_id not in {"", "0"} else raw_order_id
                dedupe_key = (
                    perm_id if perm_id not in {"", "0"} else f"{client_id}:{raw_order_id}:{symbol}"
                )

                if not order_id or not symbol or dedupe_key in seen:
                    return

                seen.add(dedupe_key)
                orders.append(
                    {
                        "order_id": order_id,
                        "tws_order_id": raw_order_id,
                        "perm_id": perm_id or None,
                        "client_id": client_id or None,
                        "ticker": symbol,
                        "action": str(getattr(order, "action", "")).upper(),
                        "qty": float(getattr(order, "totalQuantity", 0)),
                        "order_type": str(getattr(order, "orderType", "")).upper(),
                        "limit_price": float(getattr(order, "lmtPrice", 0)) or None,
                        "stop_price": float(getattr(order, "auxPrice", 0)) or None,
                        "status": status,
                    }
                )

            # reqAllOpenOrders is the authoritative paper/demo path for orders
            # visible in TWS, including orders not created by this clientId.
            for method_name in ("reqAllOpenOrders", "reqOpenOrders"):
                try:
                    method = getattr(self._ib, method_name)
                    for trade in method() or []:
                        add_trade(trade)
                    self._ib.sleep(min(max(timeout, 0.1), 3.0))
                except Exception as exc:
                    logger.debug("[IBKRService] order method %s failed: %s", method_name, exc)
                    continue

            # Then collect any trades that arrived asynchronously while ib_insync
            # processed the socket loop above.
            for accessor in ("openTrades", "trades"):
                try:
                    for trade in getattr(self._ib, accessor)() or []:
                        add_trade(trade)
                except Exception as exc:
                    logger.debug("[IBKRService] accessor %s failed: %s", accessor, exc)
                    continue

            with self._lock:
                if not orders and self._open_orders_cache:
                    cache_age = time.monotonic() - self._open_orders_cache_time
                    if cache_age < 10.0:
                        return list(self._open_orders_cache)
                self._open_orders_cache = list(orders)
                self._open_orders_cache_time = time.monotonic()

            return orders

        except Exception as exc:
            logger.warning("[IBKRService] Open orders failed: %s", exc)
            return []

    def get_status(self) -> dict[str, Any]:
        """Get structured health/status for /health/details.

        Returns:
            Dict with: connected, can_read, can_trade, cache_age_s,
                     cooldown_active, last_error, uptime_s, last_refresh_age_s
        """
        with self._lock:
            cache_age = time.monotonic() - self._cache_time
            cooldown_active = time.monotonic() < self._cooldown_until
            uptime = time.monotonic() - self._started_at
            last_refresh_age = time.monotonic() - self._last_refresh_success

            return {
                "connected": self._connected,
                "can_read": self._connected and not cooldown_active,
                "can_trade": self._connected and not cooldown_active,  # Paper trading
                "cache_age_s": round(cache_age, 1),
                "cooldown_active": cooldown_active,
                "cooldown_remaining_s": (
                    round(self._cooldown_until - time.monotonic(), 1) if cooldown_active else 0
                ),
                "last_error": self._last_error if self._last_error else None,
                "consecutive_failures": self._consecutive_failures,
                "uptime_s": round(uptime, 1),
                "last_refresh_age_s": round(last_refresh_age, 1),
                "positions_count": len(self._positions_cache),
                "equity": f"${self._equity_cache:,.2f}" if self._equity_cache else "$0.00",
                "client_id": self._client_id,
                "host": self._host,
                "port": self._port,
                "auto_recovery": self._consecutive_failures >= 100,  # Flag for UI
            }

    def force_recovery_attempt(self) -> dict[str, Any]:
        """Force an immediate recovery attempt - call when IBKR is suspected to be back online.

        Returns:
            Dict with: success, error, consecutive_failures (before reset)
        """
        logger.info("[IBKRService] Force recovery attempt triggered")

        # Reset cooldown to allow immediate retry
        self._cooldown_until = 0

        # Force disconnect to ensure clean reconnect
        self._disconnect()
        time.sleep(1.0)

        # Attempt connection
        success = self._connect()

        if success:
            failures_before = self._consecutive_failures
            self._consecutive_failures = 0  # Reset on successful recovery
            logger.info(
                "[IBKRService] Recovery successful - reset %d consecutive failures",
                failures_before,
            )
            return {
                "success": True,
                "error": None,
                "failures_reset": failures_before,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        else:
            return {
                "success": False,
                "error": self._last_error,
                "failures_reset": 0,
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def is_degraded(self) -> bool:
        """Quick check if service is in degraded state (cooldown or disconnected)."""
        with self._lock:
            return not self._connected or (time.monotonic() < self._cooldown_until)
