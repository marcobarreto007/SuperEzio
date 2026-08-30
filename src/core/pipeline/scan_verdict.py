"""Scan verdict for speech vs trace.

The system decides REJECT_ALL + reasons. Chat gets a short PT/EN tip.
Telemetry stays out of CHUNK.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScanReason:
    code: str
    count: int
    label_pt: str
    label_en: str


@dataclass(frozen=True)
class ScanVerdict:
    decision: str
    amount: str
    universe: str
    screened: int
    rejected: int
    reasons: tuple[ScanReason, ...]
    blocking_gate: str
    next_step_pt: str
    next_step_en: str
    source_errors: tuple[str, ...] = field(default_factory=tuple)


_REASON_LABELS = {
    "missing_price": ("preco atual indisponivel no data hub", "latest price unavailable from data hub"),
    "missing_liquidity": ("liquidez abaixo do minimo", "liquidity below minimum"),
    "missing_catalyst": ("sem catalisador verificavel", "no verifiable catalyst"),
    "missing_thesis": ("sem tese de curto prazo", "no short-term thesis"),
    "stage_abandoned": ("preco nao deu tempo de chegar", "price enrich abandoned at stage deadline"),
    "enrich_timeout": ("timeout ao buscar preco", "price enrich timed out"),
    "price_above_requested_max": ("preco acima do teto solicitado", "price above requested maximum"),
}


def _extract_amount(message: str) -> str:
    text = message or ""
    match = re.search(
        r"(?:cad\s*([\d.,]+)|([\d.,]+)\s*cad|usd\s*([\d.,]+)|\$\s*([\d.,]+))",
        text,
        re.IGNORECASE,
    )
    if not match:
        return ""
    raw = next((g for g in match.groups() if g), "")
    if re.search(r"\bcad\b|cad\s", text, re.IGNORECASE):
        return f"CAD {raw}"
    if "$" in text or re.search(r"\busd\b", text, re.IGNORECASE):
        return f"USD {raw}"
    return raw


def build_scan_verdict(state: dict[str, Any]) -> ScanVerdict:
    scan = state.get("scan") or {}
    if not isinstance(scan, dict):
        scan = {}
    message = str(state.get("message") or "")
    rejection = scan.get("rejection_summary") or {}
    if not isinstance(rejection, dict):
        rejection = {}
    reasons: list[ScanReason] = []
    for code, count in sorted(rejection.items(), key=lambda kv: (-int(kv[1] or 0), str(kv[0]))):
        n = int(count or 0)
        if n <= 0:
            continue
        pt, en = _REASON_LABELS.get(str(code), (str(code), str(code)))
        reasons.append(ScanReason(code=str(code), count=n, label_pt=pt, label_en=en))
    errors = tuple(str(e) for e in (scan.get("source_errors") or []) if e)
    blocking = reasons[0].code if reasons else "empty_scan"
    rejected = int(scan.get("rejected_count", 0) or 0)
    candidates = scan.get("candidates") or []
    screened = rejected + (len(candidates) if isinstance(candidates, list) else 0)
    return ScanVerdict(
        decision="REJECT_ALL" if not candidates else "CANDIDATES",
        amount=_extract_amount(message),
        universe=str(scan.get("universe") or ""),
        screened=screened,
        rejected=rejected,
        reasons=tuple(reasons),
        blocking_gate=blocking,
        next_step_pt="Me passe um ticker com preco (ex. TD.TO) ou peca um scan de mini cap com catalisador.",
        next_step_en="Give me a priced ticker (e.g. TD.TO) or ask for a mini-cap scan with a catalyst.",
        source_errors=errors,
    )


def render_scan_speech(verdict: ScanVerdict, *, portuguese: bool) -> str:
    amount = verdict.amount or ("esse capital" if portuguese else "this capital")
    if portuguese:
        lines = [
            f"Voce pediu uma ideia com {amount}.",
            "",
            f"Tentei {verdict.screened} nomes. Nenhum candidato passou no gate.",
        ]
        if verdict.blocking_gate in {"missing_price", "stage_abandoned", "enrich_timeout"}:
            lines.append(
                "O data hub falhou: o preco falhou para a maioria dos nomes. "
                "Sem preco nao existe entrada, stop nem tamanho — e eu nao invento ticker."
            )
        elif verdict.reasons:
            top = ", ".join(f"{r.label_pt} ({r.count})" for r in verdict.reasons[:3])
            lines.append(f"Nao tenho nome. Motivo principal: {top}.")
        else:
            lines.append("Nao tenho nome com evidencia verificada neste run.")
        lines.extend(
            [
                "",
                (
                    f"Minha opiniao com {amount} hoje: fica em caixa. "
                    "Live continua congelado. Paper so com preco e liquidez reais."
                ),
                "",
                f"Proximo passo: {verdict.next_step_pt}",
            ]
        )
        return "\n".join(lines)
    lines = [
        f"You asked for an idea with {amount}.",
        "",
        f"I screened {verdict.screened} names. No candidate passed the gate.",
    ]
    if verdict.blocking_gate in {"missing_price", "stage_abandoned", "enrich_timeout"}:
        lines.append(
            "I have no name because price did not come back. No price means no entry, "
            "stop, or size — and I will not invent a ticker."
        )
    elif verdict.reasons:
        top = ", ".join(f"{r.label_en} ({r.count})" for r in verdict.reasons[:3])
        lines.append(f"I have no name. Main reasons: {top}.")
    else:
        lines.append("I have no name with verified evidence on this run.")
        lines.extend(
            [
                "",
                (
                    f"My take with {amount} today: stay in cash. "
                    "Live stays frozen. Paper only with a real price and liquidity."
                ),
                "",
                f"Next step: {verdict.next_step_en}",
            ]
        )
    return "\n".join(lines)


def render_small_capital_speech(message: str, scan: dict[str, Any] | None = None) -> str:
    """Allocation of a small cash pile with no verified ticker."""
    amount = _extract_amount(message) or "CAD 100"
    state = {"message": message, "scan": scan or {}}
    verdict = build_scan_verdict(state)
    portuguese = bool(
        re.search(
            r"\b(voce|você|nao|não|uma|para|com|como|investir|sugere|quero)\b",
            message or "",
            re.IGNORECASE,
        )
    )
    if scan and isinstance(scan, dict) and scan.get("candidates"):
        return render_scan_speech(verdict, portuguese=portuguese)
    if portuguese:
        return (
            f"Voce pediu alto risco e maximo retorno com {amount}.\n"
            "\n"
            "Nao tenho um nome com preco verificado neste run. "
            "Sem preco eu nao monto entrada, stop nem tamanho — e nao invento ticker.\n"
            "\n"
            f"Minha opiniao com {amount} hoje: fica em caixa ou espera a proxima janela. "
            "Cem dolares num nome sem preco confirmado morre no spread.\n"
            "\n"
            "Live continua congelado. Paper so com evidencia.\n"
            "Proximo passo: me de um ticker (ex. TD.TO) ou peca um scan de mini cap com catalisador."
        )
    return (
        f"You asked for high risk and max return with {amount}.\n"
        "\n"
        "I do not have a name with a verified price on this run. "
        "Without a price I will not build entry, stop, or size — and I will not invent a ticker.\n"
        "\n"
        f"My take with {amount} today: stay in cash or wait for the next window.\n"
        "\n"
        "Live stays frozen. Paper only with evidence.\n"
        "Next step: give me a ticker (e.g. TD.TO) or ask for a mini-cap scan with a catalyst."
    )
