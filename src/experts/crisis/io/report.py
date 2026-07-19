"""Honest report generation for the crisis expert."""

from ..contracts.schemas import CrisisReport


def build_crisis_summary(report: CrisisReport) -> str:
    if report.status == "unavailable":
        return "Dados insuficientes para estimar risco de crise; nenhum sinal verde foi emitido."

    if report.alert_level == "black":
        parts = ["[ALERTA PRETO] Os dados indicam condição extrema de risco sistêmico."]
    elif report.alert_level == "red":
        parts = ["Os dados indicam estresse relevante no ambiente financeiro."]
    elif report.alert_level == "yellow":
        parts = ["Os dados indicam fragilidade crescente; atenção é necessária."]
    else:
        parts = ["Os dados disponíveis indicam baixo risco sistêmico no horizonte analisado."]

    parts.append(
        f"O regime estimado é {report.regime.upper()} com alerta {report.alert_level.upper()}."
    )
    if report.alert_level in {"red", "black"}:
        parts.append("O risco elevado requer revisão imediata de exposição e liquidez.")

    summary = " ".join(parts)
    fraud_hits = [
        result.details.get("fraud_hits", [])
        for result in report.sensor_results
        if result.details.get("fraud_hits")
    ]
    if fraud_hits:
        summary += (
            "\n\n[ALERTA DE SEGURANÇA]: Foram encontrados padrões históricos de fraude "
            "compatíveis com este contexto."
        )
    return summary


def get_default_limitations() -> list[str]:
    return [
        "Os modelos estimam risco em horizontes declarados; não preveem datas exatas.",
        "Scores dependem da qualidade, frequência e cobertura dos dados.",
        "Indicadores macroeconômicos podem ter defasagem e revisão de publicação.",
        "O resultado apoia gestão de risco e não substitui validação independente.",
    ]
