
# SuperEzio — Mapa Completo de Guardrails

## LAYER 1: Input Security (antes de tudo)

| Modulo | Classe/Funcao | O que faz | Conectado? |
|---|---|---|---|
| pipeline/security.py | SecurityContext | XSS, SQL injection, null bytes, rate limit, PII filter, output sanitize | endpoint call |
| pipeline/security.py | validate_input() | 10KB max, caracteres de controle, padroes proibidos | endpoint call |
| pipeline/security.py | sanitize_output() | Redact PII, forbidden phrases, truncate 50KB | endpoint call |
| model_serving/sanitizer.py | strip_private_model_channels() | Remove thinking blocks, visible tokens sujos | chamado pelo security |

## LAYER 2: Provider Reliability

| Modulo | Classe | O que faz | Conectado? |
|---|---|---|---|
| pipeline/circuit_breaker.py | CircuitBreaker | CLOSED->OPEN->HALF_OPEN per provider, 5 falhas consecutivas abre | scanner enricher |
| investor/cost_guard.py | CostGuard | Daily budget (0), max 50 runs/dia, estima custo por token | gateway |
| model_serving/gateway.py | ModelGateway | Provider routing, fallback chain, retry, timeout | todo o pipeline |

## LAYER 3: Data Quality Gates

| Modulo | Classe/Funcao | O que faz | Conectado? |
|---|---|---|---|
| pipeline/trade_order.py | evaluate_quality_gates() | 8 gates: ticker, exchange, price, volume, catalyst, risk, invalidation, confidence | scanner + agent |
| pipeline/trade_order.py | decide_final_action() | BUY_CANDIDATE se confidence >= 65 e zero gate failures | scanner + agent |
| pennylab/veracity_gate.py | PennylabVeracityGate | Verifica se dados de penny stock sao confiaveis | pennylab |
| f51/gates.py | VeracityGate | Gate de veracidade de dados generico | f51_verdict |
| f51/gates.py | AdversarialCritic | Critica adversarial — tenta quebrar a propria tese | f51_verdict |

## LAYER 4: Risk Analysis

| Modulo | Classe | O que faz | Conectado? |
|---|---|---|---|
| risk_firewall/sdca_lite.py | (funcoes) | ALLOW/REVIEW/BLOCK baseado em ghost tokens, regime, concentration | sdca_firewall node |
| risk_firewall/experience_memory.py | retrieve_experiences() | Busca episodios passados similares (Blake2b embedding) | sdca_lite |
| ml/reward_gate.py | RewardGate | DeBERTa-v3-base reward model (304M params) scoring 0-1 | Nao conectado |
| ml/sanity.py | SanityCheck | Verifica se resposta contem dados inventados, contradicoes, hallucination | Nao conectado |

## LAYER 5: Fraud Detection

| Modulo | Classe | O que faz | Conectado? |
|---|---|---|---|
| investor/fraud_analyst.py | FraudPatternAnalyst | Analise de padroes de fraude em tickers | Nao conectado |
| investor/fraud_memory.py | (funcoes) | Memoria de fraudes detectadas | Nao conectado |
| rag/fraud_rag.py | FraudPatternMatcher | Busca patterns de fraude no RAG forense | Nao conectado |
| pennylab/scoring.py | compute_scores() | Scoring de manipulação: pump_score, dump_risk, whale_print | pennylab tool |

## LAYER 6: Trading Guardrails

| Modulo | Classe | O que faz | Conectado? |
|---|---|---|---|
| trading/kill_switch.py | KillSwitch | Daily loss 00, max drawdown 10%, 5 losses consecutivas = bloqueia | DEFINIDO, nao integrado |
| trading/approval_gate.py | ApprovalGate | Trade acima de 00 risco requer aprovacao humana | DEFINIDO, nao integrado |
| trading/position_sizer.py | PositionSizer | Max 10% equity por posicao, max 2% risco por trade | DEFINIDO, nao integrado |
| trading/reward.py | RewardFunction | RL reward: PnL alignment + risk-adjustment + confidence calibration | DEFINIDO, nao integrado |
| trading/alerter.py | EmailAlerter | Alerta por email (SMTP) em eventos criticos | DEFINIDO, nao integrado |

## LAYER 7: Crisis & Systemic Risk (12 modelos)

| Modulo | Modelo | O que detecta | Conectado? |
|---|---|---|---|
| crisis/models/lppls_bubble.py | LPPLS | Bolha financeira (log-periodic power law) | Nao |
| crisis/models/markov_regime.py | Markov Switching | Mudanca de regime (bull/bear/crise) | Nao |
| crisis/models/network_contagion.py | Network | Contagio sistemico entre ativos | Nao |
| crisis/models/systemic_bank_risk.py | Systemic Risk | Risco sistemico bancario | Nao |
| crisis/models/shiller_valuation.py | Shiller CAPE | Supervalorizacao por CAPE ratio | Nao |
| crisis/models/minsky_keen.py | Minsky-Keen | Ciclo de credito Minskyano | Nao |
| crisis/models/growth_at_risk.py | GaR | Growth-at-Risk (quantile regression) | Nao |
| crisis/models/hawkes_stress.py | Hawkes | Stress contagion (point process) | Nao |
| crisis/models/bis_credit_gap.py | BIS Credit Gap | Hiato de credito BIS | Nao |
| crisis/models/credit_asset_growth.py | Credit/Asset | Crescimento de credito vs ativos | Nao |
| crisis/models/debt_service_ratio.py | DSR | Debt service ratio | Nao |
| crisis/models/imf_mispricing.py | IMF Mispricing | Misprecificacao de ativos | Nao |
| crisis/expert/crisis_expert.py | CrisisMathExpert | Orquestrador dos 12 modelos | Nao |
| crisis/logic/ensemble.py | Ensemble | Combina score dos 12 modelos em 1 veredito | Nao |

## LAYER 8: Committee & Final Decision

| Modulo | Classe | O que faz | Conectado? |
|---|---|---|---|
| investor/committee.py | InvestorCommittee | Agrega vereditos dos experts, detecta dissenso, calcula confianca composta | parcial |
| pipeline/nodes/sdca_firewall.py | node_sdca_firewall | ALLOW/REVIEW/BLOCK final antes da decisao | sim |
| pipeline/nodes/f51.py | node_f51_verdict | Scoring composto F51 (passed, confidence, risk_flags) | sim |
| pipeline/nodes/guardrails.py | _sdca_blocked_response | Resposta quando SDCA bloqueia | sim |
| pipeline/prompts/builder.py | build_ceo_prompt | Monta prompt do Bob com todos os guardrails | sim |

## RESUMO: Conectado vs Isolado

CONECTADO (7): SecurityContext, CircuitBreaker, CostGuard, QualityGates, SDCA, F51, PromptBuilder
ISOLADO (23): RewardGate, SanityCheck, FraudAnalyst, FraudMemory, FraudRAG, KillSwitch,
                ApprovalGate, PositionSizer, RewardFunction, Alerter, 12 Crisis Models,
                CrisisExpert, Ensemble, InvestorCommittee(parcial)
