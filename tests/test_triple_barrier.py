"""Testes da barreira tripla (triple_barrier.py) e do mapa de horizonte.

Cobrem as adaptacoes obrigatorias do porte: high/low intrabar, desempate pessimista
no stop, gap de abertura e o motivo no vocabulario do paper_journal.
"""

from __future__ import annotations

import pytest

from core.trading.holding_period import (
    DEFAULT_HOLDING_PERIOD,
    HOLDING_PERIOD_BARS,
    bars_to_calendar_days,
    holding_period_bars,
    holding_period_days,
    holding_period_horizon,
    normalize_holding_period,
)
from core.trading.triple_barrier import (
    STOP_LOSS,
    TAKE_PROFIT,
    TIME_EXIT,
    evaluate_triple_barrier,
    normalize_side,
)


def _bar(open_: float, high: float, low: float, close: float, stamp: str = "2026-01-02") -> dict:
    return {"open": open_, "high": high, "low": low, "close": close, "datetime": stamp}


# ---------------------------------------------------------------------------
# Toque intrabar: high e low, nao so close
# ---------------------------------------------------------------------------


def test_take_profit_touched_intrabar_by_high():
    """Barra fecha ABAIXO do alvo mas o high passa dele: o alvo foi tocado."""
    bars = [_bar(100.0, 106.0, 99.0, 100.5)]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=105.0, time_horizon_bars=1
    )
    assert touch is not None
    assert touch.exit_reason == TAKE_PROFIT
    assert touch.exit_price == 105.0


def test_stop_touched_intrabar_by_low():
    """Barra fecha ACIMA do stop mas o low passa dele: o stop foi tocado."""
    bars = [_bar(101.0, 103.0, 94.0, 102.0)]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=115.0, time_horizon_bars=1
    )
    assert touch is not None
    assert touch.exit_reason == STOP_LOSS
    assert touch.exit_price == 95.0


def test_close_only_bars_regress_to_original_behaviour():
    """Sem high/low a barra cai no comportamento do original (tudo = close)."""
    bars = [{"close": 96.0, "datetime": "2026-01-02"}]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=115.0, time_horizon_bars=1
    )
    # close 96 > stop 95: sem faixa nao ha toque.
    assert touch is None or touch.exit_reason == TIME_EXIT


# ---------------------------------------------------------------------------
# Gap de abertura
# ---------------------------------------------------------------------------


def test_gap_down_through_stop_fills_at_open():
    """Barra inteira abaixo do stop: preenche pelo open, que e pior que o nivel."""
    bars = [_bar(92.0, 93.0, 90.0, 91.0)]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=115.0, time_horizon_bars=1
    )
    assert touch is not None
    assert touch.exit_reason == STOP_LOSS
    assert touch.exit_price == 92.0  # o open, nao 95.0
    assert touch.gapped is True


def test_gap_up_through_short_stop_fills_at_open():
    """Espelho para o lado curto: stop acima, gap de alta, preenche pelo open."""
    bars = [_bar(110.0, 112.0, 108.0, 111.0)]
    touch = evaluate_triple_barrier(
        bars, side="short", stop_loss_price=105.0, take_profit_price=90.0, time_horizon_bars=1
    )
    assert touch is not None
    assert touch.exit_reason == STOP_LOSS
    assert touch.exit_price == 110.0
    assert touch.gapped is True


def test_stop_inside_bar_fills_at_level_not_open():
    """Stop DENTRO da faixa: preenche no nivel, mesmo com open longe dele."""
    bars = [_bar(101.0, 103.0, 93.0, 94.0)]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=115.0, time_horizon_bars=1
    )
    assert touch is not None
    assert touch.exit_price == 95.0  # clamp: dentro da barra, nivel exato
    assert touch.gapped is False


def test_gap_through_target_does_not_inflate_the_win():
    """Alvo atravessado por gap NAO realiza acima do nivel.

    Divergencia deliberada do ml4t (que devolveria o open): no lado do ganho o
    projeto nao maquia para cima.
    """
    bars = [_bar(120.0, 125.0, 118.0, 124.0)]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=115.0, time_horizon_bars=1
    )
    assert touch is not None
    assert touch.exit_reason == TAKE_PROFIT
    assert touch.exit_price < 120.0  # nunca o open de 120


# ---------------------------------------------------------------------------
# Desempate: barra que toca stop E alvo
# ---------------------------------------------------------------------------


def test_dual_touch_resolves_as_stop_loss():
    """A ordem intrabar nao e observavel: assume o STOP (pessimista)."""
    bars = [_bar(100.0, 106.0, 94.0, 100.0)]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=105.0, time_horizon_bars=1
    )
    assert touch is not None
    assert touch.exit_reason == STOP_LOSS
    assert touch.exit_price == 95.0


def test_dual_touch_short_resolves_as_stop_loss():
    bars = [_bar(100.0, 106.0, 94.0, 100.0)]
    touch = evaluate_triple_barrier(
        bars, side="short", stop_loss_price=105.0, take_profit_price=95.0, time_horizon_bars=1
    )
    assert touch is not None
    assert touch.exit_reason == STOP_LOSS
    assert touch.exit_price == 105.0


def test_first_touch_across_bars_wins():
    """Barras anteriores decidem: o toque de stop na barra 0 vence o alvo da barra 1."""
    bars = [
        _bar(100.0, 101.0, 94.0, 95.0, "2026-01-02"),
        _bar(95.0, 120.0, 95.0, 119.0, "2026-01-03"),
    ]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=115.0, time_horizon_bars=2
    )
    assert touch is not None
    assert touch.exit_reason == STOP_LOSS
    assert touch.exit_index == 0
    assert touch.bars_held == 1


# ---------------------------------------------------------------------------
# Barreira vertical (prazo)
# ---------------------------------------------------------------------------


def test_vertical_barrier_closes_at_close_of_last_bar():
    bars = [
        _bar(100.0, 104.0, 98.0, 100.0, "2026-01-02"),
        _bar(100.0, 105.0, 99.0, 101.0, "2026-01-03"),
        _bar(101.0, 106.0, 99.0, 102.0, "2026-01-04"),
    ]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=90.0, take_profit_price=120.0, time_horizon_bars=3
    )
    assert touch is not None
    assert touch.exit_reason == TIME_EXIT
    assert touch.exit_price == 102.0  # close da ultima barra do prazo
    assert touch.bars_held == 3
    assert touch.exit_index == 2


def test_vertical_barrier_ignores_bars_beyond_horizon():
    """Barra 4 toca o alvo, mas o prazo venceu na 3: o desfecho e prazo."""
    bars = [
        _bar(100.0, 104.0, 98.0, 100.0),
        _bar(100.0, 105.0, 99.0, 101.0),
        _bar(101.0, 106.0, 99.0, 102.0),
        _bar(102.0, 130.0, 101.0, 129.0),
    ]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=90.0, take_profit_price=120.0, time_horizon_bars=3
    )
    assert touch is not None
    assert touch.exit_reason == TIME_EXIT
    assert touch.exit_price == 102.0


def test_horizon_not_elapsed_returns_none():
    """Faltando barra para o prazo, nao ha desfecho -- o trade segue aberto."""
    bars = [_bar(100.0, 104.0, 98.0, 100.0)]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=90.0, take_profit_price=120.0, time_horizon_bars=5
    )
    assert touch is None


def test_stop_hit_early_closes_without_waiting_the_horizon():
    """REGRESSAO: stop tocado na barra 1 de 5 fecha na barra 1, nao espera o prazo.

    Faltar barra para completar o horizonte indetermina o desfecho por PRAZO; nao
    pode indeterminar um toque horizontal que ja aconteceu.
    """
    bars = [_bar(100.0, 101.0, 94.0, 95.0)]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=115.0, time_horizon_bars=5
    )
    assert touch is not None
    assert touch.exit_reason == STOP_LOSS
    assert touch.bars_held == 1


def test_target_hit_early_closes_without_waiting_the_horizon():
    bars = [_bar(100.0, 106.0, 99.0, 105.0)]
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=95.0, take_profit_price=105.0, time_horizon_bars=5
    )
    assert touch is not None
    assert touch.exit_reason == TAKE_PROFIT
    assert touch.bars_held == 1


def test_no_bars_at_all_returns_none():
    assert (
        evaluate_triple_barrier(
            [], side="long", stop_loss_price=95.0, take_profit_price=115.0, time_horizon_bars=5
        )
        is None
    )


def test_start_index_skips_the_entry_bar():
    """A barra de entrada nao e reavaliada (nao se sabe o toque antes/depois)."""
    bars = [
        _bar(100.0, 101.0, 90.0, 91.0, "2026-01-02"),  # entrada: low 90 toca o stop 95
        _bar(96.0, 99.0, 96.0, 98.0, "2026-01-03"),  # nada acontece (low 96 > stop 95)
    ]
    kwargs = {"stop_loss_price": 95.0, "take_profit_price": 115.0, "time_horizon_bars": 1}

    from_entry = evaluate_triple_barrier(bars, side="long", start_index=0, **kwargs)
    assert from_entry is not None
    assert from_entry.exit_reason == STOP_LOSS
    assert from_entry.exit_index == 0

    after_entry = evaluate_triple_barrier(bars, side="long", start_index=1, **kwargs)
    assert after_entry is not None
    assert after_entry.exit_reason == TIME_EXIT  # o toque da entrada foi ignorado
    assert after_entry.exit_index == 1
    assert after_entry.exit_price == 98.0


# ---------------------------------------------------------------------------
# Vocabulario do journal e rotulo binario
# ---------------------------------------------------------------------------


def test_exit_reasons_match_the_journal_vocabulary():
    from core.trading.triple_barrier import BARRIER_EXIT_REASONS

    assert BARRIER_EXIT_REASONS == {STOP_LOSS, TAKE_PROFIT, TIME_EXIT}
    # O journal aceita estes (paper_journal.py:118-120) e nada fora disso.
    assert BARRIER_EXIT_REASONS <= {
        "take_profit",
        "stop_loss",
        "thesis_broken",
        "time_exit",
        "manual",
    }


def test_binary_label_is_one_only_on_profit():
    profit = evaluate_triple_barrier(
        [_bar(100.0, 106.0, 99.0, 105.0)],
        side="long",
        stop_loss_price=95.0,
        take_profit_price=105.0,
        time_horizon_bars=1,
    )
    assert profit is not None and profit.to_binary_label() == 1

    stopped = evaluate_triple_barrier(
        [_bar(100.0, 101.0, 94.0, 95.0)],
        side="long",
        stop_loss_price=95.0,
        take_profit_price=115.0,
        time_horizon_bars=1,
    )
    assert stopped is not None and stopped.to_binary_label() == 0


def test_normalize_side_accepts_broker_spellings():
    assert normalize_side("BUY") == "long"
    assert normalize_side("long") == "long"
    assert normalize_side("SELL") == "short"
    assert normalize_side("short") == "short"
    with pytest.raises(ValueError):
        normalize_side("sideways")


# ---------------------------------------------------------------------------
# Validacao de dado persistido
# ---------------------------------------------------------------------------


def test_inverted_barriers_raise():
    with pytest.raises(ValueError, match="Inverted barriers for long"):
        evaluate_triple_barrier(
            [_bar(100.0, 101.0, 99.0, 100.0)],
            side="long",
            stop_loss_price=110.0,
            take_profit_price=105.0,
            time_horizon_bars=1,
        )
    with pytest.raises(ValueError, match="Inverted barriers for short"):
        evaluate_triple_barrier(
            [_bar(100.0, 101.0, 99.0, 100.0)],
            side="short",
            stop_loss_price=95.0,
            take_profit_price=105.0,
            time_horizon_bars=1,
        )


def test_non_positive_barriers_raise():
    with pytest.raises(ValueError):
        evaluate_triple_barrier(
            [_bar(100.0, 101.0, 99.0, 100.0)],
            side="long",
            stop_loss_price=0.0,
            take_profit_price=105.0,
            time_horizon_bars=1,
        )


def test_non_positive_horizon_raises():
    with pytest.raises(ValueError, match="time_horizon_bars"):
        evaluate_triple_barrier(
            [_bar(100.0, 101.0, 99.0, 100.0)],
            side="long",
            stop_loss_price=95.0,
            take_profit_price=105.0,
            time_horizon_bars=0,
        )


def test_exact_touch_survives_float_noise():
    """Stop calculado por multiplicacao nao perde o toque exato (ruido de float)."""
    entry = 100.0
    stop = entry * (1 - 0.05)  # 95.00000000000001
    bars = [_bar(entry, entry + 1, 95.0, entry)]  # low exatamente 95.0
    touch = evaluate_triple_barrier(
        bars, side="long", stop_loss_price=stop, take_profit_price=115.0, time_horizon_bars=1
    )
    assert touch is not None
    assert touch.exit_reason == STOP_LOSS


# ---------------------------------------------------------------------------
# Mapa expected_holding_period -> barras/dias
# ---------------------------------------------------------------------------


def test_swing_maps_to_five_bars_and_seven_days():
    """O valor escolhido e DESTE teste: mudar a tabela tem que quebrar aqui."""
    assert HOLDING_PERIOD_BARS["swing"] == 5
    assert holding_period_bars("swing") == 5
    assert holding_period_days("swing") == 7


def test_full_holding_period_table():
    assert HOLDING_PERIOD_BARS == {
        "day_trade": 1,
        "swing": 5,
        "position": 21,
        "long_term": 63,
    }
    assert holding_period_bars("day_trade") == 1
    assert holding_period_bars("position") == 21
    assert holding_period_bars("long_term") == 63


def test_swing_is_the_lower_end_of_the_observed_swing_bucket():
    """Consistencia com feedback_loop: o bucket 'swing' medido vai ate 7 dias."""
    from core.trading.holding_period import TRADING_DAYS_PER_WEEK

    # Uma semana de pregao == o limite INFERIOR do bucket "swing" de feedback_loop
    # (que vai ate 7 dias corridos).
    assert holding_period_bars("swing") == TRADING_DAYS_PER_WEEK
    assert holding_period_bars("swing") <= 7
    # O bucket medido e o prometido sao a mesma faixa: 5 dias uteis cabem em 7 corridos.
    assert holding_period_days("swing") == 7


def test_calendar_days_round_up():
    assert bars_to_calendar_days(1) == 2  # 1,4 dia -> 2 (cobre o dia de pregao)
    assert bars_to_calendar_days(5) == 7
    assert bars_to_calendar_days(21) == 30
    assert bars_to_calendar_days(63) == 89
    assert bars_to_calendar_days(0) == 0


def test_unknown_holding_period_falls_back_to_the_conservative_default():
    for value in (None, "", "unknown", "scalp", 42):
        assert holding_period_bars(value) == HOLDING_PERIOD_BARS[DEFAULT_HOLDING_PERIOD] == 5


def test_holding_period_normalization():
    assert normalize_holding_period("SWING") == "swing"
    assert normalize_holding_period("  swing  ") == "swing"
    assert normalize_holding_period("day-trade") == "day_trade"
    assert normalize_holding_period("day trade") == "day_trade"
    assert holding_period_bars("SWING") == 5
    assert holding_period_bars("day-trade") == 1


def test_holding_period_horizon_payload():
    assert holding_period_horizon("swing") == {
        "expected_holding_period": "swing",
        "time_horizon_bars": 5,
        "time_horizon_days": 7,
    }
