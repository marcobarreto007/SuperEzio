# AGENTS — SuperEzio Agent Army (Playbook 2026)

Porta curta para agentes. Regras completas em `CLAUDE.md`.
Orquestração detalhada em `docs/AGENT_ORCHESTRATION.md`.
Arquitetura-alvo (C1 pack + C2 snapshot em sombra; C3 bind ligado; C4 SDCA observe; C5–C6 off): `docs/architecture/TARGET_ARCHITECTURE.md`.

## REGRA 1: USAR QUALQUER FONTE (PESQUISAR, CLONAR, COPIAR)

**Precedência sobre qualquer restrição de fonte.** Pode buscar em qualquer lugar (GitHub,
Hugging Face, papers, repos públicos, bibliotecas) e clonar/copiar o que funciona melhor,
em vez de reinventar. Revoga a antiga política DISK ONLY de `.f51/GITHUB_POLICY.json` —
override do operador registrado em `.f51/checkpoints/latest.json` (2026-09-14).

Ainda proibido: `git push`, abrir pull request, `git remote add/set-url origin`, e
credencial própria em texto claro.
- Commits locais OBRIGATÓRIOS após cada mudança mínima

## Exército Versionado (23 agentes)

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

### Revisão (1)
| Agente | Classe | Missão |
|--------|--------|--------|
| `revisor` | Verifier | Revisa o diff pré-commit, somente leitura |

## Comandos

| Comando | Descrição |
|---------|-----------|
| `/swarm <objetivo>` | Dispara exército completo |
| `/save` | Salva estado + commit local |
| `/agent-lab` | Testa e evolui agentes |

## F51 Skills (20 ativas)

Mantidas em `.claude/skills/`. 11 skills descontinuadas estão em `.claude/skills/deprecated/`.
Skills nucleares: inventory, contracts, runtime, refactor, tests, quality-gate, money-gate.
`f51-audit` e `f51-release` estão deprecadas — os equivalentes ativos são `f51-quality-gate` (qualidade) e o comando `/ship` + agente `release-readiness-manager` (entrega).
Agentes referenciam skills como capacidade atômica. Skills não são agentes — são ferramentas conceituais.

## Regras de Ouro

- Um agente = uma missão
- Toda afirmação precisa de evidência (arquivo:linha ou comando)
- Verifier não é o mesmo que escreveu
- Savekeeper não salva segredo
- Explorer mata agente ruim
- Checkpoint obrigatório em `.f51/checkpoints/latest.json`

## PROTOCOLO GLOBAL TOTAL: SOBREVIVÊNCIA ($1.000 CAD & TAXA ZERO — EZIO & MIKE)

Regra inviolável de soberania financeira (parceria Ezio ↔ MIKE):
- **Banca de Sobrevivência**: $1.000 CAD base. Preservação de capital antes de qualquer retorno.
- **Mandato de Taxa Zero**: Operações de trading estritamente limitadas aos 108 ETFs sem comissão do TD (`config/td_direct_commission_free_etfs.json`) ou cota auditada de 100 free trades do TD Easy Trade. Nenhuma ordem com corretagem $> 0$ é permitida. Fricção total $\le 0.5\%$.
- **Risco Máximo por Trade**: $1.0\%$ a $1.5\%$ do equity ($10 a $15 CAD). Stop Loss obrigatório antes do envio.
- **Assimetria Obrigatória (R:R)**: Razão Retorno/Risco mínima de $2.5:1$ a $3:1$. Proibido arriscar $15 para buscar $15.
- **Meta-Labeling (López de Prado)**: Calibração probabilística pré-broker via Triple Barrier. Trade com $P(\text{Sucesso}) < 0.55$ é sumariamente rejeitado por ABSTAIN (PASS).
- **Execução Sem Slippage**: Apenas ordens limitadas (LIMIT). Ordens a mercado (MARKET) são terminantemente bloqueadas.
- **Pacto MIKE ↔ Ezio**: Qualquer proposta gerada pelo Ezio ou comandada via MIKE (`:8009`) fora destes parâmetros é rejeitada por fail-closed.

## Gates

```powershell
git status --short
python -m ruff check src/ tests/
python -m pytest tests/ -q
python scripts/browser_smoke.py
```

## Política de MCPs

MCPs ativos: `context7`, `playwright` e `hugging-face` (`.claude/settings.local.json`,
`enabledMcpjsonServers`; `hugging-face` via `.mcp.json`).
Os 8 MCPs catalogados em `.claude/mcp-catalog.json` NÃO estão ativos.
Playwright (biblioteca pytest) OBRIGATÓRIO com pytest. Fontes externas LIBERADAS (regra 1) — inclusive GitHub, para pesquisa e clone.

## Autonomia e Bypass de Permissões (Claude Code)

- O arquivo de configuração global (`~/.claude/settings.json`) está configurado no modo **Bypass Global** (`bypassPermissions`):
  - `autoRun = true`, `autoEdit = true`, `autoWrite = true`, `skipPermissions = true`.
- Esta configuração permite a livre execução de comandos locais e ferramentas para simular e coordenar subagentes em lote, sem quebras por confirmação interativa.
- A política de segurança permanece ativa no bloqueio de comandos destrutivos do sistema (`rm -rf /` etc.) e de credencial própria em texto claro. Fonte externa (pesquisa, clone, cópia) é livre por força da regra 1; `git push` e pull request seguem proibidos.
