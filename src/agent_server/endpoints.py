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

from core.math.indicators import (
    calc_bollinger,
    calc_ema,
    calc_macd,
    calc_rsi,
    calc_sma,
)
from core.pipeline.intents import (
    detect_ticker,
    should_block_vague_financial_prompt,
    has_hint,
)
from core.risk_firewall import DecisionCandidate, evaluate_decision_with_sdca
from data.data_hub import hub

from .protocol import A2AMessage, MessageType

logger = logging.getLogger(__name__)
router = APIRouter()

VAGUE_FINANCIAL_RESPONSE = (
    "Para análise financeira, informe pelo menos um ativo/ticker, o prazo desejado "
    "(ex.: AAPL 14 dias, tendência, risco, valuation, notícias)."
)


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------


VALID_TIMEFRAMES = frozenset({"1D", "1W", "1M", "3M", "6M", "1Y", "5Y"})

SSE_REFRESH_INTERVAL: dict[str, int] = {
    "1D": 2,
    "1W": 3,
    "1M": 5,
    "3M": 10,
    "6M": 15,
    "1Y": 30,
    "5Y": 30,
}


def _sanitize_ticker(raw: str) -> str:
    clean_ticker = re.sub(r"[^\w.\-\^]", "", raw).upper()
    if not clean_ticker:
        raise HTTPException(status_code=400, detail="Ticker invalido")
    return clean_ticker


def _parse_candle_time(raw: str) -> int:
    """Converte timestamp string do provider para Unix epoch (segundos)."""
    from datetime import datetime

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(raw, fmt).timestamp())
        except ValueError:
            continue
    return 0


def _build_ohlcv(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normaliza candles de qualquer provider para o formato do frontend."""
    ohlcv: list[dict[str, Any]] = []
    for c in candles:
        t_raw = c.get("time", "")
        t = int(t_raw) if isinstance(t_raw, (int, float)) else _parse_candle_time(str(t_raw))
        ohlcv.append(
            {
                "time": t,
                "open": round(float(c["open"]), 4),
                "high": round(float(c["high"]), 4),
                "low": round(float(c["low"]), 4),
                "close": round(float(c["close"]), 4),
                "volume": int(c.get("volume", 0)),
            }
        )
    return ohlcv


@router.get("/api/chart-data/{ticker}")
async def get_chart_data(
    ticker: str,
    timeframe: str = Query("6M", pattern="^(1D|1W|1M|3M|6M|1Y|5Y)$"),
) -> dict:
    """Retorna OHLCV + indicadores tecnicos para renderizar charts — via DataHub."""
    clean_ticker = _sanitize_ticker(ticker)

    result = hub.get_candles(clean_ticker, timeframe=timeframe)
    if "error" in result:
        attempts = result.get("attempts", [])
        detail = result["error"] if not attempts else str(attempts)
        raise HTTPException(status_code=502, detail=f"DataHub: {detail}")

    candles = result.get("candles", [])
    if not candles:
        raise HTTPException(status_code=404, detail=f"Sem dados para {clean_ticker}")

    profile_result = hub.get_profile(clean_ticker)
    if "error" in profile_result:
        logger.warning(
            "Profile lookup failed for %s: %s",
            clean_ticker,
            profile_result.get("error"),
        )
        info: dict[str, Any] = {"name": clean_ticker}
    else:
        info = {
            "name": profile_result.get("name") or clean_ticker,
            "sector": profile_result.get("sector"),
            "currency": profile_result.get("currency", "USD"),
            "exchange": profile_result.get("exchange"),
            "market_cap": profile_result.get("market_cap"),
        }

    ohlcv = _build_ohlcv(candles)

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
    """SSE de velas em tempo real (polling) para painel live — via DataHub."""

    clean_ticker = _sanitize_ticker(ticker)
    default_refresh = SSE_REFRESH_INTERVAL.get(timeframe, 3)
    effective_refresh = max(refresh_s, default_refresh)

    async def _event_gen():
        last_sig = ""
        first_snapshot = True

        while True:
            if await request.is_disconnected():
                break

            try:
                result = await asyncio.to_thread(hub.get_candles, clean_ticker, timeframe=timeframe)
                if "error" in result:
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {
                                "ticker": clean_ticker,
                                "detail": str(
                                    result.get("error") or result.get("attempts", "Unknown")
                                ),
                                "timeframe": timeframe,
                            }
                        ),
                    }
                else:
                    all_candles = _build_ohlcv(result.get("candles", []))
                    ohlcv = (
                        all_candles[-max_points:] if len(all_candles) > max_points else all_candles
                    )
                    if not ohlcv:
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
                        latest = ohlcv[-1]
                        signature = (
                            f"{latest['time']}:{latest['close']}:{latest['volume']}:{len(ohlcv)}"
                        )

                        if first_snapshot:
                            payload = {
                                "ticker": clean_ticker,
                                "timeframe": timeframe,
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
            await asyncio.sleep(effective_refresh)

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
            "label": "Local CEO (Qwen3.6-35B Q4_K_M)",
            "description": "Local Qwen3.6-35B CEO via llama.cpp — consolidates conflicts and chooses one permitted next step.",
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
        raise HTTPException(status_code=500, detail="Brain not initialized (Pipeline missing)")
    return pipeline


@router.post("/task/submit")
async def submit_task(envelope: A2AMessage, request: Request) -> StreamingResponse:
    """Submit a task to the pipeline and stream NDJSON updates."""
    logger.info("Received task: %s from %s", envelope.type, envelope.from_agent)

    if envelope.type != MessageType.TASK_SUBMIT:
        raise HTTPException(status_code=400, detail="Invalid message type for this endpoint")

    pipeline = _get_pipeline(request)

    try:
        payload = envelope.payload if isinstance(envelope.payload, dict) else {}
        raw_message = (
            payload.get("message") or payload.get("task_description") or str(envelope.payload or "")
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
                yield (json.dumps({"type": "CHART_DATA", "ticker": detected_ticker}) + "\n")
            yield json.dumps({"type": "STREAM_START", "msg_id": envelope.msg_id}) + "\n"

            try:
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
                                        yield (json.dumps(event, ensure_ascii=False) + "\n")
                                        continue
                                except json.JSONDecodeError:
                                    pass
                        yield (
                            json.dumps({"type": "CHUNK", "content": chunk}, ensure_ascii=False)
                            + "\n"
                        )

                yield json.dumps({"type": "STREAM_END"}) + "\n"
            except Exception as exc:
                yield (json.dumps({"type": "ERROR", "detail": _safe_error_detail(exc)}) + "\n")
                yield json.dumps({"type": "STREAM_END"}) + "\n"

        return StreamingResponse(stream_result(), media_type="application/x-ndjson")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_safe_error_detail(exc)) from exc


@router.get("/capabilities")
async def get_capabilities(request: Request) -> dict:
    return {
        "agent": "f51_universal",
        "supported_tasks": [
            "echo",
            "task/submit (pipeline completo)",
            "experts/neural-decision/predict",
            "api/sdca/evaluate",
            "experts/pennylab/predict",
            "data/providers",
        ],
        "brain": "UnifiedPipeline",
        "orchestrator": None,
        "product": PRODUCT_MANIFEST,
    }


@router.get("/product/manifest")
async def product_manifest(request: Request) -> dict:
    """Public product contract consumed by the browser UI."""
    pipeline = getattr(request.app.state, "pipeline", None)
    status = pipeline.get_status() if pipeline else {}
    manifest = dict(PRODUCT_MANIFEST)
    manifest["runtime"] = {
        "brain": "UnifiedPipeline",
        "status": status,
    }
    return manifest


@router.post("/api/sdca/evaluate")
async def evaluate_sdca(candidate: DecisionCandidate) -> dict:
    """Evaluate a candidate decision with SDCA-Lite. Does not execute trades."""

    decision = evaluate_decision_with_sdca(candidate)
    return decision.model_dump(mode="json")


@router.post("/experts/neural-decision/predict")
async def predict_neural_decision(payload: dict) -> dict:
    """Evaluate technical signals and risk regimes via NeuralDecisionExpert."""
    from experts.neural_decision import NeuralDecisionExpert

    symbol = payload.get("symbol", "")
    timeframe = payload.get("timeframe", "")
    features = payload.get("features", {})
    context = payload.get("context", {})

    expert = NeuralDecisionExpert()
    result = expert.predict(symbol, timeframe, features, context)

    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail={
                "error": result["error"],
                "validation_errors": result.get("validation_errors", []),
                "recommendation": result.get("recommendation"),
                "veto": result.get("veto"),
            },
        )

    return result
