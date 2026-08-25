"""Taxonomia central de reason codes das recusas de trade.

Fonte normativa dos codigos UPPER_SNAKE emitidos pelo F51 trade gate. O
objetivo e tornar as recusas agregaveis (taxa por codigo) em vez de texto
livre — a agregacao responde "qual gate esta doendo" com numero, nao com
impressao.

Uso: o gate continua emitindo strings (contrato publico ja fixado em
testes); este modulo e o registro de referencia, e o teste de conformidade
em tests/test_reason_codes.py garante que nenhum codigo novo entra no gate
sem passar por aqui. Adocao incremental: os demais emissores de motivo
(position_sizer, manual_trade_workflow, approval_gate) seguem com texto
descritivo e serao migrados um a um.
"""

from __future__ import annotations

from typing import Final

REASON_CODES: Final[dict[str, str]] = {
    # Gate 1 — freeze operacional
    "EXECUTION_FREEZE": "Trading congelado por flag de ambiente (F51_TRADING_EXECUTION_FREEZE).",
    # Gate 1.5 — estado de consciencia
    "MAN_AT_WORK": "CEO brain em modo diagnostico; nenhuma ordem sai.",
    "MAN_AT_WORK_UNAVAILABLE": "Sonda de consciencia inacessivel; fail-closed.",
    # Gate 2 — intencao
    "NON_TRADE_INTENT": "Mensagem sem pedido explicito de trade.",
    # Gates 3-5 — ticker
    "BLACKLISTED_TICKER": "Ticker em lista de bloqueio.",
    "INVALID_TICKER_FORMAT": "Ticker fora do padrao esperado.",
    "TICKER_MISMATCH": "Ticker da ordem diverge da tese da mensagem.",
    # Gates 7-8 — quantidade/preco placeholder
    "PLACEHOLDER_QUANTITY": "Quantidade placeholder (5/10/100 com preco 99) bloqueada.",
    "INVALID_QUANTITY": "Quantidade invalida (<= 0).",
    "PLACEHOLDER_PRICE": "Preco placeholder $99.00 bloqueado por politica.",
    # Gate 9 — validacao DataHub
    "TICKER_VALIDATION_FAILED": "DataHub nao validou o ticker.",
    # Gate 9.5 — colar de preco
    "LIMIT_PRICE_COLLAR": "limit_price desvia alem da banda da referencia DataHub.",
    # Gate 9b — IBKR
    "IBKR_OFFLINE": "TWS/Gateway IBKR inalcancavel.",
    # Gate 10 — journal
    "JOURNAL_UNAVAILABLE": "Journal de trades inacessivel.",
    # Terminal positivo
    "ALL_GATES_PASSED": "Todos os gates passaram.",
}


def is_registered_reason_code(code: str) -> bool:
    """True se o codigo consta na taxonomia central."""
    return code in REASON_CODES
