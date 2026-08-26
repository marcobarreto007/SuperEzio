# AGENTS — SuperEzio Agent Army (Playbook 2026)

Porta curta para agentes. Regras completas em `CLAUDE.md`.
Orquestração detalhada em `docs/AGENT_ORCHESTRATION.md`.

## REGRA CRÍTICA: GITHUB BLOQUEADO

Fonte: `.f51/GITHUB_POLICY.json`. Modo **DISK ONLY**.
- NUNCA `git push`, `git pull`, `git fetch`, `gh`
- Commits locais OBRIGATÓRIOS após cada mudança mínima

## Exército Versionado (22 agentes)

### Delivery (5 candidatos)
| Agente | Classe | Missão |
|--------|--------|--------|
| `product-delivery-orchestrator` | Orchestrator | Slice, critérios de aceite, ownership e gates |
| `product-implementer` | Builder | Implementa um ticket em arquivos explicitamente atribuídos |
| `ai-eval-verifier` | Verifier | Evals, regressões, baseline, latência e valor fora da amostra |
| `reliability-sre-operator` | Operator | Startup, recovery, restart, restore e rollback por runbook |
| `release-readiness-manager` | Release | Artefato reproduzível, manifesto, checksums e matriz de gates |

### Verifiers (7)
| Agente | Classe | Missão |
|--------|--------|--------|
| `security-reviewer` | Verifier | Audita segredos, env vars, superfície de ataque |
| `code-quality-reviewer` | Verifier | Lint, dead code, complexidade, tipagem |
| `runtime-verifier` | Verifier | Portas, GPU, processos, logs, health checks |
| `training-verifier` | Verifier | Classifica scripts, valida datasets e checkpoints |
| `api-contract-verifier` | Verifier | Contratos públicos, breaking changes, schema drift |
| `frontend-ux-reviewer` | Verifier | Smoke test, acessibilidade, chat flow |
| `model-gateway-verifier` | Verifier | Provider cascade, latência, fallback, GGUF |

### Researchers (2)
| Agente | Classe | Missão |
|--------|--------|--------|
| `recon-researcher` | Researcher | Mapeia arquitetura real, entrypoints, órfãos |
| `kb-domain-reviewer` | Researcher | Precisão conceitual, docs, signal ledger |

### Meta / Evolution (3)
| Agente | Classe | Missão |
|--------|--------|--------|
| `agent-explorer` | Explorer | Avalia qualidade dos agentes, detecta duplicação |
| `agent-benchmarker` | Explorer | Testa agentes com mesma tarefa, compara scores |
| `agent-replacer` | Explorer | Substitui agentes ruins, promove candidatos |

### Savekeeper (1)
| Agente | Classe | Missão |
|--------|--------|--------|
| `savekeeper` | Savekeeper | Salva verdade durável, checkpoints, changelog |

### Mercado (3)
| Agente | Classe | Missão |
|--------|--------|--------|
| `market-data-puller` | Researcher | Snapshot read-only e rastreável |
| `market-thesis-writer` | Builder | Único writer da tese em runtime |
| `market-thesis-auditor` | Verifier | Auditoria independente da tese |

### Orquestração (1)
| Agente | Classe | Missão |
|--------|--------|--------|
| `captain` | Orchestrator | Seleciona slice e coordena delivery sem liberar o próprio trabalho |

## Comandos

| Comando | Descrição |
|---------|-----------|
| `/swarm <objetivo>` | Dispara exército completo |
| `/save` | Salva estado + commit local |
| `/agent-lab` | Testa e evolui agentes |

## F51 Skills (32 skills)

Mantidas em `.claude/skills/`. Skills nucleares: inventory, contracts, runtime, refactor, tests, audit, release, money-gate.
Agentes referenciam skills como capacidade atômica. Skills não são agentes — são ferramentas conceituais.

## Regras de Ouro

- Um agente = uma missão
- Toda afirmação precisa de evidência (arquivo:linha ou comando)
- Verifier não é o mesmo que escreveu
- Savekeeper não salva segredo
- Explorer mata agente ruim
- Checkpoint obrigatório em `.f51/checkpoints/latest.json`

## Gates

```powershell
git status --short
python -m ruff check src/ tests/
python -m pytest tests/ -q
python scripts/browser_smoke.py
```

## Política de MCPs

MCP autorizado: apenas `chrome-devtools-plugin` / `chrome_devtools` (testes de UI e
depuração do frontend — ver CLAUDE.md, seção "MCPs Registrados e Autorizados").
Playwright (biblioteca pytest) OBRIGATÓRIO com pytest. GitHub BLOQUEADO.

## Autonomia e Bypass de Permissões (Claude Code)

- O arquivo de configuração global (`~/.claude/settings.json`) está configurado no modo **Bypass Global** (`bypassPermissions`):
  - `autoRun = true`, `autoEdit = true`, `autoWrite = true`, `skipPermissions = true`.
- Esta configuração permite a livre execução de comandos locais e ferramentas para simular e coordenar subagentes em lote, sem quebras por confirmação interativa.
- A política de segurança permanece ativa no nível de bloqueio estrito de GitHub (`git push/pull/fetch/gh`) e comandos destrutivos do sistema (`rm -rf /` etc.).
