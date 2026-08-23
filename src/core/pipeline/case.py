"""Financial Case — contrato estrutural obrigatorio.

Um CASE define o que PRECISA acontecer antes do Bob dar veredito.
Nao e opcional. Nao e "se quiser usar tools".
E mandatorio: a mesa estuda, o Bob decide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CaseType(str, Enum):
    INVESTMENT_ANALYSIS = "investment_analysis"  # "analisa AAPL", "vale investir em DIBS?"
    TRADE_ORDER = "trade_order"  # "comprar 10 NOK limite $5"
    MARKET_DISCOVERY = "market_discovery"  # "me ache penny stocks", "scan setor energia"
    PORTFOLIO_REVIEW = "portfolio_review"  # "como estamos?", "carteira"
    CASUAL = "casual"  # "oi", "bom dia"


@dataclass
class CaseStep:
    name: str
    completed: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class FinancialCase:
    """Um case financeiro obrigatorio.

    Bob so pode dar veredito depois que todas as etapas obrigatorias
    forem completadas. Nao existe "responder sem dados".
    """

    case_type: CaseType
    ticker: str = ""
    mandate: str = ""  # o que o usuario pediu
    steps: dict[str, CaseStep] = field(default_factory=dict)
    verdict: str = ""  # BUY / SELL / WAIT / REJECT (preenchido pelo Bob)
    verdict_reason: str = ""
    run_id: str = ""

    @property
    def is_complete(self) -> bool:
        """Todas as etapas obrigatorias foram completadas?"""
        required = self.required_steps()
        return all(self.steps.get(name, CaseStep(name="")).completed for name in required)

    @property
    def pending_steps(self) -> list[str]:
        """Etapas obrigatorias que ainda nao foram completadas."""
        required = self.required_steps()
        return [name for name in required if not self.steps.get(name, CaseStep(name="")).completed]

    def required_steps(self) -> list[str]:
        """Etapas obrigatorias para este tipo de case."""
        base = ["system_status"]  # IBKR + guardrails sempre

        if self.case_type == CaseType.CASUAL:
            return base

        if self.case_type == CaseType.MARKET_DISCOVERY:
            return base + [
                "scanner",
                "price_enrichment",
                "sentiment_check",
                "guardrails",
            ]

        if self.case_type in (CaseType.INVESTMENT_ANALYSIS, CaseType.TRADE_ORDER):
            steps = base + [
                "data_collection",
                "math_hub",
                "genie_sentiment",
                "deep_analysis",
                "expert_committee",
                "trinity_deliberation",
                "guardrails",
                "verdict",
            ]

        if self.case_type == CaseType.TRADE_ORDER:
            steps.append("paper_order")

        if self.case_type == CaseType.PORTFOLIO_REVIEW:
            return base + [
                "portfolio_snapshot",
                "sentiment_check",
                "guardrails",
            ]

        return steps

    def mark_complete(self, step_name: str, evidence: dict | None = None) -> None:
        """Marca uma etapa como concluida."""
        if step_name not in self.steps:
            self.steps[step_name] = CaseStep(name=step_name)
        self.steps[step_name].completed = True
        if evidence:
            self.steps[step_name].evidence.update(evidence)

    def mark_error(self, step_name: str, error: str) -> None:
        """Marca uma etapa com erro (nao bloqueia o veredito, mas registra)."""
        if step_name not in self.steps:
            self.steps[step_name] = CaseStep(name=step_name)
        self.steps[step_name].error = error
        self.steps[step_name].completed = True  # erro nao bloqueia

    def to_state(self) -> dict[str, Any]:
        """Serializa para o state do LangGraph."""
        return {
            "case_type": self.case_type.value,
            "case_ticker": self.ticker,
            "case_mandate": self.mandate,
            "case_steps": {
                name: {
                    "completed": step.completed,
                    "error": step.error,
                }
                for name, step in self.steps.items()
            },
            "case_is_complete": self.is_complete,
            "case_pending": self.pending_steps,
            "case_verdict": self.verdict,
            "case_verdict_reason": self.verdict_reason,
        }

    def to_context(self) -> str:
        """Renderiza o case como contexto para o Bob."""
        lines = [
            "═" * 50,
            f"CASE: {self.case_type.value}",
            f"TICKER: {self.ticker or 'nao especificado'}",
            f"MANDATO: {self.mandate}",
            f"STATUS: {'COMPLETO' if self.is_complete else 'INCOMPLETO'}",
            "",
            "ETAPAS:",
        ]
        for name in self.required_steps():
            step = self.steps.get(name, CaseStep(name=name))
            icon = "✅" if step.completed else "⬜"
            error = f" [ERRO: {step.error}]" if step.error else ""
            lines.append(f"  {icon} {name}{error}")

        if self.pending_steps:
            lines.append("")
            lines.append(f"PENDENTE: {', '.join(self.pending_steps)}")
            lines.append("Voce PRECISA completar estas etapas antes de dar veredito.")

        if self.is_complete:
            lines.append("")
            lines.append("CASE COMPLETO. Voce pode dar o veredito final agora.")

        lines.append("═" * 50)
        return "\n".join(lines)


def create_case(message: str, ticker: str = "", run_id: str = "") -> FinancialCase:
    """Cria um case financeiro baseado na mensagem do usuario.

    Classificacao simples e pragmatica — sem regex fragil.
    Olha palavras-chave e contexto.
    """
    from core.pipeline.intents import _is_casual_message, detect_ticker

    if _is_casual_message(message):
        return FinancialCase(
            case_type=CaseType.CASUAL,
            mandate=message,
            run_id=run_id,
        )

    resolved_ticker = ticker or detect_ticker(message)
    has_ticker = bool(resolved_ticker)
    msg = message.lower().strip() if message else ""

    # Caso 1: Ordem explicita
    trade_words = (
        "comprar",
        "compre",
        "compra",
        "vender",
        "venda",
        "vendido",
        "buy",
        "sell",
        "ordem",
        "order",
        "executar",
        "execute",
        "papel",
        "paper_ticket",
        "paper ticket",
        "submit",
    )
    has_trade = any(w in msg for w in trade_words)

    if has_trade and has_ticker:
        return FinancialCase(
            case_type=CaseType.TRADE_ORDER,
            ticker=resolved_ticker,
            mandate=message,
            run_id=run_id,
        )

    # Caso 2: Analise de ticker
    analysis_words = (
        "analisa",
        "analise",
        "analisar",
        "analyze",
        "analysis",
        "avalia",
        "avaliar",
        "avaliacao",
        "evaluate",
        "o que acha",
        "what do you think",
        "opiniao",
        "opiniao",
        "vale a pena",
        "is it worth",
        "investir em",
    )
    has_analysis = any(w in msg for w in analysis_words)

    if (has_analysis or has_ticker) and not has_trade:
        return FinancialCase(
            case_type=CaseType.INVESTMENT_ANALYSIS,
            ticker=ticker,
            mandate=message,
            run_id=run_id,
        )

    # Caso 3: Descoberta de mercado
    discovery_words = (
        "ache",
        "achar",
        "encontre",
        "encontrar",
        "find",
        "search",
        "busca",
        "buscar",
        "procura",
        "procurar",
        "scan",
        "scanner",
        "descubra",
        "descobrir",
        "discover",
        "oportunidade",
        "penny",
        "small cap",
        "microcap",
        "setor",
        "sector",
        "recomend",
        "recomendar",
        "sugira",
        "sugerir",
    )
    if any(w in msg for w in discovery_words):
        return FinancialCase(
            case_type=CaseType.MARKET_DISCOVERY,
            mandate=message,
            run_id=run_id,
        )

    # Caso 4: Portfolio / status
    portfolio_words = (
        "carteira",
        "portfolio",
        "posicao",
        "posicoes",
        "como estamos",
        "how are we",
        "status",
        "saldo",
        "quanto tenho",
        "what do I have",
    )
    if any(w in msg for w in portfolio_words):
        return FinancialCase(
            case_type=CaseType.PORTFOLIO_REVIEW,
            mandate=message,
            run_id=run_id,
        )

    # Caso 5: Casual
    return FinancialCase(
        case_type=CaseType.CASUAL,
        mandate=message,
        run_id=run_id,
    )
