---
name: f51-quality-gate
description: Checklist completo antes de declarar pronto. Verifica lint, testes, build, cobertura e regressões.
---

Depois de qualquer mudança funcional:
1. verifique `git status`
2. rode lint, testes e build disponíveis
3. capture falhas reais
4. explique a causa raiz
5. não declare sucesso sem evidência

Defaults para este repo:
- `python -m ruff check src tests`
- `python -m ruff format --check src tests`
- `python -m pytest tests -q`
- `msbuild /property:GenerateFullPaths=true /t:build /consoleloggerparameters:NoSummary` se aplicável

Responda com:

## F51 QUALITY GATE

### Git Status
[clean / dirty]

### Lint
- ruff check: [PASS / FAIL / SKIP]
- ruff format: [PASS / FAIL / SKIP]

### Tests
- pytest: [PASS / FAIL / SKIP]

### Build
- build: [PASS / FAIL / SKIP]

### Cobertura
- [medição real ou SKIP]

### Veredito
[PASS / FAIL / PARTIAL]

### Falhas
- [falha] — [causa raiz]

### Checkpoint
- Atualizar `.f51/checkpoints/latest.json` com resultado do quality gate.