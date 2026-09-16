# AGENT_ORCHESTRATION.md — SuperEzio Agent Army Operating Manual

Status: **active**
Version: 1.0
Based on: Playbook 2026 — Exércitos de Claude Code + F51 Operational Layer

## Filosofia

O exército de agentes do SuperEzio não é um bando de agentes falando ao mesmo tempo.
É um sistema com:

- **objetivo claro** por missão;
- **papéis separados** sem sobreposição de escrita;
- **contexto limpo** por agente;
- **evidência obrigatória** em toda afirmação;
- **gates determinísticos** antes de aceitar qualquer saída;
- **seleção natural** — agentes ruins são substituídos por melhores.

## Estrutura de Agentes

```
.claude/agents/
├── captain.md                   # ★ Capitão residente — orquestrador autônomo (cron-driven)
├── product-delivery-orchestrator.md # Slice, aceite, ownership e gates
├── product-implementer.md       # Único builder de produto por ticket
├── ai-eval-verifier.md          # Evals e regressões independentes
├── reliability-sre-operator.md  # Operação e recuperação por runbook
├── release-readiness-manager.md # Release candidate reproduzível
├── recon-researcher.md          # Arqueólogo — mapeia arquitetura real
├── security-reviewer.md         # Auditor de segurança — secrets, vulns, vetores
├── code-quality-reviewer.md     # Qualidade de código — lint, dead code, complexidade
├── runtime-verifier.md          # Runtime — health checks, GPU, processos, logs
├── training-verifier.md         # Treino — classifica scripts, valida datasets
├── api-contract-verifier.md     # Contratos — breaking changes, schema drift
├── model-gateway-verifier.md    # Gateway — DeepSeek oficial, latência, fail-closed (GLM opcional)
├── frontend-ux-reviewer.md      # Frontend — smoke test, acessibilidade, chat
├── kb-domain-reviewer.md        # Conhecimento — precisão conceitual, docs
├── savekeeper.md                # Verdade durável — docs, checkpoints, changelog
├── agent-explorer.md            # Meta — avalia qualidade dos agentes
├── agent-benchmarker.md         # Meta — testa agentes com mesma tarefa
├── agent-replacer.md            # Meta — substitui agentes ruins
├── market-data-puller.md        # Mercado — folha de dados (read-only, anti-injeção)
├── market-thesis-writer.md      # Mercado — único Write-holder (tese em runtime/reports/)
├── market-thesis-auditor.md     # Mercado — auditoria pass/fail (read-only)
├── heart-p0-ingest.md           # Coração P0 — gravador cru (composer-2.5-fast)
├── heart-p1-archive.md          # Coração P1 — universo + as-traded
├── heart-p2-events.md           # Coração P2 — livro de eventos
├── heart-p3-cause.md            # Coração P3 — atribuição
├── heart-p4-panel.md            # Coração P4 — painel ranking
├── heart-p5-ml.md               # Coração P5 — gestor de caminhos (primeira classe)
└── deprecated/                  # Cemitério de agentes
```

O **Captain** é o único agente **residente**. Os outros de produto são one-shot disparados por ele ou pela sessão.
Os 6 `heart-*` são o exército permanente do módulo Coração; lançar sempre com `model: composer-2.5-fast`.
Roster JSON: `docs/superpowers/agents/heart-roster.json`.
O trio `market-*` segue o padrão de separação de poderes dos templates oficiais da Anthropic
(data-puller → builder → auditor) — ver `docs/architecture/AGENT_PATTERNS_ANTHROPIC_FS.md`.
O Captain executa o ciclo selecionado pelo risco:
slice/aceite → implementer → verifier independente → SRE/runtime → release → savekeeper.
Pesquisa independente pode ser paralela; edição acoplada é sequencial.

## Ciclo de Vida do Agente

```
candidate → (benchmark win) → active → (3 elite scores) → elite
                                              ↓
                                        (3 failures)
                                              ↓
                                        deprecated → (30 dias) → killed
```

## Agentes vs Skills

Agentes F51 são **papéis operacionais** com escopo e ferramentas.
Skills F51 (`.claude/skills/`) são **capacidades atômicas** que agentes podem referenciar.

Exemplo: `security-reviewer` referencia `f51-secure-scan` e `f51-safety-science`.

## Orquestrador

O orquestrador (Claude Code na sessão principal) é responsável por:
1. Entender o objetivo real
2. Criar plano com papéis definidos
3. Montar contexto limpo para cada agente
4. Escolher subagentes (nunca todos ao mesmo tempo sem necessidade)
5. Integrar relatórios
6. Cortar duplicação
7. Rodar gates
8. Responder ao usuário

## Tamanho do Exército

| Tamanho | Quando Usar |
|---|---|
| 1 agente | Pergunta simples, editar 1 arquivo, rodar 1 teste |
| 4 agentes | Feature ou bug médio (recon + builder + verifier + savekeeper) |
| 8 agentes | Auditoria grande (todos os reviewers) |
| 10 agentes | Release (8 reviewers + benchmarker + savekeeper) |
| 12+ agentes | Só se cada agente tiver pergunta DIFERENTE |

## Regra de Ouro

Token infinito não resolve agente ruim.

O que resolve é:
```
missão clara
+ contexto certo
+ evidência obrigatória
+ verificação
+ seleção natural de agentes
```
