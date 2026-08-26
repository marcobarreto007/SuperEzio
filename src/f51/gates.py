"""
f51 unified core — gates.
VeracityGate (checagem de claims) + AdversarialCritic + ProxyReward.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import ClassVar

from .formulas import clamp
from .formulas import proxy_reward as proxy_formula

# =============================================================================
# VERACITY GATE
# =============================================================================


@dataclass
class VeracityResult:
    passed: bool
    confidence: float
    verified: int
    total: int
    mismatches: list[dict]
    details: str


class VeracityGate:
    """Verifica claims (numéricos e lógicos) contra dados reais."""

    DEFAULT_TOLERANCE = 0.10

    def verify(
        self,
        claims: list[tuple[str, float, str]],  # (field, value, context)
        ground_truth: dict[str, float],
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> VeracityResult:
        if not claims:
            return VeracityResult(
                False,
                0.0,
                0,
                0,
                [],
                "Sem claims independentes para verificar.",
            )

        verified = 0
        mismatches = []
        unverifiable = []

        for field_name, value, context in claims:
            actual = ground_truth.get(field_name)
            if actual is None:
                unverifiable.append(f"{field_name}: sem dado real")
                continue

            try:
                claimed_value = float(value)
                actual_value = float(actual)
            except (TypeError, ValueError):
                unverifiable.append(f"{field_name}: valor não numérico")
                continue
            if not math.isfinite(claimed_value) or not math.isfinite(actual_value):
                unverifiable.append(f"{field_name}: valor não finito")
                continue

            diff = abs(claimed_value - actual_value) / max(abs(actual_value), 0.001)
            if diff <= tolerance:
                verified += 1
            else:
                mismatches.append(
                    {
                        "field": field_name,
                        "claimed": claimed_value,
                        "actual": actual_value,
                        "diff": round(diff, 3),
                        "tolerance": tolerance,
                    }
                )

        total = len(claims)
        confidence = clamp(verified / total) if total > 0 else 1.0
        if mismatches:
            severe = sum(1 for m in mismatches if m["diff"] > 2 * tolerance)
            confidence *= 0.5**severe

        passed = confidence >= 0.6
        details_parts = [f"{verified}/{total} claims verificados, confiança {confidence:.1%}"]
        if mismatches:
            details_parts.append(f"{len(mismatches)} discrepâncias")
        if unverifiable:
            details_parts.append(f"{len(unverifiable)} não verificáveis")

        return VeracityResult(
            passed, confidence, verified, total, mismatches, " | ".join(details_parts)
        )

    def check_decision_consistency(
        self, decision: str, constraint: str, expected: str
    ) -> VeracityResult:
        """Verifica se decisão respeita constraints."""
        ok = not (constraint == "force_wait_or_avoid" and decision in ("buy", "small_position"))
        return VeracityResult(
            ok,
            1.0 if ok else 0.0,
            1 if ok else 0,
            1,
            [] if ok else [{"decision": decision, "constraint": constraint}],
            "OK" if ok else f"Decisão {decision} viola constraint {constraint}",
        )


# =============================================================================
# ADVERSARIAL CRITIC
# =============================================================================


@dataclass
class CriticResult:
    is_valid: bool
    confidence: float
    errors: list[str] = field(default_factory=list)
    reasoning: str = ""


class AdversarialCritic:
    """Crítico adversarial: tenta DESTRUIR respostas.

    Pode usar LLM externo ou fallback baseado em regras.
    """

    CHECKLIST: ClassVar[list[str]] = [
        "Contradiz premissa?",
        "Funciona em casos limite (0, 1, -1, ∞)?",
        "Substituindo na equação original, confere?",
        "Cada passo segue logicamente do anterior?",
    ]

    def __init__(self, llm=None):
        self.llm = llm

    def critique(self, answer: str, problem: str) -> CriticResult:
        if self.llm is None:
            # Fallback: verificação básica por regras
            return self._rule_based(answer, problem)
        return self._llm_critique(answer, problem)

    def _rule_based(self, answer: str, problem: str) -> CriticResult:
        errors = []
        # Verifica se resposta contém números onde esperado
        problem_nums = re.findall(r"\d+", problem)
        if problem_nums and not re.findall(r"\d+", answer):
            errors.append("Resposta não contém valores numéricos esperados")
        # Sanidade básica
        if len(answer) < 3:
            errors.append("Resposta muito curta")
        return CriticResult(
            is_valid=len(errors) == 0,
            confidence=0.5 if errors else 0.7,
            errors=errors,
        )

    def evaluate_finance(self, features: dict[str, float]) -> CriticResult:
        """Crítica lógica financeira: verifica inconsistências grotescas."""
        issues = []
        robustness = 1.0

        mcap = features.get("market_cap", 0)
        price = features.get("price", 0)
        # Se market_cap < 50M e price > 10, microcap caro = alerta
        if mcap > 0 and price > 0 and mcap < 50_000_000 and price > 10:
            issues.append("microcap_preco_alto")
            robustness *= 0.8

        vol = features.get("annual_volatility", 0)
        var95 = features.get("var_95", 0)
        if vol > 0 and var95 != 0:
            # VaR aproximado = -z * vol; se divergir muito, alerta
            expected_var = -1.645 * vol
            if abs(var95 - expected_var) / max(abs(expected_var), 0.001) > 0.5:
                issues.append("var_inconsistente")
                robustness *= 0.85

        # Hype keywords excessivos sem revenue
        hype = features.get("hype_keyword_count", 0)
        revenue = features.get("total_revenue", 1)
        if hype >= 3 and revenue < 1_000_000:
            issues.append("hype_sem_receita")
            robustness *= 0.75

        return CriticResult(
            is_valid=len(issues) == 0,
            confidence=round(robustness, 3),
            errors=issues,
        )

    def _llm_critique(self, answer: str, problem: str) -> CriticResult:
        prompt = (
            "You are an adversarial critic. Find errors in this answer.\n\n"
            f"Problem: {problem}\nAnswer: {answer}\n\n"
            "Checklist:\n" + "\n".join(f"- {c}" for c in self.CHECKLIST) + "\n\n"
            "If error found: ERROR: [description]\nIf valid: VALID: [reason]"
        )
        try:
            output = self.llm.generate(prompt=prompt, temperature=0.1, max_tokens=300)
            errors = []
            for line in output.split("\n"):
                if "ERROR:" in line:
                    errors.append(line.split("ERROR:")[-1].strip())
            return CriticResult(
                is_valid=len(errors) == 0,
                confidence=max(0.1, 1.0 - 0.2 * len(errors)),
                errors=errors,
                reasoning=output,
            )
        except Exception as e:  # noqa: BLE001 — LLM externo pode lançar qualquer exceção; fail closed é deliberado
            # Fail CLOSED: erro no critique adversarial não pode virar "tudo
            # certo com confiança média". Sem crítica real, tratamos como
            # não-validado e com confiança BAIXA (mesmo princípio de
            # f51_trade_gate.py: "If in doubt, BLOCK").
            return CriticResult(
                is_valid=False,
                confidence=0.1,
                errors=[f"critique_failed: {e}"],
                reasoning=f"AdversarialCritic._llm_critique raised {e!r}; failing closed.",
            )


# =============================================================================
# PROXY REWARD (cálculo)
# =============================================================================


class ProxyReward:
    """Calcula recompensa sem ground truth."""

    @staticmethod
    def calculate(
        consensus: float,
        critic_result: CriticResult | None = None,
        sanity_ok: bool = True,
        diversity: float = 1.0,
        has_ground_truth: bool = False,
        ground_truth_match: bool = False,
    ) -> float:
        critic_score = critic_result.confidence if critic_result else 0.5
        return proxy_formula(
            consensus=consensus,
            critic=critic_score,
            sanity=1.0 if sanity_ok else 0.0,
            diversity_penalty=1.0 - diversity,
            ground_truth_bonus=1.0 if ground_truth_match else 0.0,
            has_ground_truth=has_ground_truth,
        )
