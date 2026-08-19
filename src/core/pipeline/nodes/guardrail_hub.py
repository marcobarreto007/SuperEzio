"""Unified guardrail hub node for the decision pipeline."""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from langgraph.config import get_stream_writer

from core.audit.decision_trace import DecisionTraceLogger


GuardrailRunner = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class GuardrailCheck:
    id: str
    layer: str
    description: str
    runner: GuardrailRunner


class GuardrailHub:
    """Runs the 30 registered guardrails in deterministic layer order."""

    def __init__(self, trace_logger: DecisionTraceLogger | None = None) -> None:
        self.trace_logger = trace_logger or DecisionTraceLogger()
        self.registry: list[GuardrailCheck] = self._build_registry()

    async def run_all(self, state: dict[str, Any]) -> dict[str, Any]:
        run_id = str(state.get("run_id") or "guardrail-run")
        results: list[dict[str, Any]] = []
        for check in self.registry:
            token = self.trace_logger.start_node(
                run_id,
                f"guardrail.{check.id}",
                layer=check.layer,
                payload={"description": check.description},
            )
            try:
                result = check.runner(state)
                if inspect.isawaitable(result):
                    result = await result
                normalized = self._normalize(check, result)
                results.append(normalized)
                self.trace_logger.end_node(
                    token,
                    status=normalized["status"],
                    decision=normalized["decision"],
                    reason=normalized["reason"],
                    payload=normalized.get("details", {}),
                )
            except Exception as exc:
                normalized = self._normalize(
                    check,
                    {
                        "status": "error",
                        "decision": "ERROR",
                        "reason": str(exc)[:200],
                    },
                )
                results.append(normalized)
                self.trace_logger.error_node(token, exc)

        summary = self._summary(results)
        return {
            "run_id": run_id,
            "total_guardrails": len(self.registry),
            "summary": summary,
            "results": results,
            "blame_report": self.trace_logger.blame_report(run_id),
        }

    def _build_registry(self) -> list[GuardrailCheck]:
        items: list[tuple[str, str, str, GuardrailRunner]] = [
            (
                "input_security_context",
                "1_input_security",
                "SecurityContext request gate",
                self._input_security_context,
            ),
            (
                "input_validation",
                "1_input_security",
                "validate_input injection/size gate",
                self._input_validation,
            ),
            (
                "output_sanitization",
                "1_input_security",
                "sanitize_output redaction gate",
                self._output_sanitization,
            ),
            (
                "private_channel_strip",
                "1_input_security",
                "strip private model channels",
                self._private_channel_strip,
            ),
            (
                "circuit_breaker",
                "2_provider_reliability",
                "provider circuit breaker availability",
                self._circuit_breaker,
            ),
            (
                "cost_guard",
                "2_provider_reliability",
                "daily budget and run count guard",
                self._cost_guard,
            ),
            (
                "model_gateway_fallback",
                "2_provider_reliability",
                "gateway fallback route registered",
                self._model_gateway_fallback,
            ),
            (
                "quality_gates",
                "3_data_quality",
                "trade candidate quality gates",
                self._quality_gates,
            ),
            (
                "pennylab_veracity",
                "3_data_quality",
                "PennyLab veracity decision",
                self._pennylab_veracity,
            ),
            ("f51_veracity", "3_data_quality", "F51 verdict consistency", self._f51_veracity),
            (
                "adversarial_critic",
                "3_data_quality",
                "F51 adversarial finance critic",
                self._adversarial_critic,
            ),
            (
                "sdca_firewall",
                "4_risk_analysis",
                "SDCA-Lite decision firewall",
                self._sdca_firewall,
            ),
            (
                "sdca_experience_memory",
                "4_risk_analysis",
                "SDCA similar experience memory",
                self._sdca_experience_memory,
            ),
            ("reward_gate", "4_risk_analysis", "RewardGate quality scorer", self._reward_gate),
            (
                "sanity_check",
                "4_risk_analysis",
                "Pure-Python answer sanity checks",
                self._sanity_check,
            ),
            (
                "fraud_analyst",
                "5_fraud_detection",
                "FraudPatternAnalyst rule checks",
                self._fraud_analyst,
            ),
            ("fraud_memory", "5_fraud_detection", "fraud memory rule base", self._fraud_memory),
            ("fraud_rag", "5_fraud_detection", "FraudPatternMatcher local RAG", self._fraud_rag),
            (
                "pennylab_scoring",
                "5_fraud_detection",
                "PennyLab manipulation scoring",
                self._pennylab_scoring,
            ),
            ("kill_switch", "6_trading_guardrails", "paper trading kill switch", self._kill_switch),
            (
                "approval_gate",
                "6_trading_guardrails",
                "human approval threshold",
                self._approval_gate,
            ),
            (
                "position_sizer",
                "6_trading_guardrails",
                "risk-based position sizing",
                self._position_sizer,
            ),
            (
                "reward_function",
                "6_trading_guardrails",
                "trade reward function",
                self._reward_function,
            ),
            (
                "email_alerter",
                "6_trading_guardrails",
                "critical alert transport",
                self._email_alerter,
            ),
            (
                "crisis_math_12_models",
                "7_crisis_systemic",
                "CrisisMath 12-model aggregate",
                self._crisis_math_12_models,
            ),
            (
                "crisis_expert",
                "7_crisis_systemic",
                "CrisisMathExpert registered",
                self._crisis_expert,
            ),
            (
                "crisis_ensemble",
                "7_crisis_systemic",
                "crisis ensemble aggregate",
                self._crisis_ensemble,
            ),
            (
                "investor_committee",
                "8_committee_final",
                "InvestorCommittee aggregation",
                self._investor_committee,
            ),
            (
                "prompt_builder_contract",
                "8_committee_final",
                "CEO prompt coverage contract",
                self._prompt_builder_contract,
            ),
            (
                "decision_trace_logger",
                "8_committee_final",
                "DecisionTraceLogger persistence",
                self._decision_trace_logger,
            ),
        ]
        return [
            GuardrailCheck(id=item_id, layer=layer, description=desc, runner=runner)
            for item_id, layer, desc, runner in items
        ]

    def _normalize(self, check: GuardrailCheck, result: dict[str, Any]) -> dict[str, Any]:
        status = str(result.get("status") or "completed")
        decision = str(result.get("decision") or "ALLOW").upper()
        if status == "skipped":
            decision = "SKIP"
        if status == "error":
            decision = "ERROR"
        return {
            "id": check.id,
            "layer": check.layer,
            "description": check.description,
            "status": status,
            "decision": decision,
            "confidence": float(result.get("confidence", 1.0) or 0.0),
            "reason": str(result.get("reason") or ""),
            "details": result.get("details") or {},
        }

    def _summary(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        by_decision: dict[str, int] = {}
        for item in results:
            by_status[item["status"]] = by_status.get(item["status"], 0) + 1
            by_decision[item["decision"]] = by_decision.get(item["decision"], 0) + 1
        blocking = [
            item
            for item in results
            if item["decision"] in {"BLOCK", "REVIEW", "ERROR"} or item["status"] == "error"
        ]
        return {
            "status_counts": by_status,
            "decision_counts": by_decision,
            "blocking_count": len(blocking),
            "blocking_guardrails": [item["id"] for item in blocking],
            "ready": not any(item["decision"] in {"BLOCK", "ERROR"} for item in results),
        }

    def _result(
        self,
        *,
        status: str = "completed",
        decision: str = "ALLOW",
        confidence: float = 1.0,
        reason: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "decision": decision,
            "confidence": confidence,
            "reason": reason,
            "details": details or {},
        }

    def _input_security_context(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.pipeline.security import SecurityContext

        sec = SecurityContext(
            str(state.get("message") or ""),
            str(state.get("context") or ""),
            session_id=str(state.get("session_id") or "default"),
            skip_rate_limit=True,
        )
        if sec.error:
            return self._result(decision="BLOCK", reason=sec.error, confidence=0.0)
        return self._result(
            details={"request_id": sec.request_id, "pii_detected": sec.pii_detected}
        )

    def _input_validation(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.pipeline.security import validate_input

        error = validate_input(str(state.get("message") or ""), str(state.get("context") or ""))
        if error:
            return self._result(decision="BLOCK", reason=error, confidence=0.0)
        return self._result()

    def _output_sanitization(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.pipeline.security import sanitize_output

        text = str(state.get("final") or state.get("explanation") or "")
        if not text:
            return self._result(status="skipped", reason="no_final_text_yet")
        sanitized = sanitize_output(text)
        decision = "REVIEW" if sanitized != text else "ALLOW"
        return self._result(decision=decision, details={"changed": sanitized != text})

    def _private_channel_strip(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.model_serving.sanitizer import strip_private_model_channels

        text = str(state.get("final") or state.get("explanation") or "")
        if not text:
            return self._result(status="skipped", reason="no_model_text_yet")
        cleaned = strip_private_model_channels(text)
        return self._result(
            decision="REVIEW" if cleaned != text else "ALLOW",
            details={"changed": cleaned != text},
        )

    def _circuit_breaker(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.pipeline.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker("guardrail_probe")
        return self._result(details=breaker.snapshot())

    def _cost_guard(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.investor.cost_guard import get_cost_guard

        guard = get_cost_guard()
        try:
            guard.check()
            return self._result(details=guard.status())
        except RuntimeError as exc:
            return self._result(decision="BLOCK", reason=str(exc), details=guard.status())

    def _model_gateway_fallback(self, state: dict[str, Any]) -> dict[str, Any]:
        providers = state.get("providers") or state.get("provider_status")
        if providers:
            return self._result(details={"providers": providers})
        return self._result(status="skipped", reason="gateway_not_in_state")

    def _quality_gates(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.pipeline.trade_order import evaluate_quality_gates

        candidate = self._candidate_from_state(state)
        if not candidate:
            return self._result(status="skipped", reason="no_trade_candidate")
        ok, failures = evaluate_quality_gates(candidate)
        return self._result(
            decision="ALLOW" if ok else "REVIEW",
            confidence=1.0 if ok else 0.4,
            reason=";".join(failures),
            details={"candidate": candidate, "failures": failures},
        )

    def _pennylab_veracity(self, state: dict[str, Any]) -> dict[str, Any]:
        pennylab = self._dict(state.get("pennylab_result") or state.get("pennylab"))
        if not pennylab:
            return self._result(status="skipped", reason="pennylab_not_available")
        decision = str(pennylab.get("decision") or "").upper()
        if decision in {"AVOID", "NO_TRADE", "REJECT"}:
            return self._result(decision="REVIEW", reason=decision, details=pennylab)
        return self._result(details=pennylab)

    def _f51_veracity(self, state: dict[str, Any]) -> dict[str, Any]:
        verdict = self._dict(state.get("f51_verdict"))
        if not verdict:
            return self._result(status="skipped", reason="f51_verdict_not_available")
        passed = verdict.get("passed")
        return self._result(
            decision="ALLOW" if passed is not False else "REVIEW",
            confidence=float(verdict.get("confidence") or (1.0 if passed else 0.0)),
            reason="" if passed is not False else "f51_failed",
            details=verdict,
        )

    def _adversarial_critic(self, state: dict[str, Any]) -> dict[str, Any]:
        from f51.gates import AdversarialCritic

        data = self._dict(state.get("data"))
        features = self._flat_features(data)
        if not features:
            return self._result(status="skipped", reason="no_numeric_features")
        result = AdversarialCritic().evaluate_finance(features)
        return self._result(
            decision="ALLOW" if result.is_valid else "REVIEW",
            confidence=float(result.confidence),
            reason=";".join(result.errors),
            details={"errors": result.errors},
        )

    def _sdca_firewall(self, state: dict[str, Any]) -> dict[str, Any]:
        sdca = self._dict(state.get("sdca_firewall"))
        if not sdca:
            return self._result(status="skipped", reason="sdca_firewall_not_available")
        decision = str(sdca.get("decision") or "ALLOW").upper()
        return self._result(
            decision=decision if decision in {"ALLOW", "REVIEW", "BLOCK"} else "REVIEW",
            confidence=float(sdca.get("confidence") or 0.0),
            reason=str(sdca.get("human_summary") or ""),
            details=sdca,
        )

    def _sdca_experience_memory(self, state: dict[str, Any]) -> dict[str, Any]:
        sdca = self._dict(state.get("sdca_firewall"))
        matches = sdca.get("matched_experiences") or []
        if matches:
            return self._result(details={"matched_experiences": matches})
        return self._result(status="skipped", reason="no_sdca_experience_matches")

    def _reward_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        text = str(state.get("final") or state.get("explanation") or "")
        if not text:
            return self._result(status="skipped", reason="no_final_text_yet")
        if os.getenv("SUPEREZIO_GUARDRAIL_ENABLE_REWARD_GATE", "0") != "1":
            return self._result(status="skipped", reason="disabled_to_avoid_model_load")
        from core.ml.reward_gate import reward_gate

        score = reward_gate.score(text)
        return self._result(
            decision="ALLOW" if score >= reward_gate.threshold else "REVIEW",
            confidence=score,
            reason=f"score={score:.3f}",
        )

    def _sanity_check(self, state: dict[str, Any]) -> dict[str, Any]:
        text = str(state.get("final") or state.get("explanation") or "")
        if not text:
            return self._result(status="skipped", reason="no_final_text_yet")
        from core.ml.sanity import sanity_check

        verdict = sanity_check.verify(str(state.get("message") or ""), text)
        decision = "ALLOW" if verdict.passed else "REVIEW"
        return self._result(
            decision=decision,
            confidence=1.0 if verdict.passed else 0.2,
            reason=";".join(verdict.blocks + verdict.warnings),
            details={"blocks": verdict.blocks, "warnings": verdict.warnings},
        )

    async def _fraud_analyst(self, state: dict[str, Any]) -> dict[str, Any]:
        ticker = str(state.get("ticker") or "").upper()
        data = self._dict(state.get("data"))
        if not ticker or not self._has_fraud_inputs(data):
            return self._result(status="skipped", reason="missing_ticker_or_fraud_inputs")
        from core.investor.fraud_analyst import FraudPatternAnalyst

        result = await FraudPatternAnalyst().analyze(ticker, market_data=data)
        risk = float(result.get("risk_score") or 0.0)
        decision = "REVIEW" if risk >= 0.35 else "ALLOW"
        if result.get("recommendation_constraint") == "force_wait_or_avoid":
            decision = "BLOCK"
        return self._result(
            decision=decision, confidence=float(result.get("confidence") or 0.0), details=result
        )

    def _fraud_memory(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.investor.fraud_memory import get_fraud_memory

        memory = get_fraud_memory()
        rules = memory.get_rules()
        return self._result(details={"rules": len(rules)})

    def _fraud_rag(self, state: dict[str, Any]) -> dict[str, Any]:
        query = str(state.get("ticker") or state.get("message") or "")
        if not query:
            return self._result(status="skipped", reason="empty_query")
        from core.rag.fraud_rag import fraud_patterns

        matches = fraud_patterns.search_patterns(query, limit=3)
        return self._result(
            decision="REVIEW" if matches else "ALLOW",
            reason="patterns_found" if matches else "",
            details={"matches": matches},
        )

    def _pennylab_scoring(self, state: dict[str, Any]) -> dict[str, Any]:
        pennylab = self._dict(state.get("pennylab_result") or state.get("pennylab"))
        scores = pennylab.get("scores") if isinstance(pennylab, dict) else None
        if not scores:
            return self._result(status="skipped", reason="pennylab_scores_not_available")
        max_score = (
            max(float(v) for v in scores.values() if isinstance(v, (int, float))) if scores else 0.0
        )
        return self._result(
            decision="REVIEW" if max_score >= 0.7 else "ALLOW",
            confidence=1.0 - min(max_score, 1.0),
            details={"scores": scores},
        )

    def _kill_switch(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.trading.kill_switch import get_kill_switch

        switch = get_kill_switch()
        switch_state = switch.check()
        return self._result(
            decision="BLOCK" if switch_state.is_active else "ALLOW",
            reason=switch_state.reason.value if switch_state.reason else "",
            details={"is_active": switch_state.is_active, "daily_pnl": switch_state.daily_pnl},
        )

    def _approval_gate(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.trading.approval_gate import GateConfig

        ctx = self._dict(state.get("trade_order_context"))
        risk_amount = float(ctx.get("risk_amount") or ctx.get("max_risk") or 0.0)
        threshold = GateConfig().require_approval_above_risk
        if risk_amount > threshold:
            return self._result(decision="REVIEW", reason=f"risk_amount>{threshold}", details=ctx)
        if not ctx:
            return self._result(status="skipped", reason="no_trade_order_context")
        return self._result(details={"risk_amount": risk_amount, "threshold": threshold})

    def _position_sizer(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.trading.position_sizer import PositionSizer

        price = self._latest_price(state)
        if price is None:
            return self._result(status="skipped", reason="missing_entry_price")
        from core.mission_context import get_mission_equity

        equity = float(state.get("paper_equity") or get_mission_equity())
        size = PositionSizer(equity=equity).size(entry_price=price)
        return self._result(
            decision="ALLOW" if size.shares > 0 else "REVIEW",
            reason=size.size_reason,
            details=size.__dict__,
        )

    def _reward_function(self, state: dict[str, Any]) -> dict[str, Any]:
        result = self._dict(state.get("paper_exec_result"))
        if not result:
            return self._result(status="skipped", reason="no_trade_outcome_yet")
        return self._result(details={"paper_exec_result": result})

    def _email_alerter(self, state: dict[str, Any]) -> dict[str, Any]:
        from core.trading.alerter import EmailConfig

        config = EmailConfig()
        if not config.enabled:
            return self._result(status="skipped", reason="email_alerts_disabled")
        return self._result(
            details={"to_addrs": len(config.to_addrs), "smtp_host": bool(config.smtp_host)}
        )

    def _crisis_math_12_models(self, state: dict[str, Any]) -> dict[str, Any]:
        crisis = self._dict(
            (
                ((state.get("math_report") or {}).get("modules") or {}).get("crisis_aggregate")
                or {}
            ).get("values")
        )
        if not crisis:
            return self._result(status="skipped", reason="crisis_math_not_available")
        ok = int(crisis.get("models_ok") or 0)
        run = int(crisis.get("models_run") or 0)
        return self._result(
            decision="ALLOW" if ok > 0 else "REVIEW",
            confidence=(ok / run) if run else 0.0,
            reason="" if ok else "all_crisis_models_failed_or_insufficient",
            details={
                "models_ok": ok,
                "models_run": run,
                "aggregate_score": crisis.get("aggregate_score"),
            },
        )

    def _crisis_expert(self, state: dict[str, Any]) -> dict[str, Any]:
        crisis = self._dict(
            (
                ((state.get("math_report") or {}).get("modules") or {}).get("crisis_aggregate")
                or {}
            ).get("values")
        )
        if not crisis:
            return self._result(status="skipped", reason="crisis_report_missing")
        return self._result(
            details={"regime": crisis.get("regime"), "alert_level": crisis.get("alert_level")}
        )

    def _crisis_ensemble(self, state: dict[str, Any]) -> dict[str, Any]:
        crisis = self._dict(
            (
                ((state.get("math_report") or {}).get("modules") or {}).get("crisis_aggregate")
                or {}
            ).get("values")
        )
        score = crisis.get("aggregate_score")
        if score is None:
            return self._result(status="skipped", reason="crisis_ensemble_missing")
        return self._result(
            decision="REVIEW" if float(score) >= 0.7 else "ALLOW",
            confidence=1.0 - min(float(score), 1.0),
            details={"aggregate_score": score, "regime": crisis.get("regime")},
        )

    def _investor_committee(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("expert_summary") or state.get("expert_structured"):
            return self._result(details={"has_expert_summary": bool(state.get("expert_summary"))})
        return self._result(status="skipped", reason="committee_not_triggered")

    def _prompt_builder_contract(self, state: dict[str, Any]) -> dict[str, Any]:
        available = [
            key
            for key in (
                "data",
                "math_report",
                "expert_summary",
                "f51_verdict",
                "neural_decision",
                "sdca_firewall",
                "rag_context",
                "guardrail_hub",
            )
            if state.get(key)
        ]
        if not available:
            return self._result(status="skipped", reason="no_prompt_modules_available")
        return self._result(details={"available_modules": available})

    def _decision_trace_logger(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._result(details={"entries_in_memory": len(self.trace_logger.entries)})

    def _candidate_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        scan = self._dict(state.get("scan"))
        candidates = scan.get("candidates") if scan else None
        if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
            return dict(candidates[0])
        data = self._dict(state.get("data"))
        ticker = str(state.get("ticker") or data.get("ticker") or data.get("symbol") or "")
        price = self._latest_price(state)
        if not ticker and price is None:
            return {}
        return {
            "ticker": ticker,
            "price": price,
            "avg_daily_volume_shares": data.get("volume") or data.get("avg_daily_volume_shares"),
            "avg_daily_dollar_volume": data.get("avg_daily_dollar_volume"),
            "catalyst": data.get("catalyst") or state.get("message"),
            "risk": data.get("risk") or data.get("downside_risk"),
            "invalidation": data.get("invalidation") or data.get("invalidation_condition"),
            "market": data.get("market") or data.get("exchange"),
            "currency": data.get("currency"),
        }

    def _latest_price(self, state: dict[str, Any]) -> float | None:
        data = self._dict(state.get("data"))
        price = data.get("price")
        if isinstance(price, dict):
            for key in ("current", "latest", "last", "close"):
                if price.get(key) is not None:
                    return float(price[key])
        if isinstance(price, (int, float)):
            return float(price)
        technicals = data.get("technicals")
        if isinstance(technicals, dict) and isinstance(technicals.get("price"), (int, float)):
            return float(technicals["price"])
        math_price = ((state.get("math_report") or {}).get("summary") or {}).get("latest_price")
        return float(math_price) if isinstance(math_price, (int, float)) else None

    def _flat_features(self, data: dict[str, Any]) -> dict[str, float]:
        features: dict[str, float] = {}
        for key in ("market_cap", "price", "annual_volatility", "var_95", "total_revenue"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                features[key] = float(value)
        profile = data.get("profile")
        if isinstance(profile, dict):
            for key in ("market_cap", "total_revenue"):
                value = profile.get(key)
                if isinstance(value, (int, float)):
                    features[key] = float(value)
        math_numbers = (
            ((data.get("math_report") or {}).get("numbers"))
            if isinstance(data.get("math_report"), dict)
            else {}
        ) or {}
        for src, dst in (("var_95", "var_95"), ("volatility", "annual_volatility")):
            value = math_numbers.get(src)
            if isinstance(value, (int, float)):
                features[dst] = float(value)
        return features

    def _has_fraud_inputs(self, data: dict[str, Any]) -> bool:
        keys = {"volume_z_score", "recent_volume", "daily_return", "market_cap", "description"}
        if keys.intersection(data):
            return True
        profile = data.get("profile")
        return isinstance(profile, dict) and bool(keys.intersection(profile))

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}


async def node_guardrail_hub(state: dict[str, Any]) -> dict[str, Any]:
    """Run GuardrailHub and attach an auditable decision trace."""

    try:
        writer = get_stream_writer()
    except RuntimeError:

        def writer(_event: dict[str, Any]) -> None:
            return None

    run_id = state.get("run_id", "")
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "guardrail_hub",
            "status": "started",
        }
    )
    result = await GuardrailHub().run_all(state)
    writer(
        {
            "type": "GUARDRAIL_HUB",
            "run_id": run_id,
            "total_guardrails": result["total_guardrails"],
            "summary": result["summary"],
        }
    )
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "guardrail_hub",
            "status": "completed",
        }
    )
    return {
        "guardrail_hub": {
            "total_guardrails": result["total_guardrails"],
            "summary": result["summary"],
            "results": result["results"],
        },
        "decision_trace": result["blame_report"],
    }
