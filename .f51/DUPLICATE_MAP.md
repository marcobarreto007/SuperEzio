# F51 Duplicate Map — SuperEzio

Este arquivo mapeia de forma detalhada as redundâncias de código, acoplamentos e sobreposições funcionais críticas identificadas no repositório.

---

## 1. Tabela Geral de Duplicatas e Sobreposições (`duplicate`)

| ID | Componente A (Ativo/Novo) | Componente B (Legado/Duplicado) | Nível de Risco | Descrição do Impacto |
|---|---|---|---|---|
| D01 | `src/core/pipeline/prompts/builder.py` | `src/core/pipeline/ceo_prompts.py` | **Alto** | Ambas as classes expõem lógica idêntica de construção de prompts para o CEO local. Alterações de diretrizes em um não se aplicam no outro. |
| D02 | `src/core/pipeline/nodes/*.py` (funções soltas) | `src/core/pipeline/nodes/_mixin.py` (métodos de classe) | **Alto** | Todos os nós do grafo estão implementados de duas formas: como métodos de classe mixin e como funções isoladas. Bugfixes precisam ser feitos em duplicado. |
| D03 | `src/core/math/indicators.py` (Novo) | `src/core/engine/indicators.py` (Legado) | **Médio** | Mesmos 5 indicadores técnicos calculados de formas ligeiramente diferentes (scalar vs pandas series). O legado é importado por endpoints e coletores antigos. |
| D04 | `src/core/pipeline/prompts/gemma.py` | `src/core/prompts/financial_prompts.py` | **Baixo** | Templates de prompts financeiros redundantes, carregando regras antigas misturadas com novas diretrizes. |

---

## 2. Análise Detalhada e Mitigação Recomendada

### D01: Duplicação de Prompts do CEO Local
* **Ocorrência**: `src/core/pipeline/prompts/builder.py` vs `src/core/pipeline/ceo_prompts.py`
* **Por que existe?**: Transição incompleta de arquitetura durante a migração do modelo CEO legado (Nemotron-Nano) para o modelo atual (Qwen3.6-35B / Gemma-4).
* **Risco**: Risco severo de divergência de persona. Se o comitê ou o CEO receber diretrizes divergentes ou desatualizadas (ex: o legado aponta para um modelo e o novo para outro), o veredito pode falhar ou ignorar regras de compliance financeiro.
* **Mitigação Recomendada**: Centralizar toda a construção de prompts no `builder.py` e substituir imports de `ceo_prompts.py` em todo o pipeline. Excluir `ceo_prompts.py` em seguida sob uma tarefa dedicada da skill `f51-refactor`.

### D02: Estrutura Duplicada de Nós do Grafo (Mixin vs Standalone)
* **Ocorrência**: `src/core/pipeline/nodes/_mixin.py` vs `src/core/pipeline/nodes/*.py` (arquivos individuais de nós)
* **Por que existe?**: Sobrevivência de uma arquitetura baseada em herança de mixins clássicos para a transição do LangGraph moderno (que prefere funções puras e isoladas para cada nó).
* **Risco**: Risco crítico de regressão. Qualquer ajuste de comportamento em nós do pipeline (ex: `f51_verdict`, `orchestrator`, `experts`) precisa ser testado e corrigido em ambas as implementações se o grafo de importação do runtime alternar silenciosamente entre as duas.
* **Mitigação Recomendada**: Mapear de onde o `UniversalPipeline` importa os nós do grafo de execução em runtime. Migrar o grafo definitivamente para funções isoladas e remover `_mixin.py` por completo.

### D03: Indicadores Técnicos Duplicados (Math vs Engine)
* **Ocorrência**: `src/core/math/indicators.py` vs `src/core/engine/indicators.py`
* **Por que existe?**: O módulo `core/engine/` foi marcado como depreciado, mas o servidor de API (`endpoints.py`) e os scrapers locais ainda dependem dele devido a tipos de retorno acoplados em formato Pandas.
* **Risco**: Risco médio. O cálculo de Bollinger Bands ou RSI pode dar resultados ligeiramente discrepantes entre a lógica de math (vetorial pura) e a lógica de engine (estruturada em Pandas), gerando falsos positivos na tomada de decisão dos experts técnicos.
* **Mitigação Recomendada**: Refatorar os endpoints de gráficos da API (`agent_server/endpoints.py`) para consumir os indicadores de `core/math/indicators.py` e remover o diretório `core/engine/`.

### D04: Prompts Financeiros Antigos
* **Ocorrência**: `src/core/pipeline/prompts/gemma.py` vs `src/core/prompts/financial_prompts.py`
* **Por que existe?**: Templates experimentais que restaram de sprints antigas do PennyLab e comitês de família.
* **Risco**: Risco baixo de namespace poluído.
* **Mitigação Recomendada**: Consolidar no módulo de prompts do pipeline (`core/pipeline/prompts/`) e apagar os arquivos fora da estrutura canônica do pipeline.
