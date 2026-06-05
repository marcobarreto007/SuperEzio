"""Read-only broker connectivity probe for demo/readiness checks.

This script never submits, cancels, or modifies broker orders. It only checks
optional paper/read-only connectivity for Interactive Brokers and Alpaca.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import sys
from typing import Any


IBKR_PAPER_PORTS = (7497, 4002)
IBKR_LIVE_PORTS = (7496, 4001)


def _package_present(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _env_state(names: list[str]) -> dict[str, dict[str, bool]]:
    return {name: {"present": bool(os.getenv(name))} for name in names}


def _tcp_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _safe_error(exc: BaseException) -> str:
    message = str(exc).strip()
    return message[:500] if message else exc.__class__.__name__


def probe_ibkr(
    host: str = "127.0.0.1",
    port: int = 7497,
    client_id: int = 91,
    timeout: float = 2.0,
) -> dict[str, Any]:
    """Probe IBKR TWS/Gateway in read-only mode when reachable."""

    port_open = _tcp_open(host, port, timeout)
    result: dict[str, Any] = {
        "provider": "ibkr",
        "mode": "read_only",
        "host": host,
        "port": port,
        "paper_port": port in IBKR_PAPER_PORTS,
        "live_port_warning": port in IBKR_LIVE_PORTS,
        "package_present": _package_present("ib_insync"),
        "port_open": port_open,
        "connected": False,
        "account_equity": None,
        "positions_count": None,
        "error": None,
    }

    if not result["package_present"]:
        result["error"] = "package_missing: install ib-insync"
        return result
    if not port_open:
        result["error"] = "port_closed: start TWS/IB Gateway paper API and enable socket clients"
        return result

    ib = None
    try:
        from ib_insync import IB  # type: ignore[import]

        ib = IB()
        try:
            ib.connect(host, port, clientId=client_id, timeout=timeout, readonly=True)
        except TypeError:
            # Older ib_insync builds may not expose the readonly argument.
            ib.connect(host, port, clientId=client_id, timeout=timeout)

        result["connected"] = bool(ib.isConnected())
        if result["connected"]:
            summary = ib.accountSummary()
            for item in summary:
                if item.tag == "NetLiquidation":
                    result["account_equity"] = item.value
                    break
            result["positions_count"] = len(ib.positions())
    except Exception as exc:  # pragma: no cover - depends on local broker state.
        result["error"] = _safe_error(exc)
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass

    return result


def probe_alpaca_paper(timeout: float = 10.0) -> dict[str, Any]:
    """Probe Alpaca paper account with read-only account/positions calls."""

    env = _env_state(["ALPACA_API_KEY", "ALPACA_SECRET_KEY"])
    credentials_present = all(item["present"] for item in env.values())
    result: dict[str, Any] = {
        "provider": "alpaca",
        "mode": "paper_read_only",
        "package_present": _package_present("alpaca.trading"),
        "credentials": env,
        "credentials_present": credentials_present,
        "connected": False,
        "account_status": None,
        "account_equity": None,
        "positions_count": None,
        "error": None,
    }

    if not result["package_present"]:
        result["error"] = "package_missing: install alpaca-py"
        return result
    if not credentials_present:
        result["error"] = "credentials_missing: set ALPACA_API_KEY and ALPACA_SECRET_KEY"
        return result

    try:
        from alpaca.trading.client import TradingClient

        client = TradingClient(
            api_key=os.environ["ALPACA_API_KEY"],
            secret_key=os.environ["ALPACA_SECRET_KEY"],
            paper=True,
            raw_data=False,
        )
        account = client.get_account()
        positions = client.get_all_positions()
        result["connected"] = True
        result["account_status"] = str(getattr(account, "status", "unknown"))
        result["account_equity"] = str(getattr(account, "equity", ""))
        result["positions_count"] = len(positions)
    except Exception as exc:  # pragma: no cover - depends on external credentials.
        result["error"] = _safe_error(exc)

    return result


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    providers = []
    if args.provider in ("all", "ibkr"):
        providers.append(
            probe_ibkr(
                host=args.ibkr_host,
                port=args.ibkr_port,
                client_id=args.ibkr_client_id,
                timeout=args.timeout,
            )
        )
    if args.provider in ("all", "alpaca"):
        providers.append(probe_alpaca_paper(timeout=args.timeout))

    return {
        "safe_mode": "read_only_no_orders",
        "providers": providers,
        "connected_count": sum(1 for item in providers if item.get("connected")),
    }


def _print_human(payload: dict[str, Any]) -> None:
    print(f"safe_mode: {payload['safe_mode']}")
    for item in payload["providers"]:
        status = "connected" if item.get("connected") else "not_connected"
        print(f"{item['provider']}: {status}")
        if item.get("error"):
            print(f"  error: {item['error']}")
        if item["provider"] == "ibkr":
            print(f"  endpoint: {item['host']}:{item['port']} port_open={item['port_open']}")
            if item.get("live_port_warning"):
                print("  warning: live IBKR port selected; prefer paper port for proof")
        if item["provider"] == "alpaca":
            print(f"  credentials_present: {item['credentials_present']}")
        if item.get("positions_count") is not None:
            print(f"  positions_count: {item['positions_count']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only broker connectivity probe.")
    parser.add_argument("--provider", choices=["all", "ibkr", "alpaca"], default="all")
    parser.add_argument("--ibkr-host", default=os.getenv("IBKR_HOST", "127.0.0.1"))
    parser.add_argument("--ibkr-port", type=int, default=int(os.getenv("IBKR_PORT", "7497")))
    parser.add_argument(
        "--ibkr-client-id",
        type=int,
        default=int(os.getenv("IBKR_CLIENT_ID", "91")),
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--require-connection",
        action="store_true",
        help="Exit 2 when no provider connects.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = run_probe(args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_human(payload)

    if args.require_connection and payload["connected_count"] == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
