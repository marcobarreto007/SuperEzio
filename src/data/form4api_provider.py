"""
Form4API — SEC insider trading data provider.

Uses the Form4API REST API (https://api.form4api.com) to fetch insider
transactions, cluster buy/sell signals, and 10b5-1 plan detection.

Authentication: X-Api-Key header (register at https://form4api.com/dashboard)
Free tier: 500 requests/day, no credit card required.

Endpoints (free tier):
  GET /v1/transactions   — search insider transactions
  GET /v1/filings/recent — most recent Form 4 filings

Cluster signals (GET /v1/signals) require a Business plan.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    import requests as _requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# Map of SEC transaction codes to human-readable labels
_TX_CODE_MAP: dict[str, str] = {
    "P": "purchase",
    "S": "sale",
    "A": "grant",
    "D": "sale_to_issuer",
    "F": "tax_withholding",
    "I": "discretionary_transaction",
    "M": "exercise_conversion",
    "X": "exercise_otc",
    "G": "gift",
    "W": "bequest",
    "Z": "trust_distribution",
    "U": "transfer",
    "C": "conversion_derivative",
    "E": "expiration_short",
    "H": "expiration_long",
    "L": "small_acquisition",
    "K": "equity_swap",
    "J": "other",
}


class Form4APIProvider:
    """SEC insider trading data from Form4API."""

    BASE_URL = "https://api.form4api.com"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("FORM4API_KEY") or ""
        self._session: _requests.Session | None = None

    @property
    def session(self) -> _requests.Session:
        if self._session is None:
            s = _requests.Session()
            s.headers.update(
                {
                    "X-Api-Key": self.api_key,
                    "User-Agent": "SuperEzio/1.0 market-research",
                    "Accept": "application/json",
                }
            )
            self._session = s
        return self._session

    @property
    def healthy(self) -> bool:
        """Check whether the provider has a usable API key."""
        return bool(self.api_key) and _HAS_REQUESTS

    # ── public API ──────────────────────────────────────────────────────

    def get_insider_trades(
        self,
        ticker: str,
        limit: int = 20,
        significant_only: bool = True,
    ) -> dict[str, Any]:
        """Return recent insider trades for *ticker*.

        Parameters
        ----------
        ticker : str
            Ticker symbol (e.g. "AAPL").
        limit : int
            Max number of transactions to return (max 100).
        significant_only : bool
            When True, returns only discretionary open-market trades
            (excludes 10b5-1 plan trades).

        Result shape::

            {"ticker": "GME", "insider_buys": [...], "insider_sells": [...],
             "cluster_buy": False, "transaction_count": 12,
             "source": "form4api"}

        On failure the ``error`` key contains a machine-readable message.
        """
        if not self.healthy:
            return {
                "ticker": ticker.upper(),
                "error": "form4api_unavailable — FORME4API_KEY not set",
            }

        try:
            params: dict[str, Any] = {
                "ticker": ticker.upper(),
                "per_page": min(limit, 100),
            }
            if significant_only:
                params["significant"] = "true"

            resp = self.session.get(
                f"{self.BASE_URL}/v1/transactions",
                params=params,
                timeout=15,
            )

            if resp.status_code == 401:
                return {
                    "ticker": ticker.upper(),
                    "error": "form4api_unauthorized — invalid or missing API key",
                }
            if resp.status_code == 402:
                return {
                    "ticker": ticker.upper(),
                    "error": "form4api_plan_required — endpoint requires paid plan",
                }
            if resp.status_code == 429:
                return {
                    "ticker": ticker.upper(),
                    "error": "form4api_rate_limited — free tier allows 500 req/day",
                }
            resp.raise_for_status()
            data: dict = resp.json()

            return self._normalize_trades(ticker.upper(), data)

        except _requests.ConnectionError:
            return {
                "ticker": ticker.upper(),
                "error": "form4api_unreachable — check network / DNS",
            }
        except Exception as exc:  # noqa: BLE001 — catch amplo deliberado: provedor externo falha de formas variadas (rede, timeout, JSON); retorna erro estruturado
            logger.warning("[Form4API] get_insider_trades(%s) failed: %s", ticker, exc)
            return {
                "ticker": ticker.upper(),
                "error": f"form4api_error: {exc}",
            }

    def get_cluster_signals(self) -> dict[str, Any]:
        """Return cluster buy/sell signals across the market.

        .. note::
            This endpoint requires a **Business** plan.  Free and Pro keys
            will receive a ``form4api_plan_required`` error.

        Result shape::

            {"cluster_buys": [...], "cluster_sells": [...],
             "total_signals": N, "source": "form4api"}
        """
        if not self.healthy:
            return {
                "error": "form4api_unavailable — FORME4API_KEY not set",
                "cluster_buys": [],
                "cluster_sells": [],
                "total_signals": 0,
            }

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/v1/signals",
                timeout=15,
            )

            if resp.status_code == 402:
                return {
                    "error": "form4api_plan_required — signals require Business plan",
                    "cluster_buys": [],
                    "cluster_sells": [],
                    "total_signals": 0,
                }
            if resp.status_code == 401:
                return {
                    "error": "form4api_unauthorized",
                    "cluster_buys": [],
                    "cluster_sells": [],
                    "total_signals": 0,
                }
            resp.raise_for_status()
            data: dict = resp.json()

            rows = data if isinstance(data, list) else data.get("data", [])
            buys = [s for s in rows if (s.get("signal_type") or "").lower() == "buy"]
            sells = [s for s in rows if (s.get("signal_type") or "").lower() == "sell"]

            return {
                "cluster_buys": buys[:20],
                "cluster_sells": sells[:20],
                "total_signals": len(rows),
                "source": "form4api",
            }

        except _requests.ConnectionError:
            return {
                "error": "form4api_unreachable — check network / DNS",
                "cluster_buys": [],
                "cluster_sells": [],
                "total_signals": 0,
            }
        except Exception as exc:  # noqa: BLE001 — catch amplo deliberado: provedor externo falha de formas variadas (rede, timeout, JSON); retorna erro estruturado
            logger.warning("[Form4API] get_cluster_signals failed: %s", exc)
            return {
                "error": f"form4api_error: {exc}",
                "cluster_buys": [],
                "cluster_sells": [],
                "total_signals": 0,
            }

    def get_recent_filings(
        self, ticker: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Return most recent Form 4 filings, optionally filtered by *ticker*."""
        if not self.healthy:
            return []

        try:
            params: dict[str, Any] = {"per_page": min(limit, 50)}
            if ticker:
                params["ticker"] = ticker.upper()

            resp = self.session.get(
                f"{self.BASE_URL}/v1/filings/recent",
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data: dict = resp.json()
            rows = data if isinstance(data, list) else data.get("data", [])
            return [
                {
                    "ticker": r.get("ticker", ""),
                    "company": r.get("issuer_name", ""),
                    "insider": r.get("insider_name", ""),
                    "transaction_type": _TX_CODE_MAP.get(
                        r.get("transaction_code", ""), r.get("transaction_code", "")
                    ),
                    "shares": r.get("shares", 0),
                    "price": r.get("price", 0),
                    "filing_date": r.get("filing_date", ""),
                    "transaction_date": r.get("transaction_date", ""),
                    "is_10b5_1": bool(r.get("is_10b5_1", False)),
                }
                for r in rows
            ]
        except Exception as exc:  # noqa: BLE001 — catch amplo deliberado: provedor externo falha de formas variadas (rede, timeout, JSON); retorna erro estruturado
            logger.warning("[Form4API] get_recent_filings failed: %s", exc)
            return []

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_trades(ticker: str, data: dict[str, Any]) -> dict[str, Any]:
        """Normalise raw Form4API JSON into the canonical result shape.

        The API returns::

            {"data": [...], "meta": {"total": N, "per_page": 20, "page": 1}}
        """
        rows = data if isinstance(data, list) else data.get("data", [])

        if isinstance(rows, dict):
            rows = [rows]

        buys: list[dict[str, Any]] = []
        sells: list[dict[str, Any]] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            code = (row.get("transaction_code") or "").upper()
            is_buy = code == "P"
            is_sell = code == "S"
            if not is_buy and not is_sell:
                continue  # skip grants, taxes, gifts, etc.

            normalized = {
                "filing_date": row.get("filing_date", ""),
                "transaction_date": row.get("transaction_date", ""),
                "shares": int(row.get("shares", 0) or 0),
                "price": float(row.get("price", 0) or 0),
                "insider": row.get("insider_name", ""),
                "relationship": row.get("relationship", ""),
                "is_10b5_1": bool(row.get("is_10b5_1", False)),
            }

            if is_buy:
                buys.append(normalized)
            else:
                sells.append(normalized)

        total = len(buys) + len(sells)
        cluster_buy = len(buys) >= 3  # heuristic: 3+ buys in result = cluster

        return {
            "ticker": ticker,
            "insider_buys": buys,
            "insider_sells": sells,
            "cluster_buy": cluster_buy,
            "transaction_count": total,
            "source": "form4api",
        }
