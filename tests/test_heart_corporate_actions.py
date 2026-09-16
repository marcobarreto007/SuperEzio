"""Peça 1c: o preço as-traded ganha sempre contra o evento Yahoo."""

from __future__ import annotations

from core.heart.corporate_actions import SplitEvent, classify_split_day


def test_matching_drop_is_a_confirmed_split():
    event = SplitEvent(numerator=10, denominator=1)
    decision = classify_split_day(prev_close=125.2, close=12.52, event=event)
    assert decision.kind == "confirmed_split"
    assert decision.apply_to_archive is True


def test_event_without_price_jump_means_archive_already_adjusted():
    event = SplitEvent(numerator=4, denominator=1)
    decision = classify_split_day(prev_close=129.0, close=129.4, event=event)
    assert decision.kind == "already_adjusted"
    assert decision.apply_to_archive is False


def test_price_jump_without_event_is_an_unexplained_move():
    decision = classify_split_day(prev_close=50.0, close=25.0, event=None)
    assert decision.kind == "unexplained_move"
    assert decision.apply_to_archive is False


def test_canadian_old_for_new_prose_matches_yahoo_ratio():
    # Boletim TSXV "10 old for 1 new" == Yahoo 1:10 (preço sobe 10x).
    event = SplitEvent.from_yahoo_ratio("1:10")
    decision = classify_split_day(prev_close=1.00, close=10.00, event=event)
    assert event.numerator == 1
    assert event.denominator == 10
    assert decision.kind == "confirmed_split"


def test_never_merge_a_delisted_yahoo_404_into_a_recycled_ticker():
    from core.heart.corporate_actions import freeze_on_yahoo_missing

    assert freeze_on_yahoo_missing(status=404) is True
    assert freeze_on_yahoo_missing(status=200) is False
