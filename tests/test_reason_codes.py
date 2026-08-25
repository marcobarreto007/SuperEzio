"""Conformidade dos reason codes do F51 gate com a taxonomia central.

Qualquer codigo novo emitido pelo gate sem registro em
core.trading.reason_codes quebra este teste — o registro e o lugar onde a
agregacao por codigo passa a existir.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.trading.reason_codes import REASON_CODES, is_registered_reason_code

# Literais que casam com o padrao de codigo mas NAO sao reason codes.
_NON_CODES = {"BLOCK", "ALLOW", "LMT", "OK"}


def _gate_emitted_codes() -> set[str]:
    source = Path("src/core/pipeline/f51_trade_gate.py").read_text(encoding="utf-8")
    literals = set(re.findall(r'^\s*"([A-Z][A-Z0-9_]+)"\s*,\s*$', source, re.MULTILINE))
    return {
        c
        for c in literals
        if c not in _NON_CODES
        and c.endswith(
            (
                "_FAILED",
                "_OFFLINE",
                "_FREEZE",
                "_PRICE",
                "_QUANTITY",
                "_INTENT",
                "_TICKER",
                "_WORK",
                "_UNAVAILABLE",
                "_UNAVAILABLE",
                "_PASSED",
                "_COLLAR",
                "_MISMATCH",
                "_FORMAT",
                "_BLACKLIST",
                "_BLACKLISTED",
                "_LIST",
            )
        )
    }


def test_every_gate_code_is_registered() -> None:
    emitted = _gate_emitted_codes()
    assert emitted, "regex nao encontrou codigos — ajustar a extracao"
    unregistered = sorted(code for code in emitted if not is_registered_reason_code(code))
    assert not unregistered, (
        f"reason codes emitidos pelo gate sem registro na taxonomia: {unregistered}"
    )


def test_registry_has_no_orphan_descriptions() -> None:
    for code, description in REASON_CODES.items():
        assert description.strip(), f"{code} sem descricao"


def test_new_gate_codes_are_registered() -> None:
    for code in ("MAN_AT_WORK", "MAN_AT_WORK_UNAVAILABLE", "LIMIT_PRICE_COLLAR"):
        assert is_registered_reason_code(code), f"{code} ausente da taxonomia"
