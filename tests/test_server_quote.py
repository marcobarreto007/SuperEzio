from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from core.resilience import CircuitState, get_circuit
from core.trading.server_quote import ServerQuoteError, ServerQuoteService


NOW = datetime(2026, 8, 19, 14, 30, tzinfo=timezone.utc)


class _Provider:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def get_price(self, _symbol, **_kwargs):
        self.calls += 1
        if isinstance(self.result, list):
            result = self.result[min(self.calls - 1, len(self.result) - 1)]
        else:
            result = self.result
        if isinstance(result, Exception):
            raise result
        return dict(result)


class _Hub:
    def __init__(self, providers):
        self.providers = providers

    def get_provider(self, name):
        return self.providers.get(name)


def _quote(price, provider, **overrides):
    result = {
        "price": price,
        "provider": provider,
        "source": provider,
        "as_of": (NOW - timedelta(seconds=10)).isoformat(),
        "exchange": "NASDAQ",
        "currency": "USD",
    }
    result.update(overrides)
    return result


def _service(*results, namespace="quote-test"):
    names = tuple(f"provider_{index}" for index in range(len(results)))
    hub = _Hub({name: _Provider(result) for name, result in zip(names, results, strict=True)})
    return ServerQuoteService(hub, providers=names, circuit_namespace=namespace)


def test_two_independent_server_quotes_create_consensus() -> None:
    service = _service(_quote(100.0, "one"), _quote(100.2, "two"))

    quote = service.resolve(symbol="QQQ", exchange="NASDAQ", currency="USD", now=NOW)

    assert quote["trust"] == "SERVER_VERIFIED_CONSENSUS"
    assert quote["source_count"] == 2
    assert quote["price"] == 100.1
    assert quote["stale_fallback_used"] is False
    assert len(quote["evidence_hash"]) == 64


def test_single_source_is_blocked() -> None:
    service = _service(_quote(100.0, "one"), {"error": "invalid api key"})
    with pytest.raises(ServerQuoteError, match="insufficient independent"):
        service.resolve(symbol="QQQ", exchange="NASDAQ", currency="USD", now=NOW)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"as_of": (NOW - timedelta(minutes=10)).isoformat()}, "stale"),
        ({"as_of": (NOW + timedelta(minutes=1)).isoformat()}, "future"),
        ({"exchange": "NYSE"}, "exchange mismatch"),
        ({"currency": "CAD"}, "currency mismatch"),
    ],
)
def test_invalid_provider_metadata_is_removed_from_consensus(override, message) -> None:
    service = _service(_quote(100.0, "one"), _quote(100.1, "two", **override))
    with pytest.raises(ServerQuoteError, match="insufficient independent") as exc:
        service.resolve(symbol="QQQ", exchange="NASDAQ", currency="USD", now=NOW)
    assert message in str(exc.value)


def test_excessive_provider_divergence_is_blocked() -> None:
    service = _service(_quote(100.0, "one"), _quote(105.0, "two"))
    with pytest.raises(ServerQuoteError, match="divergence"):
        service.resolve(symbol="QQQ", exchange="NASDAQ", currency="USD", now=NOW)


def test_transient_failures_open_then_half_open_and_close(monkeypatch) -> None:
    namespace = f"quote-circuit-{time.time_ns()}"
    first = _Provider([{"error": "timeout"}, {"error": "timeout"}, _quote(100, "one")])
    second = _Provider(_quote(100.1, "two"))
    hub = _Hub({"first": first, "second": second})
    service = ServerQuoteService(hub, providers=("first", "second"), circuit_namespace=namespace)
    circuit = get_circuit(f"{namespace}.first")
    circuit.failure_threshold = 2
    circuit.recovery_timeout = 0.01

    with pytest.raises(ServerQuoteError, match="insufficient"):
        service.resolve(symbol="QQQ", exchange="NASDAQ", currency="USD", now=NOW)
    assert circuit.state == CircuitState.OPEN

    time.sleep(0.02)
    quote = service.resolve(symbol="QQQ", exchange="NASDAQ", currency="USD", now=NOW)
    assert quote["source_count"] == 2
    assert circuit.state == CircuitState.CLOSED
