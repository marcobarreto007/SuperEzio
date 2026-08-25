# F51 Risk Register

Updated: 2026-08-25
Session: audit-and-harden-f51-20260824 (auditoria do caminho de trade + 15 correções cirúrgicas — ver .f51/checkpoints/latest.json)

## Active Risks

### INV-R61 - fetchJson propaga detail do 503 [LOW]

- Classification: frontend contract / observability change.
- Risk: `fetchJson` (frontend/js/api.js) agora propaga o `detail` do body em erros HTTP.
  Consumidores que comparavam a string exata do erro (ou que esperavam nunca receber
  503 de /health) podem ver texto novo — ex. "CORE MAN_AT_WORK mode active" no label
  do cockpit em vez de "CORE OFFLINE".
- Mitigation: contrato fixado em `tests/test_api_routes_sync.py`
  (test_frontend_trade_confirmation_requires_explicit_broker_confirmation atualizado);
  auth.js já tolerava 503 antes; smoke verde com servidor vivo.
- Status: MITIGATED 2026-08-25.

### INV-R60 - Lock cross-process do journal so cobre Windows [LOW]

- Classification: platform / portability.
- Risk: `_journal_file_lock` (paper_journal.py) usa msvcrt.locking; em não-Windows o
  fallback é thread-lock apenas e o lost update cross-process volta a ser possível.
  O repo é Windows-first (ambiente atual), então exposição real é zero hoje.
- Mitigation: fallback explícito + teste determinístico com subprocesso
  (tests/test_paper_journal.py::test_journal_file_lock_blocks_other_processes).
- Status: ACCEPTED 2026-08-25.

### INV-R59 - stop_loss_price do modelo ignorado [MEDIUM]

- Classification: contract / behavior change no caminho de submissão paper.
- Risk: `_submit_paper_order` deixou de honrar stop_loss_price dos args (commit
  be5cd08) — o stop é sempre derivado de `limit_price * (1 - default_stop_pct)`.
  Payloads existentes que enviam stop customizado têm o risco calculado alterado
  (testes atualizados: 501→1000 e 5010→5000). Fecha o bypass da aprovação humana
  de $500 via stop apertado proposto pelo modelo.
- Mitigation: testes de risco atualizados com comentário do motivo; approval gate
  intocado.
- Status: MITIGATED 2026-08-25.

### INV-R58 - Colar de preço LIMIT_PRICE_COLLAR [MEDIUM]

- Classification: trade gate / false-positive de recusa.
- Risk: GATE 9.5 (commit 3dc38350) recusa limit_price com desvio >5% (referência
  ≤180s) ou >10% (referência velha/desconhecida) do preço DataHub. Em penny stock
  com mercado em movimento rápido (scan de até 5 min), ordens legítimas podem ser
  recusadas — trade-off intencional contra preço alucinado/placeholder.
- Mitigation: banda condicionada à idade da referência (data_age_s passado por
  auto_execute_paper); o caminho TD mantém colar próprio de 2% com quote
  multi-provedor; evidência completa no BLOCK (deviation_pct, band_pct, data_age_s).
- Status: MITIGATED 2026-08-25.

### INV-R57 - MAN_AT_WORK enforcado no caminho de trade [MEDIUM]

- Classification: trade gate / fail-closed.
- Risk: GATE 1.5 (commit eb9a9bc) bloqueia toda ordem quando MAN_AT_WORK está ativo
  ou quando a sonda de consciência está inacessível (MAN_AT_WORK_UNAVAILABLE).
  Combinado com o hardening b16c66c (entrada só com 3 falhas consecutivas, recovery
  a cada ciclo), um restart do llama.cpp não congela mais o trading por ~11 min —
  mas 3 falhas reais do CEO (:8080) param as ordens até a recuperação. Intencional.
- Mitigation: fail-closed com motivo estruturado; testes de gate (normal/bloqueio/
  unavailable) em tests/test_f51_trade_gate.py.
- Status: MITIGATED 2026-08-25.

### INV-R56 - Classificador casual exige saudacao de mensagem inteira [LOW]

### INV-R56 - Classificador casual exige saudacao de mensagem inteira [LOW]

- Classification: routing / behavior change.
- Risk: `_is_casual_message` (src/core/pipeline/intents.py) agora so classifica como
  casual a mensagem composta INTEIRAMENTE por tokens de saudacao/cortesia. Aberturas
  conversacionais com conteudo real ("oi bob, status rapido sem operar", "bom dia, o
  mercado abre hoje?") deixam o fast-path casual e entram no pipeline completo
  (MathHub incluso — restauracao do contrato math_report quebrado pelo 54cebc8).
  Saudacoes puras ("oi bob", "bom dia bob") continuam no fast-path. Efeito colateral
  aceito: aberturas charmosas sem pedido concreto ("oi, tudo certo por ai?") agora
  rodam o pipeline em vez da resposta curta canonica.
- Mitigation: matriz pinned em `tests/test_casual_greetings_and_intent.py` (casos
  puros continuam casuais) + casos de conteudo no mesmo arquivo; verificado 16/16
  na validacao manual e 32 passed na bateria.
- Status: MITIGATED 2026-08-24.

### INV-R55 - OPEN_ACCESS na URL publica (5 pessoas) [HIGH]

- Classification: exposure / identification removed by operator decision.
- Risk: `SUPEREZIO_OPEN_ACCESS=1` com tunel publico (`supereziorealtime.com`) deixa
  chat, cockpit, metrics e paper-trade sem identificacao. Qualquer um com a URL
  usa o copiloto (custo DeepSeek dos experts). Nao transmite ordem live
  (`LIVE_TRADING_DISABLED` + `EXECUTION_FREEZE` intactos).
- Mitigation: flag reversivel; desligar `SUPEREZIO_OPEN_ACCESS` e reiniciar :8002
  restaura JWT. Registro de contas permanece 403.
- Status: ACCEPTED 2026-08-23 — decisao do operador para distribuicao a 5 pessoas.


### INV-R53 - CEO llama-server sem supervisor (queda por janela fechada) [HIGH]

- Classification: operational resilience / runtime supervision.
- Risk: `serve_agent_llamacpp.ps1` roda o modelo em foreground, preso a janela do
  terminal. Em 2026-08-23 a janela/sessao foi encerrada ~21:10Z, matou o llama-server
  sem mensagem de shutdown e nada religou: 49 min em MAN_AT_WORK ate intervencao manual
  (checkpoint `restart-ceo-20260823.json`). Sem watchdog, qualquer queda exige operador.
- Mitigation: `scripts/watchdog_ceo.ps1` (health a cada 30s, grace de 3 ciclos, relance
  detached, anti-crashloop max 4/h). Ativado 2026-08-23 em janela hidden.
- Residual: integrar ao logon (Task Scheduler) ou `start.ps1` para sobreviver a reboot;
  rehearsal de queda controlada (kill do llama-server e observar relance automatico) pendente
  de decisao do operador.
- Status: MITIGATED 2026-08-23 (watchdog ativo desde 18:38Z, PID 20284 na epoca).

### INV-R54 - Stream de chat contem trace de pipeline em EN (falso positivo no smoke) [MEDIUM]

- Classification: product language consistency / test gate false positive.
- Risk: as secoes `## DATA ... ## BOB_VERDICT` streamadas na resposta de chat eram
  instruidas em ingles no prompt (`builder.py`), e o modelo ecoava prosa EN; o
  `browser_smoke.py` checava o stream bruto e reprovava "language drift" em respostas
  cujo texto do modelo era 100% PT. Smoke falhava consistentemente pos-restart.
- Resolution: instrucoes das secoes traduzidas para PT em
  `src/core/pipeline/prompts/builder.py` (headers `## *` e marcadores `MISSING`,
  `[MODULO]`, `Bob's read`, `MANDATORY FORMAT` preservados — contratos de teste);
  checagem de idioma do smoke restrita ao segmento `SUA EXPLICACAO` do modelo
  (`browser_smoke.py`, `languageSegLength` novo no relatorio).
- Status: MITIGATED 2026-08-23 — pytest contratos/integracao 125 passed; smoke verde
  (languageOk=true, 0 marcadores EN no stream ao vivo de 2806 chars).

### INV-R51 - Manifest do universo TD degrada com idade (TTL 7 dias) [MEDIUM]

- Classification: data freshness / fail-closed degradation.
- Risk: o manifest `config/td_tradable_universe.json` (11.527 símbolos US) voucha por
  candidatos cuja fonte não prova a bolsa. Vencido (>7d) ou ausente, `is_td_tradable`
  degrada para a allowlist de bolsas — itens sem bolsa verificada são rejeitados
  (`exchange_not_td_supported`) em vez de aceitos: o sistema fica mais restrito, nunca
  mais permissivo. Mas scans podem encolher silenciosamente até o refresh.
- Evidence: `tradable_universe_state()` em `src/core/trading/td_universe.py`; estado
  exposto em `td_universe_summary()`; testes fresh/stale/invalid/missing em
  `tests/test_td_universe.py`. CA section vazia (Twelve Data quota 1550/800 em
  2026-08-23) — TSX/TSXV cobertos pela allowlist de venue nesse meio-tempo.
- Mitigation: rodar `python scripts/update_td_universe_manifest.py --only all`
  após o reset de quota (midnight UTC) e a cada ≤7 dias; NUNCA `--only ca`
  sozinho (sobrescreve o manifest com CA-only). Monitorar
  `tradable_manifest_state` no summary.
- Status: Active — degradação fail-closed por design; refresh é operacional.

### INV-R52 - Allowlist de 6 bolsas não reconfirmada em fonte oficial TD [MEDIUM]

- Classification: data provenance / verification gap.
- Risk: TSX/TSXV/NYSE/NASDAQ/NYSEAMERICAN/NYSEARCA foi derivada por consistência
  interna (Arca exigida pelos próprios ETFs commission-free SPY/GLD/SMH/GDX; AMEX
  exigida pelo contrato do ticket TD) + análise de código — não reconfirmada contra
  página oficial da TD Direct Investing (cota de WebSearch esgotada até 2026-09-14).
  CSE/NEO/TSX Alpha ficam de fora fail-closed "até o operador confirmar com a TD";
  se a TD listar alguma delas, o sistema rejeitaria ativos negociáveis (falso
  negativo, direção segura).
- Evidence: relatórios dos 3 subagentes de pesquisa (S1/S2/S3, 2026-08-23); S2 não
  conseguiu fonte TD oficial; enumeração live-validated: Nasdaq SymDir + Twelve Data.
- Mitigation: em setembro, reconfirmar a lista de bolsas suportadas na página oficial
  TD Direct Investing e revalidar símbolo a símbolo os 108 commission-free; ajustar
  `TD_EXCHANGE_CURRENCY` se necessário (única fonte, sem drift).
- Status: Active — erro na direção segura (rejeita demais, nunca aceita demais).

### INV-R50 - Quote sem finnhub depende de payload de price (change_pct/volume ausentes) [LOW]

- Classification: data quality / free-tier resilience.
- Risk: com finnhub fora, a capability `quote` e atendida por rotas de price (twelve_data, alpha_vantage, yfinance) via alias no DataHub. TwelveData e yfinance nao expoem `change_pct`; TwelveData nao expoe `volume` — o score de completude da quote cai (3-4 de 5 campos) e consumidores que exigirem variacao intradiaria podem receber dado parcial.
- Evidence: contratos atuais (`DataQualityFilter.normalize_price`, `_is_usable_result`) tratam esses campos como opcionais; nenhum consumidor em `src/` exige `change_pct` hard-fail. Observado em revisao 2026-08-23 (commit c486f78).
- Mitigation: quando a Finnhub key for rotacionada, finnhub (quote dedicada completa) volta a ser prioridade 1 automaticamente. Se necessario, enriquecer `yfinance.get_price` com change_pct via `previous_close` e `twelve_data.get_price` com `change`/`volume` do payload /quote (ja retornados pela API, nao extraidos).
- Status: Active (monitorar completude do quote enquanto finnhub estiver sem chave).

### INV-R40 - Habilidade de investimento nao comprovada [CRITICAL]

- Classification: model quality / financial evidence.
- Risk: funcionamento técnico, resposta textual estruturada e gates causais podem ser
  confundidos com capacidade de prever retornos ou superar benchmarks.
- Evidence: avaliação exploratória criada e executada na mesma sessão, com 5 anos de OHLCV
  observado em 8 ativos e 3 horizontes, carregou 24/24 casos, mas qualificou 0/24; 23 não
  superaram a validação e 1 não convergiu. Não houve pré-registro independente. O backtest
  penny causal em 4 ativos produziu 0 trades.
- Mitigation: real-capital NO-GO; abstinência fail-closed; score textual rotulado como
  `response_form_not_investment_accuracy`; coletar previsões ex-ante e outcomes antes de
  alegar skill.
- Evidence report: `docs/audit/MULTI_ASSET_INVESTMENT_QUALITY_2026-08-20.md`.
- Status: Active — bloqueia qualquer alegação de alpha, recomendação automatizada ou uso de
  capital real; não bloqueia pesquisa e aconselhamento com supervisão humana.

### INV-R16 - Predictive labels exceed implemented evidence [CRITICAL] -> MITIGATED 2026-07-19

- Classification: scientific integrity / execution safety
- Risk: F51, neural, crisis and MathHub surfaces can present heuristics, proxies,
  leakage or missing data as confidence, prediction, normal regime or ground truth.
- Evidence: predictive-truth impact map in `.f51/checkpoints/latest.json` and the
  three independent module audits executed on 2026-07-19.
- Resolution: F51 score relabeled uncalibrated and requires independent evidence;
  neural direction now uses causal temporal partitions, OOS baseline skill,
  temperature calibration, split conformal abstention and durable provenance;
  every order path requires a singleton qualified forecast; crisis/systemic modules
  return insufficient_data without required inputs; fabricated 50% and quantum paths
  were removed; random pseudo-RL was retired.
- Evidence: commits `dba0d08..aee4a1c`, report
  `docs/audit/predictive_truth_modernization_2026-07-19.md`, full suite
  `1532 passed, 11 skipped`, live browser smoke passed.
- Residual risk: statistical integrity is enforced, but profitable alpha is not proven.
  Keep paper/prequential collection active before claiming predictive edge.
- Status: Mitigated; residual performance risk active by design.

### INV-R17 - Runtime dependency drift [HIGH]

- Classification: reproducibility
- Risk: the active interpreter has NumPy 2.4.6 despite the project constraint
  `<2.3`, and `statsmodels` is declared/locked but absent. Scientific behavior can
  differ from the recorded lock and several models silently degrade.
- Evidence: direct import/version probe on 2026-07-19.
- Mitigation: do not hide optional-dependency absence; implement deterministic
  supported paths and verify the locked environment separately.
- Status: Active.

### INV-R18 - Required empirical datasets are absent [HIGH]

- Classification: model availability / scientific validity
- Risk: MacroDataset has no Parquet files in the workspace, and institution-level
  capital, liabilities, LRMES and exposure networks are unavailable. Several crisis
  sensors therefore cannot estimate their named targets.
- Evidence: recursive Parquet inventory returned zero files; SRISK/CoVaR/DebtRank
  contract tests now assert insufficient_data.
- Mitigation: keep fail-closed states; ingest versioned, timestamped real datasets
  before enabling those models. Never restore synthetic proxies.
- Status: Active and honestly surfaced.

### INV-R19 - Predictive profitability is unproven [HIGH]

- Classification: model risk
- Risk: passing OOS gates on available per-request history does not establish stable
  live alpha after costs, regime shift and repeated model selection.
- Evidence: no sufficiently long prequential prediction/outcome ledger was available
  in this session.
- Mitigation: paper-only champion/challenger evaluation by symbol/horizon; compare
  against climatology and current champion using Brier/log-loss, conformal coverage,
  turnover/costs and regime stability.
- Status: Active; autonomous execution remains heavily gated.

### INV-R1 - GitHub remains blocked [HIGH]

- Classification: policy
- Risk: Any GitHub operation violates project policy.
- Evidence: `.f51/GITHUB_POLICY.json` is active and hard-blocking.
- Mitigation: Use local commits only.
- Status: Ongoing.

### INV-R2 - Model rebuild requires intentional reintroduction [MEDIUM]

- Classification: operator workflow
- Risk: The repo no longer contains model build tooling. Production GGUF is the only model artifact.
- Evidence: Build data roots and launchers were removed from the active tree.
- Mitigation: Treat the checked-in GGUF as the production model artifact.
- Status: Accepted.

### INV-R3 - Pipeline refactor not fully re-verified [HIGH] → RESOLVED 2026-05-24

- Classification: operational
- Risk: The agentic loop refactor changed graph topology. Verified with full test suite.
- Evidence: 866 passed, 4 failed (1 pre-existing connection reset, 3 test expectations fixed), 7 skipped in 34.74s.
- Resolution: Contract synced. Dead code removed (`route_after_orchestrator`, zombie `data` node). Pipeline contract updated to reflect `orchestrator → agent ⇄ tool_executor`.
- Status: Resolved.

### INV-R4 - 4 API keys leaked in git history [HIGH]

- Classification: security
- Risk: DeepSeek, TwelveData, Alpha Vantage, NewsAPI keys were committed. Anyone with repo access can extract them.
- Evidence: `docs/internal/SECURITY_LEAKED_KEYS.md` previously documented 4 keys (file no longer present in working tree; keys remain in git history regardless).
- Mitigation: Rotate all 4 keys before any repo transfer or remote push.
- Status: **Risk knowingly accepted by operator (Marco Barreto) on 2026-07-18. Keys not rotated. Decision: proceed without rotation.**

### INV-R5 - No CI pipeline (GitHub blocked by policy) [MEDIUM]

- Classification: quality
- Risk: No automated CI runs on commit. Relies entirely on local discipline (`make verify` = ruff check src tests + ruff format --check src tests + pytest).
- Evidence: `.github/` directory does not exist. `.f51/GITHUB_POLICY.json` blocks all GitHub operations.
- Mitigation: `make verify` covers both src and tests via ruff + pytest. Run manually before every commit.
- Status: Accepted (by policy).

### INV-R6 - .f51/tmp contains 8.1 GB of stale training artifacts [LOW]

- Classification: disk waste
- Risk: Consumes significant disk space. May confuse future agents about build surface.
- Evidence: 27 files including safetensors, merged models, training scripts, SFT data.
- Mitigation: Safe to delete when disk space is needed. Not referenced by runtime.
- Status: Informational.

### INV-R7 - data/fraud_datasets contains 3.3 GB of downloaded datasets [LOW]

- Classification: disk waste
- Risk: 4 HuggingFace datasets with .cache directories. Unclear if needed at runtime.
- Evidence: Financial-Fraud-Dataset, Nigerian-Fraud-Detection, Financial_statements_fraud_dataset, financial-fraud-dpo-exact.
- Mitigation: Verify if fraud_rag.py requires local datasets. If not, safe to delete.
- Status: Needs verification.

### INV-R8 - Black vs Ruff format inconsistency [LOW] → CLOSED 2026-05-24

- Classification: tooling
- Risk: Previously thought Makefile ran both black and ruff. Makefile only uses ruff (check + format). No inconsistency.
- Evidence: Makefile `verify` target only calls `ruff check src tests` and `ruff format --check src tests`. `.github/` doesn't exist.
- Resolution: Single formatter (ruff). No conflict.
- Status: Resolved.

### INV-R9 - src/core/scanner and src/core/paths are init-only modules [LOW] -> RESOLVED 2026-07-20

- Classification: dead code risk
- Risk: Two packages contain only __init__.py with no separate source files. May indicate dead code.
- Evidence (2026-07-20): `scanner/` contains openbb_scanner.py (8881 bytes) and penny_scanner.py (2486 bytes). `paths/` __init__.py has 1270 bytes with actual path resolution code. Both modules have real content and active imports across the codebase.
- Resolution: Verified on 2026-07-20. Real code, not init-only. Risk closed.
- Status: Resolved.

### INV-R10 - Duplicate runtime log directories [LOW]

- Classification: operational
- Risk: runtime/logs/ and output/server/ both contain API/CEO logs. Redundant storage.
- Evidence: 37 files in runtime/logs, 6 files in output/server.
- Mitigation: Consolidate to one log directory.
- Status: Informational. Not addressed in Wave 4 cleanup.

---

## New Risks (2026-07-20 — Wave 4 Cleanup)

### INV-R20 - Clean tree verification [INFO]

- Classification: quality
- Risk: 23 dead modules (8,511 LOC) and 40 scripts were removed from `src/core/trading/` in a single commit. Hidden import chains or dynamic lookups could reference removed modules at runtime.
- Evidence: Full test suite (1443 tests) passes. Ruff import checks pass. Wave 3 regression hunt confirmed zero import errors. Core trading modules still active: paper_journal.py, approval_gate.py, position_sizer.py, order_builder.py (rebuilt lean version), execution_policy.py, outcome_learning.py. All others confirmed dead by 3-agent verification.
- Mitigation: None needed — verified by test suite + ruff import scan + wave 3 regression hunt.
- Status: Verified clean. No residual risk.

### INV-R21 - Deleted tests reduce coverage surface [INFO]

- Classification: quality
- Risk: 7 test files removed (autonomous_live_engine, broker_reconciler, daily_cycle, trading_loop2, xp_idempotency, debut_report, f51_blindagem_final, f51_final_shielding). Test count dropped from 1539 to 1443.
- Evidence: All removed tests covered dead code that was also removed. Zero coverage loss for active code paths. Test removal was a direct consequence of dead module removal.
- Mitigation: Rebuild coverage for any new code paths added in product phase. Consider adding --cov to pytest default when coverage quality is a concern.
- Status: Informational. Acceptable.

---

## Resolved Risks

- ~~**INV-R3** (2026-05-24): Duplicata removida 2026-07-20. INV-R3 mantido em Active Risks com status RESOLVED.~~
- ~~**INV-R5** (2026-05-24): Duplicata removida 2026-07-20. INV-R5 mantido em Active Risks acima.~~
- ~~**INV-R8** (2026-05-24): Duplicata removida 2026-07-20. INV-R8 mantido em Active Risks com status CLOSED.~~
- **Hardcoded route="general"** (2026-05-24): Removed in commit ce2bf32. Orchestrator classification now flows to agent, experts, and SDCA firewall.

---

## New Risks (2026-06-01 — Phase 1 Contracts)

### INV-R11 - 108 new contract tests not yet integrated into full suite [LOW]

- Classification: quality
- Risk: New tests in `tests/contracts/` but full `python -m pytest tests/ -q` not re-run. May surface pre-existing failures.
- Evidence: Phase 1 created 6 test files for 108 tests (all passing in isolation). Full suite had 866+ tests as of 2026-05-24.
- Mitigation: Run full test suite during Phase 3 (f51-tests).
- Status: Accepted — deferred to Phase 3.

### INV-R12 - Contract coverage gap: pennylab, rag, expert committee only partially covered [LOW]

- Classification: quality
- Risk: `test_contract_pennylab.py` and deeper expert committee tests not created. Covered tangentially by existing `test_contract_experts.py` and `test_contract_rag.py`.
- Evidence: 108 tests cover all 26 inventory modules at import/instantiation level, but deeper integration tests missing for PennyLab experts.
- Mitigation: PennyLab integration already tested in existing `test_pennylab.py` and `test_components_pennylab.py`.
- Status: Informational.

---

## New Risks (2026-06-01 — Phase 2+3 Runtime + Full Suite)

### INV-R15 - Modelo CEO local ausente [HIGH] → RESOLUÇÃO ADOTADA 2026-08-17

- Classification: operational
- Risk: GGUF esperado (Huihui-Qwen3-Next-80B IQ4_XS, ~40 GB) nunca existiu no disco; `config.ps1`/`runtime.yml`
  apontavam para `C:\llama.cpp\models\` inexistente. O sistema funcionava apenas porque `.env` sobrescrevia
  o CEO para DeepSeek cloud (contrário ao modo DISK_ONLY).
- Evidence: grep de `.env`/`.env.local` (2026-08-17): `SUPEREZIO_AGENT_BASE_URL=https://api.deepseek.com` com chave.
- Resolution (decisão do operador 2026-08-17): zero-nuvem. CEO e todos os papéis LLM apontam para o servidor
  local compartilhado do perfil cc em `http://127.0.0.1:8080/v1` — Qwen3.8-27B-UD-IQ2_XXS.gguf (8,4 GB, 2 GPUs,
  contexto 40960, validado 16/08 em `C:\Users\marco\models\qwen3.8-27b\run-cc.ps1`). Se 8080 cair: MAN_AT_WORK,
  sem fallback de nuvem.
- Status: **Resolved 2026-08-17 — zero-nuvem implementado (commit zero-cloud), 506 testes do subset passando.**
- Superseded 2026-08-21: a resolucao do CEO local permanece, mas o operador restaurou o tier externo DeepSeek para experts/judge/auditor. O contrato atual e hibrido e proibe fallback cruzado; ver `docs/runbooks/RUNBOOK.md`.

### INV-R26 - CEO depende de servidor local compartilhado com o perfil cc [MEDIUM] (2026-08-17)

- Classification: single point of failure / capacidade
- Risk: As 2 GPUs (2070 8GB + P106 6GB) sustentam UM servidor llama-server. CEO do SuperEzio compartilha
  a instância do perfil cc (:8080, 1 slot): (a) se o operador derrubar o servidor cc, o CEO cai;
  (b) carga do CC e do SuperEzio disputam o mesmo slot (latência); (c) contexto 40960 do cc difere do
  contexto 4096 herdado do runtime.yml antigo — requires re-validação.
- Evidence: `run-cc.ps1` (--parallel 1, -ts 8,6, c 40960); runtime.yml legado context_length 4096.
- Mitigation: documentar dependência no OPERATIONAL_RUNBOOK (ordem de boot: subir cc primeiro);
  health check do SuperEzio deve monitorar :8080. Servidor dedicado em 8082 só com VRAM adicional.
- Status: Active — aceito pelo operador como trade-off.

### INV-R14 - Desktop launcher cannot resolve project path [RESOLVED]

- Classification: operational
- Risk: `desktop/SuperEzio.bat` path resolution broken. **BAT file deleted by operator request.**
- Mitigation: Use direct commands: `serve_agent_llamacpp.ps1` + `python -m agent_server.main`.
- Status: **Resolved — BAT retired, launcher test removed from contract suite.**

### INV-R25 - Full suite baseline: 977 pass, 2 fail, 8 skip [INFO]

- Classification: quality
- Risk: None. Baseline recorded for future comparison.
- Evidence: `python -m pytest tests/ -q` → 977 passed, 2 failed, 8 skipped in 27.60s.
- Status: **Baseline recorded.**

---

## New Risks (2026-07-20 — Session Final)

### INV-R22 - Questrade OAuth token nao configurado [MEDIUM]

- Classification: integration
- Risk: Script `scripts/questrade_read_portfolio.py` esta implementado e funcional para scraping via Playwright (sessao persistente), mas a API oficial Questrade requer token OAuth. Sem o token, nao e possivel automatizar leitura de portfolio via API.
- Evidence: Script executa com sucesso via Playwright UI scraping. `data/questrade_portfolio.json` contem snapshot real. Commit 31c14d9 confirma "codigo pronto, falta OAuth token".
- Mitigation: Obter token OAuth do Questrade Portal e configurar via .env.
- Status: Active. Codigo pronto para integracao.

### INV-R24 - Price provider chain has 3/5 providers non-functional [HIGH]

- Classification: data integrity / availability
- Risk: DataHub price chain claims 5 providers but only 2 work (yfinance, TwelveData). Finnhub key b444a4ae is invalid (http_401). Stooq.com returns 404 on all endpoints (site offline). AKShare Chinese endpoints are blocking connections from this machine. In a scenario where TwelveData rate-limits or yfinance is blocked, price lookup fails completely — there is NO working tertiary fallback.
- Evidence: 5-provider benchmark test on 2026-07-20 with AAPL, MSFT, TSLA, SNDL, NOK. Finnhub: 0/5 (key invalid). Stooq: 0/5 (HTTP 404). AKShare: stock_us_hist connection aborted, stock_us_spot downloads 893 stocks at ~1.8s each (impractical). TwelveData: 5/5 at 0.687s avg. yfinance: 5/5 at 0.469s avg.
- Mitigation: (1) Obtain a valid Finnhub API key. (2) Replace Stooq with a working free source (e.g. Polygon.io free tier, IEX Cloud). (3) Investigate if AKShare endpoints require proxy/VPN for Chinese servers. (4) Consider adding a third working fallback (e.g. AlphaVantage GLOBAL_QUOTE). (5) Short-term: set yfinance as primary, TwelveData as fallback in data_hub.py.
- Status: Active. High risk because only 2 providers work and both could fail (rate limits, network issues).

### INV-R23 - Test regression: test_forced_expert_committee fails [LOW]

- Classification: quality
- Risk: `test_auto_full_analysis.py::test_forced_expert_committee_materializes_weighted_consensus_before_submit` esta falhando no pytest. 1533 pass, 1 fail, 11 skip no estado atual.
- Evidence: pytest output 2026-07-20: 1 failed out of 1545 total tests.
- Mitigation: Investigar se falha e pre-existente ou causada por mudancas recentes no pipeline de experts.
- Status: Active. Isolado — nao afeta 1533 testes restantes.

---

## New Risks (2026-08-17 — Save Session)

### INV-R29 - akshare py_mini_racer V8 fatal exception derruba a suíte inteira [HIGH] → MITIGADO 2026-08-18

- Classification: test infrastructure / environment
- Risk: `tests/test_pipeline_smoke.py::test_pipeline_stream_events_blocks_unscoped_ticket_reference`
  (e o teste seguinte `test_pipeline_general_route_goes_to_ceo`) disparam o provider akshare
  (`akshare_provider.get_profile` → `stock_us_sina.get_us_stock_name` → `py_mini_racer`), que
  aborta o processo Python inteiro com `Windows fatal exception: code 0x80000003`. A suíte
  completa (1691 testes) trava no 84% e morre — nenhum resultado consolidado é produzido.
  Confirmado em PRODUÇÃO 2026-08-18: chat real derrubou o servidor live no nó `data`
  (auto_full_analysis → scan → akshare).
- Evidence: saída completa em `/tmp/iso_test.txt` (2026-08-17): crash no thread de
  `py_mini_racer._make_context` dentro de `akshare.stock.stock_us_sina`; dois runs da suíte
  completa abortaram no mesmo ponto (84%). Crash live em 2026-08-18 (17:26Z): servidor
  agent_server morto durante scan de mercado.
- Mitigation (aplicada): `get_us_stock_name()` agora roda isolado em subprocesso
  (`_us_stock_names_via_subprocess` em `src/data/akshare_provider.py`) — o crash fatal do
  V8 mata o filho, não o servidor; o DataHub cai para o próximo provider. 8 testes novos
  em `tests/test_akshare_provider.py` (sem rede, sem V8). Validação live: servidor
  sobreviveu a pipeline completo de scan (108 eventos) após o fix.
- Status: Mitigated. Circuito `data.akshare` permanece aberto (INV-R24); os 2 testes da
  suíte continuam deselect até revalidação.

### INV-R30 - SuperEzio API down (trading halt ativo) [HIGH]

- Classification: runtime availability
- Risk: o servidor SuperEzio (:8002/:8082) está fora do ar desde 2026-08-08. O alerta
  `man_at_work` ativou "NO TRADING ORDERS UNTIL CLEARED". Health check de 2026-08-17:
  porta 8002 e 8082 retornam conexão recusada (WinError 10061). Browser smoke reporta
  `ok: false`; e2e browser reporta resposta do Bob com 0 chars (gateway agora 100% local
  — ver INV-R26 — e servidor local :8080 fora do ar durante o teste).
- Evidence: `data/man_at_work/latest_alert.txt` (2026-08-08, WinError 10054);
  curl de 2026-08-17 (000 em ambas as portas); `scripts/browser_smoke.py` (ok:false);
  `tests/e2e/test_browser_full_flow.py` (bob_response_length: 0).
- Mitigation: subir o servidor local compartilhado :8080 (perfil cc) antes, depois
  `python -m agent_server.main` (INV-R14), e limpar o alerta man_at_work antes de
  qualquer ordem. Fail-safe de execução permanece congelado por design.
- Status: Active.

### INV-R31 - Pain log mostra erros crônicos repetidos há semanas [MEDIUM]

- Classification: operational health
- Risk: `bob_pain_log.jsonl` cresceu para 24.732 linhas; entradas de 2026-08-07/08-11
  repetem os mesmos órgãos: `ibkr_muscles` (IBKR offline), `scanner_eyes`
  ("No module named 'src'"), `cache_liver` (cache com 0 tickers), e
  `circuit_breakers_immune` com circuito `data.akshare` aberto.
- Evidence: `data/bob_pain_log.jsonl` e `src/data/bob_pain_log.jsonl` (dif 2026-08-17).
- Mitigation: tratar como dívida operacional — o loop "IBKR offline → scanner sem src → cache
  vazio" já era conhecido desde 2026-07-20 (mesmas strings). Priorizar correção do import
  `src` no scanner e reconexão IBKR após o CEO voltar.
- Status: Active.

### INV-R32 - Novo time de agentes market-* segue padrão externo (Anthropic FS) [INFO]

- Classification: arquitetura / provenance
- Risk: baixo. O trio `market-data-puller` / `market-thesis-writer` / `market-thesis-auditor`
  (2026-08-18) foi derivado dos templates oficiais `anthropics/financial-services`
  (data-puller → builder → auditor), estudados via leitura pública web — NENHUM clone/install
  (plugin marketplace = git fetch, bloqueado pela F51_NO_GITHUB_DISK_ONLY). Prompts foram
  re-escritos para o domínio SuperEzio (day-trading, zero-cloud, stop-and-surface).
- Evidence: `docs/architecture/AGENT_PATTERNS_ANTHROPIC_FS.md` (comparação prompt a prompt,
  citações verbatim e decisões copiar/melhorar/descartar).
- Mitigation: nenhum risco aberto. Nota: os agentes ainda não têm benchmark no `/agent-lab`
  (score pendente na pontuação 0-30 do Playbook).
- Status: Info — padrão adotado como referência oficial de arquitetura multiagente do projeto.

### INV-R33 - Quality probe 2026-08-18: defeitos de qualidade nas respostas do Bob [MEDIUM]

- Classification: qualidade de resposta / UX / dados
- Contexto: bateria `scripts/quality_probe.py` (5 prompts PT) contra o runtime zero-cloud
  após o fix do INV abaixo (api_key placeholder). 5/5 respostas com geração real, 0 fallbacks.
- Achados (ranqueados):
  1. **Latência**: rotas com scan levam 13-17 min (varredura sequencial de universo em
     providers com rate-limit; o modelo em si responde em 100-130 s).
  2. **Intent misrouting**: pergunta de risco e ticker inexistente (XYZ123) roteiam para
     `market_scan` — respondem outra pergunta com scan de 15 min.
  3. **Idioma inconsistente**: prompt PT gera resposta EN na rota general sem ticker
     (macro_thesis) e no template de scan EN (refusal_edge).
  4. **Vazamento de template interno**: "PIPELINE DATA:", "YOUR EXPLANATION:", dumps de
     módulos (## DATA, ## F51_VERDICT) chegam ao usuário final; typo "NEURAL_DECION"
     no próprio template.
  5. **Ticker↔nome desincronizados no scanner**: NGVC→"Alphabet Depositary Shares",
     KIDS→"Social Capital Hedosophia", KBR→"OrthoPediatrics" — nomes errados ao lado do
     ticker, potencialmente enganosos.
  6. Catalisador genérico boilerplate para todos os candidatos (não é catalisador real).
  - (Menor) `data/man_at_work/latest_alert.txt` stale de 2026-08-08 não é limpo quando o
    CEO volta; mojibake no template de falha.
- Evidence: `runtime/quality_probe/report_20260818_113401.md` (pós-fix) e
  `report_20260818_112116.md` (pré-fix, 3/5 em template de falha).
- Mitigation proposta: cache/pré-aquecimento de universo no scanner; detectores de intent
  para "pergunta conceitual" vs "scan"; template de resposta por camada (interno vs user-
  facing); validar join ticker→nome no data hub.
- Status: Open — nenhum item bloqueia entrega v3 (sistema operacional), mas 1-3 degradam a
  experiência e devem entrar no backlog.

### INV-R34 - Client OpenAI recusava chamada local sem api_key (zero-cloud) [HIGH → Resolved]

- Classification: bug de integração / zero-cloud
- Risk: TODO o tráfego LLM morria ANTES do HTTP: providers locais construídos com
  `api_key=""` fazem o client OpenAI levantar "Missing credentials" — sintomas: circuits
  `deepseek`/`daytrade_judge` abrindo, 3/5 prompts em template de falha, RewardGate em
  fallback heurístico. O llama-server estava saudável o tempo todo.
- Fix: `LOCAL_API_KEY_PLACEHOLDER` em `providers.py` (commit 38ea6e6) — não é credencial,
  nunca sai da máquina (llama-server ignora). Mesma bateria pós-fix: 5/5 geração real.
- Evidence: commit 38ea6e6; regressões `test_local_providers_carry_nonempty_api_key` e
  `test_health_details_probes_port_from_url` (porta do probe de saúde vinha hardcoded 8082).
- Status: Resolved 2026-08-18.
### INV-R35 - TD commission-free research is not execution-ready [CRITICAL]

- Classification: live trading / broker terms / data provenance.
- Risk: TD publishes a changeable commission-free ETF list, but SuperEzio has no official TD
  order API or trusted TD quote/account feed. Caller-supplied prices and self-declared risk
  cannot authorize real money.
- Evidence: `config/td_direct_commission_free_etfs.json`,
  `src/core/trading/td_direct_ticket.py`, and the official TD source linked in the manifest.
- Mitigation: dated 7-day fail-closed list; research-only GET; authenticated local draft returns
  `ok=false` and `ready_for_execution=false`; no TD credentials, scraping, or transmission.
- Status: Active — real-money go-live blocked pending server-side provenance, Money Gate,
  portfolio/buying-power gates, durable approval, and TD preview confirmation.

### INV-R36 - V1 Windows ainda nao e transferivel [CRITICAL]

- Classification: product delivery / reproducibility.
- Risk: instaladores e launchers divergentes usam dependencias sem lock, caminhos ou portas
  historicas e fluxos de start incompletos. Nao existe pacote limpo com manifest, checksum e
  ensaio em uma maquina Windows sem o ambiente do desenvolvedor.
- Evidence: `setup_superezio.bat`, `start_all.bat`, `config.ps1`, `start.ps1`, `stop.ps1` e
  ausencia de artefato de distribuicao versionado.
- Mitigation: um unico bootstrap relativo ao diretorio do produto, instalacao pelo lock,
  start/stop com identidade de processo, ZIP allowlisted, checksum e ensaio em VM limpa.
- Status: Active — bloqueia release V1.

### INV-R37 - Contrato de autenticacao esta dividido [HIGH]

- Classification: security / onboarding.
- Risk: o setup continha credencial administrativa conhecida; frontend e backend misturam
  JWT Bearer, `X-API-Key` e modos anonimos. O operador pode receber uma tela de login que nao
  consegue atravessar o proprio middleware ou uma rota financeira pode falhar aberta.
- Evidence: `setup_superezio.bat`, `scripts/seed_admin.py`, `frontend/auth.js`,
  `frontend/api.js` e middleware de `src/agent_server/main.py`.
- Mitigation: remover toda senha padrao, definir uma unica fronteira de autenticacao,
  documentar bootstrap do primeiro usuario e testar login -> rota protegida -> logout.
- Status: Active — bloqueia release V1 e qualquer uso financeiro.

### INV-R38 - Fontes de verdade de entrega divergem [HIGH -> RESOLVED 2026-08-20]

- Classification: contracts / operational truth.
- Risk: inventario, contratos, board, launchers e docs registram portas, modelos e estado de
  conclusao diferentes. O quality probe tambem pode terminar com codigo zero apesar de
  resposta vazia ou degradada, permitindo um falso PASS de release.
- Evidence: `.f51/INVENTORY.json`, `.f51/CONTRACTS.json`, `.f51/TASK_BOARD.md`,
  `docs/AGENT_OPERATING_SYSTEM.md` e `scripts/quality_probe.py`.
- Resolution: recon independente, runtime/config/testes e documentação foram corrigidos em
  ownerships separados. A fonte executável é `config/runtime.yml` mais `config.ps1`; o
  manifesto e o runbook espelham esse contrato. Entrypoints inseguros foram aposentados
  fail-closed. Gate final: Ruff PASS, 22 agentes/32 skills PASS, `1883 passed, 10 skipped`,
  browser smoke real PASS e análise AAPL real sem fallback, overflow ou chamada cloud.
- Residual validation limit: `docker compose config --quiet` passou, mas o build/boot da
  imagem Docker não foi ensaiado porque o daemon Docker Desktop estava indisponível. Isso
  limita a evidência Docker, não reabre o drift das fontes ativas.
- Status: Resolved 2026-08-20.

### INV-R39 - Novos agentes de entrega ainda nao foram benchmarkados [MEDIUM]

- Classification: agent quality / governance.
- Risk: prompts estruturalmente validos podem produzir planos vagos, edicoes fora de escopo
  ou autoaprovacao. O gate atual prova referencias e separacao de poder, nao eficacia real.
- Evidence: `.claude/agents/product-delivery-orchestrator.md`,
  `.claude/agents/product-implementer.md`, `.claude/agents/ai-eval-verifier.md`,
  `.claude/agents/reliability-sre-operator.md` e
  `.claude/agents/release-readiness-manager.md`.
- Mitigation: executar `/agent-lab` com tarefas identicas, score minimo >20/30 e zero
  violacoes criticas antes de promover os novos papeis como confiaveis.
- Status: Active — nao bloqueia corrigir o produto; bloqueia alegar que o exército e o melhor.

### INV-R41 - Modelo local (GGUF) ausente no disco [FALSO POSITIVO DA AUDITORIA -> RESOLVIDO 2026-08-21]

- Classification: runtime / zero-cloud integrity.
- Risk registrado: `models/` do projeto contem apenas README e o CEO local seria
  fail-closed por ausencia de arquivo. O auditor adversarial olhou apenas `models/`
  (projeto) e `C:\llama.cpp\models`, e concluiu "o modelo nao existe em lugar nenhum".
- CORRECAO (2026-08-21, verificacao direta): os arquivos SEMPRE estiveram presentes em
  `C:\Users\marco\models\qwen3.8-27b\` — caminho que o `config.ps1` ja sondava:
  Q4_K_M 15.9GB (14/08), UD-IQ2_XXS 8.4GB (15/08), UD-IQ3_XXS 11.1GB (15/08),
  mmproj-BF16 0.9GB (14/08). O binario `llama-server.exe` tambem existe em
  `C:\Users\marco\tools\llama.cpp\` (build 10435). A :8080 offline decorre da pausa
  MAN_AT_WORK do operador, nao de arquivo faltante.
- Licao registrada: auditorias precisam checar TODOS os caminhos que o config sonda
  (`%USERPROFILE%\models\...`), nao apenas o dir do projeto.
- Resolution: manifest/README/checkpoint corrigidos para o estado real (commit deste
  registro). O launch com UD-IQ2_XXS (8.4GB, single GPU 3060) e viavel sem offload.
- Status: Resolved 2026-08-21 (falso positivo da auditoria).

### INV-R42 - GPU secundaria (RTX 2070) em estado de falha Code 31 [HIGH -> CONFIG RESOLVED; HARDWARE PENDENTE]

- Classification: runtime / configuration truth.
- Risk: manifest, providers.py e launch scripts assumiam 2 GPUs funcionais (`-ts 12,8`);
  na realidade a RTX 2070 8GB EXISTE fisicamente mas esta em estado Error (Code 31,
  CM_PROB_FAILED_ADD) e nao aparece no `nvidia-smi -L` — o launch perfil 2-GPU
  falharia ou degradaria.
- Evidence: `Get-PnpDevice -Class Display` (RTX 2070: Status Error; RTX 3060: OK;
  P106-100: Unknown), drivers OEM divergentes por placa (3060: oem18.inf 560.94
  Ago/2024; 2070: oem13.inf 581.80 Out/2025) — causa classica de Code 31.
- Resolution (config): tensor split 12, gpus "RTX 3060 12GB", comentarios e README
  alinhados. Commit a653c5e; testes de contrato 103 passed, 1 skipped.
- Repair path (operador): instalar UM unico pacote de driver NVIDIA (DDU em modo
  seguro + driver mais recente) para 3060 + 2070 compartilharem o mesmo driver;
  remover/ignorar a P106-100 se estiver fora de uso. Com a 2070 OK, o total de
  VRAM sobe para 20GB e o perfil original Q4_K_M/-ts 12,8 volta a valer.
- Status: Config Resolved 2026-08-21; reparo de hardware pendente do operador.

### INV-R43 - Fraud guard morto: 15 regras, 0 computaveis [HIGH -> RESOLVED 2026-08-21]

- Classification: financial safety / pump-and-dump defense.
- Risk: `red_flag_rules.json` (R001-R015) nao tinha flag computable e os dois motores
  implementam outros 6 ids; resultado medido: 0 regras montadas e confidence 0.0.
- Evidence: `data/fraud_patterns/red_flag_rules.json`, `src/core/investor/fraud_analyst.py`,
  `src/core/f51_adapter/adapter.py`.
- Resolution: dataset v3.0 marca as 15 regras provider-gated como `computable: false` com
  `limitation_when_absent`, e adiciona as 6 regras computaveis com pesos, evidence templates
  e matched_patterns. Regressao pinned em `tests/test_fraud_guard_live.py` (7 testes).
  Commit 1d4313e.
- Status: Resolved 2026-08-21.

### INV-R44 - Evidencia de cobertura autodestrutiva [HIGH -> RESOLVED 2026-08-21]

- Classification: evidence integrity / test infra.
- Risk: `--cov=src` nos addopts fazia qualquer pytest (ate collect-only) sobrescrever o
  `.coverage`; 67% identico em dois runs distintos sugere metrica copiada; commit 4f183e1
  editou a mao apenas o tempo do run (545.20s -> 574.93s) sem log do artefato.
- Resolution: `--cov` removido dos addopts (comando explicito documentado no pytest.ini);
  relatorio duravel salvo em `runtime/checkpoints/` a cada run final completo.
  Commit 9ee8dca.
- Residual: limpeza das ~14 mil linhas de teste no DB de traces pendente de decisao do
  operador (ver INV-R47).
- Status: Resolved 2026-08-21 (procedimento), com residual de dados historicos.

### INV-R45 - Drift triplo de constantes de risco (0.5% vs 2% vs "1-2%") [MEDIUM -> RESOLVED 2026-08-21]

- Classification: risk governance / documentation.
- Risk: relatorios confundiam o default do Money Gate (0.5%, teto le=2) com o default do
  PositionSizer (2%) e a faixa "1-2%" do docstring.
- Resolution: `src/core/config/settings.py` declarado como fonte unica de verdade do gate;
  docstring do PositionSizer distingue o knob pre-gate. Sem mudanca de comportamento.
  Commit 6d124ee.
- Status: Resolved 2026-08-21.

### INV-R46 - Playbook/allocator recomendavam ETFs fora do universo de 108 [MEDIUM -> RESOLVED 2026-08-21]

- Classification: product accuracy / cost drag.
- Risk: o playbook sugeria XEQT/XIC/XEF/ZSP (com corretagem) como "sem comissao", e o
  allocator recomendava candidatos nao verificados.
- Resolution: playbook usa somente simbolos do universo real (VEQT/VGRO/VBAL/VCNS, VFV/VSP,
  VCN/VCE, VIU/VXC); allocator descarta candidatos nao verificados (fail-closed), com
  flag explicita apenas para o bucket tatico (nao-ETF). Testes novos em
  `tests/test_investor_portfolio_allocator.py` (8 passed). Commit 8f5e1cf.
- Status: Resolved 2026-08-21.

### INV-R47 - DB decision_traces poluido por runs de teste [MEDIUM -> MITIGATED 2026-08-21]

- Classification: operational data integrity.
- Risk: ~14 mil linhas de run_ids de teste (auto-full-analysis-test, node1/node2,
  test_node, contract_test...) no `runtime/investor.db`; 88.4% das latencias 0.0ms.
- Resolution: `is_synthetic_run_id()` em `src/core/audit/decision_trace.py` impede novos
  writes sinteticos no ledger (defense in depth alem do redirect do conftest). Regressao em
  `tests/test_decision_trace_guard.py`. Commit 4ec5127.
- Residual: limpeza das linhas historicas pendente de aprovacao do operador (dados reais).
- Status: Mitigated 2026-08-21; residual Active ate limpeza aprovada.

### INV-R48 - Candles time=0 colapsavam charts [CRITICAL 2026-08-20 -> RESOLVED 2026-08-21]

- Classification: chart data / usability.
- Risk: checkpoint de 20/08 registrava todo candle com time=0, tornando o chart inutil.
- Verification: servidor vivo :8002 (MAN_AT_WORK) consultado hoje: 0/126 candles e 0/46
  sma20 com time=0; provider entrega ISO-8601 e `_parse_candle_time` converte para epoch.
- Resolution: regressao pinned em `tests/test_chart_data_times.py` (endpoint + builder).
  Commit 51447b5.
- Status: Resolved 2026-08-21.

### INV-R49 - RISK_REGISTER fora de gate na entrega investor [LOW -> RESOLVED 2026-08-21]

- Classification: process compliance / definicao de pronto.
- Risk: a entrega playbook/allocator (2026-08-21 09:34) nao registrou risco novo, violando
  a definicao de pronto do projeto.
- Resolution: este update registra R41-R49 e o TASK_BOARD recebeu a entrada de hoje.
- Status: Resolved 2026-08-21.
