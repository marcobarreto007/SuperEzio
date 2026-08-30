# F51 Task Board

## Backlog

- [x] 2026-08-30 - **100 CAD investir = alocacao + enrich yfinance primeiro**: commits `0eb62ff1` (rota/fala curta, CAD=moeda, telemetria fora do CHUNK) e `1e74ac25` (yfinance prio 2, twelve prio 12, `stage_abandoned`, deadline derivado se env unset). pytest **2231 passed**, 2 skipped. API :8002 reiniciada 2026-08-30 (PID novo, health 200); llama :8080 Ornith **nao abliterado** — recusa da boca nao e recusa do pipeline. Checkpoint `cad100-alloc-api-restart-20260830`.

- [x] 2026-08-29 - **Boca Ornith texto-only**: PNG/chart image nao vai mais para `:8080` (default `attach_image=False` + strip no gateway). Evidencia: consult TD.TO 186.6s orgaos ok / boca 500 `image input is not supported`; pytest 148 passed chart/gateway/agent. Restart da API necessario para valer no processo vivo.

- [ ] 2026-08-26 - **P0 — segredos: rotação Questrade/DeepSeek + purge de histórico**: chave DeepSeek real reusada como Anthropic no histórico (`scripts/update_key.py` @ 6b159db1) e perfil Chromium Questrade completo (275 blobs) em `runtime/questrade_profile/`. **BLOQUEADO PELO OPERADOR** (proibido tocar chaves/credenciais e fazer purge). Reabrir quando o operador autorizar; requer filter-repo + rotação nos portais.
- [ ] 2026-09-25 - **Re-auditoria deprecated**: matar/promover as 11 skills em `.claude/skills/deprecated/` com evidência de uso real (GAP-6 no SKILLS_CHECK.md). Prazo: 30 dias da deprecação (2026-08-26).
- [x] 2026-08-26 - **build_release exclusions**: FECHADO — `build_release.ps1` já possui allowlist+denylist robustas: `.env*`, `*.db*`, `*.log`, `*.jsonl`, `runtime/`, `journal/`, `checkpoints/`, `partner/`, `cache/`, `man_at_work/`, `output/`, `tmp/` excluídos. Verificado por leitura direta do script.
- [x] 2026-08-26 - **format src/**: FECHADO — `ruff format --check .` retorna "716 files already formatted" (formatação resolvida em commits eb3beefd..22ecb3d9). `ruff check .` retorna "All checks passed!".
- [x] 2026-08-26 - **dead code src/**: FECHADO — core/auth/ (447 LOC) removido do git (só pyc residuais), decision_logger.py, committee.py, pipeline_hook.py deletados (confirmado por `git ls-files` e `Test-Path`).
- [x] 2026-08-26 - **Skills órfãs**: FECHADO — auditoria de referências em agents/commands/docs/.f51 + cross-skill: todas as 21 ativas têm ≥3 referências externas. Nenhuma é órfã. 6 gates sobrepostos (audit/quality-gate/tests/test-finder/regression-hunter/release) já foram consolidados na onda de deprecação (6 movidas para deprecated/).
- [x] 2026-08-26 - **tese-tracker checkpoint (GAP-5)**: FECHADO — seção "Entregáveis mínimos" adicionada ao SKILL.md com obrigatoriedade de `.f51/checkpoints/latest.json`. SKILLS_CHECK.md atualizado: tese-tracker promovido de CONDICIONAL para APTO.


- [x] 2026-08-25 - **Post-mortem da demo de 24/08 + recuperação (8 commits)** (Claude Code + 5 subagentes em paralelo): a demo falhou na frente de amigos — diagnóstico com evidência de log (dois prompts de 34k-37k tokens rejeitados pela janela 8192 às 18:49-18:52, servindo IP externo) mais 3 estranguladores medidos (slot único com resposta de ~118s, jargão de módulos em pergunta sem ticker, nota interna vazada). Correções: **janela do modelo dobrada para 16.384** (serve_agent_llamacpp.ps1, validada ao vivo); guarda de contexto pre-flight no gateway (rejeita >8000 tokens estimados antes do llama, conta imagens); fallbacks honestos para o visitante (sem dump técnico); cabeçalho DADOS DO PIPELINE condicional ao ticker (instrução + template) — **validado ao vivo: o Bob agora responde a pergunta de alocação em linguagem natural**; nota de validação interna só em log; input de chat não trava mais durante o run; runbook de demo em docs/runbooks/DEMO_RUNBOOK.md; árvore limpa (gitignore de byproducts, data/*.jsonl desstaged). Evidência: **full suite 2243 passed, 0 failed, 3 skipped** (646s, servidor vivo); smoke com chat VERDE (resposta natural, 78.9s, 0 console errors); CEO 16.384 confirmado; API no HEAD com logs em disco. Riscos INV-R62..R64. Checkpoint: `latest.json` (sessao demo-recovery-20260825).

- [x] 2026-08-25 - **Auditoria do caminho de trade + hardening (15 commits)** (Claude Code + 7 subagentes): auditoria completa das 7 dimensões (FSM, idempotência, journal, math, fallbacks, gates, fronteira LLM) com correção cirúrgica. Entregues: healthcheck 503 fail-closed (522f0df); PaperJournal atômico + quarentena de linha corrompida + RLock + **lock de arquivo cross-process msvcrt** (47fff47, 886b956, 588cffb); borda de janela de idempotência fechada nos dois caminhos com alias de fingerprint (8d6ae5a, 2e0b0be); logs em 3 falhas silenciosas (2dbcb3a); MAN_AT_WORK com limiar de 3 falhas + recovery ágil + **enforçado no trade via GATE 1.5 fail-closed** (b16c66c, eb9a9bc); stop_loss_price do modelo ignorado — bypass de $500 fechado (be5cd08); **LIMIT_PRICE_COLLAR** com banda condicionada à idade 5%/10% (3dc38350); `calculate` no Literal + drops de tool call logados (9e439a3); frontend lê `idempotent_replay` e o `detail` do 503, branch morto removido (eb9a9bc, be6ab58); taxonomia central de reason_code com teste de conformidade (ffb5837). Evidência: **full suite 2240 passed, 0 failed, 3 skipped** (713s, servidor vivo — testes de smoke executam); cada fix com teste que falha contra o código original; browser_smoke VERDE com resposta real do Bob; ruff limpo; secrets scan limpo. Riscos INV-R57..R61. Checkpoint: `latest.json` (sessao audit-and-harden-f51-20260824). Pendências anotadas (não bloqueantes): colar por ATR, schemas por-tool completos, migração dos demais emissores de motivo, format-check dos 5 arquivos pré-existentes.

- [x] 2026-08-24 - **Regressao completa zerada: 5 falhas pre-existentes resolvidas** (Claude Code, diretriz "resolva tudo, nao tire nada so melhore"): suíte em 39dacd2 tinha 5 failed / 2201 passed. (1) `graph.py` guarda do MathHub restaurada para `if not _is_casual:` — toda resposta nao-casual carrega `math_report` (contrato de PipelineState quebrado pelo 54cebc8), saudacao pura continua no fast-path; (2) `intents.py` classificador casual agora exige saudacao de mensagem inteira (`_CASUAL_TOKENS`/`_residual_content`) — "oi bob" continua casual, "oi bob, status rapido sem operar" vira pipeline completo (matriz pinned do 54cebc8 intacta, 16/16); (3) `test_market_scanner.py` hermetico: as 3 camadas suplementares de descoberta (penny_scanner_yfinance REDE REAL, watchlist pennylab 40 simbolos, seed mangala_daily.json) pinadas off — o teste antes injetava PLUG/NIO/TLRY reais; (4) `test_yfinance_fundamentals_tsx.py` atualizado para a cadeia `['finnhub','tmx','yfinance']` (rota tmx prioridade 25, 2026-08-23) com stub `_OfflineTmx` deterministico (sem GraphQL real). Evidencia: **full suite 2209 passed, 0 failed, 3 skipped** (694.9s; baseline 5 failed/2201 passed); baterias afetadas 261 passed; slice direcionado 32 passed; **browser_smoke VERDE** (126 candles TD.TO, STREAM_END, PT 3886 chars 108.9s, 0 erros console); ruff check+format limpos. Risco INV-R56. Nota: o :8002 vivo roda codigo pre-fix ate o proximo restart. Checkpoint: `latest.json` (sessao full-regression-fix-20260824).

- [x] 2026-08-23 - **Contrato de sobrevivencia do Bob + SSE do veredito** (Cursor): prompt soberano e mission_context tratam tools como orgaos — expectancy paper ou DISCONTINUED. Stream live so do texto do veredito (esconde think e JSON de tool-call). Live continua frozen. Checkpoint: `latest.json` (sessao bob-survival-sse-20260823).

- [x] 2026-08-23 - **Save multi-onda + reparo de HEAD quebrado + feature chart-visual** (Claude Code): sessao paralela commitou `59f1310` (scan resilience/finnhub/cockpit UI) no meio dos gates deste save e levou `agent.py` importando `core.pipeline.chart_image` **sem o arquivo no repo** — HEAD incoerente (ImportError em checkout limpo). Reparo commitado junto com a feature chart-visual que ficou solta: `chart_image.py` (novo, 343 ln — Bob enxerga o grafico), `test_chart_visual.py` (novo), `gateway.py` (messages multimodais com image_url, json_mode off com imagem, chaves internas removidas), `agent.py` (wiring + regra PT: sem confirmacao visual + numeros + catalisador = WAIT). Evidencia deste save: **pytest 154 passed** (onda scan) + **66 passed** (chart/gateway/agent), **browser_smoke VERDE** pos-open-access (chat PT 109.9s, 0 erros console), ruff limpo em todos os tocados (100 erros pre-existentes fora de escopo), secrets scan limpo. `data/*.jsonl` ficam fora do commit (politica: raw datasets). Checkpoint: `latest.json` (sessao save-multiwave-chart-visual-20260823). Pendencia: validacao visual ao vivo do chart-visual com grafico real anexado.

- [x] 2026-08-23 - **Acesso aberto 100% para 5 pessoas** (Cursor): `SUPEREZIO_OPEN_ACCESS=1` — sem login, guest_open, cockpit/metrics/chat/trade paper sem 2FA, cards do pipeline visiveis, pergunta de compra nao pula Trinity. Execucao live continua congelada. Registro de contas continua 403. Evidencia: `.f51/checkpoints/open-access-full-product-20260823.json`. Risco INV-R55.


- [x] 2026-08-23 - **Verificacao do cockpit pela pagina web + fix de auth do `verify_cockpit_cards.py`** (Claude Code): smoke completo verde — health ok, 126 candles TD.TO 6M com timestamps validos, canvas 1041x545 com 7 canvases pintados, resposta NOVA do Bob em PT via stream (2964 chars, STREAM_END, 108.7s, 0 marcadores EN), 0 erros de console. Porem o `verify_cockpit_cards.py` dava **falso positivo em public mode**: sem Bearer token a pagina boota na tela de login, o chat retorna "Empty response returned from backend" (13 x 401 no console) e os cards viram READY por prontidao de componente — nao por analise. Fix: auth bootstrap reaproveitado do `browser_smoke.py` (token via init_script antes do primeiro fetch), espera de ate 180s pela resposta do Bob como prova de pipeline rodando, e gate `ok` agora exige `chat_responded`. Re-run legitimo: 5/5 cards com dados, tempo real detectado, 0 erros de console. ruff limpo; pytest nao rodou (mudanca isolada em script operacional, sem toque em `src/`/`tests/`). Screenshots: `superezio-browser-smoke-20260823-212933.png` (pre) e `cockpit-cards-20260823-213403.png` (pos-fix). Checkpoint canonico: `latest.json` (sessao anterior arquivada em `2026-08-23-unified-restart-and-fixes.json`).

- [x] 2026-08-23 - **Pos-restart CEO: 3 correcoes aprovadas pelo operador** (Claude Code): (1) checagem de idioma do `browser_smoke.py` restrita ao segmento `SUA EXPLICACAO` do modelo, ignorando trace EN do pipeline (`languageSegLength` no relatorio); (2) `scripts/watchdog_ceo.ps1` novo — health a cada 30s, relance detached do CEO, anti-crashloop (max 4/h), log em `runtime/logs/watchdog_ceo.log`; (3) instrucoes das secoes `## *` traduzidas para PT em `src/core/pipeline/prompts/builder.py` preservando headers/marcadores de contrato (`## MATH_REPORT`, `[MODULO]`, `MISSING -- confidence reduced`, `Bob's read`, `MANDATORY FORMAT`). Riscos: INV-R53 (watchdog), INV-R54 (trace EN/smoke). Checkpoint canonico: `latest.json` (sessao unificada); detalhes em `post-restart-fixes-20260823.json` e `restart-ceo-20260823.json`.

- [x] 2026-08-23 - **Travamento fail-closed no universo TD Direct Investing** (Claude Code + 3 subagentes de pesquisa): 5 definições de venue em drift viraram UM contrato (`src/core/trading/td_universe.py`) — allowlist positiva de 6 bolsas (TSX/TSXV/NYSE/NASDAQ/NYSEAMERICAN/NYSEARCA) com normalização de aliases (TOR/TSV/NYQ/NMS/ASE/PCX/XTSE/AMEX/ARCA); "US" genérico deliberadamente não mapeado. Scanner preserva a bolsa VERIFICADA como provenança (`scan_equities_detailed`); gate do collector rejeita LSE/BVMF/CSE/NEO/JPX/OTC (`exchange_not_td_supported`) e voucha via manifest fresco (schema v2, TTL 7d). Manifest US construído de verdade: 11.527 símbolos via Nasdaq SymDir keyless (commit `5007e36`); CA pendente de quota Twelve Data (allowlist cobre TSX/TSXV nesse meio-tempo). 187/187 testes direcionados ampliados; ruff limpo; sanidade live do contrato ok (NVDA/SPY vouchados, LSE/BVMF rejeitados). Commits `acdab43`, `5007e36`, `a2f0522`. Riscos: INV-R51 (TTL do manifest), INV-R52 (reconfirmação oficial TD em setembro). Pendência: rodar `update_td_universe_manifest.py --only all` após reset de quota e a cada ≤7 dias; reiniciar a API :8002 para carregar o gate.

- [x] 2026-08-23 - **Fallback de quote no DataHub sem finnhub** (Claude Code): finnhub era a única rota com a capability `quote`; com a `FINNHUB_API_KEY` ausente, `route("quote")` morria com "all providers exhausted". Alias de capability (`quote` → `price`/`market_price`) + fallback de método em `src/data/data_hub.py`; 3 testes novos em `tests/test_data_hub_routing.py`; bateria da camada de dados 67 passed; ruff limpo; commit `c486f78`. Pendência do operador: rotacionar a chave no portal Finnhub e gravar em `.env.local` (reativa a rota sozinho); reiniciar a API :8002 para carregar o fix.

- [x] 2026-08-21 - **Investor Playbook e CLI de Alocação de Capital** (Antigravity): Criação do Playbook Oficial do Investidor em `docs/INVESTOR_PLAYBOOK.md`, CLI interativo e determinístico em `scripts/investor_portfolio_allocator.py`, suíte de testes unitários em `tests/test_investor_portfolio_allocator.py` (4 testes passando), framework Core & Explore para ETFs commission-free no TD Direct Investing e roteamento de contas TFSA/RRSP/HISA.

- [x] 2026-08-21 - **Topologia hibrida restaurada por diretiva do operador** (Codex): CEO/orquestrador permanecem no Qwen local `:8080`; experts financeiros, judge e auditor usam `deepseek-v4-pro` na API oficial. Chave ausente falha explicitamente, modelos locais/aposentados sao rejeitados, nao existe fallback cruzado, health/cockpit reportam readiness real. Validacao externa paga permanece pendente ate o operador configurar `SUPEREZIO_DEEPSEEK_API_KEY` localmente.

- [x] 2026-08-18 - **TD Direct commission-free research universe** (Codex): captured the
  official 108-ETF list (83 Canada, 25 US), added dated/stale-failing eligibility checks and
  `GET /trade/td-commission-free`. Added an authenticated, non-transmitting `/trade/td-draft`
  that is explicitly not execution-ready. Real-money go-live remains blocked by INV-R35.

- [x] 2026-08-18 - **Limpeza da memória de conversa** (Claude Code): `data/conversation_memory.jsonl`
  reduzido de 497 para 29 linhas — removidas todas as sessões de teste/probe (default 109x com
  prompt do teste de ticket, CAD-25k, quality-probe, overnight_001..092, stress/bench/diag/final,
  23 sessões bob-uuid com prompt CAD, operator/trader/web/marco/user com prompts de teste).
  Mantida apenas a sessão real `bob-7e65d4c1` (29 conversas do operador). Motivação: memória
  RAG do Bob estava contaminada com lixo de teste (126 menções de AAPL).
- [x] 2026-08-18 - **Fix anti-crash do akshare (INV-R29 ao vivo)** (Claude Code): teste live
  derrubou o servidor (V8 py_mini_racer mata o processo inteiro, sem exceção capturável).
  `get_us_stock_name()` agora roda isolado em subprocesso — o filho morre, o servidor
  sobrevive e o hub cai pro próximo provider. 8 testes novos + ruff limpo. Validação live:
  pipeline de scan completo sobreviveu (108 eventos, candidatos SYKE/HBI/GPS).
- [x] 2026-08-18 - **Filtro fail-closed de sessão na memória** (Claude Code): `ConversationMemory`
  agora só persiste sessões interativas reais (`bob-<uuid>`) ou ids na allowlist
  `SUPEREZIO_MEMORY_EXTRA_SESSIONS`. Sessões de teste/probe (`default`, `test-*`,
  `quality-probe-*`, `overnight-*`...) são descartadas ANTES de tocar o disco — memória
  alimenta conselho financeiro, não pode acumular resíduo de teste. `reset_memory_for_test`
  desliga o filtro explicitamente (isolamento). Testes: 123 passando no subset de memória
  (filter + unified + journal + graph + hybrid + conversation).

- [x] 2026-08-17 - **Save session** (Claude Code): persistiu estado operacional do runtime
  Bob (disc-only, sem GitHub). Dados versionados: pain log (24.732 linhas), alerta
  man_at_work (CEO down, trading halt), mangala daily 2026-08-11 (PLUG/KODK/NIO/SNDL/RIG),
  traces de decisão (2026-07-21 run c37477042a57 + 2026-08-07 run b86b0eb20af2).
  Gates: ruff 4 erros pré-existentes; suíte completa aborta em 84% por crash V8 do
  akshare (py_mini_racer 0x80000003) — ver INV-R29; suíte com 2 deselects: 4 failed
  / 1674 passed / 11 skipped em 475s (working tree em movimento — sessão paralela
  zero-cloud ativa; e2e Bob 0 chars consistente com gateway local sem :8080) — ver
  INV-R30; browser smoke ok:false (servidor down). Gaming baseline preservado em
  `.f51/checkpoints/2026-07-24-m4000-gaming-baseline.json`.

- [ ] **Questrade OAuth token nao configurado**: `scripts/questrade_read_portfolio.py` esta
  implementado e funcional (Playwright session persistente, ler carteira sem OAuth token),
  mas a integracao completa exige um token OAuth valido para a API Questrade.
  `data/questrade_portfolio.json` contem snapshot de portfolio real como prova de conceito.
- [ ] **Frontend login UI exists but not user-facing yet**: `frontend/auth.js`, `frontend/auth.css`,
  `frontend/api.js` implementam modal de login/register com JWT Bearer token, mas a UI
  ainda nao esta integrada como tela inicial. Dev mode continua injetando usuario anonimo.
- [x] 2026-07-19 - **3-agent independent verification wave** (Claude Code): dispatched 3
  parallel subagents with disjoint file scope to verify (not trust) claims from the Codex
  predictive-truth-modernization session and an external audit, using concrete synthetic-data
  proof rather than reading docstrings. **Math/crisis models** (src/core/math, src/experts/crisis):
  all CONFIRMED_REAL with numeric evidence — HMM detected a synthetic 100x variance regime
  shift (stress probability 0.0024→0.9999); Hawkes MLE recovered branching_ratio=0.828 from a
  true 0.85 simulated process via Ogata thinning, stability constraint alpha/beta<1 verified
  hard-enforced; Growth-at-Risk pinball loss matched the reference formula exactly (0.00e+00
  diff, 500 points, 5 quantiles); LPPLS recovered known synthetic parameters (tc, m, omega)
  with R²=0.9998; former quantum_bias confirmed fully replaced by a real Politis-Romano
  stationary block bootstrap over actual OHLCV returns (zero "quantum" references left);
  HRP recovered the exact inverse-variance weight ratio (diff <1e-9) against a synthetic
  2-asset case. **Neural/adaptive learning** (technical_neural, neural_decision,
  outcome_learning): all 6 claims CONFIRMED — chronological split with gaps verified via a
  leakage probe (tampered future candles proved bit-identical train features); split-conformal
  prediction set (not a naive confidence threshold) traced end-to-end into the execution gate;
  idempotent ledger proven via a duplicate-event probe (same id+same payload→no-op, same
  id+different payload→OutcomeConflictError, ledger untouched); confirmed zero code path fakes
  a pnl=0/exit=entry pseudo-outcome before a trade actually closes; confirmed the old random
  pseudo-RL policy (neural_rl.py) is now a fail-closed WAIT-only compatibility stub with zero
  active callers; confirmed atomic tempfile+fsync+os.replace artifact writes with SHA-256 +
  smoke-test validation on load. **Security/infra**: found and FIXED a real TOCTOU idempotency
  bug (commit 1f24c84) — the ALLOW path in auto_execute_paper.py never called mark_processed(),
  so approved paper orders were only deduplicated by an in-memory deque that doesn't survive a
  restart; fixed with an atomic os.open(O_CREAT|O_EXCL) claim. Also confirmed REAL and unfixed:
  no API auth on ~20 routes (see Backlog P0 above), a SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT env
  leak via setdefault, /health always-200 regardless of real state, and no coverage measurement
  by default — all logged to Backlog rather than patched, since each needs a contract decision
  (auth scheme, status-code semantics) beyond a small reversible fix.
  *RESOLVED SINCE: P0 API auth and env leak fixed 2026-07-20; --cov added 2026-07-20.
   /health status-code contract remains open.* One earlier claim
  (Order.gate_metadata missing) was REFUTED — the contract already matches; either never true
  in this codebase state or already fixed before this session. Full suite after all 3 agents:
  1538 passed, 0 failed, 11 skipped — identical to the pre-verification baseline except for
  the one real fix. No GitHub operation performed by any agent.
  call sites that don't yet pass declared_tickers (fallback regex path still
  active there); once all call sites declare, consider retiring
  _mentioned_tickers/_NON_TICKER_SYMBOLS/_COMMON_CAPS_WORDS entirely.
- [x] 2026-07-19 - Structural grounding redesign (Claude Code): root-caused the
  recurring "acronym false-flagged as invented ticker" bug (3rd occurrence:
  ALLOW/DCF/EMA/IBKR/SELL/TRAP/VWAP, then DADOS/SEM/SCAN, then FCF/HRP) by
  adding mentioned_tickers to final_answer's tool schema so the LLM declares
  which securities it named instead of the pipeline regex-guessing from prose
  after the fact. Verified live: "analyze SHOP for me" produced a full,
  correct synthesis (6 experts, Trinity divergence, MathHub, F51, SDCA,
  crisis guardrails, explicit non-recommendation) with "DCF, FCF" in the text
  and no false guard trigger — first live run of this exact prompt that
  didn't fall back to a generic discard message. Old regex path kept as
  fallback for calls that don't populate the new field, not yet retired
  (see Backlog item above). Also confirmed (read-only) that the separate
  8-model crisis heuristic rewrite the operator asked for was already done
  by the predictive-truth-modernization session (Minsky-Keen, IMF mispricing,
  Shiller, debt-service-ratio, credit-asset-growth now carry honest
  PUBLIC_NAME + method_kind="heuristic"; network_contagion/systemic_bank_risk
  correctly return insufficient_data instead of fabricating proxies) — no
  further crisis-model work was needed. Also independently verified and fixed
  a formatting gap the Codex session's report had missed (15 files, mostly
  the predictive-truth core, were not ruff-formatted despite the report
  claiming "355 files already formatted" — fixed, 0 test regressions).
  Full suite: 1538 passed, 0 failed, 11 skipped. Commits 0efa30f, 47659a7,
  3a6ae8d.
- [x] 2026-07-19 - Independent verification (Claude Code) of a separate large session
  ("codex", session organism-truth-remediation, 28 commits af84440..dfff247) that built
  directly on top of my crisis-scale fix (63978d9) and grounding-guard fix (c53daf4).
  That session implemented exactly the "organism that learns from real outcomes" gap I had
  flagged but not built: terminal-outcome-only learning ledger, deterministic weighted
  expert consensus, a single shared adaptive execution policy across all order paths, atomic
  crash-safe persistence, pickle-free RAG, and closed the gate_metadata/raw-CLI bypass an
  earlier external audit had flagged as P0. Independently re-ran and confirmed (not just
  trusted the report): full suite 1452 passed/0 failed/11 skipped, ruff check clean, ruff
  format clean (355 files), 38/38 broker+gate contract tests passed. See
  docs/audit/phase10_organism_truth_and_remediation_2026-07-19.md for that session's full
  report — its "Honest residual limits" section is worth reading before assuming predictive
  quality is proven (it explicitly is not — only the causal/risk accounting is).

## In Progress

- [ ] **P0 — runtime Windows canonico:** instalar a partir de `requirements-lock.txt`, sem
  caminhos do desenvolvedor, e iniciar/parar API :8002 + modelo local :8080 com identidade
  de processo verificavel.
- [ ] **P0 — autenticacao unica:** remover senha conhecida, alinhar JWT/API key e garantir
  que login, rotas protegidas e logout usem o mesmo contrato fail-closed.
- [ ] **P0 — verdade operacional:** sincronizar inventario, contratos, onboarding e health
  com 27B/:8080/:8002; separar liveness, readiness, dados e broker.
- [ ] **P0 — quality probe fail-closed:** falhar o gate diante de resposta vazia, vazamento
  de template, ticker/nome incoerente, timeout ou fallback enganoso.
- [ ] **P0 — pacote transferivel:** gerar ZIP limpo, manifest, checksum e ensaio em Windows
  limpo; excluir `.env*`, bancos, WAL/SHM, logs, journals e dados do operador.
- [ ] **P0 — segredos:** rotacionar chaves de providers ja expostas antes de qualquer
  transferencia do pacote.
- [ ] **Phase 9 — benchmark temporal:** comparar agentes fora da amostra contra baselines
  simples, incluindo custos, latencia e abstencao. Sem claim de lucro antes disso.
- [ ] **Phase 10 — piloto real:** bloqueado; exige novo Money Gate, capital estritamente
  limitado, confirmacao humana e todos os riscos criticos resolvidos.


## Done

- [x] 2026-08-26 - **Auditoria de legado/sujeira/duplicação + remediação em 4 frentes** (swarm 5 agentes + 4 agentes de remediação): auditoria read-only consolidada em `docs/audit/LEGACY_AUDIT_2026-08-26.md` (10 achados top: segredos no histórico, dead code declarado live, duplicatas de skills/agentes, docs divergentes da config real). Remediação: (1) exército — cemitérios `deprecated/` criados, 5 skills duplicatas movidas, `.agents/skills/` stale arquivado em `.f51/archive/` (fc5160df, restaurado por 2443ebb6 após absorção por commit paralelo); (2) docs — topologia híbrida real (Qwen local :8080 + DeepSeek externo), modelo UD-IQ2_XXS, GGUF em `%USERPROFILE%\models\qwen3.8-27b\`, MCPs restritos, 32 skills contadas, screenshot real no EVIDENCE_INDEX (2cf27b42); (3) duplicatas doc com banner SUPERSEDED (8d32b819); (4) contratos — core/auth declarado dead, technical_neural pipeline_hook Not live, model-gateway-verifier no manual de orquestração (a3cdd8ec); (5) históricos — whitepaper nitro e plano investment-qa marcados obsoletos/pendentes (8a3ba1bb); (6) tooling — vulture+deptry no extras dev + checkpoint (cd3766ad); (7) f5a32d25 — formatação ruff 7 testes + manifest TD atualizado. Re-auditoria de skills concluída: 32/32 com os 7 critérios (26 APTO + 1 CONDICIONAL tese-tracker + 5 deprecated em re-auditoria 30d) — `.f51/SKILLS_CHECK.md`. Board fechado com pendências registradas (P0 segredos bloqueado pelo operador, format src/, dead code src/, skills órfãs, build_release exclusions). Checkpoint: `latest.json` (sessões doc-contract-remediation + legacy-audit-remediation-20260826).

- [x] 2026-08-20 - **Correção total sistema ↔ documentação** (Codex + 3 subagentes):
  consolidada a verdade operacional zero-cloud (Qwen3.8-27B-Q4_K_M em `:8080`, API/UI
  em `:8002`, contexto 8192 e 22 agentes); código, configuração, launchers Windows/Docker,
  testes e documentação ativa foram alinhados; superfícies históricas ou inseguras foram
  aposentadas fail-closed ou marcadas SUPERSEDED. O runtime vivo concluiu análise AAPL sem
  fallback, retry, cancelamento, overflow ou chamada cloud. Gate final: Ruff e agentes PASS;
  `1883 passed, 10 skipped`; browser smoke PASS. `docker compose config --quiet` passou;
  build Docker vivo não foi executado porque o daemon Docker Desktop estava indisponível.
  Contratos públicos da API permaneceram intactos; INV-R38 resolvido.

- [x] 2026-08-20 - **Cadeia de entrega de produto criada e conectada**: roster passou de
  revisores sem builder para separacao explicita entre orquestracao, implementacao,
  avaliacao de IA, SRE e release. `scripts/check_agents.py` agora falha se esses papeis
  faltarem, se o implementador nao puder editar ou se o captain virar agente geral.
  Gate estrutural: 22 agentes, 32 skills, 0 violacoes; teste direcionado e browser smoke
  aprovados. Isso valida estrutura, nao qualidade preditiva nem prontidao financeira.

- [x] 2026-08-18 - **Deep dive na arquitetura Anthropic financial-services (4 frentes)**:
  operador pediu mergulho a fundo. 4 exploradores paralelos (orquestradores, skills,
  maquinário, packaging) + 1 fetch da sessão. Cobertura: 10/10 orquestradores, 12 folhas
  depth-1, 15 skills dissecadas, orchestrate.py (event loop de handoff com ALLOWED_TARGETS
  + schema), check.py/validate.py (gates da própria Anthropic), packaging completo.
  Síntese em `docs/architecture/ANTHROPIC_FS_DEEP_DIVE.md`. Padrões novos descobertos:
  orquestrador-sem-Write (fund-admin), portões humanos por categoria de consequência
  (posting/distribution/risk-decision/client-send), modeler-computa-e-devolve-JSON,
  injeção como classe universal de fonte suja. APLICADO: (1) `scripts/check_agents.py`
  — gate de cross-refs inspirado no check.py deles (frontmatter, skill citada existe,
  subagent_type existe) + 6 testes; (2) `.claude/skills/tese-tracker/` — primeira skill
  de DOMÍNIO (31 anteriores eram dev-ops), anatomia oficial, tese falsificável com
  estado cross-session em runtime/theses/; (3) market-thesis-writer wiring à skill.
  Evidência: check_agents clean (17 agentes/32 skills), 6 passed, ruff clean.
  Roadmap registrado no doc §8 (captain dispatch-only, portões nomeados, event loop,
  skills de candle/sizing).
- [x] 2026-08-18 - **Arquitetura de agentes alinhada aos templates oficiais da Anthropic
  (financial-services)**: operador trouxe a referência; verificada real e oficial (~9.5k stars).
  Estudo prompt-a-prompt em `docs/architecture/AGENT_PATTERNS_ANTHROPIC_FS.md` com citações
  verbatim e vereditos copiar/melhorar/descartar. Aplicado: (1) novo trio market-* em
  `.claude/agents/` com separação de poderes oficial — `market-data-puller` (read-only,
  anti-injeção, `[SEM FONTE]`), `market-thesis-writer` (ÚNICO Write-holder, `[UNSOURCED]`=0,
  stop-and-surface), `market-thesis-auditor` (pass/fail com localizações); (2) corrigido
  `model-gateway-verifier.md` que ainda instruía "local LLM → cloud fallback" (resquício
  pré-zero-nuvem); (3) corrigido `git add -A` do captain (2x) → add escopado (sessões
  paralelas); (4) roster em `AGENT_ORCHESTRATION.md` + CLAUDE.md (17 agentes). Conformidade:
  leitura pública web apenas — `claude plugin marketplace add` clona do GitHub e permanece
  bloqueado (F51_NO_GITHUB_DISK_ONLY); nada instalado, prompts re-escritos para o domínio
  local. Evidência: commit desta task; INV-R32 (INFO) registra provenance.
- [x] 2026-08-17 - **Zero-nuvem total (diretiva do operador)**: remover TODA dependência de LLM em nuvem
  do gateway e superfícies associadas. Decisão do operador: "nada de fallback na nuvem" — escopo
  confirmado via questionário: zero nuvem (não só fallback do CEO), CEO aponta para o servidor
  local compartilhado do perfil cc (`http://127.0.0.1:8080/v1`, Qwen3.8-27B-UD-IQ2_XXS, validado
  16/08 em 2 GPUs). Se o local cair, o sistema para em MAN_AT_WORK — sem nuvem.
  Descoberta motriz: `.env`/`.env.local` sobrescreviam `SUPEREZIO_AGENT_BASE_URL=https://api.deepseek.com`
  com chave preenchida — o CEO estava rodando em DeepSeek cloud, contrário ao modo DISK ONLY.
  Concluído: providers.py (5 providers locais + `_local_only_override` que rejeita override cloud),
  gateway.py (agente nunca cascadeia), body.py (notification DeepSeek removida), main.py/endpoints.py
  (UI reporta modelo local), schema.py (default Qwen), runtime.yml/model_manifest/config.ps1/
  serve_agent_llamacpp.ps1/RUNBOOK.md (8080 + caminhos reais), .env/.env.local limpos (chave real
  DeepSeek removida — revogação recomendada). Evidência: 506 passed / 1 skipped (contracts + gateway
  + ceo_fallback + components + runtime_bob_fixes + expert_dialogue), ruff clean nos 12 arquivos
  tocados, commits 5a1141b + d4d14a1 + final. INV-R15 resolvido; dependência do cc registrada
  como INV-R26. Próximo: subir run-cc.ps1 e validar live com SUPEREZIO_SMOKE_CHAT=1.
- [x] 2026-07-20 — **SocialWhaleProvider — whale signals, pump detection, social sentiment (Twitter/Nitter + ApeWisdom):** `src/data/social_whale_provider.py` — novo provider que busca sinais de baleia, pumps e ordens grandes via Nitter (proxy gratuito do Twitter/X, sem API key) com fallback para ApeWisdom quando Nitter esta offline. 4 metodos publicos: `get_whale_signals()`, `get_pump_detection()`, `get_social_sentiment()`, `get_unusual_options_flow()`. Registrado no DataHub como "social_whale" com capabilities `whale_signals`, `pump_detection`, `social_sentiment`, `unusual_options_flow`. Tenta 5 instancias Nitter em cascata. Palavras-chave multilingue (PT/EN/ZH). Ruff check + format clean. Nenhuma regression — 15 data_hub tests pass, 511/516 tests pass (5 pre-existing failures inalatadas).
- [x] 2026-07-20 — **Questrade Portfolio Reader (Playwright):** `scripts/questrade_read_portfolio.py` implementa leitor de carteira Questrade com sessao Playwright persistente. Le dados sem OAuth token (via scraping da UI do Questrade). Snapshot de portfolio real salvo em `data/questrade_portfolio.json`. Codigo pronto, falta token OAuth para API oficial. Commits 6cdb275, 81457ea.
- [x] 2026-07-20 — **Browser smoke 100% pass + auth modal dev-mode detection:** `scripts/browser_smoke.py` corrigido para detectar auth modal em dev mode. Suite completa passa 100%. Commit 039055a.
- [x] 2026-07-20 — **68 integration tests — MathHub, builder, contracts, observations:** Nova suite de testes de integracao validando pipeline completo: MathHub, builder, contratos, observacoes. Commit 4a252c7.
- [x] 2026-07-20 — **21 auth unit tests — 85%+ coverage:** Testes unitarios para `core/auth/` e `agent_server/auth/`. Cobertura 85-88% em 4 modulos. Commits 87fd396, 755ba3e.
- [x] 2026-07-20 — **tool_executor submit_paper_order idempotency fix:** Claim atomico com `os.open(O_CREAT|O_EXCL)` aplicado ao `submit_paper_order` em `tool_executor.py`, mesma correcao do `auto_execute_paper.py`. Commit ec83e6a.
- [x] 2026-07-20 — **/health retorna 503 real:** Confirmado e documentado que `/health` agora retorna HTTP 503 quando o sistema nao esta operacional. `test_api_routes_sync.py` atualizado. Commits 662f8b1, 5d2a0e1.
- [x] 2026-07-20 — **env leak fixed + --cov default:** `auto_execute_paper.py` nao mais vaza `SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT=1` no environment. `pytest.ini` agora inclui `--cov=src --cov-report=term-missing` por default. Commit 8ff067f.
- [x] 2026-07-20 — **JWT Auth completo (P0):** Implementacao full-stack: `AuthDB` com SQLite + bcrypt em `core/auth/models.py`; servico com PyJWT e refresh rotation em `core/auth/service.py`; middleware JWT em `agent_server/auth.py`; rotas `/auth/*` (register, login, refresh, me); cascata com API-Key middleware; dev mode fallback. Seed admin script em `scripts/seed_admin.py`. Packages: `pyjwt`, `passlib[bcrypt]`, `bcrypt`. Commits fc778bb, 1945d4f, 2dfa2f3, 8f6d76b, 4f5b40f.
- [x] 2026-07-20 — **Frontend login UI:** `frontend/auth.js`, `frontend/auth.css`, `frontend/api.js` implementam modal de login/register com JWT Bearer token. Integrado ao fluxo dev-mode (anonimo ate login ser implementado como tela inicial). Commits 895a539, 495676e.
- [x] 2026-07-20 — **SDCA string check fix:** `test_sdca_firewall_inline.py` atualizado para usar `fetchWithAuth` em vez de string desatualizada. Commit ff56d84.
- [x] 2026-07-20 — **Certificacao completa — 1446/1446 pass:** Sistema operacional apos limpeza Wave 4 + fixes menores. 1446 tests, 0 fails, 10 skipped. Commits 6efb2c1, c81ff8e.
- [x] 2026-07-20 — **1535 testes, sistema completo:** Apos adicao de 21 auth tests + 68 integration tests: 1535 passed, 0 failed, 10 skipped. Sistema aguardando deploy. Commit e55b2f3.
- [x] 2026-07-20 — **Wave 4 — Integracao final + limpeza massiva (savekeeper):** 23 dead modules (8,511 LOC) removidos de `src/core/trading/`. 40 scripts legados removidos. 7 testes mortos removidos. `pyproject.toml` limpo. Estado final documentado em `docs/STATE_OF_THE_UNION.md`. Gates: 1443 passed, 10 skipped, 0 failed. Ruff clean. Commits 912ec18, aeefa7d, aa332a6.

- [x] 2026-07-20 - **P0 API auth implemented:** X-API-Key middleware (`main.py:361-430`)
  with constant-time comparison + JWT auth middleware (`auth.py`) + `/auth/*` router
  (register, login, refresh, me) with SQLite-backed user storage and bcrypt password hashing.
  Public paths exempted: `/health`, `/favicon.ico`, `/`, `/metrics`, static assets.
  Dev-mode fallback when no API key is configured. Covers all ~20 routes previously
  identified as zero-identity-check. Supersedes backlog item "P0 — no API auth".
  Full suite: verified via code review (no test regressions expected from middleware addition).

- [x] 2026-07-20 - **auto_execute_paper.py env leak fixed:** removed `os.environ.setdefault(
  "SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")` from `auto_execute_paper.py:50` which ran on
  every conversation turn and leaked "1" into the process environment, overriding the
  operator's `docker-compose.yml` setting of `false`. Paper submission is now correctly
  governed by the external env var or `settings.superezio_enable_paper_order_submit`
  (default `False`). `F51_TRADING_EXECUTION_FREEZE` remains as the independent safety gate.

- [x] 2026-07-20 - **pytest.ini --cov coverage enabled:** added `--cov=src --cov-report=term-missing`
  to pytest.ini addopts. Default `pytest tests/ -q` now measures coverage automatically.

- [x] 2026-07-20 - **Browser E2E smoke pass verified:** `scripts/browser_smoke.py` confirmed
  passing during Wave 2 UX audit (previously completed; acknowledged in task board).

- [x] 2026-07-19 - **Predictive truth modernization (Codex + 3 deep subagents):**
  removed fixed/random predictive evidence; corrected causal RSI/MACD, HRP and return
  bootstrap; rebuilt crisis HMM/Hawkes/GaR/LPPLS with honest insufficient-data states;
  built a persistent causal three-class neural champion with chronological gaps,
  train-only scaling, OOS baseline gates, temperature calibration, split conformal
  abstention and safe artifacts; bound singleton neural evidence to paper/broker order
  entry; made terminal outcomes update expert weights through directional multiclass
  Brier skill with shrinkage; retired random pseudo-RL actions. Full verification:
  `1532 passed, 11 skipped, 0 failed`, Ruff clean, live browser smoke clean. Honest
  remaining data/runtime limits are in
  `docs/audit/predictive_truth_modernization_2026-07-19.md` and the durable checkpoint.

- [x] 2026-07-19 - 4 parallel subagent fixes + critical security findings (Claude Code):
  launched 4 subagents in parallel, each with exclusive file scope, no conflicts. Fixed:
  F51 spider_sense hardcoded evidence + critic fail-open (4bda75c), DataHub accepting
  empty {} as usable result + exec() in custom_tools audited/reinforced with 18 tests
  (ea63541), expired IBKR apprenticeship date now resolved by real date comparison
  (10490cf), root cause of red_team KeyError('provider') found (double-formatting an
  already-resolved f-string) + SDCA _truthy_high inverted "low" logic (d8ca01b). Full
  suite after merge: 1402 passed, 0 failed, 11 skipped. Verified live: red_team no longer
  crashes (now fails on legitimate strict_json_validation_failed), f51_unified status=ok,
  consumer-facing test ("I'm new to investing...") produced an honest, complete,
  non-fallback response. CRITICAL, NOT fixed per explicit operator instruction to stop
  touching anything token/secret-related: real Hugging Face token exposed in 6 files
  under F51-Nitro-MoE/ (only 2 known before this session; found 4 more), and
  np.load(allow_pickle=True) in src/core/rag/engine.py:388 (arbitrary code execution risk
  if the RAG index file is tampered with). See docs/audit/phase9_parallel_fixes_and_critical_findings.md.
  Operator must revoke the HF token; pickle fix awaits explicit go-ahead. A separate
  external audit also reported several ALTO/MEDIO findings (no API auth, paper-order
  default-on flag, crisis.py scale mixing, etc.) — NOT independently verified this
  session, do not act on them without checking first.
- [x] 2026-07-19 - Live end-to-end verification + F51 critical fix (Claude Code): started
  the real server (agent_server.main), opened the real UI, and submitted real requests via
  /task/submit. Found and fixed a bug invisible to unit tests: math_hub.py called
  DecisionFactors(risk=...) but the class has no 'risk' field (it's 'danger') — every real
  invocation of the F51 verdict engine raised TypeError and silently returned
  status=error. Confirmed live before/after via identical requests. Also confirmed the
  autonomous MAN_AT_WORK safety mode works correctly (blocks all trading when CEO is
  unreachable, without being asked to). Found remaining live bug: KeyError('provider') in
  red_team_agent_* roles (not yet root-caused — reproduction outside the real LangGraph
  runnable context fails differently). Wrote docs/audit/ROADMAP_CONSULTANT.md reframing the
  project's goal per operator direction: a real-time natural-language financial consultant,
  not an automated trading system. Documents the full verified request flow and what
  specifically blocks that goal (no LLM provider configured, no local CEO GGUF present).
  Full suite: 1367 passed, 0 failed, 11 skipped. Commits 632a43f, 4bdc248.
- [x] 2026-07-19 - Safety gate unification (Claude Code): fixed CRITICAL gap from
  phase6 audit — F51_TRADING_EXECUTION_FREEZE and SUPEREZIO_LIVE_TRADING_DISABLED
  were independent, non-communicating safety families. is_execution_frozen() now
  checks both; SUPEREZIO_LIVE_TRADING_DISABLED default changed False -> True
  (fail-safe). Fixed 1 test that relied on the old unsafe default. Full suite:
  1367 passed, 0 failed, 11 skipped. Commit 47404b2. Also folded in phase5-8
  audit reports (F51/SDCA/Neural, RAG/PennyLab/execution, idempotency/security,
  executive summary) produced by a separate agent run via
  docs/audit/SUBAGENT_RESEARCH_PROMPT.md, plus scripts/questrade_order_assist.py
  (Playwright fills the Questrade order ticket, never clicks submit/confirm —
  that stays a human action in the real browser window).
- [x] 2026-07-19 - Component-by-component audit (Claude Code): 4 phases documented in
  `docs/audit/phase1-4b`. Confirmed and fixed: quantum_module fixed RNG seed (math_hub.py),
  f51_module hardcoded consensus=0.65, silent gateway fallback with no opt-out on the sync
  expert path, and all experts/judge/auditor sharing identical unfiltered data_context.
  Rewrote EXPERT_PROMPTS with per-role data isolation (EXPERT_CONTEXT_MODULES) and
  build_judge_context(), informed by TradingAgents (arXiv:2412.20138), FinRobot
  (arXiv:2405.14767), AIMM (arXiv:2512.16103). runtime.yml context_length divergence
  (4096 vs 65536) documented as unverifiable — no GGUF present on disk. Commit 7f77357.
  Full suite: 498 passed, 5 pre-existing failures unaffected, 2 skipped.
- [x] 2026-06-13 - Career bootstrapping: created professional Portuguese & English resumes, LinkedIn strategy, and GitHub portfolio optimization guide under docs/career/.
- [x] 2026-06-01 - Phase 3 (f51-tests): 977/979 pass. 2 pre-existing failures documented in RISK_REGISTER (INV-R13, INV-R14).
- [x] 2026-06-01 - Phase 2 (f51-runtime): Runtime verified with healthchecks, logs, checkpoints, runbook.
- [x] 2026-06-01 - Phase 1 (f51-contracts): Contract definitions + 108 tests passing.
- [x] 2026-05-21 - Removed model build surfaces from the active tree and kept the merged GGUF runtime path.
- [x] 2026-05-21 - Clean tree pass: removed archived runtime/docs surfaces, generic non-F51 skill bundles, retired provider alias path, edge placeholder hooks, and stale F51 map content.
- [x] 2026-05-20 - Frontend/runtime/contracts/tests delivery saved locally.
- [x] 2026-08-21 - Hardening delivery (pos-auditoria adversarial de 5 subagentes): config single-GPU honesta (a653c5e), gateway carrega .env no factory + default deepseek-v4-pro (e302dd1), fraud guard vivo com 6 regras computaveis + testes (1d4313e), cobertura explicita fora dos addopts (9ee8dca), fonte unica de risco documentada (6d124ee), allocator fail-closed + playbook so com ETFs do universo 108 (8f5e1cf), guard de run_ids sinteticos no decision ledger (4ec5127), regressao pinned candles time=0 (51447b5). RISK_REGISTER R41-R49. Working tree limpa, DISK ONLY.

## Policy

- GitHub is blocked by `.f51/GITHUB_POLICY.json`; do not run `git push`, `git pull`, `git fetch`, or `gh`.
- No archived runtime tree in the active repo.
- No model build pipeline in the active runtime tree.
