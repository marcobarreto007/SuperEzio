"""
FraudPatternAnalyst — Especialista de detecção de padrões de fraude/manipulação
=================================================================================
Consulta a base local de padrões históricos (FraudManipulationMemory) e compara
o ativo atual com red flags conhecidas usando dados computáveis do DataHub.

REGRAS DE LINGUAGEM OBRIGATÓRIAS:
  ✅ "red flags resembling known manipulation patterns"
  ✅ "requires caution"
  ✅ "insufficient evidence to conclude"
  ✅ "similar to documented case types"
  ❌ NUNCA: "this company is manipulating"
  ❌ NUNCA: "fraud confirmed"
  ❌ NUNCA: "illegal activity detected"
  ❌ NUNCA: claim numérico sem evidence_id

OUTPUT:
  {
    "specialist": "fraud_pattern_analyst",
    "asset": ticker,
    "matched_patterns": [...],
    "similar_case_types": [...],
    "risk_score": 0.0,       # 0.0 – 1.0
        "rule_risk_score": 0.0,  # score pelas regras históricas
        "whale_activity_score": 0.0,
        "whale_signals": [...],
        "guardrails": [...],
    "confidence": 0.0,       # fração de regras avaliáveis que foram avaliadas
    "evidence_ids": [...],   # IDs rastreáveis para dados reais usados
    "limitations": [...],    # o que não pôde ser verificado
    "recommendation_constraint": "none|force_study_more|force_wait_or_avoid"
  }
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from ..observability.neural_log import log_event
from .fraud_memory import FraudManipulationMemory, get_fraud_memory

# Limite inferior de capitalização para classificar como microcap (USD/CAD)
MICROCAP_THRESHOLD_USD = 50_000_000

# Limiar de variação diária de preço para acionar regra de spike
PRICE_SPIKE_THRESHOLD = 0.15  # 15% para qualquer ativo
PRICE_SPIKE_MICROCAP_THRESHOLD = 0.10  # 10% para microcaps

# Thresholds de volume z-score
VOLUME_Z_UNUSUAL = 2.0  # acima → unusual_volume
VOLUME_Z_EXTREME = 3.5  # acima → extreme_volume_spike (subsume unusual)

# Mínimo de hype keywords para acionar regra de descrição
HYPE_KEYWORD_MIN_COUNT = 2

# Thresholds de risk_score para recommendation_constraint
RISK_SCORE_FORCE_WAIT = 0.70
RISK_SCORE_FORCE_STUDY = 0.35

# Limiar de confidence para "baixa qualidade de evidência"
LOW_CONFIDENCE_THRESHOLD = 0.50

# Thresholds de atividade "tipo baleia" / fluxo anômalo
WHALE_VOLUME_ALERT_THRESHOLD = 2.5
WHALE_SOCIAL_POST_THRESHOLD = 3
WHALE_SOCIAL_HYPE_THRESHOLD = 2
WHALE_SOCIAL_QUALITY_THRESHOLD = 4.0


class FraudPatternAnalyst:
    """
    Analista de padrões de fraude/manipulação de mercado.

    Args:
        memory: FraudManipulationMemory. Usa singleton global se não fornecido.
    """

    def __init__(self, memory: FraudManipulationMemory | None = None) -> None:
        self._memory = memory or get_fraud_memory()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        ticker: str,
        market_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analisa o ativo e retorna avaliação de red flags.

        Args:
            ticker: Símbolo do ativo (ex: ENB.TO, AAPL, XYZ.V).
            market_data: Dados de mercado pré-computados (opcional).
                         Se None, busca via DataHub em thread separada.

        Returns:
            Dicionário com risk_score, matched_patterns, limitations, etc.
        """
        log_event("FRAUD_ANALYST", "START", {"ticker": ticker})

        normalized_market_data = self._normalize_market_data_input(ticker, market_data)
        fetch_limitations: list[str] = []

        # Obter dados de mercado ou enriquecer o payload parcial com DataHub.
        if market_data is None or self._needs_market_fetch_enrichment(normalized_market_data):
            fetched_market_data = await self._fetch_market_data(ticker)
            if "error" in fetched_market_data:
                if market_data is None or not self._has_any_observable_data(normalized_market_data):
                    normalized_market_data = fetched_market_data
                else:
                    fetch_limitations.append(
                        f"market_data_enrichment_failed: Could not enrich whale/rule signals from DataHub "
                        f"({fetched_market_data.get('error', 'unknown error')})"
                    )
            else:
                normalized_market_data = self._merge_market_data(
                    normalized_market_data, fetched_market_data
                )

        fetch_failed = "error" in normalized_market_data and not self._has_any_observable_data(
            normalized_market_data
        )

        # Avaliar regras
        rules = self._memory.get_rules()
        computable = self._memory.get_computable_rules()
        non_computable = self._memory.get_non_computable_rules()

        triggered_rules, evaluated_count, evidence_ids, compute_limitations = (
            self._evaluate_computable_rules(
                computable, normalized_market_data, ticker, fetch_failed
            )
        )

        whale_signals, whale_activity_score, whale_evidence_ids, whale_limitations = (
            self._evaluate_whale_signals(normalized_market_data, ticker)
        )
        evidence_ids.extend(whale_evidence_ids)

        # Limitações de regras não computáveis
        provider_limitations = [
            r["limitation_when_absent"] for r in non_computable if r.get("limitation_when_absent")
        ]

        # Limitação de fetch de dados
        if fetch_failed:
            fetch_limitations.append(
                f"market_data_fetch_failed: Could not retrieve market data from DataHub "
                f"({normalized_market_data.get('error', 'unknown error')}) — "
                "computable rules were not evaluated"
            )

        all_limitations = (
            fetch_limitations + compute_limitations + whale_limitations + provider_limitations
        )

        # Calcular score e confidence
        rule_risk_score = self._calculate_risk_score(triggered_rules)
        risk_score = max(rule_risk_score, whale_activity_score)
        confidence = self._calculate_confidence(
            evaluated_count=evaluated_count,
            total_rules=len(rules),
            fetch_failed=fetch_failed,
        )

        # Mapear padrões e casos similares
        triggered_rule_ids = [r["rule_id"] for r in triggered_rules]
        matched_patterns = self._match_patterns(triggered_rule_ids)
        similar_case_types = self._find_similar_case_types(matched_patterns)

        # Determinar constraint
        constraint = self._build_constraint(risk_score, confidence)

        result: dict[str, Any] = {
            "specialist": "fraud_pattern_analyst",
            "asset": ticker,
            "matched_patterns": matched_patterns,
            "similar_case_types": similar_case_types,
            "risk_score": round(risk_score, 3),
            "rule_risk_score": round(rule_risk_score, 3),
            "whale_activity_score": round(whale_activity_score, 3),
            "whale_signals": whale_signals,
            "guardrails": self._build_guardrails(
                risk_score=risk_score,
                whale_signals=whale_signals,
                constraint=constraint,
            ),
            "confidence": round(confidence, 3),
            "evidence_ids": evidence_ids,
            "limitations": all_limitations,
            "recommendation_constraint": constraint,
        }

        log_event(
            "FRAUD_ANALYST",
            "DONE",
            {
                "ticker": ticker,
                "risk_score": result["risk_score"],
                "whale_signals": whale_signals,
                "constraint": constraint,
                "triggered_rules": triggered_rule_ids,
            },
        )

        return result

    def _normalize_market_data_input(
        self,
        ticker: str,
        market_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Normaliza market_data flat ou payload completo do DataCollector."""
        if not market_data:
            return {}

        if "error" in market_data:
            return dict(market_data)

        # Payload já no formato flat esperado pelo analista
        flat_keys = {
            "volume_z_score",
            "recent_volume",
            "daily_return",
            "market_cap",
            "description",
            "revenue",
            "evidence_base_id",
        }
        if flat_keys.intersection(market_data.keys()):
            normalized = dict(market_data)
            normalized.setdefault("ticker", ticker)
            return normalized

        normalized: dict[str, Any] = {
            "ticker": market_data.get("ticker", ticker),
            "analysis_id": market_data.get("analysis_id"),
        }
        collected_at = str(market_data.get("collected_at") or "")
        normalized["data_date"] = (
            # UTC: data usada como chave (evidence_id/data_date); evita dependencia de fuso local
            collected_at[:10] if len(collected_at) >= 10 else datetime.now(UTC).date().isoformat()
        )
        normalized["evidence_base_id"] = (
            market_data.get("analysis_id")
            or f"collected_{normalized['ticker']}_{normalized['data_date']}"
        )

        profile = market_data.get("profile") if isinstance(market_data.get("profile"), dict) else {}
        technicals = (
            market_data.get("technicals") if isinstance(market_data.get("technicals"), dict) else {}
        )
        realtime = (
            market_data.get("realtime_price")
            if isinstance(market_data.get("realtime_price"), dict)
            else {}
        )
        reddit = market_data.get("reddit") if isinstance(market_data.get("reddit"), dict) else {}
        sentiment = (
            market_data.get("sentiment") if isinstance(market_data.get("sentiment"), dict) else {}
        )

        normalized["market_cap"] = profile.get("market_cap")
        normalized["description"] = (
            profile.get("business_summary") or profile.get("description") or ""
        )
        normalized["revenue"] = profile.get("revenue") or profile.get("total_revenue")
        normalized["recent_volume"] = technicals.get("volume")

        daily_return = (
            realtime.get("change_percent")
            or realtime.get("change_pct")
            or technicals.get("daily_return")
        )
        if isinstance(daily_return, (int, float)):
            normalized["daily_return"] = (
                daily_return / 100.0 if abs(daily_return) > 1.5 else daily_return
            )

        top_posts = reddit.get("top_posts") if isinstance(reddit.get("top_posts"), list) else []
        normalized["reddit_qualified_count"] = reddit.get("qualified_count")
        normalized["reddit_hype_flags_count"] = sum(
            len(post.get("hype_flags", [])) for post in top_posts if isinstance(post, dict)
        )
        normalized["reddit_top_quality_score"] = max(
            (float(post.get("quality_score", 0.0)) for post in top_posts if isinstance(post, dict)),
            default=0.0,
        )
        normalized["reddit_signal_label"] = reddit.get("signal_label")
        normalized["reddit_evidence_id"] = (
            reddit.get("evidence_id") or f"reddit_{normalized['ticker']}_{normalized['data_date']}"
        )
        normalized["news_sentiment_score"] = sentiment.get("sentiment_score")
        normalized["news_count"] = sentiment.get("news_count")

        return normalized

    @staticmethod
    def _merge_market_data(
        base_market_data: dict[str, Any],
        fetched_market_data: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(fetched_market_data)
        merged.update(
            {
                key: value
                for key, value in base_market_data.items()
                if value not in (None, "", [], {})
            }
        )
        return merged

    @staticmethod
    def _has_any_observable_data(market_data: dict[str, Any]) -> bool:
        observable_keys = (
            "volume_z_score",
            "recent_volume",
            "daily_return",
            "market_cap",
            "reddit_qualified_count",
            "reddit_hype_flags_count",
        )
        return any(market_data.get(key) not in (None, "") for key in observable_keys)

    @staticmethod
    def _needs_market_fetch_enrichment(market_data: dict[str, Any]) -> bool:
        if not market_data:
            return True
        required_keys = ("volume_z_score", "daily_return", "market_cap")
        return any(market_data.get(key) in (None, "") for key in required_keys)

    # ------------------------------------------------------------------
    # Market data fetch
    # ------------------------------------------------------------------

    async def _fetch_market_data(self, ticker: str) -> dict[str, Any]:
        """Busca dados de mercado via DataHub em thread pool (não bloqueia o event loop)."""
        try:
            return await asyncio.to_thread(self._fetch_market_data_sync, ticker)
        except Exception as exc:
            return {"error": str(exc), "ticker": ticker}

    def _fetch_market_data_sync(self, ticker: str) -> dict[str, Any]:
        """Execução síncrona via DataHub (chamada em thread separada)."""
        from data.data_hub import hub

        today_str = datetime.now(UTC).date().isoformat()  # UTC: chave de data do contexto diario

        candles_result = hub.get_candles(ticker, timeframe="3M")
        if "error" in candles_result:
            return {"error": str(candles_result.get("error")), "ticker": ticker}

        candles = candles_result.get("candles", [])
        if len(candles) < 5:
            return {"error": "insufficient_history", "ticker": ticker}

        # Volume statistics
        volumes = [c["volume"] for c in candles]
        recent_vol = volumes[-1]
        window = min(20, len(volumes))
        avg_vol_20d = sum(volumes[-window:]) / window
        variance = sum((v - avg_vol_20d) ** 2 for v in volumes[-window:]) / window
        std_vol_20d = variance**0.5
        volume_z_score = (recent_vol - avg_vol_20d) / std_vol_20d if std_vol_20d > 0 else 0.0

        # Daily price return
        closes = [c["close"] for c in candles]
        if len(closes) >= 2 and closes[-2] != 0:
            daily_return = float((closes[-1] - closes[-2]) / closes[-2])
        else:
            daily_return = 0.0

        # Company info via profile
        market_cap = None
        description = ""
        revenue = None
        try:
            profile = hub.get_profile(ticker)
            if "error" not in profile:
                market_cap = profile.get("market_cap")
                description = ""
                revenue = None
        except Exception:
            pass

        return {
            "ticker": ticker,
            "volume_z_score": volume_z_score,
            "recent_volume": recent_vol,
            "avg_volume_20d": avg_vol_20d,
            "daily_return": daily_return,
            "market_cap": market_cap,
            "description": description,
            "revenue": revenue,
            "data_date": today_str,
            "evidence_base_id": f"datahub_{ticker}_{today_str}_3mo",
        }

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def _evaluate_computable_rules(
        self,
        rules: list[dict[str, Any]],
        market_data: dict[str, Any],
        ticker: str,
        fetch_failed: bool,
    ) -> tuple[list[dict], int, list[str], list[str]]:
        """
        Avalia regras computáveis contra os dados de mercado.

        Returns:
            (triggered_rules, evaluated_count, evidence_ids, compute_limitations)
        """
        triggered: list[dict[str, Any]] = []
        evidence_ids: list[str] = []
        limitations: list[str] = []
        evaluated = 0

        # Não duplicar entre unusual_volume e extreme_volume_spike
        extreme_volume_fired = False

        for rule in rules:
            rule_id = rule["rule_id"]

            if fetch_failed:
                # Não pode avaliar nenhuma regra computável
                continue

            fired, evidence = self._evaluate_single_rule(
                rule, market_data, ticker, extreme_volume_fired
            )
            evaluated += 1

            if rule_id == "extreme_volume_spike" and fired:
                extreme_volume_fired = True

            if fired:
                triggered.append(rule)
                if evidence:
                    evidence_ids.append(evidence)
            else:
                # Se a regra não disparou por ausência de dado (ex: market_cap=None)
                absence_note = self._check_data_absence(rule_id, market_data)
                if absence_note:
                    limitations.append(absence_note)

        return triggered, evaluated, evidence_ids, limitations

    def _evaluate_single_rule(
        self,
        rule: dict[str, Any],
        market_data: dict[str, Any],
        ticker: str,
        extreme_already_fired: bool = False,
    ) -> tuple[bool, str | None]:
        """Avalia uma regra individual. Retorna (fired, evidence_id)."""
        rule_id = rule["rule_id"]
        today = market_data.get("data_date", datetime.now(UTC).date().isoformat())  # UTC: default de data_date

        if rule_id == "extreme_volume_spike":
            z = market_data.get("volume_z_score")
            if z is None:
                return False, None
            if z >= VOLUME_Z_EXTREME:
                return True, f"extreme_volume_zscore_{ticker}_{today}={z:.2f}"
            return False, None

        if rule_id == "unusual_volume_without_clear_news":
            if extreme_already_fired:
                # extreme_volume_spike subsume este — não duplicar
                return False, None
            z = market_data.get("volume_z_score")
            if z is None:
                return False, None
            if VOLUME_Z_UNUSUAL <= z < VOLUME_Z_EXTREME:
                return True, f"volume_zscore_{ticker}_{today}={z:.2f}"
            return False, None

        if rule_id == "price_spike_high_volatility":
            ret = market_data.get("daily_return")
            if ret is None:
                return False, None
            cap = market_data.get("market_cap")
            threshold = (
                PRICE_SPIKE_MICROCAP_THRESHOLD
                if (cap is not None and cap < 200_000_000)
                else PRICE_SPIKE_THRESHOLD
            )
            if abs(ret) >= threshold:
                return True, f"price_spike_{ticker}_{today}={ret:.2%}"
            return False, None

        if rule_id == "microcap_concentration":
            cap = market_data.get("market_cap")
            if cap is None:
                return False, None
            if cap < MICROCAP_THRESHOLD_USD:
                return True, f"market_cap_{ticker}_{today}={cap}"
            return False, None

        if rule_id == "vague_hype_sector_description":
            desc = (market_data.get("description") or "").lower()
            if not desc:
                return False, None
            hype_keywords: list[str] = rule.get("hype_keywords", [])
            found = [kw for kw in hype_keywords if kw in desc]
            if len(found) >= HYPE_KEYWORD_MIN_COUNT:
                return True, f"hype_keywords_{ticker}_{today}={','.join(found[:3])}"
            return False, None

        if rule_id == "no_revenue_with_operations":
            revenue = market_data.get("revenue")
            cap = market_data.get("market_cap")
            desc = market_data.get("description") or ""
            # Revenue=0 AND market_cap > $10M AND has description (suggests it's operational)
            if (
                revenue is not None
                and revenue == 0
                and cap is not None
                and cap > 10_000_000
                and len(desc) > 50
            ):
                return True, f"revenue_zero_{ticker}_{today}"
            return False, None

        # Unknown rule — skip silently
        return False, None

    def _check_data_absence(self, rule_id: str, market_data: dict[str, Any]) -> str | None:
        """Returns a limitation note if a required data field is missing."""
        if (
            rule_id in ("microcap_concentration", "price_spike_high_volatility")
            and market_data.get("market_cap") is None
        ):
            return f"{rule_id}_skipped: market_cap not available from DataHub for this ticker"
        if rule_id == "no_revenue_with_operations" and market_data.get("revenue") is None:
            return f"{rule_id}_skipped: totalRevenue not available from DataHub for this ticker"
        if rule_id == "vague_hype_sector_description" and not (market_data.get("description") or "").strip():
            return f"{rule_id}_skipped: company description not available from DataHub for this ticker"
        return None

    # ------------------------------------------------------------------
    # Score, confidence, patterns
    # ------------------------------------------------------------------

    def _calculate_risk_score(self, triggered_rules: list[dict[str, Any]]) -> float:
        """Soma dos pesos das regras disparadas, capped at 1.0."""
        total = sum(r.get("weight", 0.0) for r in triggered_rules)
        return min(1.0, total)

    def _calculate_confidence(
        self,
        evaluated_count: int,
        total_rules: int,
        fetch_failed: bool,
    ) -> float:
        """
        Fração de regras avaliadas vs. total de regras conhecidas.
        Se fetch falhou, confidence = 0.
        """
        if fetch_failed or total_rules == 0:
            return 0.0
        return round(evaluated_count / total_rules, 3)

    def _evaluate_whale_signals(
        self,
        market_data: dict[str, Any],
        ticker: str,
    ) -> tuple[list[str], float, list[str], list[str]]:
        """Deriva sinais de atividade tipo baleia / fluxo coordenado."""
        signals: list[str] = []
        evidence_ids: list[str] = []
        limitations: list[str] = []
        today = market_data.get("data_date", datetime.now(UTC).date().isoformat())  # UTC: default de data_date
        whale_score = 0.0

        volume_z = market_data.get("volume_z_score")
        daily_return = market_data.get("daily_return")
        market_cap = market_data.get("market_cap")
        reddit_count = market_data.get("reddit_qualified_count")
        reddit_hype_flags = market_data.get("reddit_hype_flags_count")
        reddit_quality = market_data.get("reddit_top_quality_score")
        reddit_evidence = market_data.get("reddit_evidence_id")

        if isinstance(volume_z, (int, float)) and volume_z >= WHALE_VOLUME_ALERT_THRESHOLD:
            signals.append("volume_anomaly")
            evidence_ids.append(f"whale_volume_{ticker}_{today}={volume_z:.2f}")
            whale_score = max(whale_score, 0.45 if volume_z < VOLUME_Z_EXTREME else 0.6)

        if (
            isinstance(reddit_count, int)
            and reddit_count >= WHALE_SOCIAL_POST_THRESHOLD
            and isinstance(reddit_hype_flags, int)
            and reddit_hype_flags >= WHALE_SOCIAL_HYPE_THRESHOLD
        ):
            signals.append("social_hype_cluster")
            evidence_ids.append(
                f"{reddit_evidence or f'reddit_{ticker}_{today}'}:posts={reddit_count}:hype_flags={reddit_hype_flags}"
            )
            whale_score = max(whale_score, 0.45)

        if (
            isinstance(reddit_count, int)
            and reddit_count >= WHALE_SOCIAL_POST_THRESHOLD
            and isinstance(reddit_quality, (int, float))
            and reddit_quality >= WHALE_SOCIAL_QUALITY_THRESHOLD
        ):
            signals.append("high_attention_social_cluster")
            evidence_ids.append(
                f"{reddit_evidence or f'reddit_{ticker}_{today}'}:quality={float(reddit_quality):.2f}"
            )
            whale_score = max(whale_score, 0.5)

        if (
            isinstance(daily_return, (int, float))
            and abs(daily_return) >= PRICE_SPIKE_MICROCAP_THRESHOLD
            and isinstance(market_cap, (int, float))
            and market_cap < 200_000_000
        ):
            signals.append("microcap_price_dislocation")
            evidence_ids.append(f"whale_price_dislocation_{ticker}_{today}={daily_return:.2%}")
            whale_score = max(whale_score, 0.55)

        if "volume_anomaly" in signals and (
            "social_hype_cluster" in signals or "high_attention_social_cluster" in signals
        ):
            signals.append("possible_whale_or_coordinated_flow")
            whale_score = max(whale_score, 0.75)

        if reddit_count in (None, ""):
            limitations.append(
                "social_whale_signal_limited: Reddit/social signal not available in this run"
            )

        return sorted(set(signals)), min(1.0, whale_score), evidence_ids, limitations

    def _build_guardrails(
        self,
        risk_score: float,
        whale_signals: list[str],
        constraint: str,
    ) -> list[str]:
        guardrails = [
            "Treat whale/manipulation signals as operational caution, never as proof of fraud.",
            "Social signal (Reddit/hype) is public discussion, not audited fact.",
        ]

        if whale_signals:
            guardrails.append(
                "If anomalous flow or coordinated hype signals are present, avoid urgency and state false-breakout risk."
            )
        if constraint == "force_wait_or_avoid":
            guardrails.append(
                "With constraint force_wait_or_avoid, do not suggest entry, small_position, or aggressive timing."
            )
        elif constraint == "force_study_more":
            guardrails.append(
                "With constraint force_study_more, emphasize additional diligence before any action."
            )
        elif risk_score > 0:
            guardrails.append(
                "Even without a maximum block, highlight additional confirmation of volume, news, and liquidity."
            )

        return guardrails

    def _match_patterns(self, triggered_rule_ids: list[str]) -> list[str]:
        """Retorna os pattern_ids associados às regras que dispararam."""
        patterns_found: set[str] = set()
        rules = self._memory.get_rules()
        for rule in rules:
            if rule["rule_id"] in triggered_rule_ids:
                for pid in rule.get("matched_patterns", []):
                    patterns_found.add(pid)
        return sorted(patterns_found)

    def _find_similar_case_types(self, matched_patterns: list[str]) -> list[str]:
        """
        Retorna case_types dos casos seed que coincidem com os padrões detectados.
        Apenas casos genéricos documentados — sem acusação a empresas reais.
        """
        cases = self._memory.get_enforcement_cases_by_types(matched_patterns)
        seen: set[str] = set()
        result: list[str] = []
        for case in cases:
            ct = case.get("case_type", "")
            if ct and ct not in seen:
                seen.add(ct)
                result.append(ct)
        return result

    def _build_constraint(self, risk_score: float, confidence: float) -> str:
        """
        Determina a restrição de recomendação baseada no score e confidence.

        Regras (em ordem de prioridade):
          1. risk_score >= 0.70 → force_wait_or_avoid (bloqueia small_position)
          2. risk_score >= 0.35 → force_study_more
          3. else → none

        Override adicional:
          Se risk_score >= 0.50 E confidence < LOW_CONFIDENCE_THRESHOLD
          (não conseguimos avaliar a maioria das regras) → force_study_more
          para garantir que a incerteza seja comunicada.
        """
        if risk_score >= RISK_SCORE_FORCE_WAIT:
            return "force_wait_or_avoid"

        if risk_score >= 0.50 and confidence < LOW_CONFIDENCE_THRESHOLD:
            return "force_study_more"

        if risk_score >= RISK_SCORE_FORCE_STUDY:
            return "force_study_more"

        return "none"

    # ------------------------------------------------------------------
    # Fraud context text (for injection into FINAL_COMPOSITION_PROMPT)
    # ------------------------------------------------------------------

    def format_context_for_orchestrator(self, fraud_result: dict[str, Any]) -> tuple[str, str]:
        """
        Formata o resultado do analista em texto para o prompt do Orchestrator.

        Returns:
            (fraud_context_text, constraint_instruction_text)
        """
        if not fraud_result:
            return "Fraud/manipulation analysis was not executed.", ""

        risk_score = fraud_result.get("risk_score", 0.0)
        patterns = fraud_result.get("matched_patterns", [])
        case_types = fraud_result.get("similar_case_types", [])
        limitations = fraud_result.get("limitations", [])
        confidence = fraud_result.get("confidence", 0.0)
        constraint = fraud_result.get("recommendation_constraint", "none")
        whale_score = fraud_result.get("whale_activity_score", 0.0)
        whale_signals = fraud_result.get("whale_signals", [])
        guardrails = fraud_result.get("guardrails", [])

        # Build context block
        lines = [
            f"Manipulation risk score: {risk_score:.2f} / 1.00",
            f"Whale-like activity score: {whale_score:.2f} / 1.00",
            f"Confidence (fraction of evaluated rules): {confidence:.0%}",
        ]

        if whale_signals:
            lines.append(
                f"Whale-like flow / coordination signals observed: {', '.join(whale_signals)}. "
                "This indicates anomalous or coordinated activity, not proof of illegality."
            )

        if patterns:
            lines.append(
                f"Similar patterns identified: {', '.join(patterns)}. "
                "NOTE: similarity to known patterns is not confirmation of fraud."
            )
        else:
            lines.append("No similar manipulation pattern was identified in the computable data.")

        if case_types:
            lines.append(
                f"Similar documented case types: {', '.join(case_types)} "
                "(generic patterns, not specific cases against this company)."
            )

        if limitations:
            lines.append(
                "Limitations of this analysis (unavailable data):\n"
                + "\n".join(f"  - {lim}" for lim in limitations[:5])
            )
            if len(limitations) > 5:
                lines.append(f"  (+ {len(limitations) - 5} other omitted limitations)")

        if risk_score > 0:
            lines.append(
                "Red flags detected resembling known manipulation patterns. "
                "Requires caution. Insufficient evidence to conclude fraud. "
                "Not enough data to make definitive claims."
            )
        else:
            lines.append(
                "No computable red flag was detected in the available data. "
                "Note: order book, insider filings, and social media data "
                "were not verified (see limitations)."
            )

        if guardrails:
            lines.append(
                "Active guardrails:\n" + "\n".join(f"  - {item}" for item in guardrails[:4])
            )

        context_text = "\n".join(lines)

        # Build constraint instruction
        constraint_text = ""
        if constraint == "force_wait_or_avoid":
            constraint_text = (
                "ACTIVE RESTRICTION (fraud/manipulation): suggested_next_step MUST be 'wait' or 'avoid'. "
                "It MUST NOT return 'small_position'. "
                f"Reason: risk_score={risk_score:.2f} >= 0.70 threshold."
            )
        elif constraint == "force_study_more":
            constraint_text = (
                "ACTIVE RESTRICTION (fraud/manipulation): suggested_next_step MUST be 'study_more'. "
                f"Reason: risk_score={risk_score:.2f} requires additional analysis before action."
            )

        return context_text, constraint_text

    def format_context_for_experts(self, fraud_result: dict[str, Any]) -> str:
        """Contexto compacto para injetar guardrails em todos os experts."""
        if not fraud_result:
            return "[WHALE_GUARDRAILS]\nWhale/manipulation detector was not executed in this run."

        whale_signals = fraud_result.get("whale_signals", [])
        guardrails = fraud_result.get("guardrails", [])
        constraint = fraud_result.get("recommendation_constraint", "none")

        lines = [
            "[WHALE_GUARDRAILS]",
            f"risk_score={fraud_result.get('risk_score', 0.0):.2f}",
            f"whale_activity_score={fraud_result.get('whale_activity_score', 0.0):.2f}",
            f"constraint={constraint}",
            ("signals=" + ", ".join(whale_signals) if whale_signals else "signals=none"),
            "Use these guardrails in EVERY response:",
            "- never treat social hype or anomalous flow as factual confirmation;",
            "- if constraint=force_wait_or_avoid, do not defend entry or small_position;",
            "- if constraint=force_study_more, do not frame the asset as ready to buy;",
            "- state that whale/coordination signals require additional confirmation.",
        ]

        for item in guardrails[:4]:
            lines.append(f"- {item}")

        return "\n".join(lines)
