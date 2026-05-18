# F51 Architecture: Neural Decision Expert Node

## 1. What It Is

The NeuralDecisionExpert is a rule-based decision copilot that validates market setups, classifies directional regimes, and calibrates uncertainty from forensic fraud/veracity signals.

It is **not** a trained neural network (no LSTM, no MLP, no gradient descent). It uses heuristics driven by:
- **Feature contract validation** — ensures input payload matches `feature_contract.json` spec (types, ranges, enums)
- **Regime detection** — classifies the market into 5 regimes from RSI, trend slope, volume z-score, fraud risk, and volatility
- **Calibrated uncertainty** — computes `uncertainty = 0.15 + 0.45*fraud_risk + 0.35*veracity_gap + extrema_bonus`, clamped to [0.05, 0.95]
- **Directional probability lookup** — per-regime hardcoded probabilities (not inferred from data)

## 2. Pipeline Position

```
Orchestrator → DataCollector → F51Engine → Experts (parallel) → NeuralDecision → RAG → CEO → Explanation
```

The NeuralDecision node sits after all experts emit their calls and before the CEO final verdict. It receives:
- `features` dict: return_1, return_5, rsi_14, atr_pct, volume_zscore, price_vs_ema_21, trend_slope, volatility_regime, liquidity_sweep
- `context` dict: macro_risk, news_sentiment, fraud_risk, veracity_score

It outputs a structured assessment consumed by downstream nodes (CEO, RAG, Explanation):
```json
{
  "expert": "NeuralDecisionExpert",
  "direction_prob": {"up": 0.62, "down": 0.25, "sideways": 0.13},
  "expected_return": 0.0075,
  "drawdown_risk": 0.25,
  "uncertainty": 0.28,
  "regime": "trend_real",
  "recommendation": "alerta_forte",
  "veto": false,
  "reason": "..."
}
```

## 3. Regime Classification (5 Modes)

| Regime | Trigger | Directional Bias |
|--------|---------|-----------------|
| `trend_real` | trend_slope > 0.15, RSI > 65, fraud_risk ≤ 0.6 | 62% up / 25% down / 13% sideways |
| `pump_artificial` | fraud_risk > 0.6 | 15% up / 75% down / 10% sideways |
| `liquidity_hunt` | vol_zscore > 3.0, abs(return_1) > 0.05 | 40% up / 45% down / 15% sideways |
| `high_asymmetry` | volatility_regime ∈ {high, extreme}, not caught above | neutral (33/33/34) |
| `no_edge` | default (fails all above) | neutral (33/33/34) |

## 4. Veto & Guardrails

The expert will veto and block a setup when:
- `fraud_risk > 0.5` — the data integrity is too compromised
- `veracity_score < 0.5` — the ground truth is unreliable
- `drawdown_risk > 0.8` — the risk of capital destruction is unacceptable

A veto produces: `recommendation: "veto_block"`, `veto: true`.

## 5. What This Is NOT

- **Not an LSTM** — there is no sequence model, no 600-bar training window, no gradient optimization
- **Not an MLP** — no PyTorch layers, no backpropagation, no learned weights
- **Not trained on-the-fly** — probabilities are hardcoded per regime, not inferred from price data
- **Not "Santo Graal"** — this is a rule-based guardrail, not an AI oracle

## 6. Future Evolution (Not Implemented)

A future version could replace the hardcoded probability lookup with a lightweight MLP (PriceMLP / PriceTorchMLP) trained on OHLCV features. The architecture already supports this:
- `src/experts/technical_neural/pipeline_hook.py` wires the PriceMLP classifier
- `src/experts/technical_neural/price_mlp.py` has the MLP implementation
- The `predict()` signature accepts features and context dicts — changing the internals to call an MLP instead of a lookup table would not break the contract

The current rule-based approach is correct for production: it enforces contract validity, blocks fraudulent setups deterministically, and never hallucinates a probability.
