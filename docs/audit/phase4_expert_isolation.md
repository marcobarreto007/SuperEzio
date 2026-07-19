# Fase 4 — Auditoria de Isolamento entre Especialistas

Gerado: 2026-07-19
Escopo: `src/core/pipeline/nodes/experts.py`, `src/core/pipeline/graph.py`
Método: leitura direta de código, rastreamento ponta a ponta da variável `data_context`.
Pergunta motivadora (operador): "os cérebros são sempre o mesmo modelo, com scripts e funções que
deveriam torná-los diferentes — isso está implementado de verdade?"

## Resposta curta: NÃO. Confirmado por leitura de código.

Todos os especialistas (macro, fundamental, momentum, contrarian, sentiment, social_forensics),
todo o red team, todos os juízes e o auditor recebem **exatamente a mesma string de contexto**,
sem filtragem por papel. A única diferença real entre eles é o **prompt de sistema** (a persona
declarada) e o **schema de saída pedido** (`verdict` com valores diferentes por role). Os dados de
entrada não são isolados de forma alguma.

## 1. CONFIRMED — `data_context` é uma única variável global, não segmentada por role

Rastreamento completo, `graph.py`:

- Linha 279: `data_context = str(working_state.get("data_context") or working_state.get("message") or "")`
- Linhas 281-293: `MathHub.calculate_all()` roda uma vez, gera `math_prompt` (contém TODOS os 14 módulos: técnicos, fundamentais, macro/crisis, quantum, portfolio, F51, penny momentum — ver Fase 1), e concatena em `data_context = f"{existing_context}\n\n{math_prompt}"`.
- Essa **mesma** `data_context` (uma string única, já contendo indicadores técnicos, fundamentos, crise, quantum bias, F51 confidence, tudo junto) é passada literalmente igual para:
  - Linha 360: cada especialista do comitê (`_run_one_expert`, dentro do loop `for role in roles for replica_id in range(1, replicas+1)`)
  - Linha 440: cada agente do red team (`_run_one_expert(f"red_team_agent_{i}", 1)`)
  - Linha 469: cada juiz (`_run_judge`)
  - Linha 469 (auditor): o auditor final

Não existe nenhuma função de filtragem, whitelist de campos, ou exclusão de seção antes de montar o payload de cada role. É a mesma variável Python, sem cópia nem edição, passada N vezes.

## 2. CONFIRMED — o prompt por role não pede exclusão de dados, só pede formato de saída diferente

`EXPERT_PROMPTS` (experts.py:119-163) define, para cada um dos 6 roles conhecidos, um par `(system_prompt, user_prompt_template)`. Exemplos:

- `momentum_technical`: `"Technicals for {ticker}.\nContext:\n{context}\n"` — recebe o `{context}` completo (que inclui notícias/macro/crisis se estiverem no math_prompt), não uma fatia técnica isolada.
- `sentiment`: `"Sentiment for {ticker}.\nContext:\n{context}\n"` — mesma coisa, `{context}` completo, incluindo indicadores técnicos.

Nenhum template recorta ou reordena o conteúdo do `{context}`. A única coisa que muda entre eles é a `system_prompt` (persona) e o schema JSON de saída pedido — não os dados fornecidos.

## 3. CONFIRMED — roles sem entrada em `EXPERT_PROMPTS` usam fallback ainda mais genérico

`experts.py:248-253`:

```python
role,
(
    f"You are SuperEzio's {role} expert. Provide concise, data-driven analysis in English. Be quantitative.",
    f"Analyze {ticker} as a {role} expert.\n\nContext:\n{context[:3000]}\n\nProvide a structured assessment with key metrics and risk flags.",
),
```

Isso é usado para `red_team_agent_N`, `judge_agent_N`, `auditor_agent` — todos os papéis "de segunda camada" da arquitetura (veto, julgamento, auditoria). Eles recebem literalmente o mesmo texto template com `{role}` interpolado no nome, e o mesmo `context` (só truncado em 3000 caracteres, sem seleção de conteúdo). **O juiz e o auditor, que deveriam ver "tudo no final" segundo a arquitetura descrita, na prática veem exatamente o mesmo pacote que qualquer especialista individual via — não um resumo consolidado dos vereditos dos outros.**

## 4. O que NÃO foi encontrado (procurado explicitamente e ausente)

Busquei por qualquer mecanismo de:
- Filtrar contexto por role (ex: `if role == "momentum_technical": exclude news`)
- Passar os resultados de outros especialistas para o juiz/auditor (ex: `judge_context = summarize(expert_results)`)
- Ordem diferente de campos por role
- Proibição/validação de que um especialista não mencione dado que não recebeu

**Nenhum desses mecanismos existe no código atual.** O `judge_agent`/`auditor_agent` recebem `data_context` (o pacote bruto de mercado) e não `expert_results`/`judge_results` — ou seja, o juiz hoje **não vê os vereditos dos especialistas**, apesar da arquitetura descrita dizer "só o juiz recebe tudo no final".

## 5. O que É real e funciona

Para não exagerar o problema — o que de fato diferencia os "cérebros" hoje:

1. **System prompt / persona**: cada role tem uma frase de identidade e um schema de verdict diferente (`BULLISH|BEARISH` vs `UNDERVALUED|OVERVALUED` vs `MANIPULATED|CLEAN`).
2. **Temperatura/tokens/timeout podem divergir** por provider (`daytrade_judge` e `daytrade_auditor` têm entradas próprias em `providers.py` com `temperature=0.2` fixo — igual entre si e igual ao `deepseek` genérico, então nem isso diverge de fato hoje).
3. **Réplicas (`SUPEREZIO_EXPERT_REPLICAS`)** rodam o mesmo role múltiplas vezes com o mesmo contexto — isso mede variância de resposta do modelo sob mesmo prompt+dado, não diversidade de perspectiva.

Ou seja: a "diversidade" atual é 100% de prompt (texto de instrução), 0% de dado. Isso é exatamente o inverso do que a especificação original considerava essencial para evitar "seis versões da mesma opinião".

## 6. Resumo executivo desta fase

| Achado | Severidade | Status |
|---|---|---|
| Todos os especialistas recebem o mesmo `data_context` sem filtragem | **ALTA** | CONFIRMED |
| Prompts por role não recortam nem reordenam dados, só mudam persona/schema | ALTA | CONFIRMED |
| Red team / juízes / auditor usam fallback genérico, mesmo contexto truncado em 3000 chars | ALTA | CONFIRMED |
| Juiz/auditor NÃO recebem `expert_results` — não veem os vereditos que deveriam arbitrar | **ALTA** | CONFIRMED |
| Nenhum mecanismo de "momentum não vê notícias" existe | ALTA | CONFIRMED |

## Implicação prática

A pergunta do operador estava certa: hoje, os 6+ "cérebros" são o mesmo modelo, com o mesmo pacote de dados, diferenciados apenas por um parágrafo de instrução. Isso não é necessariamente inútil (prompting por persona pode gerar ângulos de análise úteis), mas **não é o que a arquitetura de pesquisa original exigia** para medir "estabilidade e sensibilidade do veredito" com informação genuinamente segmentada. Sem isolamento real de dado, a correlação entre respostas dos especialistas tende a ser alta — o comitê de 6-18 chamadas mede principalmente ruído de amostragem do mesmo modelo sobre o mesmo prompt longo, não desacordo genuíno entre perspectivas informacionalmente distintas.

Isso não foi corrigido nesta auditoria (é uma mudança de escopo maior — exigiria desenhar um esquema de segmentação de `data_context` por role e um resumo estruturado para o juiz). Registrado para decisão do operador sobre prioridade.

## Próximo passo sugerido

Implementar segmentação de contexto por role (extrair de `math_report.modules` só as seções relevantes por especialista) e dar ao juiz/auditor um resumo de `expert_results` em vez do `data_context` bruto — ou decidir conscientemente manter como está e documentar que a diversidade é apenas de prompt, não de dado.
