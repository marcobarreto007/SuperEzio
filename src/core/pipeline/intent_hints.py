"""Hint constants for intent detection — extracted from intents.py."""

RISK_LAB_HINTS = (
    "risk lab", "risk-lab", "risklab", "laboratorio de risco",
    "lab de risco", "risk experiment", "treino de risco",
    "50 dolares", "50 cad", "cad 50", "$50", "50 por semana",
    "50/week", "bet small", "pequena aposta", "risk budget",
    "orcamento de risco", "banca de risco",
)

INDUSTRY_RESEARCH_HINTS = (
    "industry research", "industry analysis", "setor", "sector",
    "industria", "pesquisa de setor", "analise setorial",
    "market landscape", "cadeia de valor", "value chain",
    "competitive landscape", "tam sam som", "market size",
    "industry trend", "tendencia do setor", "tendencia de setor",
    "mapeamento", "ecossistema", "ecosystem",
)

FORENSIC_RAG_HINTS = (
    "forensic", "forense", "fraud", "fraude", "manipulation",
    "manipulacao", "pump and dump", "pump & dump", "ponzi",
    "securities fraud", "insider trading", "wash trading",
    "spoofing", "layering", "sec investigation", "doj investigation",
)

BROKER_STATUS_SUBJECT_HINTS = (
    "ibkr", "broker", "corretora", "tws", "interactive brokers",
    "conectado", "connected", "online", "offline",
    "status do broker", "broker status",
)

BROKER_STATUS_CONTEXT_HINTS = (
    "status", "conectado", "connected", "online", "offline",
    "funcionando", "working", "rodando", "running",
    "tudo bem", "tudo certo", "tudo ok", "all good",
    "como esta", "how is", "como estamos", "how are we",
)

VAGUE_FINANCIAL_HINTS = (
    "find", "scan", "search", "look for", "show me", "give me",
    "recommend", "suggest", "pick", "choose", "select",
    "best", "top", "good", "great", "cheap", "undervalued",
    "growth", "value", "dividend", "momentum", "penny",
    "small cap", "large cap", "mid cap", "tech", "energy",
    "healthcare", "financial", "consumer", "industrial",
    "real estate", "utility", "material", "communication",
)

SCAN_KEYWORDS = (
    "scan", "scanner", "market scan", "screen", "screener",
    "find me", "find a", "look for", "search for",
    "discover", "explore", "hunt", "hunting",
    "opportunity", "opportunities", "idea", "ideas",
    "pick", "picks", "stock pick", "stock picks",
    "recommendation", "recommend",
)

SCOPE_KEYWORDS = (
    "canada", "canadian", "tsx", "tsx-v", "cse",
    "us", "usa", "united states", "nyse", "nasdaq", "otc",
    "china", "chinese", "hong kong", "europe", "european",
    "brazil", "brazilian", "b3", "latin america",
    "emerging", "emerging markets", "frontier",
)
