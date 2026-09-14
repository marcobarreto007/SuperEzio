"""data_health no veredito do scan (transparencia do incidente 10/09)."""

from core.pipeline.scan_verdict import build_scan_verdict, render_scan_speech


def _state():
    return {
        "message": "pesquisa oportunidades de curto prazo",
        "scan": {
            "universe": "penny",
            "rejected_count": 24,
            "candidates": [],
            "rejection_summary": {
                "missing_catalyst": 10,
                "liquidity_below_minimum": 9,
                "missing_price": 5,
            },
        },
    }


def test_verdict_carries_data_health():
    verdict = build_scan_verdict(_state())
    joined = "; ".join(verdict.data_health)
    assert "price=" in joined
    assert "catalyst=" in joined


def test_render_speech_shows_data_health_pt():
    verdict = build_scan_verdict(_state())
    speech = render_scan_speech(verdict, portuguese=True)
    assert "Saude dos dados" in speech


def test_render_speech_shows_data_health_en():
    verdict = build_scan_verdict(_state())
    speech = render_scan_speech(verdict, portuguese=False)
    assert "Data health" in speech


def test_news_catalyst_route_is_registered_as_keyless_fallback():
    from data.data_hub import hub

    routes = {r["name"]: r for r in hub.list_routes("short_term_catalyst")}
    assert "news_catalyst" in routes
    assert routes["news_catalyst"]["configured"] is True
    assert routes["news_catalyst"]["required_key"] is None


def test_measured_telemetry_reported_honestly_when_scan_trace_present():
    state = {
        "message": "pesquisa oportunidades de curto prazo",
        "scan": {
            "universe": "penny",
            "rejected_count": 24,
            "candidates": [],
            "rejection_summary": {
                "missing_catalyst": 10,
                "liquidity_below_minimum": 9,
                "missing_price": 5,
            },
            "scan_trace": {
                "provider_sources_used": ["finnhub"],
            },
        },
    }
    verdict = build_scan_verdict(state)
    joined = "; ".join(verdict.data_health)
    # Price was measured and used by Finnhub
    assert "price=finnhub" in joined
    # Catalyst was NOT delivered by any provider (honest reflection)
    assert "catalyst=none" in joined


def test_derive_missing_risk_satisfies_quality_gates():
    from core.pipeline.nodes.collector import _derive_missing_risk
    from core.pipeline.trade_order import evaluate_quality_gates

    candidate = {
        "ticker": "TEST.TO",
        "price": 10.50,
        "avg_daily_volume_shares": 500_000,
        "catalyst": "q3 earnings beat expectations with revenue guidance raised",
        "provenance": {
            "ticker": {"source": "td_universe"},
            "price": {"source": "finnhub"},
            "avg_daily_volume_shares": {"source": "finnhub"},
            "catalyst": {"source": "news_catalyst"},
        },
    }

    # Before derivation, risk is missing
    _, failures = evaluate_quality_gates(candidate)
    assert "missing_risk" in failures
    assert "missing_invalidation" in failures

    # After derivation, risk and invalidation are populated with actionable keywords and valid provenance
    _derive_missing_risk(candidate)
    assert candidate.get("risk") is not None
    assert candidate.get("invalidation") is not None

    _, failures_after = evaluate_quality_gates(candidate)
    assert "missing_risk" not in failures_after
    assert "missing_risk_provenance" not in failures_after
    assert "missing_invalidation" not in failures_after
    assert "missing_invalidation_provenance" not in failures_after

