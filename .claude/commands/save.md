# Save — Persiste o estado atual do SuperEzio

Goal: Salvar documentação, checkpoint e changelog com o estado real do projeto.

## O que salvar
1. `.f51/checkpoints/latest.json` — estado atual dos gates
2. `CLAUDE.md` e `AGENTS.md` — se houve mudança de regra
3. `docs/` — documentação atualizada
4. `ROADMAP.md` — se milestones mudaram
5. Git commit local — OBRIGATÓRIO após cada mudança mínima

## O que NUNCA salvar
- Segredos, tokens, API keys
- Fotos privadas, dados pessoais
- Modelos (.gguf, .bin)
- Datasets crus (>1MB)
- Logs temporários
- `.agent_bus/runtime/` (volátil)

## Gates antes de salvar
```powershell
git status --short
git diff --stat
python -m ruff check src/ tests/
```

## Commit message format
```
<type>(<scope>): <description>
```
Types: feat, fix, docs, refactor, test, chore, save
Scope: f51, pipeline, experts, model, agents, docs, runtime

## Exemplo
```
save(agents): deploy 10-agent swarm + commands v1
```
