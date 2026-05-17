# Duplicate Map — SuperEzio

> Atualizado: 2026-05-17 | Branch: main

## Duplicatas Ativas (codigo em src/)

### D1 — VeracityGate (HIGH)
```
src/f51/gates.py                              ← CANONICO
src/core/investor/veracity_gate.py             ← DUPLICATA
src/experts/pennylab/experts/veracity_gate.py  ← DUPLICATA
```
- **Risco:** 3 implementacoes podem divergir
- **Acao:** Consolidar imports para `src/f51/gates.py`

### D2 — GEMMA aliases (LOW)
```
src/core/pipeline/prompts/gemma.py
  GEMMA_SYSTEM_PROMPT = QWEN_SYSTEM_PROMPT   ← SHIM
  GEMMA_PERSONA = QWEN_PERSONA               ← SHIM
```
- **Risco:** Confusao de nomenclatura. GEMMA nao existe mais.
- **Acao:** Remover arquivo, atualizar imports em builder.py e __init__.py

## Duplicatas Arquivadas (seguro, sem acao)

### A1 — SpiderSense
```
src/f51/detectors.py                          ← ATIVO
archive/deprecated/core/math/detectors.py     ← ARQUIVADO
```

### A2 — EpisodeMemory
```
src/f51/memory.py (import opcional)           ← ATIVO
archive/quarantine/f51/memory.py              ← ARQUIVADO
```

## Sobreposicoes de Responsabilidade

### S1 — Investor Committee vs F51 Engine
- `src/core/investor/` — Investor committee com fraud detection, veracity gate proprio
- `src/f51/` — Motor canonico com VeracityGate, AdversarialCritic, RiskEngine
- **Risco:** Dois sistemas de veracity gate coexistindo. Pipeline usa qual?
- **Acao:** Verificar no pipeline graph qual VeracityGate e usado em runtime

### S2 — Data Collector vs Data Hub
- `src/core/data_collector/` — ProfessionalCollector com provider mesh
- `src/data/data_hub.py` — Hub central de dados
- `src/adapters/data_collector/subprocess_collector.py` — Coleta via subprocesso
- **Risco:** 3 camadas de coleta. Orquestracao pode ser confusa.
- **Acao:** Documentar fluxo: User → Pipeline → DataCollector → DataHub → Providers

### S3 — Prompts duplicados
- `src/core/prompts/financial_prompts.py` — Prompts financeiros genericos
- `src/core/pipeline/prompts/builder.py` — Builder de prompts do CEO
- `src/core/investor/prompts.py` — Prompts do investor committee
- **Risco:** Prompts espalhados. Dificil manter consistencia.
- **Acao:** Centralizar ou documentar proposito de cada arquivo

## Modelos Duplicados (resolvido)
- ~~gemma-4-31b-it-Q4_K_M.gguf~~ → Movido para Desktop/modelos antigos/
- ~~Qwen3.6-27B-Q4_K_M.gguf~~ → Movido para Desktop/modelos antigos/
- **Ativo:** Apenas `qwen36-35b-f51.Q4_K_M.gguf`
