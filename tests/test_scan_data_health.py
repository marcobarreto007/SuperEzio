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
