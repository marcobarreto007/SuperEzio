"""Tests for Finnhub symbol normalization."""

from __future__ import annotations

from data.finnhub_symbols import finnhub_symbol_variants


def test_brk_class_share_variants() -> None:
    variants = finnhub_symbol_variants("BRK-B")
    assert "BRK-B" in variants
    assert "BRK.B" in variants


def test_canadian_to_suffix_variants() -> None:
    td_variants = finnhub_symbol_variants("TD.TO")
    assert td_variants[0] == "TD.TO"
    assert "TD" not in td_variants

    ry_variants = finnhub_symbol_variants("RY.TO", market="Canada")
    assert ry_variants[0] == "RY.TO"
    assert "RY" not in ry_variants


def test_canadian_bare_symbol_adds_to_suffix() -> None:
    variants = finnhub_symbol_variants("RY", market="Canada")
    assert "RY" in variants
    assert "RY.TO" in variants


def test_canadian_v_suffix_variants_do_not_include_us_homonym() -> None:
    variants = finnhub_symbol_variants("SHOE.V")
    assert "SHOE.V" in variants
    assert "SHOE" not in variants
