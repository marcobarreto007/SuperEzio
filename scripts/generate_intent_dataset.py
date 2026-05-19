"""Generate 600-example intent classification training dataset for Qwen3.6-35B fine-tuning.

Covers: ticker_analysis, market_scan, general_question, explain_capabilities, needs_scope
Languages: Portuguese (primary) + English
Edge cases: time horizons vs tickers, currency amounts, typos, slang, ambiguous

Output: data/intent_training.jsonl (ShareGPT conversational format)
Also: data/intent_fewshot.jsonl (best ~50 examples for few-shot prompting)
"""

import json
import random
from pathlib import Path

random.seed(42)

SYSTEM_PROMPT = (
    "You are SuperEzio's intent classifier. Your job is to parse a user's financial message "
    "and return a structured JSON object with the following fields:\n\n"
    "- route: one of 'ticker_analysis', 'market_scan', 'general', 'needs_scope'\n"
    "- intent: one of 'ticker_analysis', 'market_scan', 'general_question', "
    "'explain_capabilities', 'missing_required_slot', 'unsafe_unspecified_recommendation'\n"
    "- action: one of 'collect_data', 'scan_market', 'answer', 'answer_directly', "
    "'ask_for_ticker', 'ask_for_scope'\n"
    "- ticker: the stock ticker mentioned, or empty string if none. "
    "Always uppercase with suffix preserved (.TO, .SA, .V). "
    "NEVER extract common words, time units, or currency amounts as tickers.\n"
    "- time_horizon: investment horizon mentioned (e.g., '14 days', '2 weeks', '3 months'), "
    "or empty string if not specified\n"
    "- filters: object with 'country' and 'sector' for market scans, empty for other routes\n"
    "- entities: object with 'amount' (number), 'currency' (CAD/USD/BRL), "
    "'risk_tolerance' (low/medium/high), 'asset_class' (stock/penny_stock/crypto/etf/options) — "
    "all null if not specified\n"
    "- required_slots: list of missing required info (e.g., ['ticker']), empty if complete\n"
    "- confidence: 0.0 to 0.99\n"
    "- reasons: list of short reasons for the classification\n\n"
    "CRITICAL RULES:\n"
    "1. If no ticker is present and the user asks for analysis/recommendation, "
    "route MUST be 'needs_scope'\n"
    "2. Time horizons ('14D', '6M', '1W') are NEVER tickers. If a message says "
    "'AAPL 14D', the ticker is AAPL and time_horizon is '14 days'\n"
    "3. Currency amounts ('500cad', '1000usd') are NEVER tickers\n"
    "4. Scan commands ('me indica', 'scan', 'busque', 'find me') with country/sector → "
    "'market_scan'\n"
    "5. 'quero investir' without a ticker → 'needs_scope', NOT 'market_scan'\n"
    "6. Capability questions ('what tools', 'como funciona', 'quais fontes') → "
    "'general' with intent 'explain_capabilities'\n"
    "7. Preserve ticker suffixes: .TO = TSX, .SA = B3, .V = TSX Venture\n"
    "Return ONLY the JSON object, nothing else."
)

# ---------------------------------------------------------------------------
# Template banks
# ---------------------------------------------------------------------------

TICKERS = {
    "TSX": ["ENB.TO", "SHOP.TO", "TD.TO", "BNS.TO", "SU.TO", "CNQ.TO", "CP.TO", "RY.TO"],
    "TSX_V": ["HIVE.V", "ACB.TO", "WEED.TO", "LUCK.V", "NGT.TO"],
    "NYSE_NASDAQ": [
        "AAPL",
        "TSLA",
        "NVDA",
        "MSFT",
        "META",
        "AMD",
        "PLTR",
        "GME",
        "AMC",
        "SPY",
        "QQQ",
    ],
    "B3": ["PETR4.SA", "VALE3", "ITUB4.SA", "BBAS3", "ABEV3"],
    "CRYPTO": ["BTC-USD", "ETH-USD", "SOL-USD"],
    "DIGIT": ["PETR4", "VALE3", "ITUB4", "BBAS3", "ABEV3"],
}

TIME_HORIZONS = {
    "pt_short": ["14 dias", "7 dias", "15 dias", "21 dias", "30 dias", "3 dias", "5 dias"],
    "pt_medium": ["2 semanas", "4 semanas", "1 mes", "2 meses", "3 meses", "6 meses"],
    "pt_long": ["1 ano", "2 anos"],
    "en_short": ["14 days", "7 days", "15 days", "21 days", "30 days"],
    "en_medium": ["2 weeks", "4 weeks", "1 month", "2 months", "3 months"],
    "compact": ["14d", "7d", "15d", "30d", "1w", "2w", "4w", "1m", "3m", "6m", "1y"],
}

RISK_TOLERANCE = {
    "pt": [
        "alto risco",
        "risco alto",
        "agressivo",
        "conservador",
        "moderado",
        "arriscar",
        "baixo risco",
    ],
    "en": ["high risk", "aggressive", "conservative", "moderate", "low risk", "risky"],
}

AMOUNTS = {
    "CAD": [
        "500cad",
        "500 cad",
        "1000cad",
        "1000 cad",
        "2000 cad",
        "250 cad",
        "5000 cad",
        "C$500",
        "C$1000",
    ],
    "USD": ["$500", "$1000", "$2000", "$5000", "500 dol", "1000 dollars", "500 usd"],
    "REAL": ["R$500", "R$1000", "500 reais", "1000 reais", "2 mil reais", "5k reais"],
}

# ---------------------------------------------------------------------------
# Example generators
# ---------------------------------------------------------------------------


def ticker_analysis_examples():
    """Messages with specific tickers to analyze."""
    examples = []

    # Plain ticker — generate 3 varied templates per ticker
    for ticker in TICKERS["NYSE_NASDAQ"]:
        for tpl in [
            "analise {t}",
            "analyze {t}",
            "quero saber sobre {t}",
            "what do you think about {t}",
            "me da um veredito sobre {t}",
            "should I buy {t}",
            "{t} analysis",
            "devo comprar {t}",
            "what's your take on {t}",
            "run analysis on {t}",
            "pipeline completo {t}",
            "verdict on {t}",
            "thoughts on {t}",
        ]:
            horizon = random.choice(TIME_HORIZONS["pt_short"] + TIME_HORIZONS["en_short"] + [""])
            msg = tpl.format(t=ticker)
            if horizon and random.random() < 0.5:
                msg += f" {horizon}"

            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": msg},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": "ticker_analysis",
                                    "intent": "ticker_analysis",
                                    "action": "collect_data",
                                    "ticker": ticker,
                                    "time_horizon": horizon if horizon else "",
                                    "filters": {},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": "stock",
                                    },
                                    "required_slots": [],
                                    "confidence": 0.95,
                                    "reasons": ["explicit_ticker_detected"],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

    # TSX tickers with suffix — 2 templates each
    for ticker in TICKERS["TSX"]:
        for tpl in [
            "analise {t}",
            "what about {t}",
            "devo investir em {t}",
            "should I buy {t}",
            "thoughts on {t}",
            "verdict {t}",
            "complete pipeline {t}",
        ]:
            horizon = random.choice(TIME_HORIZONS["pt_medium"] + TIME_HORIZONS["en_medium"] + [""])
            msg = tpl.format(t=ticker)
            if horizon and random.random() < 0.4:
                msg += f" horizonte {horizon}" if random.random() < 0.5 else f" {horizon}"

            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": msg},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": "ticker_analysis",
                                    "intent": "ticker_analysis",
                                    "action": "collect_data",
                                    "ticker": ticker,
                                    "time_horizon": horizon if horizon else "",
                                    "filters": {},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": "stock",
                                    },
                                    "required_slots": [],
                                    "confidence": 0.97,
                                    "reasons": ["explicit_tsx_ticker_with_suffix"],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

    # TSX Venture tickers — 2 templates each
    for ticker in TICKERS["TSX_V"]:
        for tpl in [
            "analise {t}",
            "what about {t}",
            "essa penny {t} vale a pena?",
            "is {t} a good penny stock",
            "analyze {t} pennylab",
            "run pennylab on {t}",
        ]:
            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": tpl.format(t=ticker)},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": "ticker_analysis",
                                    "intent": "ticker_analysis",
                                    "action": "collect_data",
                                    "ticker": ticker,
                                    "time_horizon": "",
                                    "filters": {},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": "penny_stock" if "penny" in tpl else "stock",
                                    },
                                    "required_slots": [],
                                    "confidence": 0.95,
                                    "reasons": ["explicit_tsx_venture_ticker"],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

    # B3/Brazilian tickers — 2 templates each
    for ticker in TICKERS["B3"]:
        for tpl in [
            "analise {t}",
            "quero saber sobre {t}",
            "{t} vale a pena",
            "o que acha de {t}",
            "{t} analise",
            "investir em {t}",
            "comprar {t}",
        ]:
            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": tpl.format(t=ticker)},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": "ticker_analysis",
                                    "intent": "ticker_analysis",
                                    "action": "collect_data",
                                    "ticker": ticker,
                                    "time_horizon": "",
                                    "filters": {},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": "stock",
                                    },
                                    "required_slots": [],
                                    "confidence": 0.95,
                                    "reasons": ["explicit_b3_ticker"],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

    # Ticker with amount — expand to 16
    for ticker in random.sample(TICKERS["NYSE_NASDAQ"] + TICKERS["TSX"], 16):
        amount = random.choice(AMOUNTS["CAD"] + AMOUNTS["USD"])
        tpl = random.choice(
            [
                f"investir {amount} em {ticker}",
                f"put {amount} in {ticker}",
                f"quero colocar {amount} no {ticker}",
                f"comprar {amount} de {ticker}",
                f"buy {amount} worth of {ticker}",
            ]
        )
        currency = "CAD" if "cad" in amount.lower() or "C$" in amount else "USD"
        amt_num = (
            int("".join(c for c in amount if c.isdigit()))
            if any(c.isdigit() for c in amount)
            else None
        )
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": tpl},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "ticker_analysis",
                                "intent": "ticker_analysis",
                                "action": "collect_data",
                                "ticker": ticker,
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": amt_num,
                                    "currency": currency,
                                    "risk_tolerance": None,
                                    "asset_class": "stock",
                                },
                                "required_slots": [],
                                "confidence": 0.94,
                                "reasons": ["explicit_ticker_with_investment_amount"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # Ticker with risk tolerance — expand to 20
    for ticker in random.sample(TICKERS["NYSE_NASDAQ"] + TICKERS["TSX"] + TICKERS["B3"], 20):
        risk = random.choice(RISK_TOLERANCE["pt"] + RISK_TOLERANCE["en"])
        tpl = random.choice(
            [
                f"analise {ticker} com perfil {risk}",
                f"{ticker} analysis {risk}",
                f"quero investir em {ticker} com {risk}",
            ]
        )
        risk_level = (
            "high"
            if any(w in risk.lower() for w in ("alto", "high", "aggressive", "agressivo"))
            else "low"
            if any(w in risk.lower() for w in ("baixo", "low", "conservative", "conservador"))
            else "medium"
        )
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": tpl},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "ticker_analysis",
                                "intent": "ticker_analysis",
                                "action": "collect_data",
                                "ticker": ticker,
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": risk_level,
                                    "asset_class": "stock",
                                },
                                "required_slots": [],
                                "confidence": 0.93,
                                "reasons": ["explicit_ticker_with_risk_profile"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # Crypto tickers
    for ticker in TICKERS["CRYPTO"]:
        tpl = random.choice(
            [
                f"analyze {ticker}",
                f"analise {ticker}",
                f"what about {ticker}",
                f"crypto {ticker} analysis",
            ]
        )
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": tpl},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "ticker_analysis",
                                "intent": "ticker_analysis",
                                "action": "collect_data",
                                "ticker": ticker,
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": "crypto",
                                },
                                "required_slots": [],
                                "confidence": 0.94,
                                "reasons": ["explicit_crypto_ticker"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # Ticker with time horizon (compact form — critical edge case)
    for ticker in ["AAPL", "TSLA", "NVDA", "ENB.TO"]:
        for compact in ["14d", "7d", "30d", "1w", "2w", "1m", "3m"]:
            tpl = random.choice(
                [
                    f"analise {ticker} {compact}",
                    f"{ticker} {compact} analysis",
                    f"verdict {ticker} {compact}",
                ]
            )
            # Map compact to readable
            compact_map = {"d": "day", "w": "week", "m": "month"}
            num = "".join(c for c in compact if c.isdigit())
            unit_char = "".join(c for c in compact if c.isalpha()).lower()
            unit = compact_map.get(unit_char, "days")
            horizon_readable = f"{num} {unit}{'s' if num != '1' else ''}"

            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": tpl},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": "ticker_analysis",
                                    "intent": "ticker_analysis",
                                    "action": "collect_data",
                                    "ticker": ticker,
                                    "time_horizon": horizon_readable,
                                    "filters": {},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": "stock",
                                    },
                                    "required_slots": [],
                                    "confidence": 0.94,
                                    "reasons": [
                                        "explicit_ticker_with_compact_time_horizon",
                                        "time_unit_not_ticker",
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

    return examples


def market_scan_examples():
    """Scan/screening requests."""
    examples = []

    country_hints = {
        "Canada": ["canadense", "canada", "canadian", "tsx", "venture exchange", "cad", "toronto"],
        "United States": ["americano", "usa", "estados unidos", "nasdaq", "nyse", "american"],
        "Brazil": ["brasil", "brasileiro", "brasileira", "b3", "bovespa", "brazilian"],
    }
    sector_hints = {
        "Technology": ["tecnologia", "tech", "software", "ia", "ai"],
        "Energy": ["energia", "energy", "petroleo", "oil", "gas", "solar", "renewable"],
        "Financial Services": ["bancos", "bancario", "bank", "financial", "fintech", "financeiro"],
        "Healthcare": ["saude", "healthcare", "health", "farma", "biotec", "medica"],
        "Mining": ["mineracao", "mining", "gold", "ouro", "lithium", "litio", "copper", "cobre"],
        "Industrials": ["industrial", "industria", "manufacturing", "transporte", "railway"],
    }

    # Country-only scans
    for country, hints in country_hints.items():
        hint = random.choice(hints)
        for tpl in [
            f"me indica açoes {hint}",
            f"quais as melhores açoes {hint}",
            f"scan {hint} stocks",
            f"busque oportunidades no mercado {hint}",
            f"liste empresas {hint}",
            f"find me {hint} stocks",
            f"me sugira investimentos {hint}",
            f"quero ver açoes {hint}",
        ]:
            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": tpl},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": "market_scan",
                                    "intent": "market_scan",
                                    "action": "scan_market",
                                    "ticker": "",
                                    "time_horizon": "",
                                    "filters": {"country": country, "sector": None},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": "stock",
                                    },
                                    "required_slots": [],
                                    "confidence": 0.88,
                                    "reasons": ["scan_command_with_country"],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

    # Sector + country scans — generate across all combos
    for country, country_hint_list in country_hints.items():
        for country_hint in random.sample(country_hint_list, min(3, len(country_hint_list))):
            for sector, sector_hint_list in sector_hints.items():
                sector_hint = random.choice(sector_hint_list)
                tpl = random.choice(
                    [
                        f"me indica açoes {sector_hint} {country_hint}",
                        f"scan {sector_hint} stocks in {country_hint}",
                        f"busque empresas de {sector_hint} no {country_hint}",
                        f"find {sector_hint} stocks {country_hint}",
                        f"liste {sector_hint} {country_hint}",
                        f"top {sector_hint} stocks {country_hint}",
                    ]
                )
                examples.append(
                    {
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": tpl},
                            {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "route": "market_scan",
                                        "intent": "market_scan",
                                        "action": "scan_market",
                                        "ticker": "",
                                        "time_horizon": "",
                                        "filters": {"country": country, "sector": sector},
                                        "entities": {
                                            "amount": None,
                                            "currency": None,
                                            "risk_tolerance": None,
                                            "asset_class": "stock",
                                        },
                                        "required_slots": [],
                                        "confidence": 0.90,
                                        "reasons": ["scan_command_with_country_and_sector"],
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        ]
                    }
                )

    # Penny stock scans
    penny_phrases = [
        ("me indica penny stocks canadenses", "Canada", None, "penny_stock"),
        ("find me microcap stocks", None, None, "penny_stock"),
        ("busque small caps no tsx", "Canada", None, "penny_stock"),
        ("liste penny stocks de tecnologia", None, "Technology", "penny_stock"),
        ("scan micro caps americanos", "United States", None, "penny_stock"),
        ("me sugira small caps brasileiras", "Brazil", None, "penny_stock"),
        ("oportunidades em penny stocks", None, None, "penny_stock"),
        ("quais as melhores microcaps do canada", "Canada", None, "penny_stock"),
        ("penny stocks to watch", None, None, "penny_stock"),
        ("small cap screener canada", "Canada", None, "penny_stock"),
        ("acoes de centavo tsx venture", "Canada", None, "penny_stock"),
        ("microcap technology scan", None, "Technology", "penny_stock"),
    ]
    for msg, country, sector, asset in penny_phrases:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "market_scan",
                                "intent": "market_scan",
                                "action": "scan_market",
                                "ticker": "",
                                "time_horizon": "",
                                "filters": {"country": country, "sector": sector},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": asset,
                                },
                                "required_slots": [],
                                "confidence": 0.90,
                                "reasons": ["scan_command_penny_universe"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    return examples


def general_question_examples():
    """Casual, educational, and non-financial questions."""
    examples = []

    # Greetings
    greetings = [
        "oi",
        "ola",
        "hello",
        "hey",
        "bom dia",
        "boa tarde",
        "boa noite",
        "good morning",
        "good afternoon",
        "hi there",
        "e ai",
        "ei",
        "oi tudo bem",
        "hello how are you",
        "hey what's up",
        "ola como vai",
    ]
    for msg in greetings:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "general",
                                "intent": "general_question",
                                "action": "answer",
                                "ticker": "",
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": None,
                                },
                                "required_slots": [],
                                "confidence": 0.97,
                                "reasons": ["casual_greeting"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # Educational questions
    edu = [
        ("what is a P/E ratio", "EN"),
        ("o que e RSI", "PT"),
        ("como funciona o MACD", "PT"),
        ("explique value investing", "PT"),
        ("what is beta in stocks", "EN"),
        ("como calcular VAR", "PT"),
        ("what is the difference between TSX and NYSE", "EN"),
        ("o que sao dividendos", "PT"),
        ("explique analise fundamentalista", "PT"),
        ("how does short selling work", "EN"),
        ("what are penny stocks", "EN"),
        ("o que e um ETF", "PT"),
        ("how do I read a candlestick chart", "EN"),
        ("como funciona o mercado de opcoes", "PT"),
        ("what is market cap", "EN"),
        ("explique diversificacao de carteira", "PT"),
        ("o que e alavancagem", "PT"),
        ("how to assess a company's debt", "EN"),
        ("what is a stock split", "EN"),
        ("o que e um pump and dump", "PT"),
        ("explain DCF valuation", "EN"),
        ("o que sao bonds", "PT"),
        ("how do interest rates affect stocks", "EN"),
        ("como usar o indicador RSI", "PT"),
        ("what is EBITDA", "EN"),
        ("o que e Sharpe ratio", "PT"),
        ("how to read a balance sheet", "EN"),
        ("como identificar tendencia de alta", "PT"),
        ("what is dollar cost averaging", "EN"),
        ("o que sao small caps", "PT"),
        ("explain moving averages", "EN"),
        ("qual a diferenca entre acao ordinaria e preferencial", "PT"),
        ("how to calculate intrinsic value", "EN"),
        ("o que e yield de dividendo", "PT"),
        ("what is a bear market", "EN"),
        ("por que açoes caem quando juros sobem", "PT"),
        ("how do stock buybacks work", "EN"),
        ("o que e uma acao defensiva", "PT"),
        ("explain the CAPM model", "EN"),
        ("como funciona o mercado de forex", "PT"),
    ]
    for msg, lang in edu:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "general",
                                "intent": "general_question",
                                "action": "answer",
                                "ticker": "",
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": None,
                                },
                                "required_slots": [],
                                "confidence": 0.92,
                                "reasons": ["educational_financial_question"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # Market context questions
    ctx = [
        "como esta o mercado hoje",
        "how is the market doing",
        "what's happening with interest rates",
        "o fed vai cortar juros",
        "how is the TSX performing",
        "qual a perspectiva para o petroleo",
        "what sectors are hot right now",
        "como esta a inflacao no Canada",
        "is it a good time to invest",
        "qual o sentimento do mercado",
        "how are tech stocks doing",
        "como esta o mercado canadense",
        "what's the outlook for gold",
        "o banco central vai subir juros",
        "how is the energy sector performing",
        "qual a expectativa para o S&P 500",
        "what's the VIX saying",
        "como esta a volatilidade do mercado",
        "are we in a bull or bear market",
        "qual o cenario macroeconomico atual",
    ]
    for msg in ctx:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "general",
                                "intent": "general_question",
                                "action": "answer",
                                "ticker": "",
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": None,
                                },
                                "required_slots": [],
                                "confidence": 0.88,
                                "reasons": ["market_context_question"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # Casual conversation
    casual = [
        "voce e um robo",
        "quem e voce",
        "what can you tell me about yourself",
        "vc entende portugues",
        "qual seu nome",
        "who created you",
        "voce usa IA",
        "como vc funciona por dentro",
        "are you better than chatgpt",
        "vc tem emocao",
        "voce e confiavel",
        "can I trust your analysis",
        "vc ja me conhece",
        "what model are you",
        "qual seu historico de acertos",
        "vc funciona 24 horas",
        "are you free to use",
        "como vc ganha dinheiro",
        "what's your track record",
        "vc tem vies",
    ]
    for msg in casual:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "general",
                                "intent": "general_question",
                                "action": "answer",
                                "ticker": "",
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": None,
                                },
                                "required_slots": [],
                                "confidence": 0.96,
                                "reasons": ["casual_or_identity_question"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    return examples


def explain_capabilities_examples():
    """Questions about tools, methods, and capabilities."""
    examples = []

    caps = [
        "quais ferramentas voce usa",
        "what tools do you use",
        "como voce pesquisa açoes",
        "how do you find opportunities",
        "qual sua metodologia de analise",
        "what data sources do you use",
        "como funciona seu pipeline",
        "what's your stack",
        "voce usa IA pra analisar",
        "how do you screen stocks",
        "quais fontes de dados vc tem",
        "what providers do you use",
        "como vc detecta fraudes",
        "how do you spot manipulation",
        "vc faz analise tecnica",
        "do you do fundamental analysis",
        "como vc calcula risco",
        "how do you assess risk",
        "o que vc consegue fazer",
        "what can you do",
        "what are your capabilities",
        "quais sao suas capacidades",
        "como vc analisa penny stocks",
        "how do you analyze microcaps",
        "qual seu processo de decisao",
        "what's your decision process",
        "vc usa machine learning",
        "do you use neural networks",
        "como vc avalia o sentimento do mercado",
        "how do you gauge market sentiment",
        "que indicadores tecnicos vc olha",
        "what technical indicators do you watch",
        "vc faz backtest",
        "do you backtest strategies",
        "como funciona seu risk scoring",
        "how does your risk scoring work",
        "vc conecta com alguma corretora",
        "do you integrate with brokers",
        "qual a frequencia de atualizacao dos dados",
        "how often is your data updated",
    ]
    for msg in caps:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "general",
                                "intent": "explain_capabilities",
                                "action": "answer_directly",
                                "ticker": "",
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": None,
                                },
                                "required_slots": [],
                                "confidence": 0.93,
                                "reasons": ["capability_or_method_question"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    return examples


def needs_scope_examples():
    """Vague requests without tickers — need scope/block."""
    examples = []

    # "I want to invest" without ticker — SHOULD be needs_scope, NOT market_scan
    vague_invest = [
        (
            "quero investir 500cad em alto risco para os proximo 15 dias",
            "CAD",
            500,
            "high",
            "15 days",
        ),
        ("I want to invest $1000 in aggressive stocks", "USD", 1000, "high", ""),
        ("quero colocar 2 mil reais em algo arriscado", "BRL", 2000, "high", ""),
        ("where should I invest 500 dollars", "USD", 500, None, ""),
        ("me recomenda onde investir", None, None, None, ""),
        ("qual a melhor acao para comprar agora", None, None, None, ""),
        ("best stock to buy right now", None, None, None, ""),
        ("I have 5000 CAD to invest short term", "CAD", 5000, None, "short term"),
        ("tenho 1000 reais pra investir curto prazo", "BRL", 1000, None, "short term"),
        ("me indica um investimento bom", None, None, None, ""),
        ("qual acao vai subir essa semana", None, None, None, "1 week"),
        ("what stock will go up this month", None, None, None, "1 month"),
        ("recomendacao de acao para day trade", None, None, "high", "1 day"),
        ("quero fazer dinheiro rapido na bolsa", None, None, "high", ""),
        ("o que comprar na b3 hoje", None, None, None, "today"),
        ("I'm looking for high growth stocks", None, None, "high", ""),
        ("quero investir em small caps", None, None, None, ""),
        ("me indica acao pra swing trade", None, None, "medium", "2 weeks"),
        ("where to put my money now", None, None, None, ""),
        ("qual setor vai bombar esse ano", None, None, None, "1 year"),
        ("I need investment advice for retirement", None, None, "low", "long term"),
        ("quero açoes que pagam dividendos", None, None, "low", ""),
        ("qual acao barata pra comprar", None, None, None, ""),
        ("me recomenda um portfolio diversificado", None, None, "medium", ""),
        ("what should I buy with $2000", "USD", 2000, None, ""),
    ]
    for msg, currency, amount, risk, horizon in vague_invest:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "needs_scope",
                                "intent": "unsafe_unspecified_recommendation",
                                "action": "ask_for_scope",
                                "ticker": "",
                                "time_horizon": horizon,
                                "filters": {},
                                "entities": {
                                    "amount": amount,
                                    "currency": currency,
                                    "risk_tolerance": risk,
                                    "asset_class": None,
                                },
                                "required_slots": ["ticker_or_screening_scope"],
                                "confidence": 0.87,
                                "reasons": ["vague_investment_request_without_ticker"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # "analyze penny stock" without naming which one
    missing_ticker = [
        "analisar penny stock",
        "analyze microcap",
        "run pennylab",
        "rodar pennylab",
        "analise completa de penny",
        "quero analisar uma small cap",
        "run full analysis on a penny",
        "roda pipeline completo numa penny",
        "ver uns numeros de uma small cap",
        "analise fundamentalista de uma microcap",
        "run the forensic check on a penny",
        "quero ver o pennylab de uma acao barata",
        "analyze a cheap stock for me",
        "roda o f51 numa small cap",
    ]
    for msg in missing_ticker:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "needs_scope",
                                "intent": "missing_required_slot",
                                "action": "ask_for_ticker",
                                "ticker": "",
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": "penny_stock",
                                },
                                "required_slots": ["ticker"],
                                "confidence": 0.91,
                                "reasons": ["analysis_requested_without_required_ticker"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    return examples


def edge_case_examples():
    """Tricky messages that break regex-based parsers."""
    examples = []

    # Time horizon compact that looks like ticker
    edge_time_ticker = [
        ("analise AAPL 14D", "AAPL", "14 days", "compact_time_horizon_not_ticker_num_prefix"),
        ("TSLA 6M analise", "TSLA", "6 months", "compact_time_horizon_not_ticker_num_prefix"),
        ("NVDA 1W verdict", "NVDA", "1 week", "compact_time_horizon_not_ticker_num_prefix"),
        ("ENB.TO 30D analysis", "ENB.TO", "30 days", "compact_time_horizon_tsx_ticker"),
        ("AAPL 3m chart", "AAPL", "3 months", "compact_time_horizon_lowercase"),
        ("what about PLTR for 2W", "PLTR", "2 weeks", "compact_time_horizon_en"),
        ("GOOGL 21d forecast", "GOOGL", "21 days", "compact_horizon_days_lower"),
        ("MSFT 6m outlook", "MSFT", "6 months", "compact_horizon_months_lower"),
        ("AMZN 4w target", "AMZN", "4 weeks", "compact_horizon_weeks_lower"),
        ("SHOP.TO 1m prediction", "SHOP.TO", "1 month", "compact_horizon_month_lower_tsx"),
        ("META 2W swing", "META", "2 weeks", "compact_horizon_swing_trade"),
        ("BABA 30D trade", "BABA", "30 days", "compact_horizon_trade"),
    ]
    for msg, ticker, horizon, reason in edge_time_ticker:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "ticker_analysis",
                                "intent": "ticker_analysis",
                                "action": "collect_data",
                                "ticker": ticker,
                                "time_horizon": horizon,
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": "stock",
                                },
                                "required_slots": [],
                                "confidence": 0.94,
                                "reasons": [reason],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # Currency amounts that are NOT tickers
    edge_currency = [
        ("investir 500cad em açoes", "", None, None, "currency_amount_not_ticker"),
        ("2000usd in stocks", "", None, None, "currency_amount_not_ticker"),
        ("put 50k in the market", "", None, None, "quantity_abbreviation_not_ticker"),
        ("comprar 1000 dol em TSLA", "TSLA", 1000, "USD", "amount_plus_ticker"),
        ("500 reais em PETR4", "PETR4", 500, "BRL", "amount_plus_ticker"),
        ("investir 2500cad em mineracao", "", None, None, "currency_amount_no_ticker"),
        ("10000usd in tech stocks", "", None, None, "currency_amount_no_ticker"),
        ("buy 500 cad worth of VALE3", "VALE3", 500, "CAD", "amount_plus_b3_ticker"),
        ("R$3000 em BBAS3", "BBAS3", 3000, "BRL", "amount_plus_b3_ticker"),
        ("put C$1500 in ENB.TO", "ENB.TO", 1500, "CAD", "amount_plus_tsx_ticker"),
    ]
    for msg, ticker, amount, currency, reason in edge_currency:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "ticker_analysis" if ticker else "needs_scope",
                                "intent": "ticker_analysis"
                                if ticker
                                else "unsafe_unspecified_recommendation",
                                "action": "collect_data" if ticker else "ask_for_scope",
                                "ticker": ticker,
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": amount,
                                    "currency": currency,
                                    "risk_tolerance": None,
                                    "asset_class": "stock" if ticker else None,
                                },
                                "required_slots": [] if ticker else ["ticker_or_screening_scope"],
                                "confidence": 0.90,
                                "reasons": [reason],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # Messages with real num_prefix tickers (must not be blocked)
    edge_real_num_tickers = [
        ("analyze 88E stock", "88E", "num_prefix_real_ticker_88energy"),
        ("what is 6M price", "6M", "num_prefix_potential_ticker_no_time_context"),
        ("3M company analysis", "3M", "num_prefix_real_ticker_3M_company"),
    ]
    for msg, ticker, reason in edge_real_num_tickers:
        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": msg},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "route": "ticker_analysis",
                                "intent": "ticker_analysis",
                                "action": "collect_data",
                                "ticker": ticker,
                                "time_horizon": "",
                                "filters": {},
                                "entities": {
                                    "amount": None,
                                    "currency": None,
                                    "risk_tolerance": None,
                                    "asset_class": "stock",
                                },
                                "required_slots": [],
                                "confidence": 0.88,
                                "reasons": [reason],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            }
        )

    # Mixed Portuguese/English
    edge_mixed = [
        ("cara analyze NVDA for me 14 days", "NVDA", "14 days", "mixed_language"),
        ("quero buy AAPL today", "AAPL", "", "mixed_language_casual"),
        ("whats the verdict on ENB.TO pra 2 semanas", "ENB.TO", "2 weeks", "mixed_language_tsx"),
        ("scan energy stocks no canada por favor", "", None, "mixed_scan_command"),
        ("cara run the pipeline on RY.TO por favor", "RY.TO", "", "mixed_pipeline_request"),
        ("me da um breakdown da TSLA para 1 month", "TSLA", "1 month", "mixed_breakdown"),
        ("I need analise completa de PETR4", "PETR4", "", "mixed_b3_analysis"),
        ("what are the best stocks no brasil", "", None, "mixed_scan_brazil"),
        ("busque tech companies in the US pra investir", "", None, "mixed_scan_us_tech"),
    ]
    for msg, ticker, horizon, reason in edge_mixed:
        if ticker:
            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": msg},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": "ticker_analysis",
                                    "intent": "ticker_analysis",
                                    "action": "collect_data",
                                    "ticker": ticker,
                                    "time_horizon": horizon if horizon else "",
                                    "filters": {},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": "stock",
                                    },
                                    "required_slots": [],
                                    "confidence": 0.90,
                                    "reasons": [reason],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )
        else:
            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": msg},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": "market_scan",
                                    "intent": "market_scan",
                                    "action": "scan_market",
                                    "ticker": "",
                                    "time_horizon": "",
                                    "filters": {"country": "Canada", "sector": "Energy"},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": "stock",
                                    },
                                    "required_slots": [],
                                    "confidence": 0.88,
                                    "reasons": [reason],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

    # Portuguese slang and typos
    edge_slang = [
        (
            "cara qual as ferramentas q vc usa pra pesquisa as opurtunidade do penny stock",
            "general",
            "explain_capabilities",
            "typo_capability_question",
        ),
        (
            "axo q a apple vai subi",
            "needs_scope",
            "unsafe_unspecified_recommendation",
            "vague_no_ticker_slang",
        ),
        (
            "mano analisa a PETR4 pra mim",
            "ticker_analysis",
            "ticker_analysis",
            "casual_slang_ticker",
        ),
        (
            "q q vc acha da vale",
            "needs_scope",
            "unsafe_unspecified_recommendation",
            "ambiguous_company_name_not_ticker",
        ),
        (
            "essa ação é uma merda mas quero analisar",
            "needs_scope",
            "missing_required_slot",
            "vulgar_no_ticker",
        ),
        ("vc manja de options", "general", "general_question", "slang_educational"),
        (
            "broder me fala da tesla",
            "needs_scope",
            "unsafe_unspecified_recommendation",
            "slang_company_not_ticker",
        ),
        (
            "mano q q c acha da nvidia",
            "needs_scope",
            "unsafe_unspecified_recommendation",
            "slang_company_not_ticker",
        ),
        ("ta ligado como analisa acao", "general", "general_question", "slang_educational"),
        (
            "irmao vamo investi na microsoft",
            "needs_scope",
            "unsafe_unspecified_recommendation",
            "slang_company_not_ticker",
        ),
        ("cade o tutorial disso aqui", "general", "explain_capabilities", "slang_capability"),
        ("fala ai chefe qual a boa", "general", "general_question", "slang_greeting"),
        (
            "q q ce acha daquela penny la da ventura",
            "needs_scope",
            "unsafe_unspecified_recommendation",
            "vague_penny_ref",
        ),
        (
            "man analisa essa acao pra nois",
            "needs_scope",
            "missing_required_slot",
            "slang_no_ticker",
        ),
        (
            "blz me manda o pipeline da PETR4",
            "ticker_analysis",
            "ticker_analysis",
            "slang_pipeline_ticker",
        ),
        ("ow analisa VALE3 ai rapidão", "ticker_analysis", "ticker_analysis", "slang_b3_ticker"),
        ("kd o scan de small cap", "market_scan", "market_scan", "slang_scan_request"),
        (
            "pprt quero saber qual acao compra",
            "needs_scope",
            "unsafe_unspecified_recommendation",
            "slang_vague_invest",
        ),
    ]
    for item in edge_slang:
        if len(item) == 4:
            msg, route, intent, reason = item
            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": msg},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": route,
                                    "intent": intent,
                                    "action": {
                                        "general": "answer",
                                        "explain_capabilities": "answer_directly",
                                        "ticker_analysis": "collect_data",
                                        "market_scan": "scan_market",
                                        "missing_required_slot": "ask_for_ticker",
                                        "unsafe_unspecified_recommendation": "ask_for_scope",
                                    }.get(intent, "answer"),
                                    "ticker": "",
                                    "time_horizon": "",
                                    "filters": {},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": None,
                                    },
                                    "required_slots": ["ticker"]
                                    if intent == "missing_required_slot"
                                    else (
                                        ["ticker_or_screening_scope"]
                                        if intent == "unsafe_unspecified_recommendation"
                                        else []
                                    ),
                                    "confidence": 0.82,
                                    "reasons": [reason],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )
        else:
            msg, ticker, horizon, reason = item[:4]
            examples.append(
                {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": msg},
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "route": "ticker_analysis",
                                    "intent": "ticker_analysis",
                                    "action": "collect_data",
                                    "ticker": ticker,
                                    "time_horizon": horizon if horizon else "",
                                    "filters": {},
                                    "entities": {
                                        "amount": None,
                                        "currency": None,
                                        "risk_tolerance": None,
                                        "asset_class": "stock",
                                    },
                                    "required_slots": [],
                                    "confidence": 0.84,
                                    "reasons": [reason],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                }
            )

    return examples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    root = Path(__file__).resolve().parent.parent

    all_examples = []

    print("Generating ticker_analysis examples...")
    all_examples.extend(ticker_analysis_examples())

    print("Generating market_scan examples...")
    all_examples.extend(market_scan_examples())

    print("Generating general_question examples...")
    all_examples.extend(general_question_examples())

    print("Generating explain_capabilities examples...")
    all_examples.extend(explain_capabilities_examples())

    print("Generating needs_scope examples...")
    all_examples.extend(needs_scope_examples())

    print("Generating edge case examples...")
    all_examples.extend(edge_case_examples())

    # Shuffle
    random.shuffle(all_examples)

    # Deduplicate by user message
    seen = set()
    deduped = []
    for ex in all_examples:
        user_msg = ex["messages"][1]["content"]
        if user_msg not in seen:
            seen.add(user_msg)
            deduped.append(ex)

    print(f"\nTotal unique examples: {len(deduped)}")

    # Distribution stats
    routes = {}
    intents = {}
    for ex in deduped:
        output = json.loads(ex["messages"][2]["content"])
        route = output["route"]
        intent = output["intent"]
        routes[route] = routes.get(route, 0) + 1
        intents[intent] = intents.get(intent, 0) + 1

    print("\nRoute distribution:")
    for r, c in sorted(routes.items(), key=lambda x: -x[1]):
        print(f"  {r}: {c} ({100 * c / len(deduped):.0f}%)")

    print("\nIntent distribution:")
    for i, c in sorted(intents.items(), key=lambda x: -x[1]):
        print(f"  {i}: {c} ({100 * c / len(deduped):.0f}%)")

    # Write training dataset
    train_path = root / "data" / "intent_training.jsonl"
    with open(train_path, "w", encoding="utf-8") as f:
        for ex in deduped:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"\nTraining dataset written to: {train_path}")

    # Write few-shot subset (best 50, diverse)
    # Pick representatives from each route+intent combo, proportional to prevalence
    fewshot = []
    combos_seen = {}
    for ex in deduped:
        output = json.loads(ex["messages"][2]["content"])
        key = output["route"] + ":" + output["intent"]
        if key not in combos_seen:
            combos_seen[key] = []
        combos_seen[key].append(ex)

    # Take up to 12 per combo for even coverage
    for exs in combos_seen.values():
        random.shuffle(exs)
        fewshot.extend(exs[:12])
    random.shuffle(fewshot)
    fewshot = fewshot[:50]

    fewshot_path = root / "data" / "intent_fewshot.jsonl"
    with open(fewshot_path, "w", encoding="utf-8") as f:
        for ex in fewshot:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Few-shot subset ({len(fewshot)} examples) written to: {fewshot_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
