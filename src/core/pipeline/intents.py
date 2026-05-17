"""Intent and ticker detection for the chat pipeline.

Funções públicas exportadas:
  - parse_user_intent(message, rigor) -> IntentParse
  - detect_ticker(message) -> str
  - detect_diary_intent(message) -> bool
  - detect_market_scan_intent(message) -> bool
  - detect_pennylab_intent(message) -> bool
  - infer_scan_filters(message) -> dict
  - should_block_vague_financial_prompt(message, ticker, rigor) -> bool
  - normalize_message(text) -> str
  - has_hint(message, hints) -> bool

Constantes exportadas:
  - VAGUE_FINANCIAL_HINTS, SCAN_KEYWORDS, SCOPE_KEYWORDS
"""

from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..observability.debug_logger import debug_logger, MODULE_INTENTS as MODULE_INTENT

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GOLDEN_INTENT_PATH = PROJECT_ROOT / "data" / "intent_golden.jsonl"

ALLOWED_ROUTES = {"general", "ticker_analysis", "market_scan", "needs_scope"}
ALLOWED_INTENTS = {
    "general_question",
    "explain_capabilities",
    "ticker_analysis",
    "market_scan",
    "missing_required_slot",
    "unsafe_unspecified_recommendation",
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
    "general": {"general_question", "explain_capabilities"},
    "ticker_analysis": {"ticker_analysis"},
    "market_scan": {"market_scan"},
    "needs_scope": {"missing_required_slot", "unsafe_unspecified_recommendation"},
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

    def to_plan(self) -> dict[str, Any]:
        plan = asdict(self)
        plan["filters"] = self.filters or {}
        plan["entities"] = self.entities or {}
        plan["errors"] = []
        plan["intent_confidence"] = plan.pop("confidence")
        plan["intent_reasons"] = list(plan.pop("reasons"))
        plan["required_slots"] = list(plan["required_slots"])
        return plan


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_message(text: str) -> str:
    """Normaliza mensagem para busca de keywords: strip accents + lowercase."""
    return _strip_accents(text).lower()


def has_hint(message: str, hints: tuple[str, ...]) -> bool:
    """Verifica se mensagem contém algum hint.

    Hints multi-palavra ou >3 chars usam substring match.
    Hints <=3 chars usam word-boundary regex para evitar falsos positivos.
    """
    normalized = normalize_message(message)
    for hint in hints:
        normalized_hint = normalize_message(hint).strip()
        if not normalized_hint:
            continue
        if " " not in normalized_hint and len(normalized_hint) <= 3:
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
    "CEO",
    "F51",
    "RAG",
    "RL",
    "IA",
    "HUB",
    "SENSEI",
    "BOB",
    "GEMMA",
    "DEEPSEEK",
    "CLAUDE",
    "LLAMA",
    "NEMOTRON",
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
    "STOCK",
    "STOCKS",
    "PENNY",
    "PENNIES",
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
    "small cap",
    "small caps",
    "microcap",
    "micro cap",
    "microcaps",
    "micro caps",
    "hoje",
    "agora",
)

SCOPE_KEYWORDS = (
    "canadense",
    "canada",
    "brasil",
    "brasileir",
    "americano",
    "usa",
    "estados unidos",
    "tecnologia",
    "energia",
    "bancos",
    "bank",
    "saude",
    "healthcare",
    "setor",
    "sector",
    "financeiro",
    "financial",
    "industrial",
    "tsx",
    "tsx venture",
    "venture exchange",
    "canadian",
    "mercado",
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
    "acao de centavo",
    "acoes de centavo",
)

SCAN_COMMAND_HINTS = (
    "me indica",
    "me indique",
    "indica",
    "indique",
    "me sugere",
    "me sugira",
    "sugere",
    "sugira",
    "me da uma dica",
    "me da dica",
    "da uma dica",
    "da dica",
    "busque",
    "buscar",
    "pesquise",
    "procure",
    "encontre",
    "scan",
    "screen",
    "shortlist",
    "lista",
    "liste",
    "me lista",
    "oportunidades",
    "opurtunidades",
    "quero investir",
    "onde investir",
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


CACHE_TTL = 30.0  # segundos

_ticker_cache: dict[str, tuple[float, str]] = {}


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
        stale = [
            k for k, v in _ticker_cache.items() if (time.time() - v[0]) > CACHE_TTL
        ]
        for k in stale:
            _ticker_cache.pop(k, None)


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
      - .TO  → TSX (Canadá) → preservado
      - .SA  → B3 (Brasil)  → preservado
      - .V   → TSX Venture (Canadá) → preservado
      - sem sufixo → NYSE/NASDAQ (EUA)
    """
    if not message:
        return ""

    raw = message.strip()
    cache_key = f"ticker:{raw}"
    cached = _get_cached(cache_key)
    if cached is not None:
        debug_logger.trace(MODULE_INTENT, "detect_ticker cached hit", result=cached)
        return cached

    normalized = _strip_accents(raw)
    debug_logger.trace(
        MODULE_INTENT, "detect_ticker start", message_preview=message[:80]
    )
    msg_lower = normalized.lower()
    has_fin_keyword = any(kw in msg_lower for kw in FINANCIAL_KEYWORDS)
    candidates: list[tuple[str, int, int]] = []

    # 1. Sufixos de mercado EXPLÍCITOS (.SA, .TO, .V) — prioridade MÁXIMA
    #    Captura padrões como: ENB.TO, PETR4.SA, HIVE.V, XYZ.V
    suffix_matches = re.findall(
        r"\b([A-Za-z]{1,6}\d{0,2}\.(?:SA|TO|V))\b",
        raw,
        re.IGNORECASE,
    )
    for match in suffix_matches:
        upper = match.upper()
        # Preserva o sufixo! Não limpa.
        candidates.append((upper, 100, len(upper)))

    # 2. Sufixos de mercado com formato alternativo (ex: "ENB.TO" escrito como "ENB.TO")
    #    Regex adicional para capturar .SA e .TO mesmo após caracteres especiais
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

    # 3. Ticker com dígitos (ex: PETR4, VALE3) — sem sufixo, prioridade alta
    digit_matches = re.findall(r"\b([A-Za-z]{1,5}\d{1,2})\b", raw)
    for match in digit_matches:
        upper = match.upper()
        if upper not in COMMON_WORDS:
            # Não sobrescrever se já tem sufixo explícito
            if not any(
                c[0] == upper or c[0].startswith(upper + ".") for c in candidates
            ):
                candidates.append((upper, 90, len(upper)))

    # 3.5 Ticker numérico curto (ex: 6M, 88E, 3M) — comum em microcaps/OTC
    num_prefix_matches = re.findall(r"\b(\d{1,2}[A-Za-z]{1,5})\b", raw)
    for match in num_prefix_matches:
        upper = match.upper()
        if upper not in COMMON_WORDS and not any(c[0] == upper for c in candidates):
            candidates.append((upper, 80, len(upper)))

    # 4. Índices (^BVSP, ^GSPC)
    idx_matches = re.findall(r"(\^[A-Za-z]+)\b", raw)
    for match in idx_matches:
        upper = match.upper()
        if not any(c[0] == upper for c in candidates):
            candidates.append((upper, 85, len(upper)))

    # 5. Crypto pairs (BTC-USD, ETH-BTC)
    crypto_matches = re.findall(r"\b([A-Za-z]{2,5}-[A-Za-z]{2,5})\b", raw)
    for match in crypto_matches:
        upper = match.upper()
        if upper not in COMMON_WORDS and not any(c[0] == upper for c in candidates):
            candidates.append((upper, 80, len(upper)))

    # 6. Ticker explícito (ex: "ticker: AAPL", "papel: PETR4")
    explicit_symbol_matches = re.findall(
        r"\b(?:ticker|symbol|papel|ativo|acao)\s*[:=-]?\s*([A-Za-z]{1,5}\d{0,2})\b",
        normalized,
        re.IGNORECASE,
    )
    for match in explicit_symbol_matches:
        upper = match.upper()
        if upper not in COMMON_WORDS and not any(c[0] == upper for c in candidates):
            candidates.append((upper, 65, len(upper)))


    if not candidates:
        _set_cache(cache_key, "")
        debug_logger.trace(MODULE_INTENT, "detect_ticker no candidates found")
        return ""

    # Sort: maior score primeiro, desempate pelo mais longo (mais específico)
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
    return (
        has_hint(message, SCOPE_KEYWORDS)
        or re.search(r"\bcad\b", normalized) is not None
    )


def _is_market_scan_request(message: str) -> bool:
    if detect_ticker(message):
        return False
    if _is_penny_definition_question(message) or _is_capability_question(message):
        return False

    has_scan = has_hint(message, SCAN_KEYWORDS) or has_hint(message, SCAN_COMMAND_HINTS)
    has_scope = _has_scan_scope(message)
    has_penny_asset = _has_penny_asset_hint(message)
    is_scan_command = has_hint(message, SCAN_COMMAND_HINTS)
    wants_specific_analysis = has_hint(message, TICKER_REQUIRED_ANALYSIS_HINTS)
    has_financial_hint = has_hint(message, VAGUE_FINANCIAL_HINTS)

    if has_scan and has_scope:
        return True
    if has_penny_asset and is_scan_command and not wants_specific_analysis:
        return True
    # "me indique investimento", "sugira acao", "oportunidades" — scan command
    # com hint financeiro, mesmo sem escopo explicito de pais/setor.
    if is_scan_command and has_financial_hint and not wants_specific_analysis:
        return True
    return False


def _needs_ticker_for_requested_analysis(message: str) -> bool:
    if detect_ticker(message):
        return False
    if _is_capability_question(message) or _is_penny_definition_question(message):
        return False
    return _has_penny_asset_hint(message) and has_hint(
        message, TICKER_REQUIRED_ANALYSIS_HINTS
    )


def _legacy_detect_market_scan_intent(message: str) -> bool:
    if detect_ticker(message):
        return False
    normalized = normalize_message(message)
    # Ignora perguntas de definição ("o que é penny stock?")
    penny_definition_patterns = (
        r"\bwhat\s+(?:is|are)\s+(?:a\s+)?penny stocks?\b",
        r"\bo que\s+(?:e|sao)\s+(?:um\s+)?penny stocks?\b",
        r"\bexplique\s+(?:o\s+)?penny stocks?\b",
        r"\bdefine\s+(?:a\s+)?penny stocks?\b",
    )
    if any(re.search(pattern, normalized) for pattern in penny_definition_patterns):
        return False

    has_scan = has_hint(message, SCAN_KEYWORDS)
    has_scope = (
        has_hint(message, SCOPE_KEYWORDS)
        or re.search(r"\bcad\b", normalized) is not None
    )
    has_penny_stock = any(
        kw in normalized
        for kw in ("penny stock", "penny stocks", "microcap", "micro cap")
    )
    return (has_scan and has_scope) or has_penny_stock


def detect_market_scan_intent(message: str) -> bool:
    return _is_market_scan_request(message)


def should_block_vague_financial_prompt(
    raw_message: str,
    detected_ticker: str,
    rigor: str,
) -> bool:
    """Bloqueia prompts genéricos de investimento sem ticker.

    Centralizado aqui para que endpoints.py e pipeline runtime
    usem a mesma lógica, sem duplicação de constantes.
    """
    if (rigor or "strict").lower() != "strict":
        return False
    if detected_ticker:
        return False
    if _is_capability_question(raw_message) or _is_penny_definition_question(
        raw_message
    ):
        return False
    if detect_market_scan_intent(raw_message):
        return False
    if not has_hint(raw_message, VAGUE_FINANCIAL_HINTS):
        return False

    normalized = normalize_message(raw_message)
    if any(
        re.search(pattern, normalized)
        for pattern in DIRECT_UNSCOPED_RECOMMENDATION_PATTERNS
    ):
        return True
    if has_hint(raw_message, EDUCATIONAL_OR_RISK_CONTEXT_HINTS):
        return False
    return True


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
        "americano" in msg_lower or "usa" in msg_lower or "estados unidos" in msg_lower
    ):
        country = "United States"

    if "banco" in msg_lower or "bank" in msg_lower or "financ" in msg_lower:
        sector = "Financial Services"
    elif "tecnologia" in msg_lower or "tech" in msg_lower:
        sector = "Technology"
    elif "energia" in msg_lower or "energy" in msg_lower:
        sector = "Energy"
    elif "saude" in msg_lower or "health" in msg_lower:
        sector = "Healthcare"
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
    """Detecta se a mensagem quer análise específica de penny stock."""
    if not message:
        return False
    has_keyword = has_hint(message, PENNYLAB_KEYWORDS)
    has_ticker = detect_ticker(message) != ""
    return has_keyword and has_ticker


def parse_user_intent(
    message: str, rigor: str = "strict", ticker: str = ""
) -> IntentParse:
    """Parse a user request into route, intent, entities, and missing slots.

    The parser separates speech act from financial domain terms. A sentence can
    mention "penny stocks" and "research" while still being a capabilities
    question, not an executable scan.

    When *ticker* is provided (e.g. from a UI ticker field), it takes priority
    over text-based detection and must pass basic validation.
    """
    raw = message or ""
    if ticker and not _is_valid_ticker(ticker):
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

    if not raw.strip():
        return IntentParse(
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

    if capability_question:
        return IntentParse(
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

    if ticker:
        return IntentParse(
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

    if _is_market_scan_request(raw):
        return IntentParse(
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

    strict = (rigor or "strict").lower() == "strict"
    if strict and _needs_ticker_for_requested_analysis(raw):
        return IntentParse(
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

    vague = should_block_vague_financial_prompt(raw, ticker, rigor)
    if strict and vague:
        # Se a mensagem tem escopo (moeda, pais, setor, risk tolerance),
        # roteia como market_scan em vez de bloquear.
        if _has_scan_scope(raw) or infer_scan_filters(raw).get("country"):
            return IntentParse(
                route="market_scan",
                intent="market_scan",
                action="scan_market",
                filters=infer_scan_filters(raw),
                confidence=0.78,
                reasons=("vague_with_scope_rerouted_to_scan",),
                entities=entities,
                diary=diary,
                pennylab=False,
            )
        return IntentParse(
            route="needs_scope",
            intent="unsafe_unspecified_recommendation",
            action="ask_for_scope",
            filters={},
            confidence=0.84,
            required_slots=("ticker_or_screening_scope",),
            reasons=("strict_mode_blocks_unspecified_financial_recommendation",),
            entities=entities,
            diary=diary,
            pennylab=False,
        )

    return IntentParse(
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
    if intent not in ROUTE_INTENT_ACTIONS.get(route, set()):
        return None

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

    return IntentParse(
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
        return IntentParse(
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
