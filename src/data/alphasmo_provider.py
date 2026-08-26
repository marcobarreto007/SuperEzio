"""
AlphaSMO provider — free insider trading + smart-money convergence signals.

AlphaSMO is an npm-based CLI/MCP server for SEC EDGAR 13F institutional
holdings and Form 4 insider trading data. No API key is required for the
anonymous tier (rate-limited by IP).

References:
  - npm: https://www.npmjs.com/package/alphasmo
  - Web: https://alphasmo.com/en/developer

CLI commands used:
  - ``alphasmo insider summary <ticker> --json``
  - ``alphasmo insider trades <ticker> --json``
  - ``alphasmo convergence --json``
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

_ALPHASMO_AVAILABLE: bool | None = None


def _check_alphasmo() -> bool:
    """Return True if the ``alphasmo`` CLI is available via npx."""
    global _ALPHASMO_AVAILABLE
    if _ALPHASMO_AVAILABLE is not None:
        return _ALPHASMO_AVAILABLE
    try:
        result = subprocess.run(
            ["npx", "--yes", "alphasmo", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,  # returncode é lido abaixo para setar _ALPHASMO_AVAILABLE
        )
        _ALPHASMO_AVAILABLE = result.returncode == 0
    except Exception:  # noqa: BLE001 — deliberado: CLI externa indisponível degrada para False em vez de quebrar o import
        _ALPHASMO_AVAILABLE = False
    return _ALPHASMO_AVAILABLE


def _run_alphasmo(args: list[str], timeout: int = 30) -> dict[str, Any] | list[Any] | None:
    """Run ``npx alphasmo {args} --json`` and return the parsed output."""
    cmd = ["npx", "--yes", "alphasmo", *args, "--json"]
    try:
        # check=False: falha é diagnosticada via returncode/stderr abaixo
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        logger.warning("[AlphaSMO] command timed out: %s", args)
        return None
    except Exception as exc:  # noqa: BLE001 — deliberado: falha da CLI externa degrada para None com warning
        logger.warning("[AlphaSMO] command failed: %s", exc)
        return None

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.warning("[AlphaSMO] exit %d: %s", result.returncode, stderr)
        return None

    stdout = (result.stdout or "").strip()
    if not stdout:
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        logger.warning("[AlphaSMO] non-json output: %.200s", stdout)
        return None


class AlphaSMOProvider:
    """Insider-trading and smart-money convergence data via the AlphaSMO CLI.

    Methods return a dict with ``error`` on failure or standardised fields on
    success, following DataHub conventions.
    """

    def __init__(self) -> None:
        self._available = _check_alphasmo()

    # ------------------------------------------------------------------
    # Insider trades (recent Form 4 filings for a ticker)
    # ------------------------------------------------------------------

    def get_insider_trades(self, ticker: str) -> dict[str, Any]:
        """Fetch recent insider (Form 4) trades for a ticker.

        Returns:
            {
                "ticker": "AAPL",
                "insider_buys": N,
                "insider_sells": N,
                "trades": [...],
                "source": "alphasmo"
            }
        """
        if not self._available:
            return {"error": "alphasmo_not_available: npx alphasmo CLI not found"}

        raw = _run_alphasmo(["insider", "trades", ticker.upper()])
        if raw is None:
            return {"error": "alphasmo_no_data"}

        # Normalise: raw could be a list of trades or a dict with a trades key
        trades_list: list[dict[str, Any]] = []
        if isinstance(raw, list):
            trades_list = raw
        elif isinstance(raw, dict):
            trades_list = raw.get("trades") or raw.get("data") or []

        insider_buys = sum(
            1
            for t in trades_list
            if str(t.get("type") or t.get("transactionType") or "").lower() in ("buy", "purchase")
        )
        insider_sells = sum(
            1
            for t in trades_list
            if str(t.get("type") or t.get("transactionType") or "").lower() in ("sell", "sale")
        )

        return {
            "ticker": ticker.upper(),
            "insider_buys": insider_buys,
            "insider_sells": insider_sells,
            "total_trades": len(trades_list),
            "trades": trades_list,
            "source": "alphasmo",
            "provider": "alphasmo",
        }

    # ------------------------------------------------------------------
    # Insider summary (confidence scores over 30/90 days)
    # ------------------------------------------------------------------

    def get_insider_summary(self, ticker: str) -> dict[str, Any]:
        """Fetch insider confidence scores for a ticker.

        Returns:
            {
                "ticker": "AAPL",
                "confidence_30d": N,
                "confidence_90d": N,
                "cluster_buy": bool,
                "source": "alphasmo"
            }
        """
        if not self._available:
            return {"error": "alphasmo_not_available: npx alphasmo CLI not found"}

        raw = _run_alphasmo(["insider", "summary", ticker.upper()])
        if raw is None:
            return {"error": "alphasmo_no_data"}

        confidence_30d: int | None = None
        confidence_90d: int | None = None
        cluster_buy: bool = False

        if isinstance(raw, dict):
            confidence_30d = raw.get("confidence30d") or raw.get("confidence_30d")
            confidence_90d = raw.get("confidence90d") or raw.get("confidence_90d")
            cluster_buy = bool(raw.get("clusterBuy") or raw.get("cluster_buy"))

        return {
            "ticker": ticker.upper(),
            "confidence_30d": int(confidence_30d) if confidence_30d is not None else None,
            "confidence_90d": int(confidence_90d) if confidence_90d is not None else None,
            "cluster_buy": cluster_buy,
            "source": "alphasmo",
            "provider": "alphasmo",
        }

    # ------------------------------------------------------------------
    # Smart-money convergence (institutions + insiders buying together)
    # ------------------------------------------------------------------

    def get_smart_money_convergence(
        self,
        limit: int = 20,
        min_confidence: int = 60,
        days: int = 90,
    ) -> dict[str, Any]:
        """Fetch tickers where both institutions and insiders are buying.

        This is the flagship AlphaSMO signal.

        Args:
            limit: Max results (1-50).
            min_confidence: Minimum confidence score (0-100).
            days: Lookback window in days.

        Returns:
            {
                "convergence_score": 0-100 (average across all tickers),
                "tickers": [...],
                "source": "alphasmo"
            }
        """
        if not self._available:
            return {"error": "alphasmo_not_available: npx alphasmo CLI not found"}

        raw = _run_alphasmo(
            [
                "convergence",
                "--limit",
                str(max(1, min(limit, 50))),
                "--min-confidence",
                str(max(0, min(min_confidence, 100))),
                "--days",
                str(max(1, days)),
            ],
        )
        if raw is None:
            return {"error": "alphasmo_no_data"}

        # Normalise: raw could be a list of tickers or a dict with a tickers key
        tickers_list: list[dict[str, Any]] = []
        if isinstance(raw, list):
            tickers_list = raw
        elif isinstance(raw, dict):
            tickers_list = raw.get("tickers") or raw.get("data") or []

        # Compute average convergence score
        scores = [int(t.get("score") or t.get("convergenceScore") or 0) for t in tickers_list]
        avg_score = int(sum(scores) / len(scores)) if scores else 0

        return {
            "convergence_score": avg_score,
            "ticker_count": len(tickers_list),
            "tickers": tickers_list,
            "source": "alphasmo",
            "provider": "alphasmo",
        }

    # ------------------------------------------------------------------
    # Convenience: combined insider data for one ticker
    # ------------------------------------------------------------------

    def get_insider_data(self, ticker: str) -> dict[str, Any]:
        """Combine insider trades + summary into a single result dict.

        Returns:
            {
                "ticker": "AAPL",
                "insider_buys": N,
                "insider_sells": N,
                "cluster_buy": bool,
                "convergence_score": 0-100,
                "source": "alphasmo"
            }
        """
        trades = self.get_insider_trades(ticker)
        summary = self.get_insider_summary(ticker)

        return {
            "ticker": ticker.upper(),
            "insider_buys": trades.get("insider_buys", 0),
            "insider_sells": trades.get("insider_sells", 0),
            "cluster_buy": summary.get("cluster_buy", False),
            "confidence_30d": summary.get("confidence_30d"),
            "confidence_90d": summary.get("confidence_90d"),
            "convergence_score": summary.get("confidence_90d")
            or summary.get("confidence_30d")
            or 50,
            "source": "alphasmo",
            "provider": "alphasmo",
        }
