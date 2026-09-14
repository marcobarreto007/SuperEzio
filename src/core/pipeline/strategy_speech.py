"""Speech for product/strategy suggestions when the user names no ticker.

The lane gatekeeper renders this for questions with an amount and a risk
profile but no ticker ("quero investir 1000 cad em alto risco", "escolhe
um produto pra mim"). Instead of the old "stay in cash / give me a ticker"
default, this module answers with product classes that fit a small pile and
the declared profile, plus honest limits and two explicit next steps.

The module is standalone on purpose: agent.py imports it at runtime, so it
never imports agent.py back (cycle). Language detection is local to the
message; no telemetry or scan internals are quoted.
"""

from __future__ import annotations

import re

__all__ = ["render_product_strategy_suggestion"]

_AMOUNT_RE = re.compile(
    r"(?:cad\s*([\d.,]+)|([\d.,]+)\s*cad|usd\s*([\d.,]+)|\$\s*([\d.,]+))",
    re.IGNORECASE,
)

_HIGH_RISK_RE = re.compile(
    r"alto\s*risco|altissimo\s*risco|risco\s*alto|risco\s*maximo|maximo\s*risco|"
    r"maximo\s*(?:de\s*)?retorno|retorno\s*maximo|agressiv|arriscad|"
    r"alta\s*volatilidade|high\s*risk|maximum\s*risk|max\s*risk|aggressive|"
    r"maximum\s*return|highly\s*volatile|high\s*return",
    re.IGNORECASE,
)

_LOW_RISK_RE = re.compile(
    r"conservador|baixo\s*risco|avesso\s*a\s*risco|segur|estavel|"
    r"conservative|low\s*risk|risk\s*averse|safe\b|stable",
    re.IGNORECASE,
)

_PORTUGUESE_HINT_RE = re.compile(
    r"\b(voce|você|nao|não|uma|um|uns|para|com|como|quero|queria|preciso|"
    r"investir|aplicar|aplico|aplica|escolhe|escolha|escolher|pra|mim|"
    r"produto|algum|alguma|indica|indique|sugere|sugira|recomenda|"
    r"recomende|estou|esta|está|gostaria|qual|seria|pode|poderia)\b",
    re.IGNORECASE,
)

_PT_INTRO_HIGH = (
    "Com capital pequeno e perfil de alto risco, as classes que cabem "
    "(premissas ilustrativas, sem ticker inventado):"
)
_PT_INTRO_LOW = (
    "Com capital pequeno e perfil conservador, as classes que cabem "
    "(premissas ilustrativas, sem ticker inventado):"
)
_EN_INTRO_HIGH = (
    "With a small pile and a high-risk profile, the classes that fit "
    "(illustrative assumptions, no invented ticker):"
)
_EN_INTRO_LOW = (
    "With a small pile and a conservative profile, the classes that fit "
    "(illustrative assumptions, no invented ticker):"
)


def _extract_amount(message: str) -> str:
    """Best-effort currency amount from the user message.

    Same shape as scan_verdict._extract_amount: returns "" when the message
    carries no amount, otherwise a labelled value such as "CAD 1000".
    """
    text = message or ""
    match = _AMOUNT_RE.search(text)
    if not match:
        return ""
    raw = next((group for group in match.groups() if group), "")
    if re.search(r"\bcad\b|cad\s", text, re.IGNORECASE):
        return f"CAD {raw}"
    if "$" in text or re.search(r"\busd\b", text, re.IGNORECASE):
        return f"USD {raw}"
    return raw


def _classify_risk(message: str) -> str:
    """Classify the declared risk profile: "high", "low" or "none"."""
    text = message or ""
    if _HIGH_RISK_RE.search(text):
        return "high"
    if _LOW_RISK_RE.search(text):
        return "low"
    return "none"


def _sniff_portuguese(message: str) -> bool:
    return bool(_PORTUGUESE_HINT_RE.search(message or ""))


def _pt_profile_head(amount: str, risk: str) -> str:
    if amount and risk == "high":
        return f"Leitura do perfil: valor {amount} com perfil de alto risco."
    if amount and risk == "low":
        return f"Leitura do perfil: valor {amount} com perfil conservador."
    if amount:
        return (
            f"Leitura do perfil: valor {amount}; perfil nao declarado — "
            "assumo conservador ate voce dizer o contrario."
        )
    if risk == "high":
        return "Leitura do perfil: valor nao declarado; perfil de alto risco."
    if risk == "low":
        return "Leitura do perfil: valor nao declarado; perfil conservador."
    return (
        "Leitura do perfil: valor nao declarado e perfil nao declarado — "
        "assumo conservador ate voce dizer o contrario."
    )


def _en_profile_head(amount: str, risk: str) -> str:
    if amount and risk == "high":
        return f"Profile read: {amount} at high risk."
    if amount and risk == "low":
        return f"Profile read: {amount}, conservative."
    if amount:
        return (
            f"Profile read: {amount}; risk profile not stated — "
            "I assume conservative until you say otherwise."
        )
    if risk == "high":
        return "Profile read: no amount stated; high-risk profile."
    if risk == "low":
        return "Profile read: no amount stated; conservative profile."
    return (
        "Profile read: no amount and no risk profile stated — "
        "I assume conservative until you say otherwise."
    )


def _product_suggestion_pt(amount: str, risk: str, message: str = "") -> list[str]:
    is_cad = bool(
        re.search(r"\bcad\b", message or "", re.IGNORECASE)
        or (amount and "cad" in amount.lower())
    )
    high = risk == "high"

    if is_cad:
        intro = (
            "Com capital pequeno e perfil de alto risco, classes que cabem sob taxa zero TD:"
            if high
            else "Com capital sob o Protocolo de Sobrevivencia, classes elegiveis sob taxa zero TD:"
        )
        if high:
            classes = [
                "1) ETF de indice global de crescimento (ex.: VFV.TO ou XEQT.TO);",
                "2) ETF setorial canadense (ex.: ZEB.TO bancos);",
                "3) Acoes liquidas do TSX 60, somente com gate ticker-a-ticker.",
                "Ancora de protecao para o capital: HISA ou renda fixa (ZAG.TO).",
            ]
        else:
            classes = [
                "1) Core Global: VFV.TO (S&P 500 em CAD) ou XEQT.TO (100% acoes globais);",
                "2) Renda e Estabilidade: ZEB.TO (bancos canadenses) ou XIU.TO (TSX 60);",
                "3) Preservacao e Reserva: ZAG.TO (renda fixa) ou HISA / CASH.TO.",
            ]
        why_block = (
            "Por que: Taxa zero preserva a banca (evita arrasto de corretagem); risco maximo "
            "de 1.0% a 1.5% com R:R minimo 2.5:1 e Meta-Labeling P >= 0.55 com ordens LIMIT."
        )
        honesty = "Sem preco nem yield ao vivo neste run: operamos apenas com precos verificados."
        next_step = (
            "Proximo passo: escolha um candidato do universo TD (ex.: VFV.TO, XEQT.TO, ZEB.TO) "
            "para rodarmos os gates e niveis de Stop Loss sob o protocolo de Sobrevivencia."
        )
        closing = (
            "Decisao final e sua. Confira custos e limites atuais "
            "(ex.: espaco TFSA) no documento vigente."
        )
        return [
            _pt_profile_head(amount, risk),
            "",
            intro,
            *classes,
            "",
            why_block,
            "",
            honesty,
            "",
            next_step,
            "",
            closing,
        ]

    if high:
        classes = [
            "1) ETF de indice global de crescimento;",
            "2) ETF tematico ou setorial;",
            (
                "3) acoes individuais de pequena capitalizacao, somente com "
                "gate de dados ticker-a-ticker."
            ),
            "Ancora para o que voce nao quer expor: GIC em ladder ou HISA.",
        ]
        intro = _PT_INTRO_HIGH
    else:
        classes = [
            "1) HISA (conta de juros altos);",
            "2) GIC em ladder (vencimentos escalonados);",
            "3) ETF de renda fixa de curto prazo.",
        ]
        intro = _PT_INTRO_LOW
    honesty = (
        "Sem preco nem yield ao vivo neste run: nao nomeio produto com cotacao sem dado verificado."
    )
    closing = (
        "Decisao final e sua. Confira custos e limites atuais "
        "(ex.: espaco TFSA) no documento vigente."
    )
    return [
        _pt_profile_head(amount, risk),
        "",
        intro,
        *classes,
        "",
        honesty,
        "",
        "Proximo passo, escolha uma opcao:",
        "(a) me passe um candidato (ex.: um ticker) que eu rodo os gates de dados;",
        "(b) consulte as oportunidades verificadas no cockpit.",
        "",
        closing,
    ]


def _product_suggestion_en(amount: str, risk: str, message: str = "") -> list[str]:
    is_cad = bool(
        re.search(r"\bcad\b", message or "", re.IGNORECASE)
        or (amount and "cad" in amount.lower())
    )
    high = risk == "high"

    if is_cad:
        intro = (
            "With a small pile and high-risk profile, classes that fit under TD commission-free:"
            if high
            else "With capital under Survival Protocol, eligible classes under TD commission-free:"
        )
        if high:
            classes = [
                "1) Global growth index ETF (e.g. VFV.TO or XEQT.TO);",
                "2) Canadian sector ETF (e.g. ZEB.TO banks);",
                "3) Liquid TSX 60 stocks, only with per-ticker data gate.",
                "Capital protection anchor: HISA or fixed income (ZAG.TO).",
            ]
        else:
            classes = [
                "1) Core Global: VFV.TO (S&P 500 in CAD) or XEQT.TO (100% global equities);",
                "2) Income and Stability: ZEB.TO (Canadian banks) or XIU.TO (TSX 60);",
                "3) Capital Preservation: ZAG.TO (aggregate bonds) or HISA / CASH.TO.",
            ]
        why_block = (
            "Why: Zero commission protects the pile (no fee drag); max risk "
            "of 1.0% to 1.5% with min R:R 2.5:1 and Meta-Labeling P >= 0.55 using LIMIT orders."
        )
        honesty = "No live price or yield on this run: we operate only with verified prices."
        next_step = (
            "Next step: pick a candidate from the TD universe (e.g. VFV.TO, XEQT.TO, ZEB.TO) "
            "to run gates and Stop Loss levels under the Survival protocol."
        )
        closing = (
            "Final decision is yours. Check current costs and limits "
            "(e.g. TFSA room) in the current document."
        )
        return [
            _en_profile_head(amount, risk),
            "",
            intro,
            *classes,
            "",
            why_block,
            "",
            honesty,
            "",
            next_step,
            "",
            closing,
        ]

    if high:
        classes = [
            "1) global growth index ETF;",
            "2) thematic or sector ETF;",
            "3) individual small-cap stocks, only with a per-ticker data gate.",
            "Anchor for what you do not want exposed: GIC ladder or HISA.",
        ]
        intro = _EN_INTRO_HIGH
    else:
        classes = [
            "1) HISA (high-interest savings account);",
            "2) GIC ladder (staggered maturities);",
            "3) short-term fixed income ETF.",
        ]
        intro = _EN_INTRO_LOW
    honesty = (
        "No live price or yield on this run: I will not name a product with "
        "a quote I have not verified."
    )
    closing = (
        "Final decision is yours. Check current costs and limits "
        "(e.g. TFSA room) in the current document."
    )
    return [
        _en_profile_head(amount, risk),
        "",
        intro,
        *classes,
        "",
        honesty,
        "",
        "Next step, pick one option:",
        "(a) pass me a candidate (e.g. a ticker) and I run the data gates;",
        "(b) check verified opportunities in the cockpit.",
        "",
        closing,
    ]


def render_product_strategy_suggestion(
    message: str, scan=None, *, portuguese: bool | None = None
) -> str:
    """Render a deterministic PT/EN strategy suggestion for no-ticker asks.

    message: raw user text; amount and risk profile are sniffed from it.
    scan: reserved for lane parity; no evidence is ever quoted from it here.
    portuguese: None sniffs the message; True/False forces the language.

    The answer never invents a ticker, never quotes live prices or yields,
    names only product classes, and ends with two explicit next steps plus a
    final-decision note.
    """
    if portuguese is None:
        portuguese = _sniff_portuguese(message)
    amount = _extract_amount(message)
    risk = _classify_risk(message)
    lines = (
        _product_suggestion_pt(amount, risk, message)
        if portuguese
        else _product_suggestion_en(amount, risk, message)
    )
    return "\n".join(lines)
