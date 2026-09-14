"""Intent and ticker detection for the chat pipeline.

FunÃ§Ãµes pÃºblicas exportadas:
  - parse_user_intent(message, rigor) -> IntentParse
  - detect_ticker(message) -> str
  - detect_diary_intent(message) -> bool
  - detect_market_scan_intent(message) -> bool
  - detect_decisive_trade_intent(message) -> bool
  - is_product_strategy_suggestion(message) -> bool
  - detect_another_trade_recommendation_intent(message) -> bool
  - detect_pennylab_intent(message) -> bool
  - detect_complex_finance_intent(message) -> bool
  - infer_scan_filters(message) -> dict
  - should_block_vague_financial_prompt(message, ticker, rigor) -> bool
  - normalize_message(text) -> str
  - has_hint(message, hints) -> bool

Constantes exportadas:
  - VAGUE_FINANCIAL_HINTS, SCAN_KEYWORDS, SCOPE_KEYWORDS
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..observability.debug_logger import MODULE_INTENTS as MODULE_INTENT
from ..observability.debug_logger import debug_logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GOLDEN_INTENT_PATH = PROJECT_ROOT / "data" / "intent_golden.jsonl"

ALLOWED_ROUTES = {"agent", "general", "ticker_analysis", "market_scan", "needs_scope"}
ALLOWED_INTENTS = {
    "bob_decides",
    "general_question",
    "explain_capabilities",
    "ticker_analysis",
    "market_scan",
    "another_trade_recommendation",
    "missing_required_slot",
    "unsafe_unspecified_recommendation",
    "capital_allocation",
    "personal_finance",
}
ALLOWED_ACTIONS = {
    "answer",
    "answer_directly",
    "collect_data",
    "scan_market",
    "ask_for_ticker",
    "ask_for_scope",
}
ROUTE_INTENT_ACTIONS = {
    "general": {
        "general_question",
        "explain_capabilities",
        "capital_allocation",
        "personal_finance",
    },
    "ticker_analysis": {"ticker_analysis"},
    "market_scan": {"market_scan", "another_trade_recommendation"},
    "needs_scope": {"missing_required_slot", "unsafe_unspecified_recommendation"},
}

FINAL_ONLY_TOOLS = ("final_answer",)
FULL_TICKER_TOOLS = (
    "market_scan",
    "collect_data",
    "f51_firewall",
    "pennylab",
    "run_experts",
    "neural_decision",
    "sdca_firewall",
    "rag_forensics",
    "submit_paper_order",
    "bob_search",
    "final_answer",
)
DISCOVERY_TOOLS = (
    "market_scan",
    "collect_data",
    "run_experts",
    "neural_decision",
    "sdca_firewall",
    "rag_forensics",
    "submit_paper_order",
    "final_answer",
)
FORENSIC_ONLY_TOOLS = ("rag_forensics", "final_answer")

RISK_LAB_HINTS = (
    "cad 50",
    "$50",
    "50 cad",
    "50 dollars",
    "50 por semana",
    "50/week",
    "weekly risk",
    "risk lab",
    "laboratorio",
    "laboratÃ³rio",
    "loteria",
    "lottery",
    "aposto",
    "apostar",
    "small bet",
    "perder 50",
)

INDUSTRY_RESEARCH_HINTS = (
    "industry",
    "industria",
    "indÃºstria",
    "sector",
    "setor",
    "theme",
    "tese",
    "thesis",
    "pesquisa uma industria",
    "pesquisar uma industria",
    "fax",
)

FORENSIC_RAG_HINTS = (
    "fraud",
    "scam",
    "pump",
    "dump",
    "hype",
    "manipulation",
    "manipulacao",
    "manipulaÃ§Ã£o",
    "insider",
    "penny stock",
    "penny stocks",
)

BROKER_STATUS_SUBJECT_HINTS = (
    "ibkr",
    "interactive brokers",
    "tws",
    "trader workstation",
    "ib gateway",
    "gateway",
)

BROKER_STATUS_CONTEXT_HINTS = (
    "broker",
    "corretora",
    "api",
    "socket",
    "7497",
    "paper",
    "demo",
    "read-only",
    "read only",
    "readonly",
    "modo paper",
    "estado atual",
    "situacao atual",
    "situacao",
    "consegue ler",
    "pode ler",
    "posicoes",
    "positions",
    "equity",
    "conta",
    "market debut",
    "debut",
)


OPERATIONAL_STATUS_PATTERNS = (
    r"\b(?:qual|veja|verifica|verifique|mostra|mostre|checa|cheque|check)\b.{0,90}\b(?:estado|status|sistema|runtime|treino|treinamento|checkpoint|broker|ibkr|api|porta|operacional)\b",
    r"\b(?:estado|status)\b.{0,60}\b(?:operacional|sistema|runtime|treino|treinamento|checkpoint|broker|ibkr|api|porta)\b",
    r"\b(?:sistema|runtime|treino|treinamento|checkpoint|broker|ibkr|api|porta)\b.{0,60}\b(?:estado|status|rodando|on|online|operacional|pronto)\b",
)

NEGATIVE_TRADE_INSTRUCTION_PATTERNS = (
    r"\bnao\s+(?:me\s+)?recomende\b",
    r"\bnao\s+recomendar\b",
    r"\bsem\s+(?:recomendacao|recomendar|compra|comprar|trade|ordem)\b",
    r"\bnao\s+(?:compre|comprar|venda|vender|mande|envie|executa|execute|executar)\b",
    r"\bdo\s+not\s+(?:recommend|buy|sell|trade|send|execute)\b",
    r"\bdon'?t\s+(?:recommend|buy|sell|trade|send|execute)\b",
    r"\bno\s+(?:recommendation|buy|sell|trade|order)\b",
    r"\bwithout\s+(?:recommendation|buying|selling|trading|sending|executing)\b",
)


def detect_operational_status_request(message: str) -> bool:
    """Detect system/training/runtime status prompts that must not trigger market tools."""
    if not message or not message.strip():
        return False
    normalized = normalize_message(message)
    if any(re.search(pattern, normalized) for pattern in OPERATIONAL_STATUS_PATTERNS):
        return True
    return detect_broker_status_intent(message)


def detect_negative_trade_instruction(message: str) -> bool:
    """Detect explicit instructions not to recommend, trade, buy, sell, or send orders."""
    if not message or not message.strip():
        return False
    normalized = normalize_message(message)
    return any(re.search(pattern, normalized) for pattern in NEGATIVE_TRADE_INSTRUCTION_PATTERNS)


def _paper_order_submit_enabled() -> bool:
    return os.getenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


DEFAULT_PAPER_SUBMIT_HINTS = (
    "ticket",
    "transacao",
    "transacoes",
    "transação",
    "transações",
    "trades",
    "ordens rapidas",
)


def _default_paper_submit_for_decisive_training(message: str) -> bool:
    """Allow ticket submission by default only for explicit training ticket workflows."""
    if not message or not message.strip():
        return False
    return has_hint(message, DEFAULT_PAPER_SUBMIT_HINTS)


def _is_casual_message(message: str) -> bool:
    if not message or not message.strip():
        return True
    text = normalize_message(message).strip().lower()

    # Remove leading/trailing "bob", punctuation
    cleaned = re.sub(r"^bob[\s,:\-!\?]+", "", text).strip()
    cleaned = re.sub(r"[\s,:\-!\?]+bob$", "", cleaned).strip()

    # Direct exact casual phrases
    casual_phrases = {
        "oi",
        "ola",
        "olá",
        "hey",
        "hi",
        "hello",
        "opa",
        "fala",
        "salve",
        "tudo bem",
        "tudo bom",
        "td bem",
        "td bom",
        "como vai",
        "como esta",
        "como você esta",
        "como voce esta",
        "beleza",
        "blz",
        "tranquilo",
        "bom dia",
        "boa tarde",
        "boa noite",
        "e ai",
        "e aí",
        "teste",
        "test",
        "ping",
        "pong",
        "obrigado",
        "valeu",
        "thanks",
    }
    if text in casual_phrases or cleaned in casual_phrases:
        return True

    # Regex patterns for greetings and pleasantries
    patterns = [
        r"^(?:oi|ola|olá|hey|hi|hello|fala|e\s*ai|e\s*aí|salve|opa)\b",
        r"^(?:bom\s*dia|boa\s*tarde|boa\s*noite)\b",
        r"\b(?:tudo\s*(?:bem|bom)|como\s*vai|como\s*est[aá]|beleza|tranquilo|td\s*bem)\b",
        r"^(?:quem\s*[eé]\s*voc[eê]|o\s*que\s*voc[eê]\s*faz|como\s*funciona|ajuda|help)\b",
    ]
    words = text.split()
    financial_action_words = {
        "comprar",
        "compro",
        "compra",
        "vender",
        "vendo",
        "venda",
        "trade",
        "ordem",
        "order",
        "buy",
        "sell",
        "analise",
        "analisar",
        "alvo",
        "stop",
        "grafico",
        "gráfico",
        "scan",
        "scanner",
        "preco",
        "preço",
        "recomenda",
        "recomendacao",
        "recomendação",
        "recomendaria",
    }
    if len(words) <= 7 and not any(w in financial_action_words for w in words):
        for pat in patterns:
            if (re.search(pat, text) or re.search(pat, cleaned)) and not _residual_content(text):
                # The greeting must span the WHOLE message. "oi bob" is a
                # casual greeting; "oi bob, status rapido sem operar" carries
                # a real request and must reach the full pipeline (MathHub
                # included) — only pure pleasantry tokens may remain.
                return True

    return False


# Tokens that carry no request content — greetings, pleasantries, the
# operator name, and the identity/help phrases matched by the patterns above.
_CASUAL_TOKENS = frozenset(
    {
        # greetings / interjections
        "oi",
        "ola",
        "olá",
        "hey",
        "hi",
        "hello",
        "opa",
        "fala",
        "salve",
        "e",
        "ai",
        "aí",
        # time-of-day greetings
        "bom",
        "boa",
        "dia",
        "tarde",
        "noite",
        # pleasantries
        "tudo",
        "bem",
        "como",
        "vai",
        "esta",
        "está",
        "voce",
        "você",
        "beleza",
        "blz",
        "tranquilo",
        "td",
        "obrigado",
        "valeu",
        "thanks",
        # meta / test probes
        "teste",
        "test",
        "ping",
        "pong",
        # identity/help phrases (patterns above)
        "quem",
        "é",
        "faz",
        "que",
        "funciona",
        "ajuda",
        "help",
        # operator name
        "bob",
    }
)


def _residual_content(text: str) -> str:
    """Strip casual tokens from ``text``; return whatever real content remains."""
    tokens = [t.strip(".,:;!?-–—\"'()") for t in text.split()]
    return " ".join(t for t in tokens if t and t.lower() not in _CASUAL_TOKENS)


def _without_tools(tools: tuple[str, ...] | list[str], *blocked: str) -> list[str]:
    blocked_set = set(blocked)
    return [tool for tool in tools if tool not in blocked_set]


def detect_broker_status_intent(message: str) -> bool:
    """Detect broker/API operating-state questions, not ticker analysis."""
    if not message or not message.strip():
        return False
    if detect_decisive_trade_intent(message):
        return False
    lower = _strip_accents(message).lower()
    has_subject = any(hint in lower for hint in BROKER_STATUS_SUBJECT_HINTS)
    has_context = any(hint in lower for hint in BROKER_STATUS_CONTEXT_HINTS)
    return has_subject and has_context


def detect_risk_lab_intent(message: str) -> bool:
    """Detect a small weekly risk-budget experiment, not capital deployment."""
    return bool(message and has_hint(message, RISK_LAB_HINTS))


_INVESTMENT_THESIS_HINTS = (
    "dica",
    "dicas",
    "tip",
    "tese",
    "thesis",
    "invalidacao",
    "invalidation",
    "alvo",
    "stop",
    "direcao",
    "direction",
    "investir em",
    "investimento sobre",
    "investment thesis",
    "investment tip",
    "analisa",
    "analise",
    "analyze",
    "analysis",
)


def is_investment_thesis_request(message: str) -> bool:
    """True when the operator asks for a ticker thesis / tip / plan.

    Used to force ticker_analysis + the full decision stack. Does not by
    itself imply a market scan or a live order.
    """
    if not message or not message.strip():
        return False
    return has_hint(message, _INVESTMENT_THESIS_HINTS)


def detect_industry_research_intent(message: str) -> bool:
    """Detect industry/theme research that should not force a ticker."""
    if not message or not message.strip():
        return False
    if _is_market_scan_request(message):
        return False
    # "tese/dica sobre SPY" is ticker analysis, not a sector theme.
    if _has_inline_ticker_like_token(message) and is_investment_thesis_request(message):
        return False
    return has_hint(message, INDUSTRY_RESEARCH_HINTS)


def _needs_forensic_rag(message: str) -> bool:
    return bool(message and has_hint(message, FORENSIC_RAG_HINTS))


def infer_cognitive_contract(
    message: str,
    *,
    route: str,
    intent: str,
    action: str,
    ticker: str = "",
) -> dict[str, Any]:
    """Infer the runtime tool contract for Bob Core."""
    raw = message or ""

    if not raw.strip() or _is_casual_message(raw):
        return {
            "cognitive_mode": "CASUAL",
            "information_need": "greeting",
            "allowed_tools": ["final_answer"],
            "market_context_allowed": False,
            "scanner_allowed": False,
            "ticker_allowed": False,
            "ticket_allowed": False,
            "answer_contract": (
                "Responda com 1-3 linhas. Confirme que esta online. "
                "Nao chame market_scan, collect_data ou submit_paper_order."
            ),
        }

    operational_status_request = detect_operational_status_request(raw)
    negative_market_instruction = detect_negative_scan_instruction(
        raw
    ) or detect_negative_trade_instruction(raw)
    suppress_market_tools = operational_status_request or negative_market_instruction
    has_ticker = bool(
        ticker
        or route == "ticker_analysis"
        or intent == "ticker_analysis"
        or action == "collect_data"
        or (route == "agent" and intent == "bob_decides" and detect_ticker(raw))
    )
    # A rota vaga delegada (route=general, intent=market_scan, action=answer)
    # e decisao de fala do operador, nao um pedido de scan: action=answer nunca
    # concede scanner so pelo intent. A relacao crua com o mercado (detector de
    # scan) so vale em rotas que nao resolveram para general/answer.
    delegated_answer = route == "general" and action == "answer"
    scan_requested = bool(
        route == "market_scan"
        or (intent in {"market_scan", "another_trade_recommendation"} and action != "answer")
        or action == "scan_market"
        or (detect_market_scan_intent(raw) and not delegated_answer)
    )
    decisive_trade = detect_decisive_trade_intent(raw)

    scanner_allowed = bool(scan_requested and not suppress_market_tools)
    ticker_allowed = bool((has_ticker or scanner_allowed) and not suppress_market_tools)
    market_context_allowed = bool((scanner_allowed or ticker_allowed) and not suppress_market_tools)
    paper_submit_allowed = bool(
        scanner_allowed
        and decisive_trade
        and not detect_negative_trade_instruction(raw)
        and (_paper_order_submit_enabled() or _default_paper_submit_for_decisive_training(raw))
    )

    if suppress_market_tools:
        allowed_tools = ["final_answer"]
        cognitive_mode = "STATUS_ONLY" if operational_status_request else "ANSWER_ONLY"
        information_need = (
            "system_or_policy_status" if operational_status_request else "market_tools_blocked"
        )
        answer_contract = (
            "Responda somente o que foi pedido pelo usuario. "
            "Nao recomende compra, nao escaneie mercado e nao monte ordem."
        )
    elif scanner_allowed:
        allowed_tools = _without_tools(DISCOVERY_TOOLS, "submit_paper_order")
        if paper_submit_allowed:
            allowed_tools.insert(-1, "submit_paper_order")
        cognitive_mode = "MARKET_DISCOVERY"
        information_need = "market_scan"
        answer_contract = (
            "Use market_scan apenas porque o usuario pediu descoberta/treino de mercado. "
            "Colete evidencias, rode gates e finalize como pesquisa. "
            "submit_paper_order so pode ser chamado quando aparecer em allowed_tools."
        )
    elif ticker_allowed:
        allowed_tools = _without_tools(FULL_TICKER_TOOLS, "market_scan", "submit_paper_order")
        cognitive_mode = "TICKER_RESEARCH"
        information_need = "ticker_analysis"
        answer_contract = (
            "Analise o ticker atual com dados e verificadores. "
            "Nao escaneie mercado amplo e nao envie ordem. "
            "Nao diga sem dados se chart_context ou data_context trouxer evidencia."
        )
    else:
        allowed_tools = ["bob_search", "rag_forensics", "final_answer"]
        # Pergunta financeira substantiva sem ticker (alocacao, estrategia):
        # o comite de experts pode deliberar de verdade — responder de memoria
        # com EXPERTS=N/A era o 'ele nao pergunta aos experts' cronico das demos.
        if looks_financially_substantive(raw):
            allowed_tools.insert(-1, "run_experts")
        cognitive_mode = "ANSWER_ONLY"
        information_need = "general_answer"
        answer_contract = (
            "Responda direto. Se faltar dado operacional, diga o que nao consegue provar. "
            "Nao chame market_scan nem submit_paper_order."
        )

    return {
        "cognitive_mode": cognitive_mode,
        "information_need": information_need,
        "allowed_tools": allowed_tools,
        "market_context_allowed": market_context_allowed,
        "scanner_allowed": scanner_allowed,
        "ticker_allowed": ticker_allowed,
        "ticket_allowed": paper_submit_allowed,
        "answer_contract": answer_contract,
    }


@dataclass(frozen=True)
class IntentParse:
    """Structured result from the deterministic intent parser.

    route is the graph route. intent is the semantic user intent. Keeping both
    fields prevents a general explanatory question from being mistaken for an
    executable market operation.
    """

    route: str
    intent: str
    action: str
    ticker: str = ""
    filters: dict[str, str | None] | None = None
    confidence: float = 0.0
    required_slots: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    entities: dict[str, Any] | None = None
    diary: bool = False
    pennylab: bool = False
    cognitive_mode: str = ""
    information_need: str = ""
    allowed_tools: list[str] | None = None
    market_context_allowed: bool = False
    scanner_allowed: bool = False
    ticker_allowed: bool = False
    ticket_allowed: bool = False
    answer_contract: str = ""
    raw_message: str = ""

    def to_plan(self) -> dict[str, Any]:
        plan = asdict(self)
        raw_message = str(plan.pop("raw_message", "") or "")
        contract = infer_cognitive_contract(
            raw_message,
            route=self.route,
            intent=self.intent,
            action=self.action,
            ticker=self.ticker,
        )
        plan.update(contract)
        plan["filters"] = self.filters or {}
        plan["entities"] = self.entities or {}
        plan["errors"] = []
        plan["intent_confidence"] = plan.pop("confidence")
        plan["intent_reasons"] = list(plan.pop("reasons"))
        plan["required_slots"] = list(plan["required_slots"])
        return plan


def _with_cognitive_contract(parsed: IntentParse, message: str) -> IntentParse:
    contract = infer_cognitive_contract(
        message,
        route=parsed.route,
        intent=parsed.intent,
        action=parsed.action,
        ticker=parsed.ticker,
    )
    return replace(parsed, raw_message=message, **contract)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_message(text: str) -> str:
    """Normaliza mensagem para busca de keywords: strip accents + lowercase."""
    return _strip_accents(text).lower()


def has_hint(message: str, hints: tuple[str, ...]) -> bool:
    """Verifica se mensagem contÃ©m algum hint.

    Hints multi-palavra ou >3 chars usam substring match.
    Hints <=3 chars usam word-boundary regex para evitar falsos positivos.
    """
    normalized = normalize_message(message)
    for hint in hints:
        normalized_hint = normalize_message(hint).strip()
        if not normalized_hint:
            continue
        if " " not in normalized_hint:
            # Use word boundaries for all single-word hints to prevent false positive substring matches
            # like "lista" matching "listada" or "scan" matching "scanner".
            pattern = rf"(?<![a-z0-9_]){re.escape(normalized_hint)}(?![a-z0-9_])"
            if re.search(pattern, normalized):
                return True
        elif normalized_hint in normalized:
            return True
    return False


def normalize_for_match(text: str) -> str:
    normalized = re.sub(r"\s+", " ", normalize_message(text))
    return normalized.strip()


COMMON_WORDS = {
    "OI",
    "EU",
    "ELA",
    "ELE",
    "ME",
    "SE",
    "UM",
    "UMA",
    "DE",
    "DA",
    "DO",
    "NO",
    "NA",
    "OS",
    "AS",
    "EM",
    "COM",
    "POR",
    "QUE",
    "NOS",
    "SUA",
    "FALE",
    "FALA",
    "SOBRE",
    "DEVO",
    "COMO",
    "PODE",
    "ISSO",
    "ESSE",
    "ESSA",
    "ALGO",
    "MAIS",
    "MENOS",
    "AQUI",
    "HOJE",
    "ONTEM",
    "PARA",
    "TODO",
    "TODA",
    "TUDO",
    "NADA",
    "VOCE",
    "MEU",
    "TEU",
    "SEU",
    "SIM",
    "NAO",
    "BOM",
    "BOA",
    "MAU",
    "MAL",
    "QUAL",
    "ACHO",
    "QUERO",
    "GOSTO",
    "SERA",
    "VAMOS",
    "OLHA",
    "VEJA",
    "ONDE",
    "QUEM",
    "QUER",
    "SABE",
    "TIPO",
    "VALE",
    "ALTO",
    "BAIXO",
    "CARO",
    "REAL",
    "DOLAR",
    "FORMA",
    "DIGA",
    "FACA",
    "BUSCA",
    "BUSCAR",
    "BUSQUE",
    "PESQUISA",
    "PESQUISE",
    "PROCURA",
    "PROCURE",
    "ENCONTRA",
    "ENCONTRE",
    "SUGIRA",
    "SUGERE",
    "SUGESTAO",
    "SUGESTOES",
    "MANDE",
    "MANDA",
    "MOSTRE",
    "MOSTRA",
    "LISTA",
    "PROXIMO",
    "PROXIMOS",
    "DIA",
    "DIAS",
    "SEMANA",
    "SEMANAS",
    "MES",
    "MESES",
    "ANO",
    "ANOS",
    "DINHEIRO",
    "TRAS",
    "ATRAS",
    "ESTE",
    "ESTES",
    "ESTA",
    "ESTAS",
    "FOCO",
    "FOCADO",
    "MERCADO",
    "CANADENSE",
    "CANADA",
    "THE",
    "AND",
    "FOR",
    "ARE",
    "BUT",
    "NOT",
    "YOU",
    "ALL",
    "CAN",
    "HAS",
    "HER",
    "WAS",
    "ONE",
    "OUR",
    "OUT",
    "BUY",
    "SELL",
    "GET",
    "SET",
    "HOW",
    "WHY",
    "WHO",
    "WHAT",
    "WHEN",
    "THIS",
    "THAT",
    "WITH",
    "FROM",
    "GOOD",
    "BAD",
    "TELL",
    "TALK",
    "SHOW",
    "MAKE",
    "TAKE",
    "GIVE",
    "ALSO",
    "JUST",
    "LIKE",
    "SOME",
    "THAN",
    "THEM",
    "THEN",
    "VERY",
    "IN",
    "TO",
    "US",
    "OF",
    "OR",
    "AN",
    "AT",
    "MY",
    "ON",
    "BE",
    "IT",
    "WE",
    "WOULD",
    "ORDER",
    "NEXT",
    "DAY",
    "DAYS",
    "WEEK",
    "WEEKS",
    "MONTH",
    "MONTHS",
    "YEAR",
    "YEARS",
    "MONEY",
    "PROFIT",
    "CPU",
    "RAM",
    "GPU",
    "API",
    "URL",
    "MCP",
    "LLM",
    "BOB",
    "F51",
    "RAG",
    "RL",
    "IA",
    "HUB",
    "SENSEI",
    "DEEPSEEK",
    "TSX",
    "NYSE",
    "NASDAQ",
    "B3",
    "SEC",
    "FED",
    "CLAUDE",
    "LLAMA",
    "LORA",
    "AI",
    "ML",
    "PDF",
    "CSV",
    "JSON",
    "HTML",
    "CSS",
    "SQL",
    "SSH",
    "HTTP",
    "CAD",
    "USD",
    "BRL",
    "EUR",
    "GBP",
    "JPY",
    "AUD",
    "CNY",
    "ETF",
    "ETFS",
    "GIC",
    "REIT",
    "TFSA",
    "RRSP",
    "RESP",
    "FHSA",
    "IRA",
    "ROTH",
    "401K",
    "IPO",
    "STOCK",
    "STOCKS",
    "SHORT",
    "TERM",
    "LONG",
    "PENNY",
    "PENNIES",
    "ITM",
    "OTM",
    "ATM",
    "XYZ",
    "ABC",
    "DELTA",
    "VEGA",
    "THETA",
    "GAMMA",
    "RHO",
    "CFO",
    "EPS",
    "PE",
    "RSI",
    "MACD",
    "SMA",
    "EMA",
    "VAR",
    "CVAR",
    "BOC",
    "CPI",
    "YOY",
    "MOM",
    "BPS",
    # Financial verdict / action words â€” not tickers
    "WAIT",
    "CASH",
    "DEBT",
    "SCAN",
    "SCANS",
    "FIND",
    "BEST",
    "MOST",
    "LOW",
    "HIGH",
    "GOLD",
    "OIL",
    "GAS",
    "TAX",
    "NEWS",
    "DATA",
    "LOSS",
    "GAIN",
    "COST",
    "FUND",
    "FUNDS",
    "LOAN",
    "LOANS",
    "SAVE",
    "SAFE",
    "BILL",
    "BILLS",
    "RENT",
    "RENTAL",
    "HOME",
    "HOUSE",
    "WORK",
    "JOB",
    "BANK",
    "CARD",
    "RATE",
    "RATES",
    "OPEN",
    "CLOSE",
    "PAST",
    "LAST",
    "OVER",
    "SAID",
    "HELP",
    "NEED",
    "WANT",
    "KNOW",
    "READ",
    "USED",
    "USING",
    "LOOK",
    "LIVE",
    "STOP",
    "DONE",
    "BASE",
    "CASE",
    "PLAN",
    "PART",
    # â”€â”€ Portuguese trade/finance words (NOT tickers) â”€â”€
    "ORDEM",
    "ORDENS",
    "COMPRA",
    "VENDA",
    "DIRETA",
    "DIRETO",
    "COMPRAR",
    "VENDER",
    "ATIVO",
    "ATIVOS",
    "PAPEL",
    "PAPEIS",
    "PRECO",
    "PREÃ‡O",
    "LIMITE",
    "ACAO",
    "ACOES",
    "VALOR",
    "VALORES",
    "CARTEIRA",
    "COTACAO",
    "COTAÃ‡AO",
    "RISCO",
    "ALVO",
    "META",
    "TESE",
    "LUCRO",
    "PREJUIZO",
}

FINANCIAL_KEYWORDS = (
    "analise",
    "analyze",
    "preco",
    "price",
    "acao",
    "acoes",
    "stock",
    "ticker",
    "comprar",
    "vender",
    "buy",
    "sell",
    "mercado",
    "market",
    "investir",
    "invest",
    "cotacao",
    "quote",
    "papel",
    "lucro",
    "dividendo",
    "risco",
    "retorno",
    "risk",
    "profile",
    "volatility",
    "volatilidade",
    "fundamental",
    "technical",
    "tecnico",
    "var",
    "sharpe",
    "beta",
    "macd",
    "rsi",
    "bollinger",
    "dividend",
    "yield",
    "revenue",
    "receita",
    "earning",
    "eps",
    "pe",
    "valuation",
    "avaliacao",
    "tendencia",
    "trend",
    "grafico",
    "chart",
)

DIARY_KEYWORDS = (
    "devo comprar",
    "devo vender",
    "devo investir",
    "diario de decisao",
    "me ajuda a decidir",
    "ajuda a decidir",
    "ajude a decidir",
    "vale a pena investir",
    "vale a pena comprar",
    "analise completa",
    "should i buy",
    "should i sell",
    "should i invest",
    "vale investir",
    "posso comprar",
    "posso investir",
)

INVESTMENT_ACTION_HINTS = (
    "invista",
    "investir",
    "comprar",
    "compre",
    "compra",
    "aplicar",
    "aplique",
    "alocar",
    "aloque",
    "diversificar",
    "diversifica",
    "quero acoes",
    "quero investir",
    "me de opcoes",
    "outros ativos",
    "outras acoes",
    "quero comprar",
    "sugira",
    "recomende",
    "indique",
)

SCAN_KEYWORDS = (
    "pesquise",
    "pesquisar",
    "scan",
    "busque",
    "buscar",
    "procure",
    "encontre",
    "encontrar",
    "varredura",
    "oportunidades no mercado",
    "acoes de",
    "stocks in",
    "empresas de",
    "me lista",
    "lista de",
    "penny stock",
    "penny stocks",
    "pennystock",
    "penny-stock",
    "small cap",
    "small caps",
    "small-cap",
    "small-caps",
    "microcap",
    "micro cap",
    "microcaps",
    "micro caps",
    "hoje",
    "agora",
    # English scan / discovery commands
    "find me",
    "find a",
    "look for",
    "search for",
    "suggest a",
    "recommend a",
    "recommend me",
    "show me",
)

SCOPE_KEYWORDS = (
    # Countries / exchanges
    "canadense",
    "canada",
    "canadian",
    "americano",
    "usa",
    "estados unidos",
    "tsx",
    "tsx venture",
    "venture exchange",
    "nasdaq",
    "nyse",
    "s&p",
    "sp500",
    # Sectors â€” Portuguese
    "tecnologia",
    "energia",
    "bancos",
    "saude",
    "setor",
    "financeiro",
    "industrial",
    "mercado",
    # Sectors â€” English (stress test: missing caused market_scan miss)
    "tech",
    "technology",
    "energy",
    "bank",
    "banks",
    "healthcare",
    "financial",
    "sector",
    "equity",
    "equities",
    "biotech",
    "cannabis",
    "marijuana",
    "uranium",
    "lithium",
    "gold",
    "silver",
    "copper",
    "miner",
    "mining",
    "oil",
    "gas",
    "crypto",
    "bitcoin",
    "blockchain",
    "ai",
    "artificial intelligence",
    "software",
    "fintech",
    "real estate",
    "reit",
    "defense",
    "aerospace",
    "semiconductor",
    "chips",
    "consumer",
    "retail",
    "auto",
    "ev",
    "electric vehicle",
    "dividend",
    "high yield",
)

VAGUE_FINANCIAL_HINTS = (
    "oportunidades",
    "opportunity",
    "opportunities",
    "me acha",
    "me indica",
    "me sugere",
    "sugira",
    "dica",
    "dicas",
    "tip",
    "tips",
    "todo tipo de investimento",
    "todo tipo de investimentos",
    "recommend me",
    "recommend",
    "recommended",
    "recomende",
    "recomendar",
    "recomendacao",
    "vale investir",
    "o que comprar",
    "what to buy",
    "qual compro",
    "qual eu compro",
    "qual comprar",
    "ganhar dinheiro",
    "dinheiro rapido",
    "essa semana",
    "esta semana",
    "best stock",
    "melhor acao",
    "melhores acoes",
    "make money",
    "profit",
    "lucro",
    "lucro rapido",
    "next 7 days",
    "within the next 7 days",
    "proximos 7 dias",
    # Termos adicionais para capturar consultas gerais de investimento
    "investimento",
    "investir",
    "conselho",
    "conseil",
    "proximos 15 dias",
    "proximos 30 dias",
    "proximos dias",
    "next 15 days",
    "next 30 days",
    "next few days",
    "canada",
    "canadense",
    "tsx",
    "venture exchange",
    "agressivo",
    "aggressive",
    "curto prazo",
    "short term",
    "carteira",
    "portfolio",
    "diversificar",
    "criptomoeda",
    "crypto",
    "bitcoin",
    "ethereum",
    "opcoes",
    "opcao",
    "options",
    "option",
    "etf",
    "etfs",
    "renda fixa",
    "gic",
    "bond",
    "bonds",
    "treasury",
    "treasuries",
    "reit",
    "reits",
    "imovel",
    "imoveis",
    "real estate",
    "dividendos",
    "dividend",
    "dividends",
    "alavancagem",
    "leverage",
    # English trading/scan triggers (stress test: 25/50 prompts were English)
    "volatile",
    "oversold",
    "overbought",
    "squeeze",
    "meme stock",
    "yolo",
    "all in",
    "day trade",
    "swing trade",
    "momentum",
    "breakout",
    "dip",
    "rip",
    "moon",
    "short squeeze",
    "insider buying",
    "options activity",
    "penny stock",
    "small cap",
    "small-cap",
    "microcap",
    "double",
    "cheap",
    "explode",
    "crash",
    "paper training",
    "paper account",
    "paper trade",
    "paper trading",
    "quick trade",
    "quick trades",
    "fast trade",
    "fast trades",
    "training",
    "train",
    "treino",
    "treinamento",
)

DIRECT_UNSCOPED_RECOMMENDATION_PATTERNS = (
    r"\bwhat\s+(?:should|do)\s+i\s+buy\b",
    r"\bwhat\s+to\s+buy\b",
    r"\bbest\s+stock\b",
    r"\bone\s+ticker\b",
    r"\btell\s+me\s+what\s+to\s+buy\b",
    r"\bignore\s+risk\s+controls\b",
    r"\brecommend(?:\s+me)?\b",
    r"\bme\s+recomenda\b",
    r"\brecomenda(?:r|cao)?\b",
    r"\bme\s+indica\b",
    r"\bdica(?:s)?\b",
    r"\bo\s+que\s+comprar\b",
    r"\bqual\s+(?:eu\s+)?compro\b",
)

DECISIVE_TRADE_HINTS = (
    "what should i buy",
    "what stock would you recommend",
    "what would you recommend",
    "recommend me to buy",
    "give me the best buy",
    "give me an order",
    "best trade",
    "i want to make a profit",
    "make profit",
    "best stock to buy",
    "give me a trade",
    "give me a buy",
    "pick the best",
    "what to buy",
    "o que comprar",
    "qual comprar",
    "qual eu compro",
    "me da uma ordem",
    "me de uma ordem",
    "melhor compra",
    "melhor trade",
    "quero lucrar",
    "quero ganhar",
    "recomendar para comprar",
)

# "escolhe/escolha" so e decisive quando existe contexto de ordem/trade/
# ticker/scan/treino (composite). Sozinho ("escolhe um produto pra mim") e um
# pedido de sugestao de produto/estrategia sem ticker -> o Bob responde
# framework/produto na rota general (action=answer), sem scanner.
ESCOLHE_PICK_HINTS = (
    "escolhe",
    "escolha",
    "escolhe pra mim",
    "escolhe para mim",
    "escolha pra mim",
    "escolha para mim",
)

# Vocabulario que marca contexto de execucao de mercado (ordem/trade/ticker/
# scan/treino). Usado (a) para liberar "escolhe/escolha" como decisive apenas
# nesse contexto e (b) para excluir da sugestao de produto quem fala de
# operar/treinar/escaneiar/acionar papel.
_MARKET_EXECUTION_CONTEXT_HINTS = (
    # ordem / order
    "ordem",
    "ordens",
    "oredem",
    "oredens",
    "order",
    "orders",
    "submit",
    "send",
    # trade / operacao
    "trade",
    "trades",
    "trading",
    "transacao",
    "transacoes",
    "compra",
    "comprar",
    "compre",
    "venda",
    "vender",
    "operar",
    "operacao",
    "operacoes",
    "posicao",
    "posicoes",
    "entrada",
    "entara",
    "saida",
    "stop loss",
    "stop",
    # acao/ticker — escolher papel, nao produto/estrategia
    "acao",
    "acoes",
    "stock",
    "stocks",
    "ticker",
    "tickers",
    "acao de centavo",
    "acoes de centavo",
    # horizonte de trade
    "1 hora",
    "uma hora",
    "one hour",
    "4 horas",
    "quatro horas",
    "intraday",
    "scalp",
    "rapida",
    "rapidas",
    "rapido",
    "rapidos",
    # scan / discovery
    "scan",
    "scanear",
    "screen",
    "screener",
    "shortlist",
    "pesquise",
    "pesquisar",
    "pesquisa",
    "busque",
    "busca",
    "buscar",
    "procure",
    "procura",
    "encontre",
    "encontra",
    "encontrar",
    "oportunidades",
    "opurtunidades",
    "opportunity",
    "opportunities",
    "penny stock",
    "penny stocks",
    "pennystock",
    "small cap",
    "small caps",
    "small-cap",
    "small-caps",
    "microcap",
    "microcaps",
    "micro cap",
    "micro caps",
    "mini cap",
    "mini caps",
    "me lista",
    "lista de",
    "acoes de",
    "stocks in",
    # treino / paper
    "treino",
    "treinar",
    "treinamento",
    "training",
    "train",
    "paper",
    "simulado",
    "aprendizagem",
)

# Verbos de pedido de sugestao de produto/estrategia de investimento.
_PRODUCT_SUGGESTION_VERB_HINTS = (
    "escolhe",
    "escolha",
    "escolher",
    "escolhe pra mim",
    "escolhe para mim",
    "escolha pra mim",
    "escolha para mim",
    "sugere",
    "sugira",
    "sugerir",
    "me sugere",
    "me sugira",
    "recomenda",
    "recomende",
    "recomendar",
    "me recomenda",
    "me indica",
    "me indique",
    "me diga um produto",
    "me diga o produto",
    "me da um produto",
    "me de um produto",
    "me de uma dica",
    "me dê uma dica",
    "me da uma dica",
    "me dá uma dica",
    "de uma dica",
    "dê uma dica",
    "da uma dica",
    "dá uma dica",
    "dica",
    "dicas",
    "me de uma ideia",
    "me dê uma ideia",
    "me da uma ideia",
    "me dá uma ideia",
    "ideia de investimento",
    "ideias de investimento",
    "onde investir",
    "como investir",
    "onde aplicar",
    "como aplicar",
    "onde colocar",
    "o que comprar",
    "qual investimento",
    "qual o melhor investimento",
    "o que fazer com",
)

# Substantivos que nomeiam o alvo da sugestao: produto/estrategia/framework.
_PRODUCT_STRATEGY_NOUN_HINTS = (
    "produto",
    "produtos",
    "estrategia",
    "estrategias",
    "framework",
    "carteira",
    "investimento",
    "investimentos",
    "alocacao",
    "alocação",
)

# Perfil de risco explícito na mensagem.
_RISK_PROFILE_HINT_WORDS = (
    "risco",
    "riscos",
    "risk",
    "risks",
    "risky",
    "arriscado",
    "conservador",
    "conservadora",
    "conservative",
    "moderado",
    "moderada",
    "moderate",
    "agressivo",
    "agressiva",
    "aggressive",
    "arrojado",
    "arrojada",
)

_AMOUNT_HINT_PATTERN = re.compile(
    r"(?:[$]\s*\d|\b(?:cad|usd|brl)\s*\d|\b\d[\d.,]*(?:\.\d+)?\s*(?:cad|usd|brl)\b"
    r"|\b\d[\d.,]*\s*(?:k|mil|milhao|milhoes|reais)\b)"
)

ANOTHER_TRADE_HINTS = (
    "another recommendation",
    "another one",
    "next recommendation",
    "second option",
    "give me another",
    "what else",
    "show me the next candidate",
    "next candidate",
    "different stock",
    "different ticker",
    "another stock",
    "another trade",
    "outra recomendacao",
    "outra recomendaÃ§Ã£o",
    "outro",
    "outra",
    "mais uma",
    "mais um",
    "proxima recomendacao",
    "prÃ³xima recomendaÃ§Ã£o",
    "proximo",
    "prÃ³ximo",
    "segunda opcao",
    "segunda opÃ§Ã£o",
    "me da outra",
    "me dÃª outra",
    "me de outro",
    "me da outro",
    "me arruma outro",
    "qual o proximo",
    "qual o prÃ³ximo",
    "tem mais",
    "quero outro",
)

EDUCATIONAL_OR_RISK_CONTEXT_HINTS = (
    "how should",
    "how do",
    "how would",
    "what happens",
    "what red flags",
    "what is the risk",
    "what should i check",
    "explain",
    "assess",
    "separate",
    "when is",
    "why",
    "could",
    "compare",
    "portfolio is",
    "my portfolio",
    "risk profile",
    "concentration",
    "leverage",
    "fraud",
    "scam",
    "red flag",
    "financial statements",
    "value trap",
    "rebalancing",
    "allocation",
    "como devo",
    "como funciona",
    "explique",
    "quais ferramentas",
    "qual ferramenta",
    "que ferramentas",
    "ferramentas que voce usa",
    "ferramentas que vc usa",
    "what tools",
    "which tools",
    "what do you use",
    "quais riscos",
    "qual o risco",
    "arbitragem",
    "alavancagem",
    "opcao",
    "opcoes",
    "options",
    "portfolio",
    "portfÃ³lio",
    "hedge",
    "hedging",
    "fluxo de caixa",
    "accounting",
    "contabil",
    "contabilidade",
    "correlaÃ§Ã£o",
    "correlacao",
)

QUESTION_HINTS = (
    "?",
    "qual",
    "quais",
    "que",
    "como",
    "o que",
    "what",
    "which",
    "how",
    "do you",
    "you use",
    "voce",
    "vc",
)

CAPABILITY_HINTS = (
    "ferramenta",
    "ferramentas",
    "tools",
    "tooling",
    "stack",
    "fontes",
    "sources",
    "data source",
    "provedor",
    "provider",
    "metodologia",
    "metodo",
    "method",
    "processo",
    "workflow",
    "pipeline",
    "usa para",
    "usa pra",
    "voce usa",
    "vc usa",
    "you use",
    "do you use",
)

RESEARCH_DOMAIN_HINTS = (
    "pesquisar",
    "pesquisa",
    "research",
    "screen",
    "scanner",
    "scan",
    "oportunidade",
    "opurtunidade",
    "opportunities",
    "penny stock",
    "penny stocks",
    "pennystock",
    "penny-stock",
    "microcap",
    "micro cap",
    "mini cap",
    "mini-cap",
    "small cap",
    "small caps",
)

PENNY_ASSET_HINTS = (
    "penny stock",
    "penny stocks",
    "pennystock",
    "penny-stock",
    "microcap",
    "micro cap",
    "microcaps",
    "micro caps",
    "mini cap",
    "mini-cap",
    "mini caps",
    "mini-caps",
    "acao de centavo",
    "acoes de centavo",
)

# ---------------------------------------------------------------------------
# Complex Finance Detection â€” prevents scanner misroute for advisory questions
# ---------------------------------------------------------------------------

COMPLEX_FINANCE_HINTS = (
    # Intent names and literal phrases
    "macro thesis",
    "macro_thesis",
    "personal finance",
    "personal_finance",
    "capital allocation",
    "capital_allocation",
    "asset allocation",
    "asset_allocation",
    "real estate vs markets",
    "real_estate_vs_markets",
    "business capital",
    "business_capital",
    "fraud risk",
    "fraud_risk",
    "education investment",
    "education_investment",
    # Decision framework / analytical structure
    "decision framework",
    "decision matrix",
    "scenario analysis",
    "build a thesis",
    "build a framework",
    "build a ranked",
    "ranked decision",
    "ranked matrix",
    "expected return",
    "downside risk",
    "upside case",
    "downside case",
    "base case",
    # Real estate vs markets
    "cap rate",
    "cash-on-cash",
    "cash on cash",
    "vacancy risk",
    "vacancy stress",
    "mortgage rate",
    "mortgage stress",
    "maintenance reserve",
    "rental property",
    "rental income",
    "rental vs",
    "property vs",
    # Macro thesis / strategy
    "secular trend",
    "secular opportunity",
    "overvaluation",
    "hype zone",
    "hype zones",
    "position sizing",
    "rebalancing discipline",
    "picks-and-shovels",
    "picks and shovels",
    "ai infrastructure",
    "investment thesis",
    "ai investment thesis",
    "macro thesis",
    "portfolio allocation",
    "portfolio allocations",
    "allocation math",
    # Capital allocation / personal finance
    "capital allocation",
    "family capital",
    "emergency reserve",
    "reversibility",
    "family stability",
    "liquidity reserve",
    "time-to-cashflow",
    "time to cashflow",
    "debt threshold",
    "high-interest debt",
    "high interest debt",
    "equipment for a side business",
    "paying debt",
    "funding education",
    "pay debt",
    "keep it in cash",
    "keep in cash",
    "repay debt",
    "pay off debt",
    "paying off debt",
    "hold cash",
    "keep as cash",
    "or pay debt",
    "debt or invest",
    "cash or invest",
    "should i pay",
    "should i keep",
    "or invest in",
    "invest or pay debt",
    # Quantitative structure requests
    "quantitative framework",
    "quantitative threshold",
    "concentration risk",
    "opportunity cost",
    "tax drag",
    "liquidity premium",
    # Multi-factor evaluation phrasing
    "evaluate whether",
    "evaluating whether",
    "deciding between",
    "compare investment",
    "comparing investment",
)

# Additional signal: structural phrases indicating analytical/framework requests
_COMPLEX_FINANCE_STRUCTURAL_PATTERNS = (
    r"\bbuild\s+(?:a|the)\s+(?:thesis|framework|decision|ranked|comparison|matrix|model)\b",
    r"\bseparate\s+(?:real|hype|secular|opportunity)\b",
    r"\binclude\s+(?:leverage|vacancy|maintenance|taxes|liquidity|concentration|cap rate|mortgage)\b",
)


def detect_etf_comparison_intent(message: str) -> bool:
    normalized = normalize_message(message)
    if not re.search(r"\b(compare|comparison|versus|vs|which one|which would)\b", normalized):
        return False
    upper_symbols = set(re.findall(r"\b([A-Z]{2,5})\b", message or ""))
    etf_symbols = {
        "SPY",
        "VOO",
        "VTI",
        "IVV",
        "SCHD",
        "QQQ",
        "QQQM",
        "VXUS",
        "VEU",
        "XIU",
        "XIC",
        "VCN",
        "VFV",
        "XUU",
        "VSP",
        "XUH",
        "ZAG",
        "XBB",
    }
    return len(upper_symbols & etf_symbols) >= 2


def detect_portfolio_concentration_intent(message: str) -> bool:
    normalized = normalize_message(message)
    has_concentration = bool(
        re.search(
            r"\b(concentrated(?:\s+position)?|40\s*%|40 percent|single[-\s]?stock)\b",
            normalized,
        )
    )
    has_portfolio = bool(re.search(r"\b(portfolio|tax bill|diversify|triggering)\b", normalized))
    return has_concentration and has_portfolio


# Patterns to detect when a user explicitly tells us NOT to scan.
# "scan" appearing inside a negative construction must not trigger market_scan.
_NEGATIVE_SCAN_PATTERNS = (
    r"\bdo\s+not\s+scan\b",
    r"\bdon'?t\s+scan\b",
    r"\bno\s+scan(?:ning)?\b",
    r"\bstop\s+scan(?:ning)?\b",
    r"\bnever\s+scan\b",
    r"\bplease\s+don'?t\s+scan\b",
    r"\bwithout\s+scan(?:ning)?\b",
)


def detect_negative_scan_instruction(message: str) -> bool:
    """Return True when the user explicitly asks NOT to scan.

    A message like "Do not scan China stocks" contains the word "scan"
    but must not trigger the market scanner.
    """
    if not message or not message.strip():
        return False
    normalized = normalize_message(message)
    return any(re.search(p, normalized) for p in _NEGATIVE_SCAN_PATTERNS)


def detect_capital_allocation_intent(message: str) -> bool:
    """Detect prompts comparing multiple uses of capital (cash, debt, ETF, trade).

    This is a subset of complex finance that specifically deals with personal
    capital allocation decisions: should I keep cash, pay debt, invest in ETF,
    or make a short-term trade? The presence of multiple capital-use options
    means this is an advisory question, not a market scan.
    """
    if not message or not message.strip():
        return False
    # If the user mentions 2+ capital-use domains, it's an allocation decision.
    _CAPITAL_USE_HINTS = (
        r"\bpay\s+(?:off\s+)?debt\b",
        r"\bkeep\s+(?:it\s+)?in\s+cash\b",
        r"\bhold\s+cash\b",
        r"\binvest\s+in\s+(?:an?\s+)?ETFs?\b",
        r"\bETFs?\b",
        r"\bemergency\s+(?:fund|reserve|savings)\b",
        r"\brepay\s+(?:debt|loan)\b",
        r"\bcash\b.*\bETF\b",
        r"\bETF\b.*\bcash\b",
        r"\bdebt\b.*\b(?:invest|trade|stock)\b",
        r"\b(?:invest|trade|stock)\b.*\bdebt\b",
        r"\bkeep\s+(?:it\s+)?as\s+cash\b",
        r"\bcash\s*,?\s*invest\b",
        r"\bcapital\s+alloc",
        # PT: reserva de emergencia e comparacao reserva vs ETF sao decisoes de
        # alocacao de capital, nao scan ("reserva vs etf", "reserva de
        # emergencia vs investir em etf").
        r"\breserva\s+de\s+emergencia\b",
        r"\breserva\b.*\bvs\b.*\betfs?\b|\betfs?\b.*\bvs\b.*\breserva\b",
    )
    normalized = normalize_message(message)
    allocation_action = re.search(
        r"\b(?:allocate|allocating|decid(?:e|ing)|choose|split|divide)\b",
        normalized,
        re.IGNORECASE,
    )
    allocation_categories = (
        r"\bemergency\s+(?:cash\s+)?(?:fund|reserve|savings)\b|\bcash\b",
        r"\bdebt\b|\bloan\b|\bcredit\s+card\b",
        r"\betfs?\b|\binvest(?:ing|ment)?\b|\bportfolio\b",
        r"\bside[-\s]?business\b|\bbusiness\b|\bequipment\b",
        r"\beducation\b|\bskills?\b|\bcourse\b",
    )
    category_count = sum(
        1 for pattern in allocation_categories if re.search(pattern, normalized, re.IGNORECASE)
    )
    has_amount_or_household_context = bool(
        re.search(r"\bcad\s*\d|\busd\s*\d|\b\d[\d,]*(?:\.\d+)?\s*(?:cad|usd)\b", normalized)
        or re.search(r"\b(?:family|household|income|salary|work income)\b", normalized)
    )
    if allocation_action and category_count >= 2 and has_amount_or_household_context:
        return True

    allocation_with_amount = bool(
        re.search(r"\b(?:allocate|allocation|portfolio allocation)\b", normalized, re.IGNORECASE)
        and re.search(
            r"(?:[$â‚¬Â£]\s*\d|cad\s*\d|usd\s*\d|\b\d[\d,]*(?:\.\d+)?\s*(?:cad|usd)\b)",
            normalized,
            re.IGNORECASE,
        )
        and re.search(
            r"\b(?:risk tolerance|percentages?|tickers?|portfolio|capital|invest)\b",
            normalized,
            re.IGNORECASE,
        )
    )
    if allocation_with_amount:
        return True

    # PT/EN small-ticket apply: "tenho 100 CAD para investir" is allocation,
    # not a 2-week US/Canada discovery scan. Discovery verbs and mini-cap
    # / decisive trade stay on the scanner.
    monetary = bool(
        re.search(
            r"(?:[$]\s*\d|\bcad\s*\d|\busd\s*\d|\b\d[\d,]*(?:\.\d+)?\s*(?:cad|usd)\b)",
            normalized,
            re.IGNORECASE,
        )
    )
    apply_verb = bool(
        re.search(
            r"\b(?:investir|invista|aplicar|aplique|alocar|aloque|invest(?:ing|ment)?)\b",
            normalized,
            re.IGNORECASE,
        )
    )
    discovery = bool(
        re.search(
            r"\b(?:encontre|procure|busque|pesquise|find|search|shortlist|mini\s*cap|small[- ]cap)\b",
            normalized,
            re.IGNORECASE,
        )
    )
    if (
        monetary
        and apply_verb
        and not discovery
        and not detect_ticker(message)
        and not has_hint(message, PENNY_ASSET_HINTS)
        and not detect_decisive_trade_intent(message)
    ):
        return True

    matches = sum(1 for p in _CAPITAL_USE_HINTS if re.search(p, normalized, re.IGNORECASE))
    return matches >= 2


_SUBSTANTIVE_FINANCIAL_TOKENS = (
    "aloc",
    "invest",
    "reserva",
    "divid",
    "etf",
    "estrategia",
    "estratégia",
    "portfolio",
    "portfólio",
    "aposent",
    "renda fixa",
    "juros",
    "tesouro",
    "ação",
    "acoes",
    "allocate",
    "retirement",
    "savings",
    "dividend",
)


def looks_financially_substantive(message: str) -> bool:
    """Conservador: a pergunta fala de alocacao/estrategia/investimento?

    detect_complex_finance_intent erra para perguntas de alocacao (medido:
    'alocar 25.000 CAD entre reserva, dividas, ETFs' classifica False). Este
    detector cobre o caso com tokens simples e e usado para liberar a
    deliberacao do comite de experts na rota sem ticker — nunca para liberar
    ordem nem acesso a dado de mercado.
    """
    lowered = (message or "").lower()
    return any(token in lowered for token in _SUBSTANTIVE_FINANCIAL_TOKENS)


def detect_complex_finance_intent(message: str) -> bool:
    """Detect if a message asks for a complex financial framework/advisory answer.

    This is the PRIMARY gate that prevents complex finance questions from being
    misrouted into the market scanner. A question is complex finance if it:
    - Contains 2+ complex finance hints, OR
    - Contains 1+ complex finance hint AND a structural pattern, OR
    - Contains a structural pattern that requests building a framework/thesis.

    Returns False if the message explicitly contains a ticker or scan command.
    """
    if not message or not message.strip():
        return False
    if _has_inline_ticker_like_token(message) and is_investment_thesis_request(message):
        return False
    # If there's an explicit ticker WITH a market suffix (.TO, .SA, .V) or a
    # ticker-with-digit pattern (PETR4), this is ticker analysis, not complex finance.
    # We do NOT use the full detect_ticker() because its crypto-pair regex
    # false-positives on finance vocabulary (e.g., "time-to-cashflow" â†’ TIME-TO).
    if re.search(r"\b[A-Za-z]{1,6}\d{0,2}\.(?:SA|TO|V)\b", message, re.IGNORECASE):
        return False
    if re.search(r"\b[A-Z]{1,5}\d{1,2}\b", message):
        return False
    # Standalone uppercase words (2-5 chars) that look like tickers â€” but exclude
    # common finance/domain acronyms that appear in complex finance discussions.
    _COMPLEX_FINANCE_ACRONYMS = {
        "AI",
        "ETF",
        "CAD",
        "USD",
        "EUR",
        "GBP",
        "TSX",
        "NYSE",
        "RRSP",
        "TFSA",
        "RESP",
        "GIC",
        "REIT",
        "IPO",
        "ESG",
        "PE",
        "VC",
        "GDP",
        "CPI",
        "FED",
        "SEC",
        "CFO",
        "BOB",
        "ROI",
        "IRR",
        "NPV",
        "DCF",
        "EPS",
    }
    _upper_words = set(re.findall(r"\b([A-Z]{2,5})\b", message))
    _potential_tickers = _upper_words - COMMON_WORDS - _COMPLEX_FINANCE_ACRONYMS
    if _potential_tickers:
        return False
    # If the user explicitly requests a scan, honor it â€” unless the
    # "scan" is part of a negative instruction ("do not scan").
    # Exception: "give me" and "recommend" are too generic â€” they match
    # complex finance prompts like "Give me a framework". Only treat them
    # as scan commands when paired with financial trading hints.
    _generic_hints = {"give me", "recommend", "suggest"}
    _scan_hint = has_hint(message, SCAN_COMMAND_HINTS)
    _is_generic_only = _scan_hint and all(
        h not in SCAN_COMMAND_HINTS or h in _generic_hints
        for h in [h for h in SCAN_COMMAND_HINTS if h in message.lower()]
    )
    if _is_generic_only:
        _scan_hint = has_hint(
            message, ("scan", "screen", "find", "search", "look for", "shortlist")
        )
    if _scan_hint and not detect_negative_scan_instruction(message):
        return False

    normalized = normalize_message(message)
    if detect_capital_allocation_intent(message):
        return True

    hint_count = sum(1 for h in COMPLEX_FINANCE_HINTS if normalize_message(h) in normalized)
    has_structural = any(
        re.search(pattern, normalized) for pattern in _COMPLEX_FINANCE_STRUCTURAL_PATTERNS
    )

    if hint_count >= 2:
        return True
    if hint_count >= 1 and has_structural:
        return True
    return bool(has_structural and len(normalized.split()) > 15)


SCAN_COMMAND_HINTS = (
    # Portuguese
    "me indica",
    "me indique",
    "indica",
    "indique",
    "me sugere",
    "me sugira",
    "sugere",
    "sugira",
    "me da uma dica",
    "me de uma dica",
    "me da dica",
    "me de dica",
    "da uma dica",
    "de uma dica",
    "da dica",
    "de dica",
    "busque",
    "busca",
    "buscar",
    "pesquise",
    "pesquisa",
    "procure",
    "procura",
    "encontre",
    "encontra",
    "sugestao",
    "sugestoes",
    "scan",
    "screen",
    "shortlist",
    "lista",
    "liste",
    "me lista",
    "oportunidades",
    "opurtunidades",
    # English â€” stress test revealed 50% of prompts were English and missed
    "find me",
    "find a",
    "find the",
    "look for",
    "search for",
    "recommend",
    "suggest",
    "show me",
    "give me",
    "pick",
    "choose",
    "scan for",
    "screen for",
    "find and",
    "pick a",
    "select a",
    "paper trade",
    "paper trading",
    "apply",
    "execute",
    "training",
    "train",
    "treino",
    "treinamento",
    "trade",
    "trades",
    "trading",
)

TICKER_REQUIRED_ANALYSIS_HINTS = (
    "analise",
    "analisar",
    "analysis",
    "analyze",
    "veredito",
    "verdict",
    "rodar pennylab",
    "run pennylab",
)

REFERENTIAL_TICKER_HINTS = (
    "este ticker",
    "esse ticker",
    "neste ticker",
    "nesse ticker",
    "this ticker",
    "current ticker",
    "este ticket",
    "esse ticket",
    "neste ticket",
    "nesse ticket",
    "this ticket",
    "current ticket",
    "este ativo",
    "esse ativo",
    "neste ativo",
    "nesse ativo",
    "ativo atual",
    "esta acao",
    "essa acao",
    "nesta acao",
    "nessa acao",
    "esta aÃ§Ã£o",
    "essa aÃ§Ã£o",
    "nesta aÃ§Ã£o",
    "nessa aÃ§Ã£o",
    "this stock",
    "current stock",
    "this asset",
    "current asset",
)

REFERENTIAL_ASSET_STATUS_HINTS = (
    "travado",
    "travada",
    "stuck",
    "halted",
    "parado",
    "parada",
    "congelado",
    "congelada",
    "subindo",
    "caindo",
    "despencando",
    "pump",
    "dump",
    "fraude",
    "fraud",
    "risco",
)

REFERENTIAL_ASSET_NOUNS = (
    "ticker",
    "ticket",
    "ativo",
    "acao",
    "aÃ§Ã£o",
    "stock",
    "asset",
)


CACHE_TTL = 30.0  # segundos

_ticker_cache: dict[str, tuple[float, str]] = {}
_EXPLICIT_TICKER_COMMAND_RE = re.compile(
    r"^\s*TICKER\s+([A-Z0-9][A-Z0-9.\-]{0,11})\s*:",
    re.IGNORECASE,
)


def _get_cached(key: str) -> str | None:
    import time

    entry = _ticker_cache.get(key)
    if entry and (time.time() - entry[0]) < CACHE_TTL:
        return entry[1]
    _ticker_cache.pop(key, None)
    return None


def _set_cache(key: str, value: str) -> None:
    import time

    _ticker_cache[key] = (time.time(), value)
    # Evitar crescimento infinito
    if len(_ticker_cache) > 500:
        stale = [k for k, v in _ticker_cache.items() if (time.time() - v[0]) > CACHE_TTL]
        for k in stale:
            _ticker_cache.pop(k, None)


def _extract_explicit_ticker_command(message: str) -> str:
    """Return ticker from cockpit-generated commands like ``TICKER DIBS: ...``."""
    match = _EXPLICIT_TICKER_COMMAND_RE.match(message or "")
    if not match:
        return ""
    ticker = match.group(1).upper()
    return ticker if _is_valid_ticker(ticker) else ""


def _is_valid_ticker(ticker: str) -> bool:
    """Validate a ticker string: 1-8 chars, contains at least one letter or digit."""
    if not ticker or not isinstance(ticker, str):
        return False
    t = ticker.strip()
    return 1 <= len(t) <= 8 and bool(re.search(r"[A-Za-z0-9]", t))


def detect_ticker(message: str) -> str:
    """
    Return the most likely ticker in a message, or an empty string.

    Regras de sufixo:
      - .TO  â†’ TSX (CanadÃ¡) â†’ preservado
      - .SA  â†’ B3 (Brasil)  â†’ preservado
      - .V   â†’ TSX Venture (CanadÃ¡) â†’ preservado
      - sem sufixo â†’ NYSE/NASDAQ (EUA)
    """
    if not message:
        return ""

    raw = message.strip()

    # â”€â”€ Genie click: "TICKER USIO:" or "TICKER DIBS:" â†’ extract immediately â”€â”€
    import re as _re

    ticker_prefix = _re.match(r"^TICKER\s+([A-Z]{1,5}(?:\.[A-Z]{2})?)\s*:", raw)
    if ticker_prefix:
        return ticker_prefix.group(1).upper()

    if detect_broker_status_intent(raw):
        return ""

    cache_key = f"ticker:{raw}"
    cached = _get_cached(cache_key)
    if cached is not None:
        debug_logger.trace(MODULE_INTENT, "detect_ticker cached hit", result=cached)
        return cached

    normalized = _strip_accents(raw)
    lower = normalized.lower()
    if "ibkr" in lower:
        broker_platform_context = any(
            hint in lower
            for hint in (
                "ibkr paper",
                "paper na ibkr",
                "paper ibkr",
                "broker",
                "corretora",
                "tws",
                "trader workstation",
                "ib gateway",
                "7497",
                "ordem paper",
                "dados do ibkr",
                "dados da ibkr",
                "conta ibkr",
                "ibkr conectado",
                "conectado no ibkr",
                "paper trading",
                "treinamento paper",
                "treino paper",
            )
        )
        explicit_ibkr_stock_context = bool(
            re.search(
                r"\b(?:ibkr\s+(?:stock|shares|equity|ticker)|ticker\s+ibkr|"
                r"(?:acao|acoes|analise|analyze)\s+(?:da\s+)?ibkr)\b",
                lower,
            )
        )
        if broker_platform_context and not explicit_ibkr_stock_context:
            return ""
    debug_logger.trace(MODULE_INTENT, "detect_ticker start", message_preview=message[:80])
    candidates: list[tuple[str, int, int]] = []

    # 1. Sufixos de mercado EXPLÃCITOS (.SA, .TO, .V) â€” prioridade MÃXIMA
    #    Captura padrÃµes como: ENB.TO, PETR4.SA, HIVE.V, XYZ.V
    suffix_matches = re.findall(
        r"\b([A-Za-z]{1,6}\d{0,2}\.(?:SA|TO|V))\b",
        raw,
        re.IGNORECASE,
    )
    for match in suffix_matches:
        upper = match.upper()
        # Preserva o sufixo! NÃ£o limpa.
        candidates.append((upper, 100, len(upper)))

    # 2. Sufixos de mercado com formato alternativo (ex: "ENB.TO" escrito como "ENB.TO")
    #    Regex adicional para capturar .SA e .TO mesmo apÃ³s caracteres especiais
    alt_suffix_matches = re.findall(
        r"\b([A-Za-z]{1,6}\d{0,2})\.(SA|TO|V)\b",
        raw,
        re.IGNORECASE,
    )
    for base, suffix in alt_suffix_matches:
        full = f"{base.upper()}.{suffix.upper()}"
        # Evitar duplicatas
        if not any(c[0] == full for c in candidates):
            candidates.append((full, 100, len(full)))

    # 3. Ticker com dÃ­gitos (ex: PETR4, VALE3) â€” sem sufixo, prioridade alta
    digit_matches = re.findall(r"\b([A-Za-z]{1,5}\d{1,2})\b", raw)
    for match in digit_matches:
        upper = match.upper()
        # Não sobrescrever se já tem sufixo explícito
        if upper not in COMMON_WORDS and not any(
            c[0] == upper or c[0].startswith(upper + ".") for c in candidates
        ):
            candidates.append((upper, 90, len(upper)))

    # 3.5 Ticker numÃ©rico curto (ex: 6M, 88E, 3M) â€” comum em microcaps/OTC
    # BUT: reject monetary amounts.  "5K", "10k", "2M", "500B" are NOT tickers.
    _AMOUNT_SUFFIXES = re.compile(r"^\d{1,4}[KkMmBbHhDdWwSs]$")  # 4H=4hours, 2W=2weeks etc.
    num_prefix_matches = re.findall(r"\b(\d{1,2}[A-Za-z]{1,5})\b", raw)
    for match in num_prefix_matches:
        upper = match.upper()
        if (
            upper not in COMMON_WORDS
            and not any(c[0] == upper for c in candidates)
            and not _AMOUNT_SUFFIXES.match(upper)
        ):
            candidates.append((upper, 80, len(upper)))

    # 4. Ãndices (^BVSP, ^GSPC)
    idx_matches = re.findall(r"(\^[A-Za-z]+)\b", raw)
    for match in idx_matches:
        upper = match.upper()
        if not any(c[0] == upper for c in candidates):
            candidates.append((upper, 85, len(upper)))

    # 5. Crypto pairs (BTC-USD, ETH-BTC)
    crypto_matches = re.findall(r"\b([A-Za-z]{2,5}-[A-Za-z]{2,5})\b", raw)
    for match in crypto_matches:
        upper = match.upper()
        parts = upper.split("-")
        currencies = {
            "USD",
            "BRL",
            "EUR",
            "CAD",
            "GBP",
            "JPY",
            "AUD",
            "CNY",
            "BTC",
            "ETH",
            "USDT",
            "USDC",
            "SOL",
        }
        non_crypto_common = (COMMON_WORDS - currencies) | {
            "TIME",
            "TO",
            "FOR",
            "AND",
            "OR",
            "IN",
            "ON",
            "AT",
            "BY",
            "WITH",
            "CASH",
            # Financial compound terms â€” not tickers
            "SMALL",
            "LARGE",
            "MID",
            "CAP",
            "CAPS",
            "MICRO",
            "NANO",
            "TERM",
            "LONG",
            "RANGE",
            "SIDE",
        }
        if any(p in non_crypto_common for p in parts):
            continue
        if upper not in COMMON_WORDS and not any(c[0] == upper for c in candidates):
            candidates.append((upper, 80, len(upper)))

    # 6. Ticker explÃ­cito (ex: "ticker: AAPL", "papel: PETR4")
    #    The keyword needs its own word boundary: without it "ativos" matches
    #    "ativo" and the leftover "s" is captured as a ticker (reproduced
    #    2026-08-23: "apenas ativos listados" -> ticker "S").
    explicit_symbol_matches = re.findall(
        r"\b(?:ticker|symbol|papel|ativo|acao)\b\s*[:=-]?\s*([A-Za-z]{1,5}\d{0,2})\b",
        normalized,
        re.IGNORECASE,
    )
    for match in explicit_symbol_matches:
        upper = match.upper()
        if upper not in COMMON_WORDS and not any(c[0] == upper for c in candidates):
            candidates.append((upper, 65, len(upper)))

    # 7. Palavras em maiÃºsculas (ex: AAPL, MSFT, NVDA) â€” sem sufixo, prioridade mÃ©dia
    #    Capturado no texto original 'raw' para respeitar a capitalizaÃ§Ã£o do usuÃ¡rio,
    #    evitando falsos positivos de palavras comuns e preposiÃ§Ãµes.
    upper_matches = re.findall(r"\b([A-Z]{2,5})\b", raw)
    for match in upper_matches:
        if match not in COMMON_WORDS and not any(
            c[0] == match or c[0].startswith(match + ".") for c in candidates
        ):
            candidates.append((match, 70, len(match)))

    if not candidates:
        _set_cache(cache_key, "")
        debug_logger.trace(MODULE_INTENT, "detect_ticker no candidates found")
        return ""

    # Sort: maior score primeiro, desempate pelo mais longo (mais especÃ­fico)
    candidates.sort(key=lambda item: (item[1], item[2]), reverse=True)
    result = candidates[0][0]
    _set_cache(cache_key, result)
    debug_logger.trace(
        MODULE_INTENT,
        "detect_ticker result",
        ticker=result,
        candidates_count=len(candidates),
    )
    return result


def detect_diary_intent(message: str) -> bool:
    return has_hint(message, DIARY_KEYWORDS)


def _is_penny_definition_question(message: str) -> bool:
    normalized = normalize_message(message)
    patterns = (
        r"\bwhat\s+(?:is|are)\s+(?:a\s+)?penny[-\s]?stocks?\b",
        r"\bo que\s+(?:e|sao)\s+(?:um\s+)?penny[-\s]?stocks?\b",
        r"\bexplique\s+(?:o\s+)?penny[-\s]?stocks?\b",
        r"\bdefine\s+(?:a\s+)?penny[-\s]?stocks?\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _is_capability_question(message: str) -> bool:
    normalized = normalize_message(message)
    if not normalized.strip():
        return False

    direct_patterns = (
        r"\bqua(?:l|is)\s+(?:as\s+)?ferramentas\b",
        r"\bque\s+ferramentas\b",
        r"\b(?:voce|vc)\s+usa\b",
        r"\bwhat\s+tools\b",
        r"\bwhich\s+tools\b",
        r"\bwhat\s+do\s+you\s+use\b",
        r"\bhow\s+do\s+you\s+(?:research|screen|find)\b",
        r"\bcomo\s+(?:voce|vc)?\s*(?:pesquisa|encontra|acha)\b",
    )
    if any(re.search(pattern, normalized) for pattern in direct_patterns):
        return True

    return (
        has_hint(message, QUESTION_HINTS)
        and has_hint(message, CAPABILITY_HINTS)
        and has_hint(message, RESEARCH_DOMAIN_HINTS)
    )


def _has_penny_asset_hint(message: str) -> bool:
    return has_hint(message, PENNY_ASSET_HINTS)


def _has_scan_scope(message: str) -> bool:
    normalized = normalize_message(message)
    if has_hint(message, SCOPE_KEYWORDS):
        return True
    # "100 CAD" is currency, not a Canada geography hint.
    if re.search(r"(?:\d[\d,]*(?:\.\d+)?\s*cad|cad\s*\d)", normalized, re.IGNORECASE):
        return False
    return re.search(r"\bcad\b", normalized) is not None


def _is_market_scan_request(message: str) -> bool:
    if detect_ticker(message):
        return False
    if _is_penny_definition_question(message) or _is_capability_question(message):
        return False
    if detect_capital_allocation_intent(message):
        return False
    if detect_risk_lab_intent(message):
        return False
    if detect_operational_status_request(message) or detect_negative_trade_instruction(message):
        return False
    # Sugestao de produto/estrategia sem ticker e resposta advisory, nao scan.
    if is_product_strategy_suggestion(message):
        return False
    # Negative scan clauses block incidental scan words, but act as exclusions
    # when a positive discovery command names an allowed scope.
    normalized = normalize_message(message)
    has_scan = has_hint(message, SCAN_KEYWORDS) or has_hint(message, SCAN_COMMAND_HINTS)
    has_scope = _has_scan_scope(message)
    has_penny_asset = _has_penny_asset_hint(message)
    is_scan_command = has_hint(message, SCAN_COMMAND_HINTS)
    wants_specific_analysis = has_hint(message, TICKER_REQUIRED_ANALYSIS_HINTS)
    has_financial_hint = has_hint(message, VAGUE_FINANCIAL_HINTS)
    positive_discovery = bool(
        re.search(r"\b(find|search|look for|shortlist|list)\b", normalized)
        or has_hint(message, ("encontre", "procure", "busque", "pesquise"))
    )

    if detect_negative_scan_instruction(message) and not (positive_discovery and has_scope):
        return False

    if detect_decisive_trade_intent(message) and not wants_specific_analysis:
        return True
    if has_scan and has_scope:
        return True
    if has_scan and has_penny_asset and not wants_specific_analysis:
        return True
    if has_penny_asset and is_scan_command and not wants_specific_analysis:
        return True
    # "me indique investimento", "sugira acao", "oportunidades" â€” scan command
    # com hint financeiro, mesmo sem escopo explicito de pais/setor.
    if is_scan_command and has_financial_hint and not wants_specific_analysis:
        return True
    # Investment verbs without ticker â†’ the user wants opportunities, not a chat
    return bool(has_hint(message, INVESTMENT_ACTION_HINTS) and not detect_ticker(message))


def _needs_ticker_for_requested_analysis(message: str, ticker: str = "") -> bool:
    if ticker or detect_ticker(message):
        return False
    if _is_capability_question(message) or _is_penny_definition_question(message):
        return False
    if _references_unspecified_ticker_or_asset(message):
        return True
    return _has_penny_asset_hint(message) and has_hint(message, TICKER_REQUIRED_ANALYSIS_HINTS)


def _references_unspecified_ticker_or_asset(message: str) -> bool:
    """Detect follow-up language that points at an asset without naming it."""
    if detect_ticker(message):
        return False
    if has_hint(message, REFERENTIAL_TICKER_HINTS):
        return True
    return has_hint(message, REFERENTIAL_ASSET_NOUNS) and has_hint(
        message,
        REFERENTIAL_ASSET_STATUS_HINTS,
    )


def detect_market_scan_intent(message: str) -> bool:
    return _is_market_scan_request(message)


# Acronimos financeiros comuns que aparecem em CAPS mas nao sao ticker.
_TICKER_LIKE_STOP_WORDS = frozenset(
    {
        "AI",
        "CAD",
        "USD",
        "EUR",
        "GBP",
        "BRL",
        "CDN",
        "ETF",
        "ETFS",
        "FII",
        "FIIS",
        "IPO",
        "REIT",
        "REITS",
        "GIC",
        "TSX",
        "B3",
    }
)


def _has_inline_ticker_like_token(message: str) -> bool:
    """Aproxima detect_ticker sem chamar detect_ticker.

    detect_ticker recursa via detect_broker_status_intent ->
    detect_decisive_trade_intent, entao nao pode ser chamado dentro do
    detector de sugestao de produto nem do composite de "escolhe/escolha".
    Considera sufixos (.TO/.SA/.V), padroes com digito (PETR4/BOVA11) e tokens
    em CAPS dentro de mensagem em caixa mista, ignorando acronimos financeiros.
    """
    if not message:
        return False
    if re.search(r"\b[A-Za-z]{1,6}\d{0,2}\.(?:SA|TO|V)\b", message):
        return True
    if re.search(r"\b[A-Z]{2,6}\d{1,2}\b", message):
        return True
    if not re.search(r"[a-z]", message):
        # Mensagem inteira em CAPS (caixa alta) nao e lista de tickers.
        return False
    for token in re.findall(r"\b[A-Z]{2,6}\b", message):
        if token not in _TICKER_LIKE_STOP_WORDS:
            return True
    return False


def is_product_strategy_suggestion(message: str) -> bool:
    """Detecta pedido de sugestao de produto/estrategia de investimento sem ticker.

    True quando o operador usa verbo de sugestao ("escolhe/escolha", "sugere",
    "recomenda", "me diga um produto"...) e NAO fala de ordem/trade/ticker/
    scan/treino, com contexto financeiro: valor + perfil de risco OU alvo
    nomeado (produto/estrategia/framework). Nesse caso o Bob deve responder
    framework/produto (route=general, action=answer, sem scanner) em vez de
    cair no DECISIVE_TRADE_ORDER com scan + REJECT_ALL.
    """
    if not message or not message.strip():
        return False
    if not has_hint(message, _PRODUCT_SUGGESTION_VERB_HINTS):
        return False
    if _has_inline_ticker_like_token(message) or has_hint(
        message,
        _MARKET_EXECUTION_CONTEXT_HINTS,
    ):
        return False
    if has_hint(message, _PRODUCT_STRATEGY_NOUN_HINTS):
        return True
    normalized = normalize_message(message)
    has_amount = _AMOUNT_HINT_PATTERN.search(normalized) is not None
    if has_amount:
        return True
    has_risk_profile = has_hint(message, _RISK_PROFILE_HINT_WORDS)
    return has_risk_profile


def detect_decisive_trade_intent(message: str) -> bool:
    """Detect if the user is asking for a decisive buy/trade recommendation.

    When True, the market_scan answer renderer switches from the default
    8-section research report to the DECISIVE_TRADE_ORDER contract.
    """
    if not message or not message.strip():
        return False
    # Sugestao de produto/estrategia sem ticker nao e ordem/trade: o Bob
    # responde framework/produto na rota general em vez de scan + REJECT_ALL.
    if is_product_strategy_suggestion(message):
        return False
    if has_hint(message, DECISIVE_TRADE_HINTS):
        return True
    # "escolhe/escolha" so e decisive quando ha contexto de ordem/trade/ticker/
    # scan/treino (composite); sozinho e pedido de sugestao (rota general).
    if has_hint(message, ESCOLHE_PICK_HINTS) and (
        _has_inline_ticker_like_token(message) or has_hint(message, _MARKET_EXECUTION_CONTEXT_HINTS)
    ):
        return True

    normalized = normalize_message(message)
    training_hints = (
        "treino",
        "treinar",
        "treinamento",
        "paper",
        "simulado",
        "aprendizagem",
        "training",
    )
    fast_trade_hints = (
        "ordem",
        "ordens",
        "oredem",
        "oredens",
        "order",
        "orders",
        "paper order",
        "submit",
        "send",
        "trade",
        "trades",
        "transacao",
        "transacoes",
        "entrada",
        "entara",
        "saida",
        "stop loss",
        "stop",
        "1 hora",
        "one hour",
        "uma hora",
        "4 horas",
        "quatro horas",
        "intraday",
        "scalp",
        "rapida",
        "rapidas",
        "rapido",
        "rapidos",
    )
    allocation_hints = (
        "aplique",
        "aplike",
        "aplicar",
        "alocar",
        "aloque",
        "invista",
        "investir",
        "use",
        "usar",
        "10k",
        "10 k",
        "10 mil",
        "10000",
    )
    explosive_hints = (
        "explosiva",
        "explosivas",
        "explosisva",
        "explosisvas",
        "momentum",
    )

    has_training = any(hint in normalized for hint in training_hints)
    has_fast_trade = any(hint in normalized for hint in fast_trade_hints)
    has_allocation = any(hint in normalized for hint in allocation_hints)
    has_explosive = any(hint in normalized for hint in explosive_hints)

    if has_training and has_fast_trade:
        return True
    if has_training and has_allocation:
        return True
    if has_allocation and (has_fast_trade or has_explosive):
        return True
    return bool(has_explosive and has_fast_trade)


def detect_another_trade_recommendation_intent(message: str) -> bool:
    """Detect follow-up requests for another trade recommendation."""
    if not message or not message.strip():
        return False
    return has_hint(message, ANOTHER_TRADE_HINTS)


def should_block_vague_financial_prompt(
    raw_message: str,
    detected_ticker: str,
    rigor: str,
) -> bool:
    """Bloqueia prompts genÃ©ricos de investimento sem ticker.

    Centralizado aqui para que endpoints.py e pipeline runtime
    usem a mesma lÃ³gica, sem duplicaÃ§Ã£o de constantes.
    """
    if (rigor or "strict").lower() != "strict":
        return False
    if detected_ticker:
        return False
    if _is_capability_question(raw_message) or _is_penny_definition_question(raw_message):
        return False
    if detect_complex_finance_intent(raw_message):
        return False
    if detect_market_scan_intent(raw_message):
        return False
    if detect_negative_scan_instruction(raw_message):
        return False
    if detect_operational_status_request(raw_message) or detect_negative_trade_instruction(
        raw_message
    ):
        return False
    if detect_industry_research_intent(raw_message) or detect_risk_lab_intent(raw_message):
        return False
    if not has_hint(raw_message, VAGUE_FINANCIAL_HINTS):
        return False

    normalized = normalize_message(raw_message)
    if any(re.search(pattern, normalized) for pattern in DIRECT_UNSCOPED_RECOMMENDATION_PATTERNS):
        return True
    return not has_hint(raw_message, EDUCATIONAL_OR_RISK_CONTEXT_HINTS)


def infer_scan_filters(message: str) -> dict[str, str | None]:
    msg_lower = _strip_accents(message).lower()
    country = None
    sector = None

    if (
        "canadense" in msg_lower
        or "canada" in msg_lower
        or "canadian" in msg_lower
        or re.search(r"\bcad\b", msg_lower) is not None
        or "tsx" in msg_lower
        or "venture exchange" in msg_lower
    ):
        country = "Canada"
    elif "brasil" in msg_lower or "brasileir" in msg_lower:
        country = "Brazil"
    elif (
        "americano" in msg_lower
        or "usa" in msg_lower
        or "united states" in msg_lower
        or re.search(r"\bus\b", msg_lower) is not None
        or "estados unidos" in msg_lower
    ):
        country = "United States"

    if "banco" in msg_lower or "bank" in msg_lower or "financ" in msg_lower:
        sector = "Financials"
    elif "tecnologia" in msg_lower or "tech" in msg_lower:
        sector = "Information Technology"
    elif "energia" in msg_lower or "energy" in msg_lower:
        sector = "Energy"
    elif "saude" in msg_lower or "health" in msg_lower:
        sector = "Health Care"
    elif "industrial" in msg_lower:
        sector = "Industrials"

    return {"country": country, "sector": sector}


# ---------------------------------------------------------------------------
# PennyLab Intent Detection
# ---------------------------------------------------------------------------

PENNYLAB_KEYWORDS = (
    "penny stock",
    "penny stocks",
    "pennylab",
    "penny lab",
    "whale trap",
    "whaletrap",
    "baleia",
    "pump and dump",
    "pump & dump",
    "microcap analysis",
    "analise de penny",
    "analisar penny",
    "penny analise",
    "volume spike",
    "spike de volume",
    "acao de centavo",
    "small cap risky",
    "laboratorio de penny",
    "lab de penny",
)


def detect_pennylab_intent(message: str) -> bool:
    """Detecta se a mensagem quer anÃ¡lise especÃ­fica de penny stock."""
    if not message:
        return False
    has_keyword = has_hint(message, PENNYLAB_KEYWORDS)
    has_ticker = detect_ticker(message) != ""
    return has_keyword and has_ticker


def parse_user_intent(
    message: str,
    rigor: str = "strict",
    ticker: str = "",
    trade_order_context: dict[str, Any] | None = None,
) -> IntentParse:
    """Parse a user request into route, intent, entities, and missing slots.

    The parser separates speech act from financial domain terms. A sentence can
    mention "penny stocks" and "research" while still being a capabilities
    question, not an executable scan.

    When *ticker* is provided (e.g. from a UI ticker field), it takes priority
    over text-based detection and must pass basic validation.
    """
    raw = message or ""

    def done(parsed: IntentParse) -> IntentParse:
        return _with_cognitive_contract(parsed, raw)

    if _is_casual_message(raw):
        return done(
            IntentParse(
                route="general",
                intent="general_question",
                action="answer",
                ticker="",
                filters={},
                confidence=0.99,
                reasons=("casual_greeting_detected",),
                entities={"ticker": "", "asset_class": None, "country": None, "sector": None},
                diary=False,
                pennylab=False,
            )
        )

    broker_status_question = detect_broker_status_intent(raw)
    explicit_ticker_command = _extract_explicit_ticker_command(raw)
    if broker_status_question:
        ticker = ""
    elif explicit_ticker_command:
        ticker = explicit_ticker_command
    elif ticker and not _is_valid_ticker(ticker):
        ticker = ""
    if not ticker:
        ticker = detect_ticker(raw)
    capability_question = _is_capability_question(raw)
    filters = {} if capability_question else infer_scan_filters(raw)
    diary = detect_diary_intent(raw)
    pennylab = detect_pennylab_intent(raw)
    entities = {
        "ticker": ticker.upper() if ticker else "",
        "asset_class": "penny_stock" if _has_penny_asset_hint(raw) else None,
        "country": filters.get("country"),
        "sector": filters.get("sector"),
    }

    def done(parsed: IntentParse) -> IntentParse:
        return _with_cognitive_contract(parsed, raw)

    if not raw.strip():
        return done(
            IntentParse(
                route="general",
                intent="general_question",
                action="answer",
                filters={},
                confidence=0.99,
                reasons=("empty_or_whitespace_message",),
                entities=entities,
                diary=diary,
                pennylab=pennylab,
            )
        )

    if capability_question:
        return done(
            IntentParse(
                route="general",
                intent="explain_capabilities",
                action="answer_directly",
                ticker="",
                filters={},
                confidence=0.9,
                reasons=("capability_or_method_question",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    if broker_status_question:
        entities["ticker"] = ""
        return done(
            IntentParse(
                route="general",
                intent="general_question",
                action="answer",
                ticker="",
                filters={},
                confidence=0.96,
                reasons=("broker_status_question",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    ctx = trade_order_context or {}
    if ctx.get("mode") in {
        "DECISIVE_TRADE_ORDER",
        "DECISIVE_TRADE_ORDER_FOLLOWUP",
    } and detect_another_trade_recommendation_intent(raw):
        filters = infer_scan_filters(raw)
        if (
            ctx.get("universe")
            and not filters.get("country")
            and "US_CANADA" in str(ctx.get("universe", ""))
        ):
            filters = {**filters}
        return done(
            IntentParse(
                route="market_scan",
                intent="another_trade_recommendation",
                action="scan_market",
                filters=filters,
                confidence=0.9,
                reasons=("decisive_trade_followup",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    # Named-ticker tip/thesis must beat industry-theme wipe ("tese"),
    # dica-as-scan, and complex-finance fallthrough. Live order stays gated.
    if (
        ticker
        and is_investment_thesis_request(raw)
        and (explicit_ticker_command or _has_inline_ticker_like_token(raw) or detect_ticker(raw))
    ):
        return done(
            IntentParse(
                route="ticker_analysis",
                intent="ticker_analysis",
                action="collect_data",
                ticker=ticker.upper(),
                filters={},
                confidence=0.9,
                reasons=("investment_thesis_with_ticker",),
                entities=entities,
                diary=diary,
                pennylab=pennylab,
            )
        )

    if ticker and detect_industry_research_intent(raw) and not explicit_ticker_command:
        ticker = ""
        entities["ticker"] = ""

    # Capital allocation / personal finance gate must beat ticker detection.
    # Words like ETF/CAD or requested ticker examples are symbols inside an
    # allocation plan, not proof the user asked for ticker analysis.
    if detect_capital_allocation_intent(raw):
        return done(
            IntentParse(
                route="general",
                intent="capital_allocation",
                action="answer",
                filters={},
                confidence=0.92,
                reasons=("capital_allocation_decision_detected",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    if detect_etf_comparison_intent(raw):
        return done(
            IntentParse(
                route="general",
                intent="general_question",
                action="answer",
                filters={},
                confidence=0.9,
                reasons=("etf_comparison_advisory_detected",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    if detect_portfolio_concentration_intent(raw):
        return done(
            IntentParse(
                route="general",
                intent="personal_finance",
                action="answer",
                filters={},
                confidence=0.9,
                reasons=("portfolio_concentration_advisory_detected",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    # Sugestao de produto/estrategia sem ticker (valor+perfil de risco+verbo de
    # sugestao, ou produto/estrategia nomeado, sem vocabulario de ordem/trade/
    # ticker/scan/treino) -> o Bob responde framework/produto; nunca vira
    # DECISIVE_TRADE_ORDER com scan + REJECT_ALL.
    if is_product_strategy_suggestion(raw):
        return done(
            IntentParse(
                route="general",
                intent="personal_finance",
                action="answer",
                filters={},
                confidence=0.88,
                reasons=("product_strategy_suggestion_detected",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    # If the user message is an explicit market scan request, the scanner
    # takes priority over a ticker lingering in the chart UI. Otherwise a
    # "Find US small-cap stocks" prompt with AAPL in the chart would route
    # to ticker_analysis and never invoke the scanner.
    if ticker and not _is_market_scan_request(raw):
        return done(
            IntentParse(
                route="ticker_analysis",
                intent="ticker_analysis",
                action="collect_data",
                ticker=ticker.upper(),
                filters={},
                confidence=0.86,
                reasons=("explicit_ticker_detected",),
                entities=entities,
                diary=diary,
                pennylab=pennylab,
            )
        )

    # Complex finance gate â€” must come BEFORE market_scan and vague-financial
    # fallthrough to prevent advisory questions from triggering the scanner.
    if detect_complex_finance_intent(raw):
        return done(
            IntentParse(
                route="general",
                intent="general_question",
                action="answer",
                filters={},
                confidence=0.88,
                reasons=("complex_finance_advisory_detected",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    if _is_market_scan_request(raw):
        return done(
            IntentParse(
                route="market_scan",
                intent="market_scan",
                action="scan_market",
                filters=filters,
                confidence=0.82,
                reasons=("scan_command_with_scope_or_penny_universe",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    strict = (rigor or "strict").lower() == "strict"
    if strict and _needs_ticker_for_requested_analysis(raw, ticker):
        return done(
            IntentParse(
                route="needs_scope",
                intent="missing_required_slot",
                action="ask_for_ticker",
                filters={},
                confidence=0.88,
                required_slots=("ticker",),
                reasons=("analysis_requested_without_required_ticker",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    vague = should_block_vague_financial_prompt(raw, ticker, rigor)
    if strict and vague:
        # A vague opportunity request should not let regex pre-decide the
        # investment universe. Keep the route general and give Bob permission
        # to call market_scan only if the answer needs current candidates.
        filters = infer_scan_filters(raw)
        has_scope = _has_scan_scope(raw) or bool(filters.get("country"))
        return done(
            IntentParse(
                route="general",
                intent="market_scan",
                action="answer",
                filters=filters,
                confidence=0.62 if not has_scope else 0.78,
                reasons=(
                    ("vague_opportunity_delegated_to_bob_decision",)
                    if not has_scope
                    else ("vague_with_scope_delegated_to_bob_decision",)
                ),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        )

    return done(
        IntentParse(
            route="general",
            intent="general_question",
            action="answer",
            filters={},
            confidence=0.72,
            reasons=("no_executable_financial_intent",),
            entities=entities,
            diary=diary,
            pennylab=False,
        )
    )


def _clean_slots(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _clean_filters(value: Any) -> dict[str, str | None]:
    if not isinstance(value, dict):
        return {}
    allowed = {"country", "sector"}
    return {
        key: str(raw) if raw not in (None, "") else None
        for key, raw in value.items()
        if key in allowed
    }


def _base_entities(message: str, ticker: str, filters: dict[str, str | None]) -> dict:
    return {
        "ticker": ticker.upper() if ticker else "",
        "asset_class": "penny_stock" if _has_penny_asset_hint(message) else None,
        "country": filters.get("country"),
        "sector": filters.get("sector"),
    }


def validate_intent_candidate(
    message: str,
    candidate: dict[str, Any],
    fallback: IntentParse | None = None,
) -> IntentParse | None:
    """Validate a golden/LLM candidate under strict routing invariants."""
    if not isinstance(candidate, dict):
        return None

    route = str(candidate.get("route") or "").strip()
    intent = str(candidate.get("intent") or "").strip()
    action = str(candidate.get("action") or "").strip()
    if route not in ALLOWED_ROUTES:
        return None
    if intent not in ALLOWED_INTENTS:
        return None
    if action not in ALLOWED_ACTIONS:
        return None
    # CEO model cross-classification allowed â€” the model was trained to
    # decide route+intent jointly. ROUTE_INTENT_ACTIONS is a deterministic
    # guard, not a hard invariant for model output.

    detected_ticker = detect_ticker(message)
    candidate_ticker = str(candidate.get("ticker") or "").strip().upper()
    if candidate_ticker and not detected_ticker:
        return None
    if candidate_ticker and detected_ticker and candidate_ticker != detected_ticker:
        return None
    if route == "ticker_analysis" and not detected_ticker:
        return None
    if route == "market_scan" and detected_ticker:
        return None

    filters = _clean_filters(candidate.get("filters"))
    if route != "market_scan":
        filters = {}
    elif not filters:
        filters = infer_scan_filters(message)

    required_slots = _clean_slots(candidate.get("required_slots"))
    if route == "needs_scope" and not required_slots:
        required_slots = ("ticker",)
    if route != "needs_scope":
        required_slots = ()

    try:
        confidence = float(candidate.get("confidence", 0.75))
    except (TypeError, ValueError):
        confidence = 0.75
    confidence = max(0.0, min(confidence, 0.99))

    reasons = _clean_slots(candidate.get("reasons"))
    if not reasons:
        reasons = ("validated_intent_candidate",)

    ticker = detected_ticker.upper() if route == "ticker_analysis" else ""
    entities = deepcopy(fallback.entities) if fallback and fallback.entities else {}
    entities.update(_base_entities(message, ticker, filters))

    return _with_cognitive_contract(
        IntentParse(
            route=route,
            intent=intent,
            action=action,
            ticker=ticker,
            filters=filters,
            confidence=confidence,
            required_slots=required_slots,
            reasons=reasons,
            entities=entities,
            diary=detect_diary_intent(message),
            pennylab=detect_pennylab_intent(message) if ticker else False,
        ),
        message,
    )


@lru_cache(maxsize=4)
def load_golden_intents(path: str | None = None) -> tuple[dict[str, Any], ...]:
    """Load exact-match golden intent examples from JSONL."""
    golden_path = Path(path) if path else DEFAULT_GOLDEN_INTENT_PATH
    if not golden_path.exists():
        return ()

    entries: list[dict[str, Any]] = []
    try:
        lines = golden_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        text = raw.get("message") or raw.get("utterance")
        if not isinstance(text, str) or not text.strip():
            continue
        raw["normalized_message"] = normalize_for_match(text)
        entries.append(raw)
    return tuple(entries)


def match_golden_intent(
    message: str,
    rigor: str = "strict",
    path: str | None = None,
) -> IntentParse | None:
    """Return a validated exact-match golden intent, if one exists."""
    normalized = normalize_for_match(message)
    if not normalized:
        return None

    fallback = parse_user_intent(message, rigor=rigor)
    for entry in load_golden_intents(path):
        if entry.get("normalized_message") != normalized:
            continue
        candidate = validate_intent_candidate(message, entry, fallback=fallback)
        if not candidate:
            return None
        reasons = ("golden_dataset_match",) + tuple(candidate.reasons)
        return _with_cognitive_contract(
            IntentParse(
                route=candidate.route,
                intent=candidate.intent,
                action=candidate.action,
                ticker=candidate.ticker,
                filters=candidate.filters,
                confidence=max(candidate.confidence, 0.97),
                required_slots=candidate.required_slots,
                reasons=reasons,
                entities=candidate.entities,
                diary=candidate.diary,
                pennylab=candidate.pennylab,
            ),
            message,
        )
    return None


def needs_llm_intent_fallback(
    message: str,
    plan: dict[str, Any],
    threshold: float = 0.76,
) -> bool:
    """Decide if an LLM classifier is worth consulting."""
    if not message.strip():
        return False
    try:
        confidence = float(plan.get("intent_confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    if confidence >= threshold:
        return False
    if plan.get("ticker"):
        return False
    return any(
        (
            has_hint(message, FINANCIAL_KEYWORDS),
            has_hint(message, RESEARCH_DOMAIN_HINTS),
            has_hint(message, CAPABILITY_HINTS),
            has_hint(message, VAGUE_FINANCIAL_HINTS),
        )
    )


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Extract one JSON object from a model response."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
