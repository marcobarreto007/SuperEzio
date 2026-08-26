# Relatório Consolidado — Auditoria de Legado e Sujeira

- **Data:** 2026-08-26
- **Modo:** DISK ONLY — GitHub bloqueado (sem fetch/push/gh)
- **Execução:** Swarm /swarm — 5 agentes paralelos, cada um com lente distinta
- **Regra da auditoria:** zero alterações de arquivo; todo achado com evidência file:line
- **Status:** auditoria concluída; remediação NÃO iniciada (requer tarefas aprovadas)

## 1. Resumo executivo — Top 10 achados

| # | Sev | Achado | Local |
|---|-----|--------|-------|
| 1 | 🔴 CRÍTICO | API key DeepSeek real no histórico git, reusada como Anthropic ("removida" mas presente nos blobs) | `scripts/update_key.py` @ commit `6b159db1` |
| 2 | 🔴 CRÍTICO | Perfil Chromium Questrade completo no histórico (275 blobs: Login Data, Cookies, Trust Tokens) | `runtime/questrade_profile/` @ `81457ead` |
| 3 | 🟠 ALTA | Pacote JWT morto 447 LOC, 0 importers; inventário o declara live | `src/core/auth/` vs `.f51/INVENTORY.json:99` |
| 4 | 🟠 ALTA | Função sem chamador declarada "pipeline integration" live no contrato | `src/experts/technical_neural/pipeline_hook.py:72` vs `live-modules.contract.md:188` |
| 5 | 🟠 ALTA | Cadeia InvestorCommittee + DecisionLogger mortas (0 chamadores de produto) | `src/core/investor/committee.py`, `src/core/audit/decision_logger.py:10` |
| 6 | 🟠 ALTA | Cópia stale de 30 skills na raiz, gitignored (0 arquivos tracked) — parece oficial | `.agents/skills/` |
| 7 | 🟠 ALTA | Diretório `deprecated/` referenciado em 2 docs mas inexistente no disco — ciclo de vida do exército depende de caminho fantasma | `docs/AGENT_ORCHESTRATION.md:44`, `.claude/commands/agent-lab.md:25` |
| 8 | 🟠 ALTA | Skill duplicata ~90%: mesmo gate, mesmo deliverable | `f51-contract-watchdog` vs `f51-contracts` |
| 9 | 🟠 ALTA | Agente ativo ausente do manual de orquestração (21 listados, 22 existem) | `.claude/agents/model-gateway-verifier.md` |
| 10 | 🟡 MÉDIA | Gate de formato falha: 16 arquivos quebrariam reformatação (baseline subiu 5→16); 123 funções acima do limiar C901 | `ruff format --check`; `collector.py:814` (113) |

## 2. Achados por lente

### 2.1 Legado estrutural — recon-researcher
- **[ALTA]** `src/core/auth/` (models.py + service.py) — JWT morto 447 LOC; auth real vive em `src/agent_server/auth.py`; `.f51/INVENTORY.json:99` diverge
- **[ALTA]** `run_technical_neural_analysis` / `analyze_technical_neural_sync` — zero chamadores; contrato `live-modules.contract.md:188` desatualizado
- **[ALTA]** InvestorCommittee + `investor/prompts.py` + `financial_prompts.py` — carregados por efeito colateral de import, zero uso de produto
- **[ALTA]** `DecisionLogger` — só testes importam; docstring se autodeclara legacy
- **[MÉDIA]** `ExpertWeightRouter` — sobrevivente de limpeza Wave 4 (caminho vivo: `get_effective_expert_weights`)
- **[MÉDIA]** `nodes/collect_experts.py` — shim legacy auto-declarado, só testes seguram vivo
- **[MÉDIA]** `tmx_redirect.json` — 136KB de HTML com extensão .json no root, tracked, zero referências
- **[MÉDIA]** `cockpit_analysis.txt` — dump JS de scratch commitado, zero referências
- **[MÉDIA]** 12 probes de debug tracked em `runtime/checkpoints/` (debug_*.py, mobile-*.py, tmx_capture/*)
- **[MÉDIA]** Split-brain de checkpoint: `runtime/checkpoints/latest.json` vs `.f51/checkpoints/latest.json` (datas divergentes)
- **[MÉDIA]** `reason_codes.py` — registro normativo nunca aplicado (adocao incremental admitida na docstring)
- **[MÉDIA]** 3× DELIVERY_CHECKLIST (v1/v2/v3) sem link cruzado; `scripts/browser_smoke_mobile.py` órfão; dupla `live_chrome_operator.py` / `chromium_live_operator.py` órfã
- **[BAIXA]** `train_qwenlong_30b_gguf_f51.ps1`, `superezio.spec`, `.baseline_tests.txt`, `requirements-ci.txt` — órfãos tracked

### 2.2 Qualidade de código — code-quality-reviewer
- **[MÉDIA]** 16 arquivos falham `ruff format --check` (5 src / 11 tests) — gate de formato do CLAUDE.md quebra; baseline anterior era 5
- **[ALTA]** 123 funções > C901 (118 src / 5 tests): `collector.py:814` (113), `endpoints.py:1306` (100), `endpoints.py:1570` (79), `agent.py:2720` (77), `tool_executor.py:626` (61), `graph.py:1070` (49)
- **[MÉDIA]** Duplicação de helpers já divergindo: `_env_bool` 3× (diferença `raw` vs `str(raw)`), `_env_int` 2×, `_first_present` byte-idêntica 2×, `_clamp` 3×, `_db_path` 2×
- **[MÉDIA]** Indicadores duplicados: `_compute_rsi/ema/macd/bollinger` em `professional.py` (shim) e `financial_engine.py`
- **[BAIXA]** `_extract_candles` duplicada com lógica divergente (`math_hub.py:201` vs `neural_decision.py:143`)
- **[BAIXA]** 975 violações B/SIM/UP fora do select default (768 auto-fixáveis): UP006 ×366, UP017 ×220, UP035 ×119, UP045 ×85; B017/B011 em tests
- **[OK]** F401/F811/F841/F822/F823 limpo (imports usados OK); **vulture/deptry NÃO instalados** — varredura de dead code do f51-dead-code não executável

### 2.3 Segurança — security-reviewer
- **[CRÍTICO]** `scripts/update_key.py` (commit `6b159db1`, "removido" em `9ebb6462`) — `sk-ea2d…fed0` (DeepSeek) reusada como ANTHROPIC_API_KEY; chave atual em disco `sk-8cd…d3d2` (aparentemente rotacionada); blobs permanecem no histórico
- **[CRÍTICO]** `runtime/questrade_profile/` (add `81457ead`, del `a4c061a1`, 275 blobs) — Login Data (senhas salvas), Cookies, Trust Tokens, autofill, IndexedDB da corretora
- **[MÉDIA]** `runtime/test_token.json` tracked — JWT assinado + refresh token versionados (expirado 2026-07-20)
- **[MÉDIA]** `data/questrade_portfolio.json:13` — URL OAuth com client_id Questrade + PKCE
- **[BAIXA]** `.env` / `.env.local` em disco (gitignored OK, sem vazamento via git); `test_seed_auth.db` na raiz (não versionado)
- **[OK]** Árvore atual limpa: só `.env.example` tracked (placeholders); `secrets.py` loader limpo; testes usam chaves fake; sem tokens AWS/GCP/GitHub em blobs
- **Ação obrigatória antes de qualquer entrega externa:** rotacionar QUESTRADE/DeepSeek + purge de histórico (filter-repo)

### 2.4 Documentação — kb-domain-reviewer
- **[MÉDIA]** `README_FIRST.md:81` — experts "rodam no mesmo servidor :8080" vs `config/runtime.yml:67-77` (DeepSeek externo, allow_fallback: false)
- **[MÉDIA]** `ROADMAP.md:8` — topologia obsoleta desde 2026-08-21 sem marcador superseded
- **[MÉDIA]** `README.md:148-149` — Docker Quick Start aponta GGUF inexistente em `models/` (real: `%USERPROFILE%\models\qwen3.8-27b\`)
- **[MÉDIA]** `docs/EVIDENCE_INDEX.md` — screenshot de 2026-06-03 que não existe (mais antigo real: 2026-07-20)
- **[MÉDIA]** `docs/nitro/F51_NITRO_TRAINING_WHITEPAPER.md` — cita `nitro_training.py` inexistente, status "Ready for Implementation"
- **[MÉDIA]** `DELIVERY_CHECKLIST_v3.md:11` — "RTX 3060 + RTX 2070, tensor split 12,8" vs `runtime.yml:44-48` (única GPU RTX 3060, "12")
- **[MÉDIA]** `AGENTS.md:97` — MCPs (filesystem, playwright, firebase...) sem suporte no repo e contrários ao CLAUDE.md
- **[MÉDIA]** `RUNBOOK.md:29` — path do GGUF divergente de `runtime.yml:30`
- **[MÉDIA]** `docs/superpowers/plans/2026-05-23-…md` — cita scripts inexistentes (`invest_api_qa.py`, `invest_qa.py`)
- **[BAIXA]** Duplicatas doc: `TWO_PHASE_ORDER.md` (raiz + architecture/), `ARCHITECTURE_ONEPAGER.md` vs `SUPEREZIO_DOCS.md`, `DELIVERY_CHECKLIST_v2.md` (HISTORICO mantido na árvore, comandos fantasmas)
- **[BAIXA]** `AGENTS.md:72` — "27 skills" vs 32 no disco; `docs/audit/phase6…md` referencia `_ibkr_order.py` removido

### 2.5 Exército de agentes — agent-explorer
- **[ALTA]** `f51-contract-watchdog` ≈ 90% duplicata de `f51-contracts` (mesma superfície, mesmo gate; `api-contract-verifier.md:22` referencia ambos)
- **[ALTA]** `.agents/skills/` — cópia stale gitignored (0 tracked vs 33 em .claude/skills; perde f51-orchestrator e tese-tracker)
- **[ALTA]** `deprecated/` inexistente — quebra o ciclo candidate→deprecated→killed do /agent-lab
- **[ALTA]** `model-gateway-verifier.md` fora do manual de orquestração
- **[MÉDIA]** Cluster de 6 skills de gate sobrepostas (f51-tests, test-finder, regression-hunter, audit, quality-gate, release); 4 órfãs (só autocitações)
- **[MÉDIA]** `f51-metrics-dash` ≈ 60% de `f51-observability` (função absorvida, órfã)
- **[MÉDIA]** `arqueologist` ≈ 85% do agente `recon-researcher`; `f51-orchestrator` ≈ 80% do captain; `f51-executor` ≈ 100% do `product-implementer`
- **[MÉDIA]** 16 skills órfãs de orquestração (zero referências externas ativas)
- **[BAIXA]** `f51-dependency-scout` vs `f51-dead-code` (~40%); `f51-loop-breaker` vs `f51-circuit-breaker` (colisão de nomenclatura); `f51-inventory` vs `f51-impact-map` (~50%)
- **[BAIXA]** `.claude/partner/` órfão (referencia `f51-dual-agent-v` inexistente); `.f51/SKILLS_CHECK.md` obsoleto (22 auditadas, 32 existem); `dist/release/RELEASE_MANIFEST.json` congela cópia stale

## 3. Deduplicação entre lentes (achados em 2+ lentes)

- `deprecated/` fantasma — agent-explorer (ALTA) + kb-domain-reviewer (BAIXA)
- `.agents/skills/` — agent-explorer (ALTA) + recon-researcher (BAIXA)
- DELIVERY_CHECKLIST v2/v3 — recon (MÉDIA) + kb-domain (BAIXA)
- `model-gateway-verifier` / `AGENT_ORCHESTRATION.md` — agent-explorer + kb-domain (leitura de orquestração)

## 4. Próximos gates recomendados (ordem de prioridade)

1. **Segurança (antes de qualquer entrega externa):** rotacionar QUESTRADE + DeepSeek; purge de histórico (filter-repo); remover `test_token.json` e `questrade_portfolio.json` da árvore → skill `f51-secure-scan` / tarefa de remediação
2. **`f51-doc-sync`:** corrigir README_FIRST, ROADMAP, README Docker, EVIDENCE_INDEX, RUNBOOK, AGENTS.md, DELIVERY_CHECKLIST_v3; consolidar/arquivar duplicatas
3. **`f51-contracts`:** reconciliar `.f51/INVENTORY.json` e `live-modules.contract.md` com o código real (core/auth morto, pipeline_hook sem chamador, 22º agente)
4. **`f51-refactor` (escopos pequenos):** fatiar monólitos C901 (collector.py:814, endpoints.py:1306/1570); consolidar helpers duplicados em módulo compartilhado com teste de paridade
5. **Higiene de órfãos (tarefa explícita):** remover/arquivar `tmx_redirect.json`, `cockpit_analysis.txt`, 12 probes em `runtime/checkpoints/`, `.baseline_tests.txt`, duplas órfãs em scripts/
6. **Exército:** fundir/matar duplicatas (watchdog→contracts, arqueologist→recon, orchestrator→captain, executor→implementer, metrics-dash→observability); criar `deprecated/`; registrar `model-gateway-verifier`; auditar as 16 skills órfãs
7. **Tooling:** adicionar `vulture` + `deptry` ao extras dev (f51-dead-code fica executável); ampliar select do ruff (UP, SIM*, B905) em lote com revisão de diff

## 5. Evidência e regras

- Todo achado acima tem evidência file:line coletada pelos agentes; execução read-only (nenhum arquivo alterado)
- Gate da auditoria: 5 agentes × relatório estruturado com severidade — 3 com achados críticos (recon, security, agent-explorer)
- Remediação exige: tarefa no `.f51/TASK_BOARD.md` + gate de contrato + checkpoint atualizado (definição de pronto F51)
- Próximo passo operacional sugerido: decidir ordem de remediação no `.f51/TASK_BOARD.md`

## 6. Remediação executada — higiene estrutural (2026-08-26)

- **Autorização:** coordenador do swarm (tarefa explícita pós-auditoria). Modo DISK ONLY; nenhum fetch/push.
- **Regras respeitadas:** zero alterações em `src/`, `apps/`, `core/`, `pipelines/`, `packages/`; zero deleções (tudo via `git mv`, histórico preservado); chaves/.env*/test_token.json/questrade_portfolio.json intocados; `runtime/checkpoints/latest.json` intocado (split-brain documentado abaixo, não resolvido).
- **Verificação pré-move:** grep repo-wide (excluindo .git/node_modules/.venv/dist/build/.agent_bus) por nome de cada arquivo; nenhuma referência viva de runtime encontrada. Menções históricas registradas, não bloqueantes:
  - `.f51/checkpoints/2026-08-23-casual-greeting-intent-fix.json:1719` (tmx_redirect.json "aguardando o D3") e `:1437` (browser_smoke_mobile.py) — registros de checkpoint do passado, não dependências
  - `.f51/CONFIG_MAP.md:53` (requirements-ci.txt) — documentação de config agora stale (classificação "config", risco "version label is stale")
  - `docs/STATE_OF_THE_UNION.md:247` (família train_qwenlong) — lista histórica de deletados da Wave 4
  - `runtime/LEGACY_CATALOG.md` (catálogo de legado) e `runtime/train_qwenlong_30b.bat` (stub auto-retired, `exit /b 2`, não invoca o .ps1)
- **Arquivados: 39 arquivos** → `.f51/archive/2026-08-26/` (git mv, renomes staged):

  | Origem | Destino (.f51/archive/2026-08-26/) |
  |---|---|
  | `tmx_redirect.json`, `cockpit_analysis.txt`, `.baseline_tests.txt`, `superezio.spec`, `requirements-ci.txt` (raiz) | `./` |
  | `runtime/checkpoints/debug_flex.py`, `debug_right.py`, `debug_rows.py`, `mobile-audit-r4.py`, `mobile-contrast-probe.py`, `mobile-probe-r4.py`, `mobile-topbar-768.py`, `mobile-topbar-probe.py`, `probe_mobile_r1.py`, `shots_r1.py` | `runtime/checkpoints/` |
  | `runtime/checkpoints/tmx_capture/` (20 arquivos: capture_network.py, capture_network2.py, README.md, td_quote.html, quote_symbol.js, 10× *.js bundles, 5× gql_*.json) | `runtime/checkpoints/tmx_capture/` |
  | `scripts/live_chrome_operator.py`, `chromium_live_operator.py`, `browser_smoke_mobile.py`, `train_qwenlong_30b_gguf_f51.ps1` | `scripts/` |

- **NÃO movidos (fora do escopo desta tarefa):** código morto em `src/` — `core/auth/` (447 LOC), `audit/decision_logger.py`, `trading/expert_weights.py`, `pipeline/nodes/collect_experts.py`, `investor/committee.py`+`prompts.py`+`prompts/financial_prompts.py`, `experts/technical_neural/pipeline_hook.py`, `trading/reason_codes.py` — regra dura proíbe tocar em `src/`; ficam para gate `f51-refactor` com contrato aprovado (achados §1 itens 3-5).
- **Split-brain de checkpoint — DOCUMENTADO, NÃO resolvido (sessão paralela pode usar ambos):**
  - `.f51/checkpoints/latest.json` (mandatário — CLAUDE.md "Todo agente deve atualizar .f51/checkpoints/latest.json"; atualizado 2026-08-25)
  - `runtime/checkpoints/latest.json` (nada em src/scripts/docs referencia; atualizado 2026-08-23)
  - Resolução proposta para gate futuro: eleger `.f51/checkpoints/` como única autoridade e migrar/arquivar o segundo.
- **Commit:** escopado — apenas `.f51/archive/2026-08-26/` + este relatório. Mudanças de outras sessões em `data/`, `config/`, `tests/` não incluídas.

### 6.1 Remediação executada — exército de agentes (agent-explorer)

- **Escopo:** duplicatas de skills confirmadas na auditoria (§2.5) + cemitério oficial inexistente + cópia stale `.agents/skills/`.
- **Regras respeitadas:** zero deleções (git mv); zero alterações em `src/`/produto; skills ainda referenciadas por agentes ativos (f51-tests, f51-quality-gate, f51-release) intocadas.
- **Cemitérios criados:** `.claude/agents/deprecated/` e `.claude/skills/deprecated/` (READMEs com política/canônicas) — resolve o caminho fantasma de `docs/AGENT_ORCHESTRATION.md:44` e `.claude/commands/agent-lab.md:25`.
- **Skills movidas (5) → `.claude/skills/deprecated/`** (canônica anotada no topo de cada SKILL.md):

  | Skill movida | Canônica | Duplicata |
  |---|---|---|
  | f51-contract-watchdog | f51-contracts | ~90% |
  | arqueologist | agente recon-researcher | ~85% |
  | f51-orchestrator | agente captain | ~80% |
  | f51-executor | agente product-implementer | ~100% |
  | f51-metrics-dash | f51-observability | ~60% |

- **Referências corrigidas (arquivo:linha):**
  - `.claude/agents/api-contract-verifier.md:22` — removida menção a f51-contract-watchdog; mantida só f51-contracts.
  - `.claude/skills/f51-circuit-breaker/SKILL.md:7` — related-skills sem f51-executor.
  - `.claude/skills/f51-idempotency/SKILL.md:7` — related-skills sem f51-executor.
  - `.claude/skills/f51-prop-test/SKILL.md:7` — related-skills sem f51-executor.
  - `.claude/skills/f51-observability/SKILL.md:7` — related-skills sem f51-metrics-dash.
  - `.claude/commands/*.md` — varridos; nenhuma referência às 5 movidas.
- **Cópia stale movida:** `.agents/skills/` (30 skills, gitignored) → `.f51/archive/2026-08-26/.agents-skills-stale/` (versionada; `.agents/` fica vazio no disco).
- **Sobrou para decisão do operador:**
  - 16 skills órfãs (§2.5) não movidas — exigem decisão skill a skill (matar/fundir/manter).
  - `docs/claude-ops-catalog.md:12` ainda lista `arqueologist` como grupo permitido (doc de 2026-05-21).
  - `.f51/SKILLS_CHECK.md` (2026-06-01) audita 22 skills; hoje são 32 — re-auditar as 10 novas.
  - `model-gateway-verifier.md` ainda sem entrada no manual `AGENT_ORCHESTRATION.md` (registrar).
  - Referências históricas a `arqueologist` em `docs/architecture/RECLAMATION_REPORT.md:12` — mantidas como registro.
- **Commit:** escopado — `.claude/skills/deprecated/`, `.claude/agents/deprecated/`, referências corrigidas, `.f51/archive/2026-08-26/.agents-skills-stale/`, este relatório e checkpoint. Os 39 renames da higiene estrutural (§6) NÃO entram neste commit (sessão paralela).

### 6.2 Remediação executada — órfãs de orquestração, decisão skill a skill (onda 5)

- **Escopo:** 11 candidatas órfãs (zero referências de agentes/comandos) avaliadas individualmente; 6 deprecadas, 5 mantidas.
- **Deprecadas (6) → `.claude/skills/deprecated/`** com canônica anotada:

  | Skill | Decisão | Evidência da verificação |
  |---|---|---|
  | f51-audit | DEPRECAR → f51-quality-gate | 0 agentes/0 comandos; 13 citações são related-skills de frontmatter (autocitações do cluster); depends-on dela existia só em f51-release (também deprecada); função de severidade/BLOCK = release-readiness-manager |
  | f51-dependency-scout | DEPRECAR → f51-dead-code | ~40% overlap (deps órfãs via deptry já em f51-dead-code, ativa e usada por code-quality-reviewer); upgrade-risk/CVE sem dono (0 agentes); só SKILLS_CHECK.md (histórico) cita |
  | f51-loop-breaker | DEPRECAR → agent-lab.md | nome colide com f51-circuit-breaker ativo (protegida); função "cortar loop" já é stop condition do agent-lab.md:49 ("Same failure repeated twice → stop the loop"); 0 agentes |
  | f51-regression-hunter | DEPRECAR → f51-quality-gate + f51-tests | cluster gate com só autocitações (f51-prop-test related-skills); verificação pós-patch é papel dos agentes verifiers; 0 agentes/0 comandos |
  | f51-release | DEPRECAR → f51-quality-gate + release-readiness-manager | mesmo entregável do quality-gate (PASS/FAIL/HOLD vs PASS/FAIL/PARTIAL); agente release-readiness-manager ativo executa release na prática e NÃO referencia a skill; 0 agentes |
  | f51-test-finder | DEPRECAR → f51-tests | ~100% duplicata de f51-tests (ativa, usada por code-quality-reviewer e runtime-verifier); 0 agentes a usam |

- **Mantidas (5) com evidência:**
  - f51-inventory — MANDATÓRIA: regra mestra do CLAUDE.md ("Sem feature antes de: inventário...") gate 1; depends-on REAL de f51-contracts e f51-dead-code (ativas); contrato .f51/INVENTORY.json + INVENTORY_TEMPLATE.json existem.
  - f51-money-gate — função única (GO/DEFER/NO-GO por receita); .f51/MONEY_GATE.md lido pelo captain.md:55; 7 skills ativas citam.
  - f51-env-guard — função única (validação de env via Pydantic Settings); citada por f51-secure-scan (ativa); sem duplicata.
  - f51-no-mock-police — função única (caçar mocks em produção); alinhada à política de mocks do CLAUDE.md; sem duplicata.
  - f51-windows-compat — função única (Windows/PowerShell/venv/paths); projeto Windows-first (runtime .ps1); sem duplicata.

- **Referências corrigidas (related-skills/depends-on) em 14 skills ativas:** f51-circuit-breaker, f51-contracts, f51-dead-code, f51-env-guard, f51-idempotency, f51-money-gate, f51-observability, f51-productizer, f51-prop-test, f51-refactor, f51-runtime, f51-safety-science, f51-secure-scan (depends-on), f51-tests (linha related-skills removida). Verificado: zero referências às 6 deprecadas em .claude/skills ativas, .claude/agents/ e .claude/commands/.
- **Docs históricos mantidos como registro:** .f51/SKILLS_CHECK.md, .f51/BOOTSTRAP_REPORT.md, .f51/CONFIG_MAP.md (menção a sessão "f51-inventory-full-sweep", não à skill), docs/audit/LEGACY_AUDIT_2026-08-26.md §2.5.
- **Saldo final do exército:** 21 skills ativas + 11 deprecated; 22 agentes; 3 comandos.
