"""
Family Investor Committee â€” Motor de anÃ¡lise estratÃ©gica agressiva
========================================================
Orquestra 7 agentes especializados usando DeepSeek como cÃ©rebro.

Pipeline:
  1. OrchestratorAgent â€” define contexto
  2. EducationAgent    â€” explica em linguagem simples
  3. CompanyAnalystAgent â€” analisa tese
  4. ETFPortfolioAgent â€” sugere alternativas diversificadas
  5. RiskOfficerAgent  â€” checagem de risco (pode vetar)
  6. DevilsAdvocateAgent â€” detecta FOMO e hype
  7. DecisionJournalAgent â€” gera perguntas reflexivas
  Final: DeepSeek compÃµe o JSON de saÃ­da

Todos os agentes usam o modelo DeepSeek configurado.
RiskOfficerAgent pode escalar para thinking mode em anÃ¡lise profunda.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from core.security.constants import FORBIDDEN_OUTPUT_PHRASES as FORBIDDEN_PHRASES

from ..data_collector import DataCollector
from ..observability.neural_log import log_event
from ..observability.debug_logger import debug_logger, MODULE_COMMITTEE
from ..prompts.financial_prompts import SUPEREZIO_VERIFICATION_SYSTEM_PROMPT
from .fraud_analyst import FraudPatternAnalyst
from .prompts import (
    EDUCATION_AGENT_PROMPT,
    COMPANY_ANALYST_PROMPT,
    ETF_PORTFOLIO_AGENT_PROMPT,
    RISK_OFFICER_PROMPT,
    DEVILS_ADVOCATE_PROMPT,
    DECISION_JOURNAL_AGENT_PROMPT,
    FINAL_COMPOSITION_PROMPT,
)

# Semaphore global para controle de paralelismo nas chamadas DeepSeek
# Permite no mÃ¡ximo 4 chamadas simultÃ¢neas para evitar rate limit / sobrecarga
_COMMITTEE_SEMAPHORE = asyncio.Semaphore(4)


AI_ANALYSIS_NOTICE = (
    "Evidence-based AI analysis; not a buy/sell instruction, return promise, "
    "or investment execution."
)
FOMO_KEYWORDS = [
    "todo mundo estÃ¡ comprando",
    "nÃ£o posso perder",
    "vai explodir",
    "prÃ³ximo bitcoin",
    "chance Ãºnica",
    "fomo",
    "oportunidade Ãºnica",
    "todo mundo tÃ¡",
    "todo mundo ta",
    "oportunidade de uma vez",
    "everyone is buying",
    "can't miss",
    "going to explode",
    "next bitcoin",
    "once in a lifetime",
]


class InvestorCommittee:
    """
    Comite de 7 agentes para o Family Investor Mode.

    Args:
        deepseek: DeepSeekProvider real. Em testes, injete um stub vindo de
            ``tests/helpers.py``; nunca use mocks dentro de ``src/``.
        cost_guard: CostGuard para controle de orÃ§amento.
    """

    def __init__(
        self,
        deepseek=None,
        cost_guard=None,
        fraud_analyst: FraudPatternAnalyst | None = None,
        data_collector: DataCollector | None = None,
        max_concurrent_calls: int = 4,
    ) -> None:
        self.deepseek = deepseek
        self.cost_guard = cost_guard
        self.fraud_analyst = fraud_analyst
        self.data_collector = data_collector
        self._semaphore = asyncio.Semaphore(max_concurrent_calls)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executa o pipeline completo de anÃ¡lise estratÃ©gica agressiva.

        Args:
            user_input: Dicionario com campos de analise recebidos pelo pipeline.

        Returns:
            DicionÃ¡rio com output estruturado nos campos obrigatÃ³rios.
        """
        ticker = user_input.get("ticker", "").upper().strip()
        amount = user_input.get("amount_available", 0)
        horizon = user_input.get("time_horizon", "not provided")
        goal = user_input.get("goal", "not provided")
        risk_level = user_input.get("risk_level", "")
        has_ef = user_input.get("has_emergency_fund", None)
        notes = user_input.get("notes", "")

        debug_logger.info(
            MODULE_COMMITTEE,
            "Committee analyze START",
            ticker=ticker,
            risk_level=risk_level or "not_set",
            has_emergency_fund=has_ef,
        )
        log_event(
            "INVESTOR_COMMITTEE",
            "START",
            {
                "ticker": ticker,
                "risk_level": risk_level or "not_set",
                "has_emergency_fund": has_ef,
            },
        )

        # Hard rule: has_emergency_fund ausente â†’ tratar como False
        if has_ef is None:
            has_ef = False
            debug_logger.debug(
                MODULE_COMMITTEE, "has_emergency_fund not set - defaulting to False"
            )

        # Verificar cost guard antes de chamar API
        if self.cost_guard:
            self.cost_guard.check()  # levanta RuntimeError se exceder

        # DetecÃ§Ã£o de FOMO nas notas
        fomo_detected = self._detect_fomo(notes)
        debug_logger.debug(
            MODULE_COMMITTEE,
            "FOMO detection",
            fomo_detected=fomo_detected,
            notes_preview=notes[:200] if notes else "(empty)",
        )

        market_context = ""
        collected_market_data: Dict[str, Any] | None = None
        if self.data_collector:
            try:
                collected_market_data = await self.data_collector.collect_all(ticker)
                market_context = DataCollector.format_context(collected_market_data)
            except Exception as exc:
                log_event(
                    "INVESTOR_COMMITTEE",
                    "DATA_COLLECTOR_ERROR",
                    {"ticker": ticker, "error": str(exc)},
                )
                market_context = (
                    "MARKET DATA UNAVAILABLE: DataCollector failed. "
                    "Do not cite market numbers in this run."
                )

        if market_context:
            evidence_instruction = (
                "\n\n[COLLECTED_DATA / EVIDENCE]\n"
                f"{market_context}\n"
                "Use numbers only when an evidence_id exists. If the data is not "
                "present here, mark it as unavailable.\n"
            )
        else:
            evidence_instruction = (
                "\n\n[COLLECTED_DATA / EVIDENCE]\n"
                "No data was collected in this run. Do not cite market numbers.\n"
            )

        # â”€â”€ 1. Rodar detector de baleias / guardrails ANTES dos experts â”€â”€
        fraud_context_text = "Fraud/manipulation analysis was not executed."
        fraud_constraint_instruction = ""
        fraud_constraint = "none"
        expert_guardrail_context = (
            "\n\n[WHALE_GUARDRAILS]\n"
            "Whale/manipulation detector was not executed in this run.\n"
        )
        fraud_result = None

        if self.fraud_analyst:
            try:
                fraud_result = await self.fraud_analyst.analyze(
                    ticker,
                    market_data=collected_market_data,
                )
                fraud_context_text, fraud_constraint_instruction = (
                    self.fraud_analyst.format_context_for_orchestrator(fraud_result)
                )
                fraud_constraint = fraud_result.get("recommendation_constraint", "none")
                expert_guardrail_context = (
                    "\n\n"
                    + self.fraud_analyst.format_context_for_experts(fraud_result)
                    + "\n"
                )
            except Exception as exc:
                log_event(
                    "INVESTOR_COMMITTEE",
                    "FRAUD_ANALYST_ERROR",
                    {"ticker": ticker, "error": str(exc)},
                )
                fraud_context_text = (
                    "Whale/manipulation analysis is unavailable in this run. "
                    f"Internal error: {type(exc).__name__}."
                )
                expert_guardrail_context = (
                    "\n\n[WHALE_GUARDRAILS]\n"
                    "Whale/manipulation detector is unavailable; keep a conservative posture.\n"
                )

        shared_agent_context = (
            "\n\n[NO_GUESSING_CONTRACT]\n"
            + SUPEREZIO_VERIFICATION_SYSTEM_PROMPT
            + "\n"
            + evidence_instruction
            + expert_guardrail_context
        )

        # â”€â”€ 2. Rodar os 6 agentes jÃ¡ sob guardrails compartilhados â”€â”€â”€â”€â”€
        agent_coros = [
            self._run_agent(
                "education",
                EDUCATION_AGENT_PROMPT.format(
                    ticker=ticker, time_horizon=horizon, goal=goal
                )
                + shared_agent_context,
            ),
            self._run_agent(
                "company_analyst",
                COMPANY_ANALYST_PROMPT.format(ticker=ticker) + shared_agent_context,
            ),
            self._run_agent(
                "etf_portfolio",
                ETF_PORTFOLIO_AGENT_PROMPT.format(
                    ticker=ticker, amount_available=amount, time_horizon=horizon
                )
                + shared_agent_context,
            ),
            self._run_agent(
                "risk_officer",
                RISK_OFFICER_PROMPT.format(
                    ticker=ticker,
                    has_emergency_fund=has_ef,
                    risk_level=risk_level or "not provided",
                    time_horizon=horizon,
                    amount_available=amount,
                )
                + shared_agent_context,
                use_reasoner=not has_ef,
            ),
            self._run_agent(
                "devils_advocate",
                DEVILS_ADVOCATE_PROMPT.format(ticker=ticker, notes=notes or "no notes")
                + shared_agent_context,
            ),
            self._run_agent(
                "decision_journal",
                DECISION_JOURNAL_AGENT_PROMPT.format(ticker=ticker)
                + shared_agent_context,
            ),
        ]

        agent_results = list(await asyncio.gather(*agent_coros))

        edu_out, analyst_out, etf_out, risk_out, devil_out, journal_out = agent_results

        # â”€â”€ 3. ComposiÃ§Ã£o final pelo Orchestrator â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        agent_outputs = (
            f"[EDUCATION]\n{edu_out}\n\n"
            f"[COMPANY_ANALYSIS]\n{analyst_out}\n\n"
            f"[PORTFOLIO_ETF]\n{etf_out}\n\n"
            f"[RISK_OFFICER]\n{risk_out}\n\n"
            f"[DEVILS_ADVOCATE]\n{devil_out}\n\n"
            f"[DECISION_JOURNAL]\n{journal_out}"
        )

        final_prompt = FINAL_COMPOSITION_PROMPT.format(
            agent_outputs=agent_outputs,
            fraud_context=fraud_context_text,
            fraud_constraint_instruction=fraud_constraint_instruction,
            ticker=ticker,
            amount_available=amount,
            time_horizon=horizon,
            goal=goal,
            risk_level=risk_level or "not provided",
            has_emergency_fund=has_ef,
            notes=notes or "no notes",
        )

        raw_json = await self._call_deepseek(
            system=(
                "You are the final orchestrator. Respond ONLY with valid JSON in English.\n\n"
                + SUPEREZIO_VERIFICATION_SYSTEM_PROMPT
            ),
            user=final_prompt,
            json_mode=True,
            max_tokens=2000,
        )

        result = self._parse_and_validate(
            raw_json,
            ticker=ticker,
            has_emergency_fund=has_ef,
            risk_level=risk_level,
            fomo_detected=fomo_detected,
            journal_out=journal_out,
            fraud_constraint=fraud_constraint,
        )

        if collected_market_data:
            result["data_quality"] = collected_market_data.get(
                "data_quality", "unknown"
            )
            result["evidence_trace_id"] = collected_market_data.get("analysis_id")
            result["source_errors"] = collected_market_data.get("source_errors", [])

        # â”€â”€ 4. Adicionar fraud_manipulation_check ao resultado â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if fraud_result:
            result["fraud_manipulation_check"] = {
                "risk_score": fraud_result.get("risk_score", 0.0),
                "rule_risk_score": fraud_result.get("rule_risk_score", 0.0),
                "whale_activity_score": fraud_result.get("whale_activity_score", 0.0),
                "whale_signals": fraud_result.get("whale_signals", []),
                "guardrails": fraud_result.get("guardrails", []),
                "matched_patterns": fraud_result.get("matched_patterns", []),
                "similar_case_types": fraud_result.get("similar_case_types", []),
                "limitations": fraud_result.get("limitations", []),
                "recommendation_constraint": fraud_result.get(
                    "recommendation_constraint", "none"
                ),
            }
            result["whale_guardrails_check"] = {
                "whale_activity_score": fraud_result.get("whale_activity_score", 0.0),
                "whale_signals": fraud_result.get("whale_signals", []),
                "guardrails": fraud_result.get("guardrails", []),
                "recommendation_constraint": fraud_result.get(
                    "recommendation_constraint", "none"
                ),
            }
        else:
            result["fraud_manipulation_check"] = {
                "risk_score": 0.0,
                "rule_risk_score": 0.0,
                "whale_activity_score": 0.0,
                "whale_signals": [],
                "guardrails": [],
                "matched_patterns": [],
                "similar_case_types": [],
                "limitations": [
                    "fraud_analyst_not_configured: FraudPatternAnalyst not provided"
                ],
                "recommendation_constraint": "none",
            }
            result["whale_guardrails_check"] = {
                "whale_activity_score": 0.0,
                "whale_signals": [],
                "guardrails": [],
                "recommendation_constraint": "none",
            }

        log_event(
            "INVESTOR_COMMITTEE",
            "DONE",
            {
                "ticker": ticker,
                "suggested": result.get("suggested_next_step"),
                "fraud_risk_score": result["fraud_manipulation_check"]["risk_score"],
            },
        )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_agent(
        self,
        role: str,
        prompt: str,
        use_reasoner: bool = False,
    ) -> str:
        """Executa um Ãºnico agente e retorna o texto da resposta."""
        debug_logger.debug(
            MODULE_COMMITTEE,
            f"Running agent: {role}",
            use_reasoner=use_reasoner,
            prompt_length=len(prompt),
        )
        debug_logger.start_timer(f"_run_agent.{role}")
        try:
            result = await self._call_deepseek(
                system=f"You are the {role} agent for Family Investor Mode. "
                "Be objective, direct, and never guarantee results. Respond in English.",
                user=prompt,
                use_reasoner=use_reasoner,
                max_tokens=600,
            )
            elapsed = debug_logger.stop_timer(f"_run_agent.{role}")
            debug_logger.debug(
                MODULE_COMMITTEE,
                f"Agent {role} completed",
                duration_ms=round(elapsed, 1),
                response_length=len(result),
            )
            return result
        except Exception as exc:
            elapsed = debug_logger.stop_timer(f"_run_agent.{role}")
            debug_logger.error(
                MODULE_COMMITTEE,
                f"Agent {role} FAILED",
                role=role,
                error=str(exc),
                duration_ms=round(elapsed, 1),
            )
            log_event(
                "INVESTOR_COMMITTEE",
                "AGENT_ERROR",
                {
                    "role": role,
                    "error": type(exc).__name__,
                },
            )
            return f"[{role}] Analysis unavailable: {exc}"

    async def _call_deepseek(
        self,
        system: str,
        user: str,
        use_reasoner: bool = False,
        max_tokens: int = 800,
        json_mode: bool = False,
        model: str | None = None,
    ) -> str:
        """
        Chama DeepSeek com semÃ¡foro de paralelismo.
        MÃ¡ximo de {max_concurrent_calls} chamadas simultÃ¢neas para
        evitar rate limit e sobrecarga do provider.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        async with self._semaphore:
            return await self.deepseek.chat_completion(
                messages=messages,
                use_reasoner=use_reasoner,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )

    def _detect_fomo(self, notes: str) -> bool:
        if not notes:
            return False
        lower = notes.lower()
        return any(kw in lower for kw in FOMO_KEYWORDS)

    def _parse_and_validate(
        self,
        raw: str,
        ticker: str,
        has_emergency_fund: bool,
        risk_level: str,
        fomo_detected: bool,
        journal_out: str,
        fraud_constraint: str = "none",
    ) -> Dict[str, Any]:
        """
        Faz parse do JSON final e aplica hard rules.
        Se o JSON for invÃ¡lido, retorna estrutura de fallback segura.
        """
        try:
            # Remove possÃ­veis markdown fences
            clean = raw.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:])
                clean = clean.rstrip("`").strip()
            data: Dict[str, Any] = json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            log_event(
                "INVESTOR_COMMITTEE", "JSON_PARSE_ERROR", {"raw_preview": raw[:200]}
            )
            data = self._fallback_response(ticker, raw)

        # â”€â”€ Schema coercion â€” normaliza campos independente de como o modelo respondeu â”€â”€
        # decision_options: sempre lista de strings fixas
        data["decision_options"] = ["study_more", "wait", "small_position", "avoid"]

        # suggested_next_step: garantir que seja um dos valores vÃ¡lidos
        valid_steps = {"study_more", "wait", "small_position", "avoid"}
        if data.get("suggested_next_step") not in valid_steps:
            data["suggested_next_step"] = "study_more"

        # bull_case / bear_case / key_risks: normalizar para lista de strings
        for list_field in (
            "bull_case",
            "bear_case",
            "key_risks",
            "decision_journal_prompt",
        ):
            raw_list = data.get(list_field, [])
            if isinstance(raw_list, list):
                # Se os itens sÃ£o dicts, extrai texto legÃ­vel
                normalized = []
                for item in raw_list:
                    if isinstance(item, str):
                        normalized.append(item)
                    elif isinstance(item, dict):
                        # Tenta extrair campo de texto mais comum
                        text = (
                            item.get("option")
                            or item.get("text")
                            or item.get("description")
                            or item.get("risk")
                            or item.get("point")
                            or str(item)
                        )
                        if text and len(str(text)) < 500:
                            normalized.append(str(text))
                data[list_field] = normalized
            elif isinstance(raw_list, str):
                data[list_field] = [raw_list] if raw_list else []

        # Campos string â€” garantir que sejam strings
        for str_field in (
            "plain_english_summary",
            "business_model",
            "diversification_check",
            "fomo_check",
            "risk_officer_view",
            "devils_advocate",
            "asset_type",
        ):
            val = data.get(str_field)
            if isinstance(val, dict):
                data[str_field] = str(val)
            elif not val:
                data[str_field] = ""

        # â”€â”€ Hard rules â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # 1. Sem reserva de emergÃªncia â†’ forÃ§ar resultado conservador
        if not has_emergency_fund:
            data["suggested_next_step"] = "study_more"
            risks = data.get("key_risks", [])
            emergency_warning = (
                "CRITICAL WARNING: You do not have an emergency fund. "
                "Investing without one is risky because an emergency can force "
                "a sale at the wrong time. Build your reserve first."
            )
            if emergency_warning not in risks:
                risks.insert(0, emergency_warning)
            data["key_risks"] = risks

        # 2. Sem risk_level â†’ forÃ§ar study_more
        if not risk_level or risk_level.lower() in ("", "unclear", "unknown"):
            data["suggested_next_step"] = "study_more"

        # 3. FOMO detectado â†’ escalar para wait ou study_more
        if fomo_detected:
            current = data.get("suggested_next_step", "study_more")
            if current not in ("wait", "study_more", "avoid"):
                data["suggested_next_step"] = "wait"
            data["fomo_check"] = (
                "FOMO detected in your notes. Urgency and euphoria are major "
                "enemies of disciplined investing. Wait, breathe, and review calmly."
            )

        # 4. Fraud constraint â€” aplicado ANTES dos campos defaults
        if fraud_constraint == "force_wait_or_avoid":
            current = data.get("suggested_next_step", "study_more")
            if current not in ("wait", "avoid"):
                data["suggested_next_step"] = "wait"
            # Remover small_position das opÃ§Ãµes disponÃ­veis
            data["decision_options"] = ["study_more", "wait", "avoid"]
            risks = data.get("key_risks", [])
            fraud_warning = (
                "WARNING: Patterns similar to market manipulation were detected. "
                "Red flags resembling known manipulation patterns require additional caution. "
                "Insufficient evidence to conclude fraud."
            )
            if fraud_warning not in risks:
                risks.insert(0, fraud_warning)
            data["key_risks"] = risks

        elif fraud_constraint == "force_study_more":
            # NÃ£o sobrescreve avoid (mais restritivo), mas bloqueia small_position
            current = data.get("suggested_next_step", "study_more")
            if current not in ("wait", "avoid", "study_more"):
                data["suggested_next_step"] = "study_more"

        # 5. Garantir campos obrigatÃ³rios
        data.setdefault("ticker", ticker)
        data.setdefault("asset_type", "unknown")
        data.setdefault("plain_english_summary", "Analysis unavailable.")
        data.setdefault("business_model", "Not identified.")
        data.setdefault("bull_case", [])
        data.setdefault("bear_case", [])
        data.setdefault("key_risks", [])
        data.setdefault("diversification_check", "Consider broad ETFs.")
        data.setdefault("fomo_check", "No FOMO signal detected.")
        data.setdefault("risk_officer_view", "Risk analysis unavailable.")
        data.setdefault("devils_advocate", "Devil's advocate analysis unavailable.")
        data.setdefault(
            "decision_options", ["study_more", "wait", "small_position", "avoid"]
        )
        data.setdefault("suggested_next_step", "study_more")
        data.setdefault(
            "decision_journal_prompt", self._extract_journal_questions(journal_out)
        )
        data["analysis_notice"] = AI_ANALYSIS_NOTICE

        # 6. VerificaÃ§Ã£o de frases proibidas no output final
        output_str = json.dumps(data, ensure_ascii=False).lower()
        found_forbidden = [p for p in FORBIDDEN_PHRASES if p in output_str]
        if found_forbidden:
            log_event(
                "INVESTOR_COMMITTEE", "FORBIDDEN_PHRASE", {"phrases": found_forbidden}
            )
            data["plain_english_summary"] = (
                data.get("plain_english_summary", "")
                + "\n\n[SYSTEM] STAFF+ ENGINEER MODE ACTIVE. "
                "No investment has a guaranteed return."
            )

        return data

    def _extract_journal_questions(self, journal_text: str) -> list:
        """Extrai linhas nÃ£o vazias do output do DecisionJournalAgent."""
        lines = [
            line.strip(" -â€¢1234567890.")
            for line in journal_text.splitlines()
            if line.strip() and len(line.strip()) > 10
        ]
        return (
            lines[:7]
            if lines
            else [
                "Why do I want this asset?",
                "Do I understand how this company makes money?",
                "How much can I lose without affecting my life?",
                "Have I considered more diversified alternatives?",
                "What is my exit plan?",
            ]
        )

    @staticmethod
    def _fallback_response(ticker: str, raw: str) -> Dict[str, Any]:
        """Retorna resposta segura quando o JSON do modelo Ã© invÃ¡lido."""
        log_event(
            "INVESTOR_COMMITTEE",
            "FALLBACK_RESPONSE",
            {
                "ticker": ticker,
                "raw_preview": raw[:300] if raw else "empty",
            },
        )
        return {
            "ticker": ticker,
            "asset_type": "unknown",
            "plain_english_summary": (
                "Structured analysis could not be generated. "
                "Try again or contact support."
            ),
            "business_model": "Not identified.",
            "bull_case": [],
            "bear_case": [],
            "key_risks": ["Analysis unavailable. Try again."],
            "diversification_check": "Consider broad ETFs.",
            "fomo_check": "Analysis unavailable.",
            "risk_officer_view": "Risk analysis unavailable.",
            "devils_advocate": "Analysis unavailable.",
            "decision_options": ["study_more", "wait", "small_position", "avoid"],
            "suggested_next_step": "study_more",
            "decision_journal_prompt": [],
            "analysis_notice": AI_ANALYSIS_NOTICE,
            "_raw_response": raw[:500] if raw else "",
            "_fallback": True,
        }
