"""Dados canned e fakes para testes do SuperEzio pipeline."""

CANNED_TECHNICALS = {
    "ticker": "AAPL",
    "price": 187.32,
    "change_pct": 1.24,
    "volume": 52400000,
    "rsi": 58.3,
    "macd": 2.15,
    "macd_signal": 1.87,
    "sma_20": 185.40,
    "sma_50": 182.10,
    "sma_200": 175.60,
    "ema_20": 186.10,
    "bb_upper": 192.50,
    "bb_lower": 178.30,
    "atr": 3.45,
    "data_quality": "provider_or_computed",
}

CANNED_PROFILE = {
    "name": "Apple Inc.",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "market_cap": 2900000000000,
    "pe_ratio": 31.2,
    "forward_pe": 28.5,
    "eps": 6.01,
    "dividend_yield": 0.52,
    "beta": 1.22,
    "description": "Apple Inc. designs, manufactures, and markets smartphones...",
}

CANNED_NEWS = {
    "sentiment_label": "neutral",
    "sentiment_score": 0.12,
    "news_count": 18,
    "top_headline": "Apple Reports Record Q2 Revenue",
    "top_snippet": "Apple announced record quarterly revenue of $94.8 billion...",
    "sources": ["Yahoo Finance", "MarketWatch", "Reuters"],
}

CANNED_REDDIT = {
    "signal_label": "mildly_bullish",
    "qualified_count": 4,
    "total_posts": 8,
    "top_posts": [
        {"title": "AAPL earnings discussion", "score": 342, "num_comments": 89},
        {"title": "Apple Vision Pro sales numbers", "score": 256, "num_comments": 67},
    ],
}

CANNED_MACRO_CA = {
    "policy_rate": {"current_value": 4.50, "series": "V39079"},
    "cpi": {"current_value": 2.8, "series": "V41690973", "yoy_pct": 2.8},
    "usd_cad": {"current_value": 1.3650, "series": "FXUSDCAD"},
    "source": "Bank of Canada Valet API",
}

CANNED_EXPERT_RESPONSE = {
    "role": "fundamental",
    "ok": True,
    "provider": "deepseek",
    "stance": "bullish",
    "confidence": 0.72,
    "signals": ["Strong revenue growth", "Expanding margins", "High ROE"],
    "recommendation": "Accumulate on dips below $185",
    "raw": "AAPL shows strong fundamentals with 22% revenue growth...",
    "contradictions": [],
}

CANNED_CEO_CHUNKS = [
    "AAPL",
    " is",
    " a",
    " hold",
    " at",
    " current",
    " levels",
    ".",
    " RSI",
    " neutral",
    " at",
    " 58",
    ",",
    " MACD",
    " bullish",
    ".",
    " Wait",
    " for",
    " a",
    " pullback",
    " to",
    " $",
    "180",
    " before",
    " adding",
    ".",
]

CANNED_DATA_COLLECTED = {
    "ticker": "AAPL",
    "technicals": CANNED_TECHNICALS,
    "profile": CANNED_PROFILE,
    "quant": {"monte_carlo_paths": 1000, "expected_return": 12.5, "var_95": -18.2},
    "risk": {
        "var_95": -18.2,
        "cvar_95": -22.8,
        "sharpe": 0.85,
        "sortino": 1.12,
        "max_drawdown": -28.5,
    },
    "sentiment": CANNED_NEWS,
    "reddit": CANNED_REDDIT,
    "macro": CANNED_MACRO_CA,
    "crisis": {"systemic_risk_score": 0.23, "bubble_risk_score": 0.15},
    "realtime_price": {"price": 187.32, "source": "yfinance"},
    "quantum": {"simulation_complete": True, "shots": 1000},
    "data_quality": "provider_or_computed",
    "source_errors": [],
    "analysis_id": "test-analysis-001",
    "elapsed_s": 2.3,
}

CANNED_DATA_TIMEOUT = {
    "data_quality": "timeout",
    "source_errors": ["collector_timeout"],
    "technicals": {"error": "timeout"},
    "analysis_id": "test-timeout-001",
}

CANNED_DATA_PARTIAL = {
    "technicals": CANNED_TECHNICALS,
    "profile": CANNED_PROFILE,
    "sentiment": CANNED_NEWS,
    "quant": {"error": "import_error"},
    "risk": {"error": "computation_failed"},
    "reddit": {"error": "disabled"},
    "macro": CANNED_MACRO_CA,
    "crisis": {"error": "no_data"},
    "realtime_price": CANNED_TECHNICALS["price"],
    "quantum": {"error": "simulation_error"},
    "data_quality": "partial",
    "source_errors": [
        "quant:import_error",
        "risk:computation_failed",
        "reddit:disabled",
        "crisis:no_data",
    ],
    "analysis_id": "test-partial-001",
}


# ── Fake classes para testes ────────────────────────────────────────────


class FakeAsyncGenerator:
    """Simula o async generator do gateway.stream_generate_async."""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._idx]
        self._idx += 1
        return chunk


class FakeProvider:
    """Provider falso que retorna chunks canned."""

    def __init__(self, name="fake", chunks=None):
        self.name = name
        self.is_local = False
        self.backend = "openai_compatible"
        self.api_key = "fake-key"
        self.base_url = "http://fake/v1"
        self.model = "fake-model"
        self.timeout_s = 30
        self.max_tokens = 512
        self.temperature = 0.7
        self._chunks = chunks or CANNED_CEO_CHUNKS

    def configure_thinking(self, *args, **kwargs):
        pass


class FakeGateway:
    """Gateway falso para testes do pipeline."""

    def __init__(self, chunks=None, fail_until=None):
        self._chunks = chunks or CANNED_CEO_CHUNKS
        self._call_count = 0
        self._fail_until = fail_until  # falha as primeiras N chamadas

    def stream_generate_async(self, *args, **kwargs):
        self._call_count += 1
        if self._fail_until and self._call_count <= self._fail_until:
            raise RuntimeError("fake provider error")

        async def _gen():
            for c in self._chunks:
                yield c

        return _gen()

    def provider(self, name):
        return FakeProvider(name=name)
