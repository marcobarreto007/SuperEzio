from core.evidence.grounding import (
    collect_security_claims,
    mentioned_security_symbols,
    mismatched_price_symbols,
)


def test_claim_binds_ticker_price_source_time_and_evidence_id():
    claims = collect_security_claims(
        {
            "scan": {
                "candidates": [
                    {
                        "ticker": "REAL",
                        "price": 6.25,
                        "provider": "finnhub",
                        "collected_at": "2026-07-19T12:00:00Z",
                    }
                ]
            }
        }
    )
    claim = claims["REAL"]
    assert claim.price == 6.25
    assert claim.source == "finnhub"
    assert claim.as_of == "2026-07-19T12:00:00Z"
    assert claim.evidence_id.startswith("security:")


def test_grounded_real_ticker_overrides_ambiguous_prose_word():
    symbols = mentioned_security_symbols(
        "REAL has grounded earnings data; DADOS are incomplete.",
        grounded={"REAL"},
        exclusions=set(),
        prose_words={"REAL", "DADOS"},
    )
    assert symbols == {"REAL"}


def test_price_claim_must_match_structured_evidence():
    claims = collect_security_claims({"data": {"ticker": "AAPL", "price": 200.0, "source": "test"}})
    assert mismatched_price_symbols("AAPL trades at $201", claims) == set()
    assert mismatched_price_symbols("AAPL trades at $315", claims) == {"AAPL"}
