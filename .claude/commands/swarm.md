# Swarm — SuperEzio Agent Army

Goal: $ARGUMENTS

## Agent Roster (run in order)

### Wave 1 — Recon & Audit (parallel)
1. **recon-researcher** — mapeia arquitetura, entrypoints, órfãos
2. **security-reviewer** — audita segredos, env vars, MCPs
3. **code-quality-reviewer** — lint, imports quebrados, código morto

### Wave 2 — Runtime & Contracts (parallel, depends on Wave 1 awareness)
4. **runtime-verifier** — portas, GPU, modelo, health checks
5. **api-contract-verifier** — endpoints, schemas, breaking changes
6. **training-verifier** — scripts, datasets, checkpoints, modelos

### Wave 3 — Integration (parallel)
7. **frontend-ux-reviewer** — smoke test, UI funcional
8. **model-gateway-verifier** — provider cascade, latência

### Wave 4 — Meta & Save
9. **agent-explorer** — avalia qualidade dos agentes
10. **savekeeper** — salva docs, checkpoint, changelog

## Rules
- Todo agente devolve: `role, scope, files_read, claims, evidence, risks, next_gate`
- Toda afirmação precisa de evidência (arquivo:linha ou comando executado)
- Nenhum agente edita arquivo de produto sem ticket explícito
- Nenhum segredo, foto, modelo ou dataset cru entra no git
- Resultado final deve passar gates ou declarar bloqueios

## Gates (obrigatórios no final)
```powershell
git status --short
git diff --check
python -m ruff check src/ tests/
python -m pytest tests/ -q
```

## Output esperado
Relatório integrado com:
- Sumário de cada agente
- Bloqueios encontrados
- Riscos por severidade
- Recomendação: GO / NO-GO / HOLD
- Checkpoint atualizado em `.f51/checkpoints/latest.json`
