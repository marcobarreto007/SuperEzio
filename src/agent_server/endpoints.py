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
    detect_complex_finance_intent,
    detect_capital_allocation_intent,
    detect_market_scan_intent,
)
from core.risk_firewall import DecisionCandidate, evaluate_decision_with_sdca
from data.data_hub import hub

from .protocol import A2AMessage, MessageType

logger = logging.getLogger(__name__)
router = APIRouter()

_session_history: dict[str, dict[str, Any]] = {}


def _is_what_happened_query(message: str) -> bool:
    clean = message.strip().lower().rstrip("?").strip()
    return clean in {
        "o que houve",
        "what happened",
        "why",
        "bug",
        "what went wrong",
    }


def _extract_complex_intent(content: str) -> str | None:
    intents = [
        "MACRO_THESIS",
        "PERSONAL_FINANCE",
        "CAPITAL_ALLOCATION",
        "ASSET_ALLOCATION",
        "REAL_ESTATE_VS_MARKETS",
        "BUSINESS_CAPITAL",
        "FRAUD_RISK",
        "EDUCATION_INVESTMENT",
    ]
    match = re.search(
        r"Question\s+Classification.*?(?:" + "|".join(intents) + ")", content, re.IGNORECASE
    )
    if match:
        matched_text = match.group(0).upper()
        for intent in intents:
            if intent in matched_text:
                return intent
    for intent in intents:
        if re.search(rf"\b{intent}\b", content[:1000], re.IGNORECASE):
            return intent
    return None


VAGUE_FINANCIAL_RESPONSE = (
    "Para análise financeira, informe pelo menos um ativo/ticker, o prazo desejado "
    "(ex.: AAPL 14 dias, tendência, risco, valuation, notícias)."
)


def _build_no_empty_fallback_chunk(
    *,
    message: str,
    route_used: str,
    detected_intent: str,
    scanner_invoked: bool,
    agent_called: bool,
    candidate_count: int,
    rejected_count: int,
    rejection_line: str,
    provider_error: str | None,
    selected_ui_ticker: str,
) -> str:
    """Build a useful answer when the pipeline emitted no final content."""
    lower = (message or "").lower()
    ticker = selected_ui_ticker or detect_ticker(message) or "the requested ticker"
    header = (
        "Bob: deterministic fallback answer.\n"
        "This is an educational framework, not personalized financial advice.\n"
        f"route: {route_used}\n"
        f"detected_intent: {detected_intent}\n"
        f"scanner_invoked: {scanner_invoked}\n"
        f"agent_called: {agent_called}\n"
    )
    is_etf_comparison = (
        any(word in lower for word in ("compare", "comparison", " vs ", "versus"))
        and sum(1 for symbol in ("voo", "vti", "schd") if symbol in lower) >= 2
    )

    if route_used == "market_scan" or scanner_invoked:
        body = (
            "The scan path did not return a validated final candidate. I will not invent a trade. "
            f"Candidates passed: {candidate_count}; rejected: {rejected_count}; top reasons: {rejection_line}. "
            "Use REJECT_ALL unless a candidate has verified price, liquidity, catalyst, risk, and invalidation."
        )
        verdict = "Final verdict: REJECT_ALL"
        suggestion = "Suggestion: tighten universe, liquidity floor, catalyst window, or provide candidate tickers."
    elif is_etf_comparison:
        body = (
            "ETF comparison fallback: VOO is S&P 500 large-cap exposure, VTI is total US market exposure, "
            "and SCHD is dividend-quality/value-tilted equity exposure. For most long-term buy-and-hold investors, "
            "pick one core US equity fund instead of stacking overlapping funds. VTI is the broadest core choice; "
            "VOO is fine if you specifically want large-cap S&P 500 exposure; SCHD is a satellite for dividend tilt, not a full-market core."
        )
        verdict = "Final verdict: ETF"
        suggestion = "Suggestion: choose one core ETF first, then add SCHD only if dividend tilt is intentional."
    elif route_used == "ticker_analysis":
        if "concentrated" in lower or "40%" in lower or "40 percent" in lower:
            body = (
                f"{ticker} concentration fallback: a 40 percent single-stock weight is portfolio risk, even for a blue-chip. "
                "Do not sell blindly, but cap new exposure, route new money to diversified assets, and reduce concentration gradually "
                "with tax-aware tranches. Require a tax plan before realizing large gains."
            )
        elif "invalidate" in lower or "invalidation" in lower:
            body = (
                f"{ticker} invalidation fallback: a bullish short-term thesis is invalidated if price loses the prior support zone, "
                "volume expands on down days, relative strength breaks versus the market, or the catalyst/risk event changes the thesis. "
                "Use WAIT until current chart data confirms support, resistance, and trend."
            )
        else:
            body = (
                f"The ticker route was selected for {ticker}, but the pipeline did not return enough verified content. "
                "Treat this as WAIT, not a buy signal. Before acting, require current price, volume/liquidity, trend, "
                "next catalyst, downside risk, and a written invalidation level."
            )
        verdict = "Final verdict: WAIT"
        suggestion = (
            f"Suggestion: retry '{ticker} 14-day analysis with price, volume, RSI, "
            "support, resistance, and catalyst.'"
        )
    elif "credit card" in lower or "19 percent" in lower or "19%" in lower:
        body = (
            "With high-interest debt, the clean default is to pay debt before taking market risk. "
            "A 19 percent credit-card balance is a guaranteed drag; beating that after tax and risk "
            "is unrealistic for a normal portfolio."
        )
        verdict = "Final verdict: PAY_DEBT"
        suggestion = "Suggestion: pay the high-interest balance first, then rebuild emergency cash before ETF contributions."
    elif "capital_allocation" in detected_intent.lower() or (
        "allocate" in lower and any(term in lower for term in ("cash", "debt", "etf", "portfolio"))
    ):
        body = (
            "Capital allocation fallback: use illustrative assumptions, not forecasts. "
            "First keep 3-6 months of emergency cash reserve. Then pay debt above a 6-8 percent interest gate. "
            "Only fund side-business equipment when there is documented demand, clear payback, and time-to-cashflow evidence. "
            "Use TFSA, RRSP, RESP, or FHSA choices based on the individual's tax situation. "
            "Illustrative allocation: 40 percent emergency reserve, 30 percent high-interest debt payoff, "
            "15 percent broad diversified ETF exposure, 10 percent business/education only with payback evidence, "
            "5 percent learning/risk budget."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: fill in debt rate, monthly expenses, emergency balance, and registered-account room."
    elif "fax" in lower:
        body = (
            "Fax industry fallback: pure fax is structurally declining. The better thesis is not fax hardware or legacy fax service; "
            "it is secure document workflow, e-signature, healthcare/legal compliance automation, audit trails, and AI document intelligence. "
            "Do not start with a ticker until the replacement workflow and growth economics are clear."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: research digital document workflow and compliance adjacencies before scanning stocks."
    elif "cad 50" in lower or "lottery" in lower or "risk lab" in lower:
        body = (
            "CAD 50 risk-lab fallback: treat this as a controlled experiment, not investing capital. "
            "Max loss is CAD 50 per week. No leverage, no options, no revenge trades. Every attempt needs thesis, liquidity, entry, stop, target, and post-mortem. "
            "If there is no verifiable edge, the correct action is no bet this week."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: ask for a scan only after naming momentum, mean-reversion, or catalyst criteria."
    elif "dividend" in lower or "passive income" in lower:
        body = (
            "Dividend fallback: for a Canadian investor, prioritize dividend durability, diversification, account placement, and tax treatment over headline yield. "
            "Use Canadian-listed dividend ETFs or high-quality Canadian dividend names as research candidates, keep single-stock weights small, and verify payout ratio, debt, dividend growth, and valuation."
        )
        verdict = "Final verdict: ETF"
        suggestion = "Suggestion: screen Canadian dividend exposure by yield sustainability, MER, holdings, payout ratio, and account type."
    elif "dollar-cost" in lower or "dca" in lower or "wait for a correction" in lower:
        body = (
            "DCA fallback: default to dollar-cost averaging instead of waiting for a perfect correction. "
            "Use scheduled tranches, keep emergency cash separate, and only accelerate buying if valuation, cash stability, and risk tolerance all support it. "
            "Waiting requires a written trigger; otherwise it becomes market-timing drift."
        )
        verdict = "Final verdict: ETF"
        suggestion = "Suggestion: split the amount into 4-12 scheduled tranches and define what would pause or accelerate deployment."
    elif "mutual fund" in lower or "etf" in lower:
        body = (
            "ETF vs mutual fund framework: ETFs usually win on low cost, transparency, intraday liquidity, "
            "and tax efficiency. Mutual funds can still be useful for automatic contributions, advisor-managed "
            "plans, or niche mandates. For a beginner, prefer broad low-cost diversified exposure before specialty products."
        )
        verdict = "Final verdict: ETF"
        suggestion = "Suggestion: compare MER, holdings, tracking index, account type, and trading costs before choosing."
    elif "sell everything" in lower or "go to cash" in lower or "markets are falling" in lower:
        body = (
            "Do not sell everything only because markets are falling. Use gates: emergency cash, time horizon, debt, "
            "job risk, portfolio concentration, and whether your thesis changed. If liquidity is safe and the horizon "
            "is long, panic selling usually damages compounding."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: rebalance only if your risk limit or cash need changed; otherwise use staged DCA."
    else:
        body = (
            "I can still give a useful framework from the available context. Start with objective, time horizon, "
            "liquidity need, risk capacity, and what data is missing. Use tools only when current market evidence "
            "or a named ticker is required."
        )
        verdict = "Final verdict: WAIT"
        suggestion = "Suggestion: state the goal, horizon, amount, and whether you want framework, ticker analysis, or a scan."

    error_line = f"\nprovider_error: {provider_error}" if provider_error else ""
    return f"{header}{body}\n{verdict}\n{suggestion}{error_line}"


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
            "agent_count": 4,
            "roles": [
                "Macro & Risk Analyst",
                "Fundamental & Value Analyst",
                "Momentum & Technical Analyst",
                "Contrarian & Opportunity Analyst",
            ],
        },
    },
    "penny_guardrail": {
        "label": "PennyLab Guardrail",
        "agent_count": 5,
        "mode": "optional",
        "description": (
            "Optional forensic layer for penny-stock workflows. It does not "
            "replace the 4-expert institutional committee."
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
            "id": "experts_4",
            "label": "4 Experts",
            "description": "Experts analyze the same data under an anti-guessing contract.",
        },
        {
            "id": "agent_primary",
            "label": "Bob Agent (Qwen3-Next-80B IQ4_XS)",
            "description": "Local Qwen3-Next-80B Abliterated CEO via llama.cpp + F51 Nitro MoE — consolidates conflicts and chooses one permitted next step.",
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

        session_meta = _session_history.get(session_id) or {}
        trade_order_context = session_meta.get("trade_order_context") or {}

        # Intercept "o que houve" query if the previous request failed
        if _is_what_happened_query(raw_message):
            prev_run = _session_history.get(session_id)
            if prev_run and prev_run.get("failed"):
                prev_intent = prev_run.get("detected_intent", "unknown")
                explanation = (
                    f"The previous request failed to produce valid content. "
                    f"It was classified as {prev_intent}. "
                    f"No market scanner should have been used. "
                    f"Check runtime logs."
                )

                # Update session history to mark this query as succeeded
                _session_history[session_id] = {
                    "detected_intent": "WHAT_HAPPENED_INTERCEPT",
                    "failed": False,
                }

                async def stream_intercepted() -> AsyncGenerator[str, None]:
                    yield json.dumps({"type": "STREAM_START", "msg_id": envelope.msg_id}) + "\n"
                    yield (
                        json.dumps({"type": "CHUNK", "content": explanation}, ensure_ascii=False)
                        + "\n"
                    )
                    trace = {
                        "user_query": raw_message,
                        "detected_intent": "WHAT_HAPPENED_INTERCEPT",
                        "selected_ui_ticker": "",
                        "chart_context_attached": False,
                        "route_used": "general",
                        "scanner_invoked": False,
                        "agent_called": False,
                        "fallback_used": False,
                        "final_content_length": len(explanation),
                    }
                    logger.info("Bob Response Trace (Intercepted): %s", json.dumps(trace))
                    yield json.dumps({"type": "STREAM_END", "trace": trace}) + "\n"

                return StreamingResponse(stream_intercepted(), media_type="application/x-ndjson")

        # Ticker from UI field takes priority; fall back to message text detection
        explicit_ticker = str(payload.get("ticker") or "").strip()
        detected_ticker = explicit_ticker or detect_ticker(raw_message)

        # Hard block context leak for advisory / scan intents.
        # - Complex finance / capital allocation: chart context must never leak.
        # - Market scan: UI ticker must not hijack routing away from the scanner.
        #   The user asked to FIND stocks, not to analyze the chart ticker.
        is_complex = detect_complex_finance_intent(raw_message)
        is_capital_alloc = detect_capital_allocation_intent(raw_message)
        is_market_scan = detect_market_scan_intent(raw_message)
        if is_complex or is_capital_alloc:
            explicit_ticker = ""
            detected_ticker = ""
            chart_context = ""
            context_block = ""
            block_vague_financial = False
        elif is_market_scan and explicit_ticker and not detect_ticker(raw_message):
            # Market scan request with a chart ticker but no inline ticker:
            # the chart ticker is stale context, not the scan target.
            # Zero it so parse_user_intent routes to market_scan, not ticker_analysis.
            explicit_ticker = ""
            detected_ticker = detect_ticker(raw_message)
            chart_context = ""
            context_block = ""
            block_vague_financial = False
        else:
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

        # Trace metadata variables
        user_query = raw_message
        selected_ui_ticker = payload.get("ticker") or ""
        chart_context_attached = bool(context_block)
        detected_intent = "unknown"
        route_used = "unknown"
        scanner_invoked = False
        agent_called = False
        fallback_used = False
        final_content_length = 0
        full_content: list[str] = []
        # Scan telemetry surfaced by collector via DATA_COLLECTED events
        candidate_count = 0
        rejected_count = 0
        rejection_summary: dict[str, int] = {}
        provider_sources_used: set[str] = set()
        provider_error: str | None = None

        async def stream_result() -> AsyncGenerator[str, None]:
            nonlocal \
                detected_intent, \
                route_used, \
                scanner_invoked, \
                agent_called, \
                fallback_used, \
                final_content_length
            nonlocal candidate_count, rejected_count, rejection_summary, provider_error
            nonlocal trade_order_context
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
                        trade_order_context=trade_order_context or None,
                    ):
                        if isinstance(event, dict):
                            event_type = event.get("type")
                            if event_type == "INTENT_CLASSIFIED":
                                if event.get("intent"):
                                    detected_intent = event["intent"]
                                if event.get("route"):
                                    route_used = event["route"]
                            elif event_type == "PIPELINE_STEP":
                                step = event.get("step")
                                status = event.get("status")
                                if step == "agent_primary" and status == "started":
                                    agent_called = True
                                elif (
                                    step == "data"
                                    and status == "started"
                                    and (
                                        route_used == "market_scan"
                                        or event.get("route") == "market_scan"
                                    )
                                ):
                                    scanner_invoked = True
                            elif event_type == "DATA_COLLECTED":
                                if (
                                    route_used == "market_scan"
                                    or event.get("rejected_count") is not None
                                ):
                                    scanner_invoked = True
                                if isinstance(event.get("candidates"), int):
                                    candidate_count = event["candidates"]
                                if isinstance(event.get("rejected_count"), int):
                                    rejected_count = event["rejected_count"]
                                if isinstance(event.get("rejection_summary"), dict):
                                    rejection_summary = event["rejection_summary"]
                                for prov in event.get("providers") or []:
                                    if prov:
                                        provider_sources_used.add(str(prov))
                                # Provider errors are visible via source_errors[]
                                for err in event.get("source_errors") or []:
                                    if isinstance(err, str) and provider_error is None:
                                        provider_error = err[:200]
                            elif event_type == "ERROR":
                                fallback_used = True
                                detail = event.get("detail")
                                if isinstance(detail, str) and provider_error is None:
                                    provider_error = detail[:200]
                            elif event_type == "CHUNK":
                                content = event.get("content", "")
                                final_content_length += len(content)
                                full_content.append(content)
                            elif event_type == "TRADE_ORDER_CONTEXT":
                                trade_order_context = {
                                    k: v for k, v in event.items() if k != "type" and v is not None
                                }
                            yield json.dumps(event, ensure_ascii=False) + "\n"
                        else:
                            content_str = str(event)
                            final_content_length += len(content_str)
                            full_content.append(content_str)
                            yield (
                                json.dumps(
                                    {"type": "CHUNK", "content": content_str},
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
                        trade_order_context=trade_order_context or None,
                    )
                    async for chunk in chat_iter:
                        if isinstance(chunk, dict):
                            event_type = chunk.get("type")
                            if event_type == "INTENT_CLASSIFIED":
                                if chunk.get("intent"):
                                    detected_intent = chunk["intent"]
                                if chunk.get("route"):
                                    route_used = chunk["route"]
                            elif event_type == "PIPELINE_STEP":
                                step = chunk.get("step")
                                status = chunk.get("status")
                                if step == "agent_primary" and status == "started":
                                    agent_called = True
                                elif (
                                    step == "data"
                                    and status == "started"
                                    and (
                                        route_used == "market_scan"
                                        or chunk.get("route") == "market_scan"
                                    )
                                ):
                                    scanner_invoked = True
                            elif event_type == "DATA_COLLECTED":
                                if (
                                    route_used == "market_scan"
                                    or chunk.get("rejected_count") is not None
                                ):
                                    scanner_invoked = True
                                if isinstance(chunk.get("candidates"), int):
                                    candidate_count = chunk["candidates"]
                                if isinstance(chunk.get("rejected_count"), int):
                                    rejected_count = chunk["rejected_count"]
                                if isinstance(chunk.get("rejection_summary"), dict):
                                    rejection_summary = chunk["rejection_summary"]
                                for prov in chunk.get("providers") or []:
                                    if prov:
                                        provider_sources_used.add(str(prov))
                                for err in chunk.get("source_errors") or []:
                                    if isinstance(err, str) and provider_error is None:
                                        provider_error = err[:200]
                            elif event_type == "ERROR":
                                fallback_used = True
                                detail = chunk.get("detail")
                                if isinstance(detail, str) and provider_error is None:
                                    provider_error = detail[:200]
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
                            final_content_length += len(chunk)
                            full_content.append(chunk)
                            yield (
                                json.dumps({"type": "CHUNK", "content": chunk}, ensure_ascii=False)
                                + "\n"
                            )

                # Post-processing answer content for sub-classification if complex
                # finance or capital allocation.
                accumulated_answer = "".join(full_content)
                if is_complex or is_capital_alloc:
                    route_used = "general"
                    sub_intent = _extract_complex_intent(accumulated_answer)
                    if sub_intent:
                        detected_intent = sub_intent
                    elif is_capital_alloc:
                        detected_intent = "CAPITAL_ALLOCATION"
                    elif detected_intent == "unknown" or detected_intent == "general_question":
                        detected_intent = "MACRO_THESIS"  # default complex fallback

                # No Empty Response Rule (OPUS §7): backend must never let the
                # frontend render a blank assistant bubble. If the pipeline
                # produced zero content, emit a structured fallback CHUNK with
                # enough trace info for the user to retry usefully.
                if final_content_length == 0 or not accumulated_answer.strip():
                    fallback_used = True
                    top_reasons = sorted(
                        rejection_summary.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )[:3]
                    rejection_line = (
                        ", ".join(f"{r}:{c}" for r, c in top_reasons) if top_reasons else "n/a"
                    )
                    fallback_chunk = _build_no_empty_fallback_chunk(
                        message=raw_message,
                        route_used=route_used,
                        detected_intent=detected_intent,
                        scanner_invoked=scanner_invoked,
                        agent_called=agent_called,
                        candidate_count=candidate_count,
                        rejected_count=rejected_count,
                        rejection_line=rejection_line,
                        provider_error=provider_error,
                        selected_ui_ticker=selected_ui_ticker,
                    )
                    final_content_length = len(fallback_chunk)
                    yield (
                        json.dumps(
                            {"type": "CHUNK", "content": fallback_chunk},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

                top_rejection_reasons = [
                    f"{r}:{c}"
                    for r, c in sorted(
                        rejection_summary.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )[:3]
                ]
                # Hard runtime invariant: advisory routes must never invoke the
                # market scanner. If this fires, the routing hierarchy is broken.
                _ADVISORY_ROUTES = {"general", "capital_allocation", "personal_finance"}
                if route_used in _ADVISORY_ROUTES and scanner_invoked:
                    logger.warning(
                        "INVARIANT VIOLATION: route=%s but scanner_invoked=True. User query: %s",
                        route_used,
                        user_query[:200],
                    )

                trace = {
                    "user_query": user_query,
                    "detected_intent": detected_intent,
                    "selected_ui_ticker": selected_ui_ticker,
                    "chart_context_attached": chart_context_attached,
                    "route_used": route_used,
                    "scanner_invoked": scanner_invoked,
                    "candidate_count": candidate_count,
                    "rejected_count": rejected_count,
                    "top_rejection_reasons": top_rejection_reasons,
                    "agent_called": agent_called,
                    "fallback_used": fallback_used,
                    "final_content_length": final_content_length,
                    "provider_sources_used": sorted(provider_sources_used),
                    "provider_error": provider_error,
                }
                logger.info("Bob Response Trace: %s", json.dumps(trace))

                # Update session history
                session_record: dict[str, Any] = {
                    "detected_intent": detected_intent,
                    "failed": fallback_used,
                }
                if trade_order_context:
                    session_record["trade_order_context"] = trade_order_context
                _session_history[session_id] = session_record

                yield json.dumps({"type": "STREAM_END", "trace": trace}) + "\n"
            except Exception as exc:
                fallback_used = True
                err_detail = _safe_error_detail(exc)
                if provider_error is None:
                    provider_error = err_detail[:200]
                yield (json.dumps({"type": "ERROR", "detail": err_detail}) + "\n")

                # No Empty Response Rule (OPUS §7) also applies on exception
                # paths: if nothing reached the user, surface a structured
                # fallback CHUNK so the frontend has something to render.
                if final_content_length == 0:
                    fallback_chunk = (
                        "Bob hit a runtime error while preparing this answer.\n"
                        f"- route: {route_used}\n"
                        f"- detected_intent: {detected_intent}\n"
                        f"- scanner_invoked: {scanner_invoked}\n"
                        f"- agent_called: {agent_called}\n"
                        f"- error: {provider_error or err_detail}\n"
                        "\n"
                        "Suggestion: retry with a narrower question (specific "
                        "ticker or educational framework) so the pipeline can "
                        "route to a smaller, more reliable path."
                    )
                    final_content_length = len(fallback_chunk)
                    yield (
                        json.dumps(
                            {"type": "CHUNK", "content": fallback_chunk},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

                top_rejection_reasons = [
                    f"{r}:{c}"
                    for r, c in sorted(
                        rejection_summary.items(),
                        key=lambda kv: kv[1],
                        reverse=True,
                    )[:3]
                ]
                trace = {
                    "user_query": user_query,
                    "detected_intent": detected_intent,
                    "selected_ui_ticker": selected_ui_ticker,
                    "chart_context_attached": chart_context_attached,
                    "route_used": route_used,
                    "scanner_invoked": scanner_invoked,
                    "candidate_count": candidate_count,
                    "rejected_count": rejected_count,
                    "top_rejection_reasons": top_rejection_reasons,
                    "agent_called": agent_called,
                    "fallback_used": True,
                    "final_content_length": final_content_length,
                    "provider_sources_used": sorted(provider_sources_used),
                    "provider_error": provider_error,
                }
                logger.info("Bob Response Trace (Error): %s", json.dumps(trace))

                # Update session history
                _session_history[session_id] = {
                    "detected_intent": detected_intent,
                    "failed": True,
                }

                yield json.dumps({"type": "STREAM_END", "trace": trace}) + "\n"

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
