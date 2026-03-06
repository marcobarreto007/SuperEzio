"""
Report generation.
"""

from ..contracts.schemas import CrisisReport


def build_crisis_summary(report: CrisisReport) -> str:
    parts = []

    if report.alert_level == "black":
        parts.append(
            "[ALERTA PRETO] O sistema detecta CRISE ou condição extrema de risco sistêmico."
        )
    elif report.alert_level == "red":
        parts.append("O sistema detecta estresse relevante no ambiente financeiro.")
    elif report.alert_level == "yellow":
        parts.append("O sistema detecta fragilidade crescente. Atenção necessária.")
    else:
        parts.append(
            "O ambiente financeiro atual aparenta estar normal, com baixo risco sistêmico."
        )

    parts.append(
        f"O regime estimado é {report.regime.upper()} com alerta {report.alert_level.upper()}."
    )
    parts.append(
        "Atenção máxima: o mercado está vulnerável e qualquer choque externo pode causar uma liquidação violenta. Ação imediata de proteção é recomendada."
    )

    summary = " ".join(parts)
    # Se houver menção a fraude nos resultados
    fraud_hits = [
        r.details.get("fraud_hits", [])
        for r in report.sensor_results
        if r.details.get("fraud_hits")
    ]
    if fraud_hits:
        summary += "\n\n[ALERTA DE SEGURANÇA]: Foram detectados padrões históricos de fraude/scam compatíveis com este contexto."

    return summary


def get_default_limitations() -> list[str]:
    return [
        "Foco técnico: detecção de anomalias sistêmicas em tempo real, não prevê datas exatas.",
        "Scores dependem da qualidade e frequência dos dados (garbage in, garbage out).",
        "Indicadores macroeconômicos costumam ter defasagem na publicação.",
        "Output estratégico: use para fundamentar decisões de alocação agressiva.",
    ]
