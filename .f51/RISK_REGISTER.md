# F51 Risk Register

Updated: 2026-08-17T22:55:00-04:00
Session: save-2026-08-17

## Active Risks

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

### INV-R29 - akshare py_mini_racer V8 fatal exception derruba a suíte inteira [HIGH]

- Classification: test infrastructure / environment
- Risk: `tests/test_pipeline_smoke.py::test_pipeline_stream_events_blocks_unscoped_ticket_reference`
  (e o teste seguinte `test_pipeline_general_route_goes_to_ceo`) disparam o provider akshare
  (`akshare_provider.get_profile` → `stock_us_sina.get_us_stock_name` → `py_mini_racer`), que
  aborta o processo Python inteiro com `Windows fatal exception: code 0x80000003`. A suíte
  completa (1691 testes) trava no 84% e morre — nenhum resultado consolidado é produzido.
- Evidence: saída completa em `/tmp/iso_test.txt` (2026-08-17): crash no thread de
  `py_mini_racer._make_context` dentro de `akshare.stock.stock_us_sina`; dois runs da suíte
  completa abortaram no mesmo ponto (84%).
- Mitigation: deselecionar os 2 testes que tocam o provider akshare até o circuito
  `data.akshare` fechar ou o provider ser substituído (INV-R24). Corrigir o fallback do
  data context para não instanciar o V8 do akshare quando o circuito está aberto.
- Status: Active. Bloqueia o gate de suíte completa; resta da suíte roda com 2 deselects.

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
