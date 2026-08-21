from __future__ import annotations

from core.bob_consciousness import body
from data import data_hub


def test_datahub_health_passes_when_any_configured_symbol_has_a_real_provider(
    monkeypatch,
):
    calls: list[str] = []

    class FakeHub:
        def list_active(self):
            return ["provider_one", "provider_two"]

        def get_price(self, symbol):
            calls.append(symbol)
            if symbol == "SHOP.TO":
                return {"error": "no_provider_result_for_price"}
            return {"price": 42.5, "provider": "provider_two"}

    monkeypatch.setenv("SUPEREZIO_DATAHUB_HEALTH_SYMBOLS", " shop.to, enb.to,shop.to ")
    monkeypatch.setattr(data_hub, "DataHub", FakeHub)

    healthy, detail = body._check_datahub_health()

    assert healthy is True
    assert calls == ["SHOP.TO", "ENB.TO"]
    assert detail == "ENB.TO via provider_two"


def test_datahub_health_rejects_prices_without_active_provider_provenance(monkeypatch):
    class FakeHub:
        def list_active(self):
            return ["configured_provider"]

        def get_price(self, symbol):
            return {"price": 42.5, "provider": "synthetic"}

    monkeypatch.setenv("SUPEREZIO_DATAHUB_HEALTH_SYMBOLS", "MSFT,TD.TO")
    monkeypatch.setattr(data_hub, "DataHub", FakeHub)

    healthy, detail = body._check_datahub_health()

    assert healthy is False
    assert "DataHub probes exhausted" in detail
