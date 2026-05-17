# Duplicate Map — SuperEzio

> Atualizado: 2026-05-17 | Branch: main | Patch session: f51-executor

## Duplicatas Resolvidas (2026-05-17)

### D1 — VeracityGate core/investor → REMOVIDO
```
src/f51/gates.py                              ← CANONICO (mantido)
src/core/investor/veracity_gate.py             ← REMOVIDO (codigo morto, nenhum import)
src/experts/pennylab/experts/veracity_gate.py  ← PennylabVeracityGate (classe DIFERENTE, data quality check)
```
- **Resolucao:** `core/investor/veracity_gate.py` deletado. Nenhum arquivo importava dele.
- **PennylabVeracityGate mantido** — proposito diferente, nome diferente, nao e duplicata.

### D2 — gemma.py shim → REMOVIDO
```
src/core/pipeline/prompts/_prompts.py          ← NOVO (constantes Qwen3.6)
src/core/pipeline/prompts/gemma.py             ← REMOVIDO (shim GEMMA=QWEN)
```
- **Resolucao:** Constantes movidas para `_prompts.py`. `gemma.py` deletado. `builder.py` e `__init__.py` atualizados.

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

## Estado Atual: Zero duplicatas ativas em src/
