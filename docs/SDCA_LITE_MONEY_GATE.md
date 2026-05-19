# SDCA-Lite Money Gate

## 1. Que dor comercial esse módulo resolve?

SDCA-Lite resolve a dor de decisões ruins sob incerteza: FOMO, alavancagem impulsiva, dados ruins, latência, sinais velhos, liquidez falsa e experiências históricas ignoradas. O produto empacota isso como um AI Decision Firewall / Cognitive Risk Firewall para bloquear decisões antes que um operador humano, agente LLM ou workflow automatizado transforme incerteza em ação.

## 2. Quem compraria isso?

- Operadores e desks que usam copilotos ou agentes para triagem de decisão.
- Founders e equipes que precisam auditar decisões agentic antes de execução.
- Plataformas de análise financeira que querem uma camada defensiva vendável.
- Equipes de risco, compliance e produto que precisam provar por que uma decisão foi bloqueada, revisada ou liberada.

## 3. Como provar valor em demo de 5 minutos?

1. Enviar um payload conservador para `POST /api/sdca/evaluate` e mostrar `ALLOW` ou `REVIEW`.
2. Enviar um payload FOMO com alavancagem, spread aberto e latência alta.
3. Mostrar `BLOCK`, os `ghost_tokens`, as experiências similares, a ruminação limitada a 3 ciclos e o `audit_log`.
4. Reforçar que nenhuma ordem foi criada e nenhuma corretora foi chamada.

## 4. O módulo reduziu caos ou criou complexidade?

Reduziu caos operacional porque ficou isolado em `core.risk_firewall`, com contratos Pydantic estáveis, memória JSONL local e um endpoint próprio. A integração no pipeline é aditiva: anexa `sdca_firewall` ao estado e ao prompt do CEO sem trocar framework, sem refatorar o grafo inteiro e sem alterar contratos públicos existentes.

## 5. O que falta para virar feature vendável?

- UI simples para exibir ALLOW/BLOCK/REVIEW com ghost tokens e experiências similares.
- Painel de auditoria com filtros por operador, fonte, ativo, decisão e regra aprendida.
- Curadoria de memória real de episódios, com versionamento e revisão humana.
- Métricas de redução de perda evitada, tempo de revisão e taxa de falso positivo.
- Config por cliente para thresholds, pesos e políticas internas.

Resposta esperada: AI Decision Firewall / Cognitive Risk Firewall para operadores, founders e sistemas agentic que precisam bloquear decisões ruins sob incerteza.
