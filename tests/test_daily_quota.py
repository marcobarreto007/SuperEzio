"""Cota diária por provedor + gate do DataHub.

Contexto (2026-09-14): o free tier do Alpha Vantage é 25 requisições por DIA
(alphavantage.co/support — "25 API requests per day"; a página não menciona
limite por minuto). O hub só tinha pacing por intervalo (`12.0` s, comentado
como "5 req/min" — errado), que não limita total diário: um scan podia
disparar ~300 chamadas/hora e queimar a cota do dia em minutos. Estes testes
cobrem o contador diário e o gate que pula a rota esgotada.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from data import daily_quota
from data.data_hub import (
    _PROVIDER_DAILY_QUOTA,
    _PROVIDER_MIN_INTERVAL_S,
    DataHub,
    ProviderRoute,
)


@pytest.fixture
def quota_dir(tmp_path, monkeypatch):
    """Isola o arquivo de estado da cota em tmp_path (nunca no repo)."""
    monkeypatch.setenv("SUPEREZIO_DATA_DIR", str(tmp_path))
    return tmp_path


def _seed(provider: str, count: int, *, day_offset: int = 0) -> None:
    """Escreve estado direto no arquivo, como se o dia já tivesse sido gasto."""
    path = daily_quota.state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    date = (datetime.now(UTC).date() + timedelta(days=day_offset)).isoformat()
    path.write_text(json.dumps({provider: {"date": date, "count": count}}), encoding="utf-8")


class _FakeProvider:
    """Provider falso: conta chamadas, nunca toca a rede."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls = 0
        self._result = result if result is not None else {"price": 42.0, "source": "fake"}

    def get_quote(self, symbol: str, **_: Any) -> dict[str, Any]:
        self.calls += 1
        return dict(self._result)

    def get_price(self, symbol: str, **_: Any) -> dict[str, Any]:
        self.calls += 1
        return dict(self._result)


# ── contador ──────────────────────────────────────────────────────────────


def test_consume_increments_and_exhausts_at_limit(quota_dir) -> None:
    assert daily_quota.used("alpha_vantage") == 0
    assert daily_quota.is_exhausted("alpha_vantage", 25) is False

    for expected in range(1, 25):
        assert daily_quota.consume("alpha_vantage") == expected

    assert daily_quota.used("alpha_vantage") == 24
    assert daily_quota.remaining("alpha_vantage", 25) == 1
    assert daily_quota.is_exhausted("alpha_vantage", 25) is False  # 24 < 25

    assert daily_quota.consume("alpha_vantage") == 25
    assert daily_quota.is_exhausted("alpha_vantage", 25) is True
    assert daily_quota.remaining("alpha_vantage", 25) == 0


def test_counter_is_per_provider(quota_dir) -> None:
    daily_quota.consume("alpha_vantage")
    daily_quota.consume("alpha_vantage")
    daily_quota.consume("twelve_data")
    assert daily_quota.used("alpha_vantage") == 2
    assert daily_quota.used("twelve_data") == 1


def test_counter_resets_on_new_day(quota_dir) -> None:
    """Cota virada = contador zerado; sem isso o provedor ficaria morto para sempre."""
    _seed("alpha_vantage", 25, day_offset=-1)
    assert daily_quota.used("alpha_vantage") == 0
    assert daily_quota.is_exhausted("alpha_vantage", 25) is False
    assert daily_quota.consume("alpha_vantage") == 1


def test_same_day_count_is_not_reset(quota_dir) -> None:
    _seed("alpha_vantage", 25)
    assert daily_quota.is_exhausted("alpha_vantage", 25) is True


def test_corrupt_state_file_degrades_to_zero(quota_dir) -> None:
    """Estado ilegível não pode derrubar a chamada de dados nem explodir."""
    path = daily_quota.state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{isso nao e json", encoding="utf-8")
    assert daily_quota.used("alpha_vantage") == 0
    assert daily_quota.consume("alpha_vantage") == 1


def test_snapshot_reports_counters(quota_dir) -> None:
    daily_quota.consume("alpha_vantage")
    snap = daily_quota.snapshot()
    assert snap["alpha_vantage"]["count"] == 1
    assert snap["alpha_vantage"]["stale"] is False


# ── configuração ──────────────────────────────────────────────────────────


def test_alpha_vantage_quota_is_the_confirmed_daily_free_tier() -> None:
    """25/dia é o número da fonte primária, não uma estimativa."""
    assert _PROVIDER_DAILY_QUOTA["alpha_vantage"] == 25


def test_quota_keys_name_real_routes() -> None:
    """Chave com typo nunca dispara o gate — falha silenciosa clássica."""
    hub = DataHub(register_defaults=True)
    for name in _PROVIDER_DAILY_QUOTA:
        assert name in hub.routes, f"cota diária aponta para rota inexistente: {name}"


# ── gate no hub ───────────────────────────────────────────────────────────


def _hub_with_fake_alpha_vantage(monkeypatch, fake: _FakeProvider) -> DataHub:
    """Hub real, mas com o provedor do Alpha Vantage trocado por um falso.

    As rotas de preço à frente (finnhub 1, yfinance 2) e atrás (twelve_data 12,
    tmx 25) saem do caminho para que o teste fale só do gate de cota — nenhum
    teste toca a rede (tmx é keyless e atenderia de verdade).

    O pacing de 12 s da rota também sai: ele é real e continua valendo em
    produção, mas 25 chamadas com 12 s de intervalo custariam 5 minutos de
    suíte. O que está sob teste aqui é a cota diária, não o burst smoother.
    """
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key-no-network")
    monkeypatch.delitem(_PROVIDER_MIN_INTERVAL_S, "alpha_vantage", raising=False)
    hub = DataHub(register_defaults=True)
    for name in ("finnhub", "yfinance", "twelve_data", "tmx"):
        hub.routes.pop(name, None)
    hub.providers["alpha_vantage"] = fake
    return hub


def test_hub_calls_provider_and_consumes_quota(quota_dir, monkeypatch) -> None:
    fake = _FakeProvider()
    hub = _hub_with_fake_alpha_vantage(monkeypatch, fake)

    result = hub.route("price", "AAPL")

    assert result["source"] == "fake"
    assert fake.calls == 1
    assert daily_quota.used("alpha_vantage") == 1


def test_hub_skips_route_when_daily_quota_exhausted(quota_dir, monkeypatch) -> None:
    """Cota esgotada = rota pulada, SEM chamar o provedor.

    Uma chamada que o provedor recusa por cota já foi contada do lado dele —
    tentar de novo só queima mais. O gate pula antes do HTTP.
    """
    _seed("alpha_vantage", 25)
    fake = _FakeProvider()
    hub = _hub_with_fake_alpha_vantage(monkeypatch, fake)

    result = hub.route("price", "AAPL")

    assert fake.calls == 0, "provedor foi chamado com a cota diária esgotada"
    assert "error" in result
    assert daily_quota.used("alpha_vantage") == 25, "cota não pode ter sido consumida"
    errors = [a.get("error") for a in result.get("attempts", [])]
    assert "daily_quota_exhausted" in errors


def test_hub_falls_through_to_next_route_when_quota_exhausted(quota_dir, monkeypatch) -> None:
    """Cota esgotada é fallback normal, não fim da cadeia."""
    _seed("alpha_vantage", 25)
    fake = _FakeProvider()
    hub = _hub_with_fake_alpha_vantage(monkeypatch, fake)

    fallback = _FakeProvider({"price": 7.5, "source": "fallback"})
    hub.register_provider(
        ProviderRoute(
            name="fallback_test",
            capabilities=("price",),
            factory=lambda: fallback,
            methods={"price": "get_price"},
            priority=50,
            required_key=None,
        )
    )

    result = hub.route("price", "AAPL")

    assert result["source"] == "fallback"
    assert fake.calls == 0
    assert fallback.calls == 1


def test_cache_hit_does_not_consume_quota(quota_dir, monkeypatch) -> None:
    """Hit de cache não é requisição: não pode gastar cota."""
    fake = _FakeProvider()
    hub = _hub_with_fake_alpha_vantage(monkeypatch, fake)

    hub.route("price", "AAPL")
    hub.route("price", "AAPL")  # mesma capability + mesmo símbolo → cache

    assert fake.calls == 1
    assert daily_quota.used("alpha_vantage") == 1


def test_quota_exhausted_mid_scan_stops_calling(quota_dir, monkeypatch) -> None:
    """O caso do incidente: N símbolos num scan não podem passar da cota."""
    fake = _FakeProvider()
    hub = _hub_with_fake_alpha_vantage(monkeypatch, fake)

    for i in range(30):
        hub.route("price", f"SYM{i}")

    assert fake.calls == 25, f"esperado 25 chamadas (cota), houve {fake.calls}"
    assert daily_quota.used("alpha_vantage") == 25
    assert daily_quota.is_exhausted("alpha_vantage", 25) is True
