# F51 Engine Contract

**Module:** `src/f51/formulas.py`, `src/f51/gates.py`
**Classification:** core
**Canonical source of truth for all math and gate logic.**

## Public API

### formulas.py

| Function | Signature | Returns | Contract |
|----------|-----------|---------|----------|
| `unified_decision` | `(factors: DecisionFactors, weights: FormulaWeights \| None) -> float` | `float` ∈ [0, 1] | Calcula P(sucesso) via sigmoid ponderada. factors.validate() chamado internamente. |
| `combined_risk` | `(*risks: float) -> float` | `float` ∈ [0, 1] | T-conorm sobre riscos individuais. Risco combinado >= max(r_i). Nenhum risco individual > combined. |
| `proxy_reward` | `(consensus, critic, sanity, diversity_penalty=0, ground_truth_bonus=0, has_ground_truth=False) -> float` | `float` ∈ [0, 0.9] or [0, 1.0] | Recompensa sem gabarito. Cap 0.9 sem ground truth, 1.0 com. |
| `heuristic_uncertainty` | `(text="", numeric_features=None) -> float` | `float` ∈ [0.05, 0.95] | Estimativa de incerteza. Baseline 0.15 + penalidades. |
| `decision_threshold` | `(domain="default") -> float` | `float` ∈ [0.70, 0.85] | Threshold mínimo por domínio. |
| `FormulaWeights.default()` | `() -> FormulaWeights` | `FormulaWeights` | Pesos padrão: veracity=2.0, consensus=1.5, proxy=1.0, robustness=0.5, uncertainty=2.0, danger=3.0 |
| `DecisionFactors.validate()` | `self -> None` | raises `AssertionError` | Todos os fatores em [0, 1]. |

### gates.py

| Class | Method | Returns | Contract |
|-------|--------|---------|----------|
| `VeracityGate.verify` | `(claims, ground_truth, tolerance=0.10) -> VeracityResult` | `VeracityResult` | VeracityResult.passed = True se confidence >= 0.6. Mismatches com diff > 2*tolerance penalizam confiança em 50%. |
| `VeracityGate.check_decision_consistency` | `(decision, constraint, expected) -> VeracityResult` | `VeracityResult` | Bloqueia buy/small_position se constraint = force_wait_or_avoid. |
| `AdversarialCritic.critique` | `(answer, problem) -> CriticResult` | `CriticResult` | Fallback rule-based se sem LLM. Verifica presença de números, tamanho mínimo. |
| `AdversarialCritic.evaluate_finance` | `(features) -> CriticResult` | `CriticResult` | Detecta microcap_preco_alto, var_inconsistente, hype_sem_receita. |
| `ProxyReward.calculate` | `(consensus, critic_result, sanity_ok, diversity, has_ground_truth, ground_truth_match) -> float` | `float` | Delega para proxy_reward formula. |

## Invariants

1. `unified_decision` sempre retorna valor em [0, 1] para qualquer input válido.
2. `combined_risk(r1, r2, ..., rn) >= max(r1, r2, ..., rn)`.
3. Nenhum fator pode ser < 0 ou > 1 (validado por `DecisionFactors.validate()`).
4. `VeracityGate.verify` com lista vazia retorna `passed=True, confidence=1.0`.
5. `proxy_reward` sem ground truth nunca excede 0.9.

## Dependencies

- `core.math.utils`: sigmoid, clamp, t_norm, t_conorm
- Nenhuma dependência de rede
- Nenhuma dependência de modelo/LLM (exceto AdversarialCritic com LLM opcional)
