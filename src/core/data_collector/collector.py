"""
Data Collector - Agregador de TODAS as fontes de dados.

Pipeline:
    1. DataHub → preço, histórico, perfil, indicadores técnicos
    2. QuantEngine → Monte Carlo, ML prediction, RSI, SMA
    3. RiskCalculator → VaR, CVaR, Sharpe, Sortino, drawdown
    4. NewsScout → notícias + sentimento (Brave/DuckDuckGo)
    5. RedditPulse → posts qualificados + sentimento social
    6. BoC Valet → Policy Rate, CPI, USD/CAD (Canadá)
    7. Federal Reserve → Fed Funds Rate, CPI, US Treasury (EUA)
    8. MarketHub → preço real-time (DataHub + Yahoo scrape fallback)

Multi-mercado: detecta automaticamente pelo sufixo do ticker.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from core.math import FinancialEngine

try:
    from core.agent_runtime.ml.quant_engine import QuantEngine
except Exception:

    class QuantEngine:  # type: ignore[no-redef]
        def analyze_asset(self, ticker: str) -> Dict[str, Any]:
            try:
                from experts.technical_neural.pipeline_hook import analyze_technical_neural_sync
                res = analyze_technical_neural_sync(ticker)
                if "error" in res:
                    return {
                        "error": res["error"],
                        "ticker": ticker,
                        "rsi": 50.0,
                        "monte_carlo_prob_up": 50.0,
                        "ml_prob_up": 50.0,
                        "combined_prob_up": 50.0,
                        "ml_reinforcement_reward": 0.0,
                    }
                
                mlp_score = res.get("mlp_score", 0.5)
                pct_up = mlp_score * 100.0
                return {
                    "rsi": 50.0,
                    "monte_carlo_prob_up": 50.0,
                    "ml_prob_up": pct_up,
                    "combined_prob_up": pct_up,
                    "ml_reinforcement_reward": res.get("confidence", 0.0),
                    "ml_reinforcement_pain": 0.0,
                    "evidence": {
                        "ml": f"MLP model fit on last 600 bars: {res.get('verdict')} verdict (prob: {mlp_score:.2%}, conf: {res.get('confidence'):.2%}, convergence: {res.get('loss_convergence')})"
                    }
                }
            except Exception as exc:
                return {
                    "error": f"QuantEngine proxy failed: {exc}",
                    "ticker": ticker,
                    "rsi": 50.0,
                    "monte_carlo_prob_up": 50.0,
                    "ml_prob_up": 50.0,
                    "combined_prob_up": 50.0,
                    "ml_reinforcement_reward": 0.0,
                }


try:
    from core.agent_runtime.financial_suite.adapters import (
        tool_get_market_price,
        tool_calculate_risk_metrics,
    )
except Exception:

    async def tool_get_market_price(ticker: str) -> Dict[str, Any]:
        return {
            "error": "market_runtime_removed",
            "symbol": ticker,
        }

    async def tool_calculate_risk_metrics(
        ticker: str, days: int = 90
    ) -> Dict[str, Any]:
        return {
            "error": "risk_runtime_removed",
            "ticker": ticker,
            "days": days,
        }


from core.paths import project_path
from core.observability.neural_log import log_event
from .scraper import RealTimeScraper
from ..observability.debug_logger import debug_logger, MODULE_DATA_COLLECTOR


def detect_market(ticker: str) -> str:
    """Detecta mercado pelo sufixo do ticker (Foco: US/CA)."""
    t = ticker.upper()
    if t.endswith(".SA"):
        return "BR"
    if t.endswith(".TO") or t.endswith(".V"):
        return "CA"
    return "US"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace_safe_filename(ticker: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in ticker)


class DataCollector:
    """
    Agrega dados de TODAS as fontes disponíveis para um ticker.

    Inicialização é lazy — cada componente só é criado quando necessário.
    Todas as chamadas são paralelas via asyncio.gather.
    """

    def __init__(self, data_hub=None, quantum_walk=None) -> None:
        self._engine: FinancialEngine | None = None
        self._quant: QuantEngine | None = None
        self._scraper = RealTimeScraper()
        if data_hub is not None:
            self._data_hub = data_hub
        else:
            from data.data_hub import hub

            self._data_hub = hub
        if quantum_walk is not None:
            self._quantum = quantum_walk
        else:
            self._quantum = None

    @property
    def engine(self) -> FinancialEngine:
        if self._engine is None:
            self._engine = FinancialEngine()

        return self._engine

    @property
    def quant(self) -> QuantEngine:
        if self._quant is None:
            self._quant = QuantEngine()

        return self._quant

    async def _get_crisis_analysis(self, ticker: str) -> Dict[str, Any]:
        """Calcula risco sistêmico usando o MacroDataset (Canadá)."""
        try:
            from experts.crisis.expert.crisis_expert import CrisisMathExpert
            from experts.crisis.contracts.schemas import (
                CrisisInput,
                MacroObservation,
            )
            from core.rag.macro_dataset import macro_engine

            market = detect_market(ticker)
            country = {"CA": "Canada", "US": "United States", "BR": "Brazil"}.get(
                market, "United States"
            )

            observations_raw = macro_engine.query_context(country, top_n=24)
            observations = [MacroObservation(**o) for o in observations_raw]

            expert = CrisisMathExpert()
            input_data = CrisisInput(
                country=country, asset_symbol=ticker, observations=observations
            )

            report = await asyncio.to_thread(expert.analyze, input_data)
            return {
                "report": report.model_dump(mode="json"),
                "data_source": "MacroDataset",
            }
        except Exception as e:
            return {"error": str(e)}

    async def _get_quantum_analysis(self) -> Dict[str, Any]:
        """Simulação quântica tricolor."""
        try:
            if self._quantum is None:
                from adapters.quantum.quantum_adapter import make_quantum_walk

                self._quantum = make_quantum_walk()
            return await asyncio.to_thread(self._quantum.run_simulation)
        except Exception as exc:
            return {"error": f"quantum unavailable: {exc}"}

    async def collect_all(self, ticker: str, timeout: float = 60.0) -> Dict[str, Any]:
        """
        Coleta TODOS os dados disponíveis para um ticker.
        Executa fontes em paralelo. Cada fonte que falhar retorna erro isolado.
        """
        log_event(
            "DATA_COLLECTOR",
            "START",
            {"ticker": ticker, "market": detect_market(ticker)},
        )
        debug_logger.trace(
            MODULE_DATA_COLLECTOR, "collect_all start", ticker=ticker, timeout=timeout
        )

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    self._get_market_data(ticker),
                    self._get_company_profile(ticker),
                    self._get_quant_analysis(ticker),
                    self._get_risk_metrics(ticker),
                    self._get_sentiment(ticker),
                    self._get_reddit_signal(ticker),
                    self._get_macro(ticker, detect_market(ticker)),
                    self._get_crisis_analysis(ticker),
                    self._get_realtime_price(ticker),
                    self._get_quantum_analysis(),
                    return_exceptions=True,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            log_event(
                "DATA_COLLECTOR", "TIMEOUT", {"ticker": ticker, "timeout": timeout}
            )
            debug_logger.warn(
                MODULE_DATA_COLLECTOR,
                "collect_all timeout",
                ticker=ticker,
                timeout=timeout,
            )
            return {
                "analysis_id": f"{_trace_safe_filename(ticker)}-{uuid.uuid4().hex[:12]}",
                "ticker": ticker,
                "market": detect_market(ticker),
                "collected_at": _now_iso(),
                "technicals": {"error": f"collect_all timed out after {timeout}s"},
                "profile": {"error": f"collect_all timed out after {timeout}s"},
                "quant": {"error": f"collect_all timed out after {timeout}s"},
                "risk": {"error": f"collect_all timed out after {timeout}s"},
                "sentiment": {"error": f"collect_all timed out after {timeout}s"},
                "reddit": {"error": f"collect_all timed out after {timeout}s"},
                "macro": {"error": f"collect_all timed out after {timeout}s"},
                "crisis": {"error": f"collect_all timed out after {timeout}s"},
                "realtime_price": {"error": f"collect_all timed out after {timeout}s"},
                "quantum": {"error": f"collect_all timed out after {timeout}s"},
                "data_quality": "timeout",
                "source_errors": ["timeout"],
            }

        analysis_id = f"{_trace_safe_filename(ticker)}-{uuid.uuid4().hex[:12]}"
        collected_at = _now_iso()

        market_data = self._safe_result(results[0], "technicals")

        data: Dict[str, Any] = {
            "analysis_id": analysis_id,
            "ticker": ticker,
            "market": detect_market(ticker),
            "collected_at": collected_at,
            "technicals": market_data,
            "profile": self._safe_result(results[1], "profile"),
            "quant": self._safe_result(results[2], "quant"),
            "risk": self._safe_result(results[3], "risk"),
            "sentiment": self._safe_result(results[4], "sentiment"),
            "reddit": self._safe_result(results[5], "reddit"),
            "macro": self._safe_result(results[6], "macro"),
            "crisis": self._safe_result(results[7], "crisis"),
            "realtime_price": (
                {"price": market_data.get("price"), "symbol": ticker}
                if market_data.get("price")
                else self._safe_result(results[8], "realtime_price")
            ),
            "quantum": self._safe_result(results[9], "quantum"),
        }

        self._attach_evidence(data)
        self._persist_trace(data)

        log_event(
            "DATA_COLLECTOR",
            "DONE",
            {
                "ticker": ticker,
                "sections": [
                    k
                    for k, v in data.items()
                    if k != "ticker" and "error" not in str(v)
                ],
            },
        )

        return data

    async def collect_quick(self, ticker: str) -> Dict[str, Any]:
        """Coleta rápida: só preço + quant + macro (sem news, sem risk full)."""
        results = await asyncio.gather(
            self._get_market_data(ticker),
            self._get_quant_analysis(ticker),
            self._get_macro(ticker, detect_market(ticker)),
            self._get_crisis_analysis(ticker),
            return_exceptions=True,
        )

        data = {
            "analysis_id": f"{_trace_safe_filename(ticker)}-{uuid.uuid4().hex[:12]}",
            "ticker": ticker,
            "market": detect_market(ticker),
            "collected_at": _now_iso(),
            "technicals": self._safe_result(results[0], "technicals"),
            "quant": self._safe_result(results[1], "quant"),
            "macro": self._safe_result(results[2], "macro"),
            "crisis": self._safe_result(results[3], "crisis"),
        }

        self._attach_evidence(data)
        self._persist_trace(data)

        return data

    async def _get_market_data(
        self, ticker: str, per_source_timeout: float = 15.0
    ) -> Dict[str, Any]:
        """DataHub -> TwelveData -> AlphaVantage com timeout por fonte."""

        async def _safe_fetch(
            source_name: str, fetch_func, timeout: float = per_source_timeout
        ) -> Dict[str, Any]:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(fetch_func),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                log_event(
                    "DATA_COLLECTOR",
                    f"TIMEOUT_{source_name}",
                    {"ticker": ticker, "timeout": timeout},
                )
                return {"error": f"{source_name} timeout after {timeout}s"}
            except Exception as exc:
                log_event(
                    "DATA_COLLECTOR",
                    f"ERROR_{source_name}",
                    {"ticker": ticker, "error": str(exc)[:150]},
                )
                return {"error": f"{source_name} failed: {type(exc).__name__}: {exc}"}

        data = await _safe_fetch(
            "FINANCIAL_ENGINE", lambda: self.engine.get_market_data(ticker)
        )

        if data.get("error") or not data.get("price"):
            rt_data = await _safe_fetch(
                "SCRAPER", lambda: self._scraper.get_price(ticker)
            )
            if not rt_data.get("error") and rt_data.get("price"):
                data = {
                    "price": rt_data["price"],
                    "method": "scraper_fallback",
                    "symbol": ticker,
                }

        if data.get("error") or not data.get("price"):
            hub_data = await _safe_fetch(
                "DATA_HUB_PRICE", lambda: self._data_hub.get_price(ticker)
            )
            if not hub_data.get("error") and hub_data.get("price"):
                data = {
                    **hub_data,
                    "method": f"{hub_data.get('provider', 'data_hub')}_fallback",
                    "symbol": ticker,
                }

        return data

    async def _get_company_profile(self, ticker: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.engine.get_company_profile, ticker)

    async def _get_quant_analysis(self, ticker: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.quant.analyze_asset, ticker)

    async def _get_risk_metrics(self, ticker: str) -> Dict[str, Any]:
        return await tool_calculate_risk_metrics(ticker, days=90)

    async def _get_sentiment(self, ticker: str) -> Dict[str, Any]:
        clean = (
            ticker.replace(".TO", "")
            .replace(".to", "")
            .replace(".V", "")
            .replace(".v", "")
        )
        return await asyncio.to_thread(self._data_hub.get_sentiment_summary, clean)

    async def _get_reddit_signal(self, ticker: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._data_hub.get_reddit_signal, ticker)

    async def _get_macro(self, ticker: str, market: str = "US") -> Dict[str, Any]:
        return await asyncio.to_thread(self._data_hub.get_macro, market)

    async def _get_realtime_price(self, ticker: str) -> Dict[str, Any]:
        return await tool_get_market_price(ticker)

    @staticmethod
    def _safe_result(result: Any, section: str) -> Any:
        if isinstance(result, Exception):
            return {"error": f"{section} failed: {result}"}
        return result

    @staticmethod
    def _attach_evidence(data: Dict[str, Any]) -> None:
        ticker = data.get("ticker", "UNKNOWN")
        collected_at = data.get("collected_at") or _now_iso()
        date_part = collected_at[:10]

        sources = {
            "technicals": "datahub_history",
            "profile": "datahub_profile",
            "quant": "quant_engine",
            "risk": "risk_calculator",
            "sentiment": "news_scout_multisource",
            "reddit": "reddit_pulse",
            "macro": "macro_provider_alphavantage",
            "crisis": "crisis_rag",
            "realtime_price": "market_hub_cascaded",
            "quantum": "quantum_random_walk",
        }

        for section, source in sources.items():
            payload = data.get(section)
            if not isinstance(payload, dict):
                continue
            payload.setdefault("source", source)
            payload.setdefault("evidence_id", f"{source}_{ticker}_{date_part}")
            payload.setdefault("timestamp", collected_at)
            payload.setdefault(
                "data_quality",
                "unavailable" if "error" in payload else "provider_or_computed",
            )

        errors = [
            section
            for section in sources
            if isinstance(data.get(section), dict) and "error" in data[section]
        ]
        data["data_quality"] = "partial" if errors else "provider_or_computed"
        data["source_errors"] = errors

    @staticmethod
    def _persist_trace(data: Dict[str, Any]) -> None:
        try:
            trace_dir = project_path("data", "traces")
            trace_dir.mkdir(parents=True, exist_ok=True)
            analysis_id = data.get("analysis_id") or uuid.uuid4().hex
            path = trace_dir / f"{analysis_id}.json"
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            log_event("DATA_COLLECTOR", "TRACE_WRITE_FAIL", {"error": str(exc)})

    @staticmethod
    def _fmt(val: Any, spec: str = ".2f") -> str:
        if isinstance(val, (int, float)):
            return f"{val:{spec}}"
        return str(val) if val is not None else "?"

    @staticmethod
    def format_context(data: Dict[str, Any]) -> str:
        """Formata os dados coletados num texto legível para os agentes LLM."""
        fmt = DataCollector._fmt
        ticker = data.get("ticker", "?")
        parts = [
            f"=== COLLECTED DATA FOR {ticker} ===",
            f"Analysis ID: {data.get('analysis_id', '?')}",
            f"Market: {data.get('market', '?')}",
            f"Collected at: {data.get('collected_at', '?')}",
            f"Data quality: {data.get('data_quality', 'unknown')}",
            (
                "Rule: any number below may be cited only with its evidence_id. "
                "If a section is missing or errored, say the data is unavailable."
            ),
            "",
        ]

        rt = data.get("realtime_price", {})
        if isinstance(rt, dict) and "error" not in rt:
            if isinstance(rt.get("price"), (int, float)):
                parts.append(
                    f"[PRICE] {fmt(rt.get('price'))} "
                    f"(source={rt.get('source')}, evidence_id={rt.get('evidence_id')})"
                )
            else:
                parts.append(f"[PRICE] {rt}")

        tech = data.get("technicals", {})
        if (
            isinstance(tech, dict)
            and "error" not in tech
            and tech.get("price") is not None
        ):
            parts.append(
                f"[TECHNICALS] Price: {tech.get('price', '?')}, "
                f"RSI(14): {fmt(tech.get('rsi_14'), '.1f')}, "
                f"MACD: {fmt(tech.get('macd'), '.4f')}, "
                f"Signal: {fmt(tech.get('macd_signal'), '.4f')}, "
                f"EMA20: {fmt(tech.get('ema_20'))}, "
                f"EMA50: {fmt(tech.get('ema_50'))}, "
                f"BB_Upper: {fmt(tech.get('bb_upper'))}, "
                f"BB_Lower: {fmt(tech.get('bb_lower'))}, "
                f"Stoch_K: {fmt(tech.get('stoch_k'), '.1f')}, "
                f"Volume: {tech.get('volume', '?')} "
                f"(evidence_id={tech.get('evidence_id')})"
            )

        profile = data.get("profile", {})
        if isinstance(profile, dict) and profile.get("name"):
            parts.append(
                f"[PROFILE] {profile.get('name')} | "
                f"Sector: {profile.get('sector', '?')} | "
                f"Industry: {profile.get('industry', '?')} | "
                f"Market Cap: {profile.get('market_cap', '?')} | "
                f"P/E: {profile.get('pe_ratio', '?')} | "
                f"Dividend Yield: {profile.get('dividend_yield', '?')} | "
                f"EV/EBITDA: {profile.get('enterprise_to_ebitda', '?')} | "
                f"ROE: {profile.get('return_on_equity', '?')} | "
                f"Beta: {profile.get('beta', '?')} "
                f"(evidence_id={profile.get('evidence_id')})"
            )

        quant = data.get("quant", {})
        if (
            isinstance(quant, dict)
            and "error" not in quant
            and quant.get("rsi") is not None
        ):
            parts.append(
                f"[PREDICTIVE_ENGINE] RSI: {fmt(quant.get('rsi'), '.1f')}, "
                f"Monte Carlo Prob UP: {fmt(quant.get('monte_carlo_prob_up'), '.1f')}%, "
                f"ML Prob UP: {fmt(quant.get('ml_prob_up'), '.1f')}%, "
                f"Combined Prob UP: {fmt(quant.get('combined_prob_up'), '.1f')}%, "
                f"RL Reward: {fmt(quant.get('ml_reinforcement_reward'), '.3f')}, "
                f"RL Pain: {fmt(quant.get('ml_reinforcement_pain'), '.3f')} "
                f"(evidence_id={quant.get('evidence_id')})"
            )
            ev = quant.get("evidence", {})
            if ev:
                parts.append(f"  Monte Carlo: {ev.get('monte_carlo', '')}")
                parts.append(f"  ML: {ev.get('ml', '')}")

        risk = data.get("risk", {})
        if (
            isinstance(risk, dict)
            and "error" not in risk
            and risk.get("var_95") is not None
        ):
            try:
                parts.append(
                    f"[RISK] VaR(95%): {float(risk.get('var_95', 0)):.4f}, "
                    f"CVaR: {float(risk.get('cvar_95', 0)):.4f}, "
                    f"Sharpe: {float(risk.get('sharpe_ratio', 0)):.2f}, "
                    f"Sortino: {float(risk.get('sortino_ratio', 0)):.2f}, "
                    f"Max Drawdown: {float(risk.get('max_drawdown', 0)):.2%}, "
                    f"Volatility: {float(risk.get('annual_volatility', 0)):.2%} "
                    f"(evidence_id={risk.get('evidence_id')})"
                )
            except (ValueError, TypeError):
                pass

        sent = data.get("sentiment", {})
        if (
            isinstance(sent, dict)
            and sent.get("sentiment_label")
            and sent.get("sentiment_label") != "NO_DATA"
        ):
            parts.append(
                f"[SENTIMENT] {sent.get('sentiment_label', '?')} "
                f"(score: {fmt(sent.get('sentiment_score', 0))}, "
                f"{sent.get('news_count', 0)} news items). "
                f'Headline: "{sent.get("top_headline", "N/A")}" '
                f"(evidence_id={sent.get('evidence_id')})"
            )

        reddit = data.get("reddit", {})
        if (
            isinstance(reddit, dict)
            and reddit.get("signal_label")
            and reddit.get("signal_label") != "NO_DATA"
        ):
            parts.append(
                f"[REDDIT] {reddit.get('signal_label')} "
                f"(social score: {fmt(reddit.get('sentiment_score', 0), '.3f')}, "
                f"qualified posts: {reddit.get('qualified_count', 0)}, "
                f"method: {reddit.get('method', '?')}) "
                f"(evidence_id={reddit.get('evidence_id')})"
            )
            parts.append(
                "  Rule: Reddit is a public-discussion social signal; do not treat "
                "it as audited financial fact."
            )
            for post in reddit.get("top_posts", [])[:3]:
                parts.append(
                    f"  - r/{post.get('subreddit', '?')}: {post.get('title', '')} "
                    f"(quality={post.get('quality_score', '?')}, "
                    f"score={post.get('score', '?')}, "
                    f"comments={post.get('comments', '?')}, "
                    f"upvote_ratio={post.get('upvote_ratio', '?')}, "
                    f"url={post.get('url', '?')})"
                )
                if post.get("snippet"):
                    parts.append(f"    Snippet: {post.get('snippet')}")

        macro = data.get("macro", {})
        if isinstance(macro, dict) and "policy_rate" in macro:
            pr = macro.get("policy_rate", {})
            cpi = macro.get("cpi", {})
            fx = macro.get("usd_cad", {})
            parts.append(
                f"[MACRO CA] BoC Rate: {pr.get('current_value', '?')}% a.a. | "
                f"CPI YoY: {cpi.get('current_value', '?')}% | "
                f"USD/CAD: {fx.get('current_value', '?')} (30d: {fx.get('change_30d_pct', '?')}%) "
                f"(evidence_id={macro.get('evidence_id')})"
            )
        elif isinstance(macro, dict) and "treasury_10y" in macro:
            ff = macro.get("fed_funds_proxy", {})
            t10 = macro.get("treasury_10y", {})
            t5 = macro.get("treasury_5y", {})
            parts.append(
                f"[MACRO US] Fed Funds (T-bill 13w): {ff.get('value', '?')}% | "
                f"5-Year: {t5.get('value', '?')}% | "
                f"10-Year: {t10.get('value', '?')}% "
                f"(evidence_id={macro.get('evidence_id')})"
            )

        q = data.get("quantum", {})
        if isinstance(q, dict) and "counts" in q:
            parts.append(
                f"[QUANTUM] Simulation ({q.get('qubits', 0)} qubits): "
                f"Prob(1)={q.get('counts', {}).get('1' * q.get('qubits', 0), 0) / 10.0}% "
                f"(evidence_id={q.get('evidence_id')})"
            )

        errors = data.get("source_errors", [])
        if errors:
            parts.append(
                "[LIMITATIONS] Unavailable sources: "
                + ", ".join(str(item) for item in errors)
            )

        return "\n".join(parts)
