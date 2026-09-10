# Claude Ops Catalog

Date: 2026-09-10 (rev. 2)
Substitui a rev. 1 (2026-05-21).

Inventário do que a sessão Claude Code carrega neste projeto: MCPs, skills, comandos e agentes.
Fonte de verdade é o disco — este arquivo é um retrato datado, não uma configuração.

---

## 1. MCP Servers

### Ativos (3)

Habilitados via `.claude/settings.local.json` → `enabledMcpjsonServers`.

| Server | Uso | Origem |
|---|---|---|
| `context7` | Docs atualizadas de libs/frameworks (`resolve-library-id`, `query-docs`) | config do usuário |
| `playwright` | Automação de browser: navigate, snapshot, click, type, screenshot, network, console, tabs (~25 tools) | config do usuário |
| `hugging-face` | Busca de modelos/datasets/Spaces, doc search, Jobs | `.mcp.json` (raiz) — adicionado 2026-09-10 |

`hugging-face` exige `HF_TOKEN` no ambiente (o `.mcp.json` referencia a variável, não o valor). Sem o token o server não autentica. Snippet oficial por cliente: https://huggingface.co/settings/mcp

### Catalogados, NÃO ativos (8)

Em `.claude/mcp-catalog.json`. Referência/planejamento — não estão conectados e não respondem a chamadas:

`google-calendar`, `gmail`, `google-drive`, `notion`, `vercel`, `canva`, `hugging-face`, `play-sheet-music`

Todos HTTP transport, dependentes de OAuth. Uso governado por `AGENTS.md` e `.f51/GITHUB_POLICY.json`.

---

## 2. Skills

### 2.1 Projeto — `.claude/skills/` (21 ativas)

**Operacionais `f51-*` (20)**

| Skill | Trigger |
|---|---|
| `f51-inventory` | mapear repo, entrypoints, baseline |
| `f51-impact-map` | superfície de risco antes de editar |
| `f51-contracts` | validar APIs, schemas, assinaturas |
| `f51-refactor` | simplificação pequena e reversível |
| `f51-dead-code` | Vulture + deptry, código morto |
| `f51-no-mock-police` | caçar mock/dummy/fallback fake em produção |
| `f51-money-gate` | GO/DEFER/NO-GO por ROI 7/30 dias |
| `f51-productizer` | empacotar, pricing, MVP vendável |
| `f51-env-guard` | validar env vars com Pydantic Settings |
| `f51-runtime` | boot, health, portas, logs, runbook |
| `f51-observability` | structlog, Prometheus, trace_id |
| `f51-circuit-breaker` | tenacity, retry, backoff, degradação |
| `f51-idempotency` | idempotency key, dedup, dead letter |
| `f51-secure-scan` | Bandit SAST, secrets, vulnerabilidades |
| `f51-prop-test` | Hypothesis, fuzzing, invariantes |
| `f51-tests` | plano de teste por risco, evidência |
| `f51-quality-gate` | checklist pré-"pronto" |
| `f51-doc-sync` | sincronizar README/CLAUDE.md pós-código |
| `f51-windows-compat` | paths, encoding, subprocess, venv |
| `f51-safety-science` | pesquisa em saúde, evidência conservadora |

**Domínio (1)**

| Skill | Trigger |
|---|---|
| `tese-tracker` | scorecard de teses em `runtime/theses/<TICKER>.json` |

### 2.2 Projeto — descontinuadas (11, em contêiner)

`.claude/skills/deprecated/` — arquivadas na auditoria de 2026-08-26. O `SKILL.md` do contêiner não é skill utilizável.

Auditadas caso a caso em 2026-09-10 para verificar se alguma merecia voltar. **Nenhuma voltou — todas têm cobertura ativa.** Deixado registrado para não reabrir a discussão sem fato novo:

| Deprecada | Cobertura ativa | Veredito |
|---|---|---|
| `arqueologist` | `recon-researcher` (agente) + `f51-inventory` | coberto |
| `f51-audit` | `f51-quality-gate` + verifiers (`security-`, `code-quality-reviewer`) | coberto |
| `f51-contract-watchdog` | `f51-contracts` + `api-contract-verifier` | coberto |
| `f51-dependency-scout` | `f51-dead-code` (deptry) + `security-reviewer` | coberto |
| `f51-executor` | `product-implementer` (agente) | coberto |
| `f51-loop-breaker` | regra do `CLAUDE.md` ("travou duas vezes: pare e pergunte") | virou regra |
| `f51-metrics-dash` | `f51-observability` (Prometheus, métricas) | coberto |
| `f51-orchestrator` | `captain` (agente) + comando `/swarm` | coberto |
| `f51-regression-hunter` | `f51-tests` + comando `/fix` | coberto |
| `f51-release` | comando `/ship` + `release-readiness-manager` | coberto |
| `f51-test-finder` | `f51-tests` | coberto |

### 2.3 Comandos versionados

**Projeto — `.claude/commands/` (3)**

| Comando | Descrição |
|---|---|
| `/swarm <objetivo>` | Dispara exército completo |
| `/save` | Salva estado + commit local |
| `/agent-lab` | Testa e evolui agentes |

**Globais — `~/.claude/commands/` (3)** — NÃO versionados neste repo:

| Comando | Descrição |
|---|---|
| `/spec` | Pedido solto → spec verificável |
| `/fix` | Erro → correção + teste de regressão |
| `/ship` | Portão de entrega, reprova se falhar |

### 2.4 Built-in do Claude Code (14, não versionadas)

`code-review` · `simplify` · `security-review` · `run` · `init` · `loop` · `claude-api` · `update-config` · `keybindings-help` · `fewer-permission-prompts` · `dataviz` · `artifact-design` · `artifact-diagramming` · `workflow-authoring`

### 2.5 Lock

`skills-lock.json` na raiz está **vazio** (`{"version": 1, "skills": {}}`). Não trava nada hoje.

---

## 3. Agentes — `.claude/agents/` (23)

Segue `AGENTS.md` (playbook 2026).

**Delivery (5)**
`product-delivery-orchestrator` · `product-implementer` · `ai-eval-verifier` · `reliability-sre-operator` · `release-readiness-manager`

**Verifiers (7)**
`security-reviewer` · `code-quality-reviewer` · `runtime-verifier` · `training-verifier` · `api-contract-verifier` · `frontend-ux-reviewer` · `model-gateway-verifier`

**Researchers (2)**
`recon-researcher` · `kb-domain-reviewer`

**Meta / Evolução (3)**
`agent-explorer` · `agent-benchmarker` · `agent-replacer`

**Savekeeper (1)**
`savekeeper` — único agente autorizado a editar docs operacionais

**Mercado (3)**
`market-data-puller` (read-only) · `market-thesis-writer` (único writer) · `market-thesis-auditor` (verifier independente)

**Orquestração (1)**
`captain` — coordena delivery, não libera o próprio trabalho

**Revisão (1)**
`revisor` — revisa diff pré-commit, somente leitura

---

## 4. Hooks

`.claude/hooks/` está **vazio**. Nenhum hook ativo neste projeto.

---

## 5. Divergências conhecidas

Encontradas na rev. 2 — pendentes de reconciliação:

| Onde | Diz | Realidade |
|---|---|---|
| `AGENTS.md` §"Exército Versionado" | 22 agentes | 23 em disco — falta `revisor` na tabela |
| `AGENTS.md` §"F51 Skills" | 32 skills | 20 `f51-*` ativas (11 arquivadas em `deprecated/`) |
| `AGENTS.md` §"Skills nucleares" | cita `audit` e `release` | ambas deprecadas — ver lista corrigida na §7 |
| `.claude/mcp-catalog.json` | 8 MCPs como superfície | nenhum ativo; ativos são `context7`, `playwright`, `hugging-face` |

Os três itens do `AGENTS.md` foram encaminhados ao `savekeeper` em 2026-09-10.

---

## 6. Totais

- MCP ativos: **3** (catalogados-inativos: 8)
- Skills do projeto: **21 ativas** + 11 deprecadas
- Comandos: **3 do projeto** + 3 globais
- Built-in Claude Code: **14**
- Agentes: **23**
- Hooks: **0**

---

## 7. Os melhores (curadoria)

Escolha por **fase do trabalho**, não por prestígio. Critério: qual peça é a mais afiada para aquela etapa e por quê.

### Por fase

| Fase | Melhor peça | Por quê |
|---|---|---|
| Entender antes de mexer | `f51-inventory` + `f51-impact-map` | baseline real e superfície de risco — sem isso o resto é chute |
| Planejar | agente `captain` | seleciona slice e exige verificação independente; não libera o próprio trabalho |
| Escrever | agente `product-implementer` + `f51-tests` | patch mínimo em arquivo atribuído, com teste direcionado |
| Provar | `f51-tests` + `/ship` | gate objetivo; `/ship` reprova se qualquer item falhar |
| Blindar | `f51-secure-scan` + agente `security-reviewer` | sistema que toca ordem e dinheiro — o verifier de maior consequência |
| Operar | `f51-runtime` + agente `runtime-verifier` | boot, portas, GPU, health |
| Domínio de mercado | trio `market-data-puller` → `market-thesis-writer` → `market-thesis-auditor` | separação real entre obter, redigir e auditar — o desenho mais sólido do exército |
| Persistir verdade | `savekeeper` | único autorizado a editar docs operacionais |

### MCPs que valem

| Server | Veredito |
|---|---|
| `context7` | **manter** — evita escrever contra API desatualizada |
| `playwright` | **manter** — único jeito de validar o frontend de chat de verdade |
| `hugging-face` | **adicionado 2026-09-10** — casa com `models/`, LoRA e nitro; exige `HF_TOKEN` |

Os 8 de `.claude/mcp-catalog.json` seguem inativos. Nenhum dos restantes passa o corte: `google-drive` conflita com DISK ONLY; `gmail`/`google-calendar` são pessoais; `vercel`/`canva`/`notion`/`play-sheet-music` não tocam o domínio.

### Skills nucleares (lista corrigida)

O `AGENTS.md` citava `audit` e `release` como nucleares — ambas mortas. Núcleo ativo real:

`inventory` · `impact-map` · `contracts` · `runtime` · `refactor` · `tests` · `quality-gate` · `money-gate` · `idempotency` · `observability`

`idempotency` e `observability` entram no núcleo por serem invariantes do domínio (ordem duplicada e rastreabilidade), não por serem grandes.
