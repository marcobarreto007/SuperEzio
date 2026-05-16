import asyncio
import json
import logging
import os
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from core.engine.indicators import (
    calc_bollinger,
    calc_ema,
    calc_macd,
    calc_rsi,
    calc_sma,
)

from .protocol import A2AMessage, MessageType

logger = logging.getLogger(__name__)
router = APIRouter()

VAGUE_FINANCIAL_RESPONSE = (
    "Para análise financeira, informe pelo menos um ativo/ticker e o contexto desejado "
    "(ex.: AAPL, tendência, risco, valuation, notícias)."
)


def has_hint(text: str, hints: tuple[str, ...]) -> bool:
    low = (text or "").lower()
    return any(h.lower() in low for h in hints)


def detect_ticker(text: str) -> str:
    if not text:
        return ""
    m = _TICKER_RE.search(text.upper())
    if not m:
        return ""
    return next((g for g in m.groups() if g), "")


def should_block_vague_financial_prompt(
    raw_message: str,
    detected_ticker: str,
    rigor: str,
) -> bool:
    if detected_ticker:
        return False
    if (rigor or "").lower() not in {"strict", "high", "hard"}:
        return False
    msg = (raw_message or "").strip().lower()
    if not msg:
        return True
    finance_terms = (
        "acao",
        "ação",
        "stock",
        "ticker",
        "mercado",
        "invest",
        "trade",
        "buy",
        "sell",
        "valuation",
        "risco",
        "portfolio",
    )
    return any(term in msg for term in finance_terms)


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------


PERIOD_MAP = {
    "1D": ("1d", "5m"),
    "1W": ("5d", "15m"),
    "1M": ("1mo", "1h"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
}

SSE_PERIOD_MAP = {
    "1D": ("1d", "1m"),
    "1W": ("5d", "5m"),
    "1M": ("1mo", "15m"),
    "3M": ("3mo", "30m"),
    "6M": ("6mo", "1h"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
}


def _sanitize_ticker(raw: str) -> str:
    clean_ticker = re.sub(r"[^\w.\-\^]", "", raw).upper()
    if not clean_ticker:
        raise HTTPException(status_code=400, detail="Ticker invalido")
    return clean_ticker


def _build_ohlcv(df) -> list[dict[str, Any]]:
    ohlcv: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        ts = idx
        t = int(ts.timestamp()) if hasattr(ts, "timestamp") else int(ts)
        ohlcv.append(
            {
                "time": t,
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row.get("Volume", 0)),
            }
        )
    return ohlcv


@router.get("/api/chart-data/{ticker}")
async def get_chart_data(
    ticker: str,
    timeframe: str = Query("6M", pattern="^(1D|1W|1M|3M|6M|1Y|5Y)$"),
) -> dict:
    """Retorna OHLCV + indicadores tecnicos para renderizar charts."""
    import yfinance as yf

    clean_ticker = _sanitize_ticker(ticker)

    period, interval = PERIOD_MAP.get(timeframe, ("6mo", "1d"))

    try:
        stock = yf.Ticker(clean_ticker)
        df = stock.history(period=period, interval=interval)
        if df.empty:
            raise HTTPException(
                status_code=404, detail=f"Sem dados para {clean_ticker}"
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erro yfinance: {exc}") from exc

    try:
        raw_info = stock.info or {}
        info = {
            "name": raw_info.get("shortName")
            or raw_info.get("longName")
            or clean_ticker,
            "sector": raw_info.get("sector"),
            "currency": raw_info.get("currency", "USD"),
            "exchange": raw_info.get("exchange"),
            "market_cap": raw_info.get("marketCap"),
        }
    except Exception as exc:
        logger.warning("yfinance info lookup failed for %s: %s", clean_ticker, exc)
        info = {"name": clean_ticker, "lookup_error": str(exc)[:200]}

    ohlcv = _build_ohlcv(df)

    closes = [c["close"] for c in ohlcv]
    times = [c["time"] for c in ohlcv]

    def _series(values):
        return [{"time": t, "value": v} for t, v in zip(times, values) if v is not None]

    current_price = closes[-1] if closes else None
    prev_close = closes[-2] if len(closes) > 1 else closes[0] if closes else None
    change = None
    change_pct = None
    if current_price is not None and prev_close is not None and prev_close != 0:
        change = round(current_price - prev_close, 4)
        change_pct = round((change / prev_close) * 100, 2)

    macd_data = calc_macd(closes)
    bb = calc_bollinger(closes)
    return {
        "ticker": clean_ticker,
        "timeframe": timeframe,
        "profile": info,
        "price": {
            "current": current_price,
            "previous_close": prev_close,
            "change": change,
            "change_pct": change_pct,
        },
        "ohlcv": ohlcv,
        "indicators": {
            "sma20": _series(calc_sma(closes, 20)),
            "sma50": _series(calc_sma(closes, 50)),
            "ema20": _series(calc_ema(closes, 20)),
            "rsi": _series(calc_rsi(closes)),
            "macd": _series(macd_data["macd"]),
            "macd_signal": _series(macd_data["signal"]),
            "macd_histogram": _series(macd_data["histogram"]),
            "bb_upper": _series(bb["upper"]),
            "bb_middle": _series(bb["middle"]),
            "bb_lower": _series(bb["lower"]),
        },
    }


@router.get("/api/chart-sse/{ticker}")
async def stream_chart_data(
    ticker: str,
    request: Request,
    timeframe: str = Query("1D", pattern="^(1D|1W|1M|3M|6M|1Y|5Y)$"),
    refresh_s: int = Query(3, ge=1, le=30),
    max_points: int = Query(180, ge=30, le=500),
):
    """SSE de velas em tempo real (polling) para painel live no frontend.

    Não altera o contrato NDJSON de /task/submit.
    """
    import yfinance as yf

    clean_ticker = _sanitize_ticker(ticker)
    period, interval = SSE_PERIOD_MAP.get(timeframe, ("1d", "1m"))

    async def _event_gen():
        last_sig = ""
        first_snapshot = True

        while True:
            if await request.is_disconnected():
                break

            try:
                stock = yf.Ticker(clean_ticker)
                df = await asyncio.to_thread(
                    stock.history,
                    period=period,
                    interval=interval,
                )
                if df.empty:
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {
                                "ticker": clean_ticker,
                                "detail": "Sem dados de vela para o ticker/timeframe.",
                                "timeframe": timeframe,
                            }
                        ),
                    }
                else:
                    ohlcv = _build_ohlcv(df.tail(max_points))
                    latest = ohlcv[-1]
                    signature = f"{latest['time']}:{latest['close']}:{latest['volume']}:{len(ohlcv)}"

                    if first_snapshot:
                        payload = {
                            "ticker": clean_ticker,
                            "timeframe": timeframe,
                            "interval": interval,
                            "server_ts": int(time.time()),
                            "ohlcv": ohlcv,
                            "latest": latest,
                        }
                        yield {"event": "snapshot", "data": json.dumps(payload)}
                        first_snapshot = False
                    elif signature != last_sig:
                        payload = {
                            "ticker": clean_ticker,
                            "timeframe": timeframe,
                            "interval": interval,
                            "server_ts": int(time.time()),
                            "latest": latest,
                            "tail": ohlcv[-5:],
                        }
                        yield {"event": "candle", "data": json.dumps(payload)}

                    last_sig = signature

            except Exception as exc:
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {
                            "ticker": clean_ticker,
                            "detail": str(exc)[:300],
                            "timeframe": timeframe,
                        }
                    ),
                }

            yield {
                "event": "heartbeat",
                "data": json.dumps({"ts": int(time.time()), "ticker": clean_ticker}),
            }
            await asyncio.sleep(refresh_s)

    return EventSourceResponse(_event_gen(), ping=15)


PRODUCT_MANIFEST = {
    "product_name": "SuperEzio",
    "positioning": "Financial copilot with one pipeline, verifiable evidence, and risk guardrails.",
    "operating_principles": [
        "Evidence-based analysis, never a buy or sell order.",
        "Current financial numbers must come from collected sources with evidence_id.",
        "Missing data blocks strong conclusions and favors STUDY_MORE or WAIT.",
        "Fraud/manipulation patterns are treated as red flags, never accusations.",
        "The final verdict must show conflicts, missing data, and the permitted next step.",
    ],
    "safe_actions": ["STUDY_MORE", "WATCHLIST", "WAIT", "SMALL_POSITION", "AVOID"],
    "committee": {
        "fast_mode": {
            "label": "Family Investor Committee",
            "agent_count": 7,
            "roles": [
                "Orchestrator",
                "Education Agent",
                "Company Analyst",
                "ETF Portfolio Agent",
                "Risk Officer",
                "Devils Advocate",
                "Decision Journal Agent",
            ],
        },
        "full_mode": {
            "label": "Institutional Committee",
            "agent_count": 12,
            "roles": [
                "Fundamental Analyst",
                "Technical Analyst",
                "Risk Manager",
                "Sentiment Analyst",
                "Macroeconomist",
                "Portfolio Optimizer",
                "Fixed Income Analyst",
                "Quant Strategist",
                "ESG Analyst",
                "Derivatives Analyst",
                "Compliance Officer",
                "Sector Analyst",
            ],
        },
    },
    "penny_guardrail": {
        "label": "PennyLab Guardrail",
        "agent_count": 5,
        "mode": "optional",
        "description": (
            "Optional forensic layer for penny-stock workflows. It does not "
            "replace the 12-expert institutional committee."
        ),
        "roles": [
            "Fraud Hunter",
            "Flow Analyst",
            "Ruin Calculator",
            "Sentiment Detective",
            "Market Context",
        ],
    },
    "workflow": [
        {
            "id": "orchestrator_primary",
            "label": "Orchestrator",
            "description": "Orchestrator classifies route, ticker, and data needs.",
        },
        {
            "id": "data",
            "label": "Evidence",
            "description": "Collects price, fundamentals, technicals, news, risk, and memory when available.",
        },
        {
            "id": "experts_12",
            "label": "12 Experts",
            "description": "Experts analyze the same data under an anti-guessing contract.",
        },
        {
            "id": "ceo_primary",
            "label": "Local CEO (Gemma-4-26B-A4B-abliterated)",
            "description": "Local Gemma-4-26B CEO consolidates conflicts and chooses one permitted next step. CEO is local-only, Q4_K_M GGUF via llama-cpp.",
        },
    ],
    "decision_modes": [
        "Ticker analysis",
        "Decision diary",
        "Market research",
        "Watchlist",
        "Decision history",
    ],
}

# Regex para detectar tickers em mensagens do usuário
_TICKER_RE = re.compile(
    r"\b([A-Z]{1,5}(?:34|4|3|11)?\.(?:SA|TO|V))\b"  # BR/CA: PETR4.SA, RY.TO
    r"|\b([A-Z]{1,5})\b"  # US: AAPL, MSFT
)

_SMALLTALK_RE = re.compile(
    r"^\s*(?:"
    r"hi|hello|hey|yo|sup|"
    r"oi|ola|olá|e ai|e aí|"
    r"bom dia|boa tarde|boa noite|"
    r"tudo bem|como vai|who are you|quem e voce|quem é você"
    r")(?:[!.?\s]+)?$",
    re.IGNORECASE,
)

_CHART_CONTEXT_HINTS = (
    "grafico",
    "gráfico",
    "chart",
    "candle",
    "candles",
    "vela",
    "velas",
    "ohlcv",
    "suporte",
    "resistencia",
    "resistência",
    "trend",
    "tendencia",
    "tendência",
    "price action",
    "rsi",
    "macd",
    "sma",
    "ema",
    "volume",
    "bollinger",
    "rompimento",
    "pullback",
    "setup",
    "entry",
    "stop",
    "target",
    "alvo",
    "indicador",
    "indicator",
    "esta acao",
    "esta ação",
    "essa acao",
    "essa ação",
    "esse ativo",
    "este ativo",
    "this stock",
    "this asset",
    "this ticker",
    "this chart",
    "current chart",
    "current stock",
    "ticker atual",
    "ativo atual",
    "ativo na tela",
    "na tela",
    "no grafico",
    "no gráfico",
    "que voce ve",
    "que você vê",
    "olhando isso",
    "olhando o grafico",
    "olhando o gráfico",
)


_MAX_MESSAGE_CHARS = 8_000
_MAX_CHART_CONTEXT_CHARS = 20_000
_SECRET_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def _safe_error_detail(exc: Exception) -> str:
    detail = str(exc) or exc.__class__.__name__
    for key, value in os.environ.items():
        if (
            value
            and len(value) >= 8
            and any(marker in key.upper() for marker in _SECRET_ENV_MARKERS)
        ):
            detail = detail.replace(value, "[REDACTED]")
    return detail[:500]


def _should_include_chart_context(raw_message: str, detected_ticker: str) -> bool:
    """Decide se o chart_context deve influenciar a resposta.

    Regras:
    - Se o usuario falou um ticker explicitamente, pode anexar.
    - Small talk/greetings nunca devem herdar o ativo atual do grafico.
    - Sem ticker explicito, so anexamos se a mensagem parecer de analise
      tecnica/financeira ou fizer referencia ao grafico/ativo atual.
    """
    message = (raw_message or "").strip()
    if not message:
        return False
    if detected_ticker:
        return True
    if _SMALLTALK_RE.match(message):
        return False

    return has_hint(message, _CHART_CONTEXT_HINTS)


def _get_pipeline(request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    if not pipeline:
        raise HTTPException(
            status_code=500, detail="Brain not initialized (Pipeline missing)"
        )
    return pipeline


@router.post("/task/submit")
async def submit_task(envelope: A2AMessage, request: Request) -> StreamingResponse:
    """Submit a task to the pipeline and stream NDJSON updates."""
    logger.info("Received task: %s from %s", envelope.type, envelope.from_agent)

    if envelope.type != MessageType.TASK_SUBMIT:
        raise HTTPException(
            status_code=400, detail="Invalid message type for this endpoint"
        )

    pipeline = _get_pipeline(request)

    try:
        payload = envelope.payload if isinstance(envelope.payload, dict) else {}
        raw_message = (
            payload.get("message")
            or payload.get("task_description")
            or str(envelope.payload or "")
        )
        if not isinstance(raw_message, str):
            raw_message = str(raw_message)
        if len(raw_message) > _MAX_MESSAGE_CHARS:
            raise HTTPException(
                status_code=413,
                detail=f"Message too large. Limit is {_MAX_MESSAGE_CHARS} characters.",
            )
        prompt = raw_message
        session_id = payload.get("session_id") or envelope.from_agent or "default"
        memory_mode = payload.get("memory_mode") or "relevant_all"
        rigor = payload.get("rigor") or "strict"
        chart_context = str(payload.get("chart_context") or "")
        if len(chart_context) > _MAX_CHART_CONTEXT_CHARS:
            chart_context = chart_context[:_MAX_CHART_CONTEXT_CHARS]

        # Ticker from UI field takes priority; fall back to message text detection
        explicit_ticker = str(payload.get("ticker") or "").strip()
        detected_ticker = explicit_ticker or detect_ticker(raw_message)
        block_vague_financial = should_block_vague_financial_prompt(
            raw_message,
            detected_ticker,
            rigor,
        )

        # Inject chart context only when the user is actually asking
        # about the chart / current asset / financial analysis.
        context_block = ""
        if (
            chart_context
            and not block_vague_financial
            and _should_include_chart_context(raw_message, detected_ticker)
        ):
            context_block = (
                "\n\n[CHART_VISUAL_CONTEXT]\n"
                f"{chart_context}\n"
                "The user is viewing this chart now. Use these OHLCV data to "
                "discuss candle patterns, support, resistance, trends, and any "
                "relevant technical observation. Be specific about what the candles show.\n"
                "[/CHART_VISUAL_CONTEXT]"
            )

        # Chat unificado: o endpoint cuida do envelope, guardrails de entrada
        # e streaming NDJSON. O pipeline emite eventos estruturados quando
        # suporta stream_events; chat_async fica como fallback de testes.

        async def stream_result() -> AsyncGenerator[str, None]:
            if detected_ticker:
                yield (
                    json.dumps({"type": "CHART_DATA", "ticker": detected_ticker}) + "\n"
                )
            yield json.dumps({"type": "STREAM_START", "msg_id": envelope.msg_id}) + "\n"

            try:
                if block_vague_financial:
                    yield (
                        json.dumps(
                            {"type": "CHUNK", "content": VAGUE_FINANCIAL_RESPONSE}
                        )
                        + "\n"
                    )
                    yield json.dumps({"type": "STREAM_END"}) + "\n"
                    return

                if hasattr(pipeline, "stream_events"):
                    async for event in pipeline.stream_events(
                        prompt,
                        context=context_block,
                        session_id=session_id,
                        memory_mode=memory_mode,
                        rigor=rigor,
                        ticker=detected_ticker,
                    ):
                        if isinstance(event, dict):
                            yield json.dumps(event, ensure_ascii=False) + "\n"
                        else:
                            yield (
                                json.dumps(
                                    {"type": "CHUNK", "content": str(event)},
                                    ensure_ascii=False,
                                )
                                + "\n"
                            )
                else:
                    chat_iter = pipeline.chat_async(
                        prompt,
                        context=context_block,
                        session_id=session_id,
                        memory_mode=memory_mode,
                        rigor=rigor,
                        ticker=detected_ticker,
                    )
                    async for chunk in chat_iter:
                        if isinstance(chunk, dict):
                            yield json.dumps(chunk, ensure_ascii=False) + "\n"
                            continue
                        if isinstance(chunk, str):
                            raw_chunk = chunk.strip()
                            if raw_chunk.startswith("{") and raw_chunk.endswith("}"):
                                try:
                                    event = json.loads(raw_chunk)
                                    if event.get("type") in {"CHART_DATA"}:
                                        yield (
                                            json.dumps(event, ensure_ascii=False) + "\n"
                                        )
                                        continue
                                except json.JSONDecodeError:
                                    pass
                        yield (
                            json.dumps(
                                {"type": "CHUNK", "content": chunk}, ensure_ascii=False
                            )
                            + "\n"
                        )

                yield json.dumps({"type": "STREAM_END"}) + "\n"
            except Exception as exc:
                yield (
                    json.dumps({"type": "ERROR", "detail": _safe_error_detail(exc)})
                    + "\n"
                )
                yield json.dumps({"type": "STREAM_END"}) + "\n"

        return StreamingResponse(stream_result(), media_type="application/x-ndjson")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_safe_error_detail(exc)) from exc


@router.get("/capabilities")
async def get_capabilities(request: Request) -> dict:
    pipeline = getattr(request.app.state, "pipeline", None)

    if pipeline and pipeline.tools:
        supported = pipeline.tools.list_tools()
    else:
        supported = ["echo (fallback)"]

    return {
        "agent": "f51_universal",
        "supported_tasks": supported,
        "brain": "UnifiedPipeline",
        "orchestrator": None,
        "product": PRODUCT_MANIFEST,
    }


@router.get("/product/manifest")
async def product_manifest(request: Request) -> dict:
    """Public product contract consumed by the browser UI."""
    pipeline = getattr(request.app.state, "pipeline", None)
    status = pipeline.get_status() if pipeline else {}
    tools = pipeline.tools.list_tools() if pipeline and pipeline.tools else []
    manifest = dict(PRODUCT_MANIFEST)
    manifest["runtime"] = {
        "brain": "UnifiedPipeline",
        "tools_count": len(tools),
        "tools": tools,
        "status": status,
    }
    return manifest
