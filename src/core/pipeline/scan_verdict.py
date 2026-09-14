"""Scan verdict for speech vs trace.

The system decides REJECT_ALL + reasons. Chat gets a short PT/EN tip.
Telemetry stays out of CHUNK.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


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
    data_health: tuple[str, ...] = field(default_factory=tuple)


_REASON_LABELS = {
    "missing_price": (
        "preco atual indisponivel no data hub",
        "latest price unavailable from data hub",
    ),
    "missing_liquidity": ("liquidez abaixo do minimo", "liquidity below minimum"),
    "missing_catalyst": ("sem catalisador verificavel", "no verifiable catalyst"),
    "missing_thesis": ("sem tese de curto prazo", "no short-term thesis"),
    "stage_abandoned": (
        "preco nao deu tempo de chegar",
        "price enrich abandoned at stage deadline",
    ),
    "enrich_timeout": ("timeout ao buscar preco", "price enrich timed out"),
    "price_above_requested_max": (
        "preco acima do teto solicitado",
        "price above requested maximum",
    ),
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


def data_health_facts(scan: dict[str, Any] | None = None) -> tuple[str, ...]:
    """Fatos de saude dos dados do scan (rotas ativas, medicao real e chaves ausentes).

    Transparencia pedida no incidente 2026-09-10: o operador precisa ver que
    faltou insumo (ex.: catalisador sem provedor) em vez de so rejeicao muda.
    Reporta o que foi REALMENTE medido quando o scan executou; caso contrario,
    reporta as rotas ativas configuradas sem circuito aberto.
    Somente NOMES de chaves — nunca valores.
    """
    try:
        from data.data_hub import hub

        price = hub.list_routes("price")
        catalyst = hub.list_routes("short_term_catalyst")
    # Fronteira de melhor esforco: diagnostico nunca derruba o veredito.
    except Exception:  # noqa: BLE001
        return ()

    open_circuits = set()
    try:
        from core.resilience import get_circuit

        for r in (*price, *catalyst):
            name = str(r.get("name") or "")
            if name:
                cb = get_circuit(f"data.{name}")
                if cb.is_open:
                    open_circuits.add(name)
    except Exception:
        logger.debug("Failed checking circuit breaker states", exc_info=True)

    price_configured = [
        str(r.get("name"))
        for r in price
        if r.get("configured") and str(r.get("name")) not in open_circuits
    ]
    catalyst_configured = [
        str(r.get("name"))
        for r in catalyst
        if r.get("configured") and str(r.get("name")) not in open_circuits
    ]
    missing = sorted(
        {
            str(r.get("required_key"))
            for r in (*price, *catalyst)
            if r.get("required_key") and not r.get("configured")
        }
    )

    scan_trace = (scan.get("scan_trace") or {}) if isinstance(scan, dict) else {}
    has_telemetry = bool(
        scan_trace
        and (
            "provider_sources_used" in scan_trace
            or "price_sources_used" in scan_trace
            or "catalyst_sources_used" in scan_trace
        )
    )

    if has_telemetry:
        price_used = set(scan_trace.get("price_sources_used") or [])
        catalyst_used = set(scan_trace.get("catalyst_sources_used") or [])
        general_used = set(scan_trace.get("provider_sources_used") or [])

        price_route_names = {str(r.get("name")) for r in price}
        catalyst_route_names = {str(r.get("name")) for r in catalyst}

        measured_price: list[str] = [p for p in price_configured if p in price_used]
        measured_catalyst: list[str] = [c for c in catalyst_configured if c in catalyst_used]

        if isinstance(scan, dict):
            items = list(scan.get("candidates") or []) + list(scan.get("rejected") or [])
            for it in items:
                prov = it.get("provenance") if isinstance(it, dict) else {}
                if isinstance(prov, dict):
                    p_src = prov.get("price", {}).get("source")
                    if p_src and p_src in price_route_names and p_src not in measured_price:
                        measured_price.append(p_src)
                    c_src = prov.get("catalyst", {}).get("source")
                    if (
                        c_src
                        and (c_src in catalyst_route_names or "computed" in c_src)
                        and c_src not in measured_catalyst
                    ):
                        measured_catalyst.append(c_src)

        # Fallback when specific capability traces were not recorded:
        if not price_used and not measured_price:
            measured_price = [p for p in price_configured if p in general_used]
        rejection_sum = scan.get("rejection_summary") or {} if isinstance(scan, dict) else {}
        if not catalyst_used and not measured_catalyst and not rejection_sum.get("missing_catalyst"):
            measured_catalyst = [c for c in catalyst_configured if c in general_used]

        price_val = ",".join(sorted(measured_price)) or "none"
        catalyst_val = ",".join(sorted(measured_catalyst)) or "none"
    else:
        price_val = ",".join(price_configured) or "none"
        catalyst_val = ",".join(catalyst_configured) or "none"

    facts = [
        f"price={price_val}",
        f"catalyst={catalyst_val}",
    ]
    if open_circuits:
        facts.append(f"circuits_open={','.join(sorted(open_circuits))}")
    if missing:
        facts.append(f"missing_keys={','.join(missing)}")
    return tuple(facts)


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
        next_step_pt="Me passe um ticker com preco (ex. VFV.TO, TD.TO) ou consulte oportunidades TD no cockpit.",
        next_step_en="Give me a priced ticker (e.g. VFV.TO, TD.TO) or check TD opportunities in the cockpit.",
        source_errors=errors,
        data_health=data_health_facts(scan),
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
        if verdict.data_health:
            lines.extend(["", "Saude dos dados: " + "; ".join(verdict.data_health)])
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
    if verdict.data_health:
        lines.extend(["", "Data health: " + "; ".join(verdict.data_health)])
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
            "Proximo passo: me de um ticker (ex. VFV.TO, TD.TO) ou consulte as oportunidades TD no cockpit."
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
        "Next step: give me a ticker (e.g. VFV.TO, TD.TO) or check TD opportunities in the cockpit."
    )
