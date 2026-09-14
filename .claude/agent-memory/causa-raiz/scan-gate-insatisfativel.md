---
name: scan-gate-insatisfativel
description: O gate de qualidade do market_scan exige catalyst/risk/invalidation que nenhum caminho de produção produz; 21/21 scans de 14/09 deram 0 candidatos
metadata:
  type: project
---

O `market_scan` do SuperEzio **nunca aprovou um candidato** em 14/09/2026: 21 runs
com `market_scan`, 0 com `candidates >= 1`. Todo scan termina em `REJECT_ALL` e o
chat responde "Nenhum candidato passou no gate / Nao tenho nome".

**Why:** a causa não é o mercado nem os provedores de preço — preço funciona.
É o gate `evaluate_quality_gates` (`src/core/pipeline/trade_order.py:257`) exigir
`catalyst` + `risk` + `invalidation` com proveniência, e **a única fonte dos três
ser `_generate_fallback_catalyst`** (`src/core/pipeline/nodes/collector.py:599`),
que nunca dispara:

- P1 exige `earnings_date` — nenhum provedor em `src/data/*.py` emite;
- P2 exige `ma50`/`ma200` — nenhum provedor emite;
- P3 exige `change_pct` — o finnhub **entrega** (medido), mas o campo falta no
  allow-list `_RICH_FIELDS` de `_merge` em `_run_scan`, então é descartado.

Nenhum provedor emite `risk`/`downside_risk` para o scan — ou seja, `missing_risk`
é insatisfatível por construção. Medido: candidato com catálise de manchete real
ainda falha em `['missing_risk', 'missing_invalidation']`.

**Resolution (14/09/2026):**
- **Camada 1 resolvida:** Adicionado `change_pct` ao allow-list `_RICH_FIELDS` em `collector.py:1527`. Proveniência de preço e variação agora é carimbada e o fallback de momentum diário dispara quando `change_pct > 2`.
- **Camada 2 resolvida:** Criada função `_derive_missing_risk` em `collector.py`. Quando candidato recebe catalisador externo sem campos de risco/invalidação, deriva risco e invalidação com termos acionáveis (`margin`, `consensus`, `close below`) e proveniência `computed:risk_from_catalyst` amarrada aos inputs reais (`price`/`catalyst`).
- **Camada 3 resolvida:** `data_health_facts` em `scan_verdict.py` atualizado para receber `scan` e inspecionar a telemetria real (`scan_trace`, `provider_sources_used`, proveniência e estado de circuitos abertos). Quando nenhum catalisador é entregue no scan, reporta honestamente `catalyst=none` em vez de mentir que rotas apenas configuradas estão saudáveis.

