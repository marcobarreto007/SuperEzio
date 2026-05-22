"""Tests for Finnhub symbol normalization."""

from __future__ import annotations

from data.finnhub_symbols import finnhub_symbol_variants


def test_brk_class_share_variants() -> None:
    variants = finnhub_symbol_variants("BRK-B")
    assert "BRK-B" in variants
    assert "BRK.B" in variants


def test_canadian_to_suffix_variants() -> None:
    variants = finnhub_symbol_variants("RY.TO", market="Canada")
    assert variants[0] == "RY.TO"
    assert "RY" in variants


def test_canadian_bare_symbol_adds_to_suffix() -> None:
    variants = finnhub_symbol_variants("RY", market="Canada")
    assert "RY" in variants
    assert "RY.TO" in variants
