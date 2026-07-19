# Fase 7 - Idempotencia, Seguranca, Reprodutibilidade

Gerado: 2026-07-19
Escopo: src/core/idempotency/*.py, src/core/security/*.py, src/data/data_hub.py, src/core/pipeline/nodes/experts.py
Metodo: leitura de codigo, busca textual de padroes e smoke checks locais

## Achados

### 7.1 - idempotencia marca bloqueio, mas sucesso nao ficou claramente marcado no fluxo auditado
- Arquivo: src/core/pipeline/nodes/auto_execute_paper.py:107
- Arquivo: src/core/pipeline/nodes/auto_execute_paper.py:113
- Arquivo: src/core/pipeline/nodes/auto_execute_paper.py:172
- Arquivo: src/core/pipeline/nodes/tool_executor.py:717
- Verdict: CONFIRMED
- Classe: INFRAESTRUTURA
- Severidade: ALTA

### 7.2 - exec dinamico presente em custom_tools
- Arquivo: src/tools/custom_tools.py:315
- Verdict: CONFIRMED
- Classe: RISCO
- Severidade: ALTA

### 7.3 - fallback de provider ativo fora de modo pesquisa
- Arquivo: src/core/pipeline/nodes/expert_dialogue.py:204
- Arquivo: src/core/pipeline/nodes/expert_dialogue.py:226
- Arquivo: src/core/model_serving/gateway.py:577
- Verdict: CONFIRMED
- Classe: REPRODUTIBILIDADE
- Severidade: ALTA

### 7.4 - cache de experts sem TTL/limite explicito e chave parcial
- Arquivo: src/core/pipeline/nodes/experts.py:22
- Arquivo: src/core/pipeline/nodes/experts.py:83
- Arquivo: src/core/pipeline/nodes/experts.py:333
- Verdict: CONFIRMED
- Classe: INFRAESTRUTURA
- Severidade: MEDIA

### 7.5 - search_web/extract_web sem shell=True (bom), mas com risco residual de path/env
- Arquivo: src/data/data_hub.py:545
- Arquivo: src/data/data_hub.py:563
- Arquivo: src/data/data_hub.py:598
- Verdict: CONFIRMED
- Classe: SEGURANCA
- Severidade: MEDIA

### 7.6 - DataHub aceita dict vazio como utilizavel
- Arquivo: src/data/data_hub.py:454
- Arquivo: src/data/data_hub.py:483
- Verdict: CONFIRMED
- Classe: EVIDENCIA
- Severidade: MEDIA

## Resumo executivo

| Achado | Classe | Severidade | Status |
|---|---|---|---|
| lacuna de marcacao de sucesso na idempotencia | INFRAESTRUTURA | ALTA | CONFIRMED |
| exec dinamico em custom_tools | RISCO | ALTA | CONFIRMED |
| fallback ativo fora de pesquisa | REPRODUTIBILIDADE | ALTA | CONFIRMED |
| cache sem TTL/limite explicito | INFRAESTRUTURA | MEDIA | CONFIRMED |
| subprocess sem shell=True, com risco residual | SEGURANCA | MEDIA | CONFIRMED |

## Proximo passo
1. Garantir mark_processed tambem no sucesso.
2. Forcar modo sem fallback em pesquisa reprodutivel.
3. Adicionar TTL/LRU no cache de experts.
