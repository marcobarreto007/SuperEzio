"""Regressao 2026-09-10: tese macro nao herda o ticker do dropdown da UI.

"Build a thesis ... secular opportunity" grudava em AAPL porque "thesis"
esta na lista de hints de tese de ativo. Tese macro/tematica deve soltar o
ticker; dica de ativo com ticker do dropdown deve mante-lo.
"""

from agent_server.endpoints import _should_keep_ui_ticker

MACRO_THESIS = (
    "An investor believes AI will dominate the next decade and wants heavy exposure "
    "to AI infrastructure, semiconductors, cloud, energy, and automation. Build a thesis "
    "that separates real secular opportunity from hype, overvaluation, and concentration risk."
)
TICKER_TIP = "me da uma dica de investimento nesse papel"


def test_macro_theme_does_not_keep_ui_ticker():
    assert (
        _should_keep_ui_ticker(
            message=MACRO_THESIS,
            detected_ticker="",
            explicit_ticker="AAPL",
            is_complex=True,
            is_capital_alloc=False,
        )
        is False
    )


def test_macro_theme_does_not_keep_ui_ticker_even_with_capital_flag():
    assert (
        _should_keep_ui_ticker(
            message=MACRO_THESIS,
            detected_ticker="AAPL",
            explicit_ticker="AAPL",
            is_complex=False,
            is_capital_alloc=True,
        )
        is False
    )


def test_ticker_tip_with_dropdown_ticker_keeps_ui_ticker():
    assert (
        _should_keep_ui_ticker(
            message=TICKER_TIP,
            detected_ticker="",
            explicit_ticker="TD.TO",
            is_complex=False,
            is_capital_alloc=False,
        )
        is True
    )


def test_tip_without_any_ticker_does_not_keep_ui_ticker():
    assert (
        _should_keep_ui_ticker(
            message=TICKER_TIP,
            detected_ticker="",
            explicit_ticker="",
            is_complex=False,
            is_capital_alloc=False,
        )
        is False
    )
