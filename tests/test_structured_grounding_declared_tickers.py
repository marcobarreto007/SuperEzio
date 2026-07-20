"""Regression tests for the structured mentioned_tickers grounding path.

Three prior incidents (commit c53daf4, docs/audit/phase9 report, commit
47659a7) all had the same root cause: _mentioned_tickers() regex-scans
Bob's free-form prose for anything that looks like a ticker, and every new
domain acronym Bob happened to write in caps (ALLOW/DCF/EMA/IBKR/SELL/TRAP/
VWAP, then DADOS/SEM/SCAN, then FCF/HRP) triggered a false "you invented a
ticker" guard that discarded a real, correct analysis. These tests prove
the structural fix: when the LLM declares which tickers it named via
final_answer's mentioned_tickers arg, the guard trusts that declaration
instead of guessing from prose, so a domain acronym in the text can never
trigger a false positive again — regardless of what new acronym Bob's
prose uses next.
"""

from core.pipeline.nodes.agent import _apply_grounding_guard, _parse_declared_tickers


def test_parse_declared_tickers_normalizes_and_filters():
    assert _parse_declared_tickers(["shop", " AAPL ", "", 123, None]) == {"SHOP", "AAPL"}


def test_parse_declared_tickers_empty_list_is_trusted_not_none():
    # An empty list is a valid, meaningful answer ("no ticker named") and
    # must NOT be treated the same as "field absent" (which falls back to
    # regex scanning).
    assert _parse_declared_tickers([]) == set()


def test_parse_declared_tickers_missing_field_returns_none():
    assert _parse_declared_tickers(None) is None
    assert _parse_declared_tickers("not-a-list") is None


def _state_with_grounded_shop():
    return {
        "data": {
            "ticker": "SHOP",
            "price": 117.85,
            "provider": "finnhub",
            "data_quality": "partial",
        },
        "ticker": "SHOP",
    }


def test_declared_tickers_prevents_false_positive_on_domain_acronyms():
    """The exact failure mode from the three prior incidents: prose mentions
    FCF and HRP (real module/metric names, not tickers). With the old
    regex-only path this discarded the whole analysis. With declared
    tickers = {"SHOP"} (what the model actually named), the acronyms in the
    text are irrelevant — the guard only checks what was declared.
    """
    content = (
        "SHOP: FCF is negative this quarter. Portfolio sizing uses HRP "
        "allocation. Final verdict: BEARISH."
    )
    result = _apply_grounding_guard(_state_with_grounded_shop(), content, {"SHOP"})
    assert result == content  # untouched — no guard message injected
    assert "FCF" not in result or "tickers not collected" not in result


def test_declared_tickers_still_catches_real_ungrounded_ticker():
    """If the model declares a ticker it was never given data for, the
    guard must still fire — declared tickers are trusted for WHAT they
    say, not exempt from the grounding check itself.
    """
    content = "SHOP looks weak. NVDA looks strong too. Final verdict: WAIT."
    result = _apply_grounding_guard(_state_with_grounded_shop(), content, {"SHOP", "NVDA"})
    assert result != content
    assert "NVDA" in result


def test_no_declared_tickers_falls_back_to_regex_scan():
    """Backward compatibility: when the model doesn't provide
    mentioned_tickers (older prompt path, or a model that ignores the new
    arg), the guard still works via the original regex scan — it must not
    silently stop protecting against ungrounded tickers.
    """
    content = "SHOP looks weak. NVDA looks strong too. Final verdict: WAIT."
    result = _apply_grounding_guard(_state_with_grounded_shop(), content, None)
    assert result != content
    assert "NVDA" in result
