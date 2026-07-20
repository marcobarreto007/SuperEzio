# SuperEzio — Catálogo de Código Legado

Gerado em: 2026-07-19
Propósito: Catalogar código deprecated, padrões obsoletos, e artefatos mortos sem deletar nada.
Ações possíveis: APAGAR | ATUALIZAR | MANTER

---

## 1. MARCADORES DE DEPRECIAÇÃO

### 1.1 Marcadores explícitos "deprecated" / "legacy"

| Arquivo | Trecho | Último toque (git log) | Ação |
|---------|--------|------------------------|------|
| `src/core/audit/decision_logger.py:12` | `"""Small audit-log facade used by gateway and legacy contracts."""` | 0cb3bf8 (2026-06) | MANTER — shim de compatibilidade usado por contratos legados |
| `src/core/pipeline/nodes/collect_experts.py:1` | `"""Compatibility shim for the legacy collect_experts node path."""` | b365216 (2026-06) | MANTER — shim de compatibilidade, redireciona para experts.py |
| `src/core/trading/neural_rl.py` | Classe NeuralPolicy que só retorna WAIT; `# legacy neural_rl updates are retired` | aee4a1c (2026-07-14) | MANTER — compatibilidade: impede caller de reativar random policy |
| `src/core/trading/adaptive_agent.py:191-194` | `"""Reject the legacy outcome API because it lacks immutable provenance."""` + RuntimeError | Recente (2026-07) | MANTER — proteção: impede chamada de API legada |
| `src/core/pipeline/prompts/builder.py:575` | `f"score_type={f51.get('score_type', 'legacy_unknown')}"` | wave4 (2026-07) | ATUALIZAR — fallback 'legacy_unknown' deveria ser 'unknown' ou None |
| `src/data/wolfram_provider.py:198` | `"""Range-check legacy F51 numerical scores without implying calibration."""` | aa0ce8d (2025) | MANTER — função de verificação ainda usada |
| `src/core/pipeline/contracts.py:73` | `portfolio_context: str  # legacy alias, populated by graph.py IBKR probe` | wave4 (2026-07) | MANTER — alias legado ainda populado por graph.py |
| `src/core/trading/dynamic_watchlist.py:204` | `logger.warning("universe_builder not available, falling back to legacy")` | Recente (2026-07) | ATUALIZAR — o fallback legacy não é especificado: qual é? |

### 1.2 TODO / FIXME / HACK (apenas em src/)

| Arquivo | Tipo | Último toque | Ação |
|---------|------|---------------|------|
| `src/core/data_collector/collector.py:165` | Comentário "TODOS" (português = "all") | FALSO POSITIVO | MANTER — é português, não marcador |
| `src/core/pipeline/intents.py:539` | String literal "TODO" | wave4 (2026-07) | MANTER — parte de enum/constante |
| `src/core/pipeline/nodes/agent.py:765` | String literal "TODOS" | wave4 (2026-07) | MANTER — português |
| `src/core/pipeline/f51_trade_gate.py:86` | String literal "TODOS" | wave4 (2026-07) | MANTER — português |
| `src/core/trading/auto_executor.py:11` | Comentário "TODOS" | wave4 (2026-07) | MANTER — português |
| `src/core/pipeline/nodes/auto_execute_paper.py:396` | Comentário sobre padrão 'TICKER XXXX:' | wave4 (2026-07) | MANTER — documentação |
| `src/core/pipeline/nodes/auto_execute_paper.py` | 1 `XXX` (9 chamadas de ferramenta) | recente | ATUALIZAR — investigar se XXX é marcador |

**Conclusão 1.2:** Não há marcadores HACK/WORKAROUND/XXX críticos no src/. Os TODOs em português são strings literais, não marcadores de débito técnico. Score: limpo.

---

## 2. APIS ANTIGAS / PADRÕES OBSOLETOS

### 2.1 `from __future__ import annotations` — 163 arquivos usam

Isto é um padrão **intencional** no projeto (Python 3.11+ com avaliação lazy de anotações). NÃO é legado. Todas as datas destes imports são da criação do arquivo.

**Ação: MANTER** — padrão correto para o target py311 do projeto.

### 2.2 `from typing import` — arquivos SEM `from __future__ import annotations`

Estes 22 arquivos pagam custo runtime para avaliar anotações. Prioridade ALTA para ATUALIZAR.

| Arquivo | Imports | Risco | Último toque |
|---------|---------|-------|---------------|
| `src/core/observability/event_hub.py` | `Callable, Awaitable, Dict, Any, List, Optional` | ALTO — Optional[Queue], Optional[EventHub] | wave4 (2026-07) |
| `src/core/observability/neural_log.py` | `Dict, Any, Optional` | ALTO — 5 assinaturas com Optional | wave4 (2026-07) |
| `src/core/rag/macro_dataset.py` | `List, Dict, Any, Optional` | MÉDIO — Optional[pd.DataFrame] | wave4 (2026-07) |
| `src/core/ports/protocol.py` | `Any, Dict, List, Optional` | MÉDIO — A2A message fields | Recente |
| `src/experts/crisis/contracts/schemas.py` | `Any, Literal, Optional` | ALTO — 15+ campos Pydantic | wave4 (2026-07) |
| `src/data/twelve_data.py` | `Dict, Any` | BAIXO — 2 usos | aa0ce8d (2025) |
| `src/data/alpha_vantage.py` | `Dict, Any` | BAIXO — 2 usos | aa0ce8d (2025) |
| `src/core/data_collector/scraper.py` | `Dict, Any` | BAIXO — 1 uso | aa0ce8d (2025) |
| `src/core/scanner/__init__.py` | `Dict, List` | BAIXO — type alias | aa0ce8d (2025) |
| `src/experts/crisis/expert/crisis_expert.py` | `List` | BAIXO | aa0ce8d (2025) |
| `src/experts/technical_neural/pipeline_hook.py` | `Dict, Any` | BAIXO | Recente |

**Ação: ATUALIZAR** — adicionar `from __future__ import annotations` e/ou trocar `Optional[X]` por `X | None`, `Dict` por `dict`, `List` por `list`.

### 2.3 `Optional[X]` ainda no código-fonte

15 arquivos usam `Optional[X]`. 11 deles já têm `from __future__ import annotations` (cosmético). 5 não têm (p. 2.2 acima — prioridade).

| Arquivo (com `__future__`) | Uso | Pode trocar para `X \| None`? |
|---|---|---|
| `src/core/config/secrets.py:42` | `_PROJECT_ROOT: Optional[Path] = None` | Sim — `Path \| None` |
| `src/data/data_hub.py:350` | `def get_provider(...) -> Optional[Any]` | Sim — `Any \| None` |
| `src/data/news_feed.py:392` | `self.brave_key: Optional[str]` | Sim — `str \| None` |
| `src/data/news_feed.py:393` | `self.newsapi_key: Optional[str]` | Sim — `str \| None` |
| `src/experts/pennylab/schemas.py` | 12+ campos `Optional[float/int]` | Sim — `float \| None` |
| `src/experts/pennylab/data_provider.py` | 5+ assinaturas `Optional[...]` | Sim |
| `src/core/investor/storage.py` | 4+ usos `Optional` | Sim |
| `src/core/pipeline/security.py` | 3 usos `Optional` | Sim (sem `__future__`) |
| `src/experts/crisis/contracts/schemas.py` | 15+ usos `Optional` | Sim (sem `__future__`) |

**Ação: ATUALIZAR** — 15 arquivos, baixo risco, mudança cosmética.

### 2.4 `Union[X, Y]` — ZERO ocorrências

**Conclusão:** Projeto já não usa `Union`. Limpo.

### 2.5 `List[X]` / `Dict[K,V]` / `Tuple` de typing em vez de builtins

19 arquivos importam `List`, `Dict`, ou `Tuple` de `typing`. Com Python 3.9+ (projeto usa 3.11), `list`, `dict`, `tuple` builtins funcionam em anotações.

**Ação: ATUALIZAR** — usar builtins (`list[X]` em vez de `List[X]`), especialmente nos 163 arquivos com `from __future__ import annotations` onde já é seguro.

---

## 3. ADAPTERS / BROKERS / DATA PROVIDERS — MORTO VS VIVO

### 3.1 Brokers

| Broker | Status | Evidência | Ação |
|--------|--------|-----------|------|
| **Alpaca** (`alpaca-py`) | VIVO mas subutilizado | `AlpacaPaperAdapter` em `broker.py`; importado em `__init__.py`; config em settings.py | MANTER — code complete, mas sem uso ativo em pipeline |
| **Interactive Brokers** (`ib_insync`) | VIVO | `ibkr_adapter.py`, `ibkr_service.py`, `ibkr_order_worker.py` — importados de 8+ lugares | MANTER — uso ativo |
| **Robinhood** | MORTO | Zero referências em código fonte (só menção em docs) | MANTER — sem código para apagar |
| **Questrade** | MORTO | `scripts/questrade_order_assist.py` não é importado de src/ | MANTER — script standalone assistivo |

### 3.2 Data Providers Registrados no DataHub

Provider registrado em `data_hub.py` e **ativo** (importado por route):

| Provider | Capacidades | Status | Ação |
|----------|-------------|--------|------|
| finnhub | price, quote, profile, fundamentals, catalyst, candles, news | ATIVO — prioridade 1 | MANTER |
| twelve_data | price, candles | ATIVO — fallback prio 12 | MANTER |
| yfinance | price, candles, profile | ATIVO — fallback prio 30 | MANTER |
| alpha_vantage | treasury | ATIVO — prio 25 | MANTER |
| stooq | price | ATIVO — keyless emergency prio 45 | MANTER |
| news_scout | news, sentiment | ATIVO — prio 22 | MANTER |
| reddit_pulse | reddit, social_sentiment | ATIVO — prio 20 | MANTER |
| boc_macro | macro, macro_ca | ATIVO — prio 20 | MANTER |
| fed_macro | macro, macro_us | ATIVO — prio 30 | MANTER |
| newsapi | news, sentiment, market_sentiment | ATIVO — prio 15 | MANTER |
| wolfram | quantitative, math_verify | ATIVO — prio 30 | MANTER |

### 3.3 Providers NÃO registrados no DataHub (arquivos órfãos)

| Arquivo | Classe | Último toque | Está sendo usado? | Ação |
|---------|--------|--------------|-------------------|------|
| `src/data/alpha_vantage.py` | `AlphaVantageProvider` | 2025-12 (aa0ce8d) | SIM — registrado no hub (treasury) | MANTER |
| `src/data/twelve_data.py` | `TwelveDataProvider` | 2025-12 (aa0ce8d) | SIM — registrado no hub (price/candles) | MANTER |
| `src/data/boc_provider.py` | `get_macro_summary_ca` | 2025-12 (aa0ce8d) | SIM — registrado no hub | MANTER |
| `src/data/fed_provider.py` | `get_macro_summary_us` | 2025-12 (aa0ce8d) | SIM — registrado no hub | MANTER |
| `src/data/wolfram_provider.py` | `WolframProvider` | 2026-07-19 | SIM — registrado no hub | MANTER |
| `src/data/reddit_provider.py` | `RedditPulse` | 2025-12 | SIM — registrado no hub | MANTER |
| `src/data/newsapi_provider.py` | `NewsAPIProvider` | 2025-12 | SIM — registrado no hub | MANTER |
| `src/data/news_feed.py` | `NewsScout` | 2025-12 | SIM — registrado no hub | MANTER |
| `src/data/stooq_provider.py` | `StooqProvider` | 2025-12 | SIM — registrado no hub | MANTER |
| `src/data/finnhub_provider.py` | `FinnhubProvider` | 2025-12 | SIM — registrado no hub (primary) | MANTER |
| `src/data/finnhub_symbols.py` | Symbol resolver | 2025-12 | SIM — importado por finnhub_provider | MANTER |
| `src/data/yfinance_provider.py` | `YFinanceProvider` | 2025-12 | SIM — registrado no hub | MANTER |

**Nenhum data provider está morto.** Todos os 12 arquivos em `src/data/` são referenciados pelo DataHub.

### 3.4 FRED / BOC — Status

Ambos estão **vivos**:
- **BOC**: `boc_provider.py` → registrado como `boc_macro` no DataHub → usado em pipeline macro
- **FRED (Fed)**: `fed_provider.py` → registrado como `fed_macro` no DataHub → usado em pipeline macro

### 3.5 Wolfram — Status

VIVO. `wolfram_provider.py` → registrado como `wolfram` no DataHub → endpoint `run_math_verify()` no hub.

### 3.6 Finnhub — Status

VIVO. Provider primário de market data (prioridade 1). `finnhub_provider.py` + `finnhub_symbols.py`.

### 3.7 Dead Adapter Import (BUG)

`src/core/trading/trading_engine_live.py:148`:
```python
from adapters.market.market_data_provider import get_market_data_provider
```
O diretório `src/adapters/market/` **não existe**. O import está dentro de try/except ImportError então falha silenciosamente. É um caminho de código morto.

**Ação: ATUALIZAR** — remover import morto ou criar o adapter.

---

## 4. SCRIPTS ONE-OFF / EXPERIMENTAIS

### 4.1 Scripts de Treinamento (11 arquivos — todos one-off experimentais)

| Script | Linhas | Último toque | Propósito | Ação |
|--------|--------|--------------|-----------|------|
| `scripts/train_qwenlong_30b_f51.py` | 92 | 2026-06-29 | Treino LoRA QwenLong v1 | APAGAR (se não for reutilizar) |
| `scripts/train_qwenlong_30b_f51_cpu.py` | 80 | 2026-06-29 | Treino CPU v1 | APAGAR |
| `scripts/train_qwenlong_30b_f51_v2.py` | 109 | 2026-06-29 | Treino v2 | APAGAR |
| `scripts/train_qwenlong_30b_f51_v3.py` | 146 | 2026-06-29 | Treino v3 | APAGAR |
| `scripts/train_qwenlong_30b_f51_v4.py` | 98 | 2026-06-29 | Treino v4 | APAGAR |
| `scripts/train_qwenlong_30b_gguf_f51.py` | 118 | 2026-06-29 | Treino GGUF v1 | APAGAR |
| `scripts/train_qwenlong_30b_gguf_f51_v5.py` | 149 | 2026-06-29 | Treino GGUF v5 | APAGAR |
| `scripts/train_qwenlong_30b_gguf_f51_v6.py` | 170 | 2026-06-29 | Treino GGUF v6 | APAGAR |
| `scripts/train_qwenlong_30b_gguf_f51_v7.py` | 209 | 2026-06-29 | Treino GGUF v7 | APAGAR |
| `scripts/train_qwenlong_30b_gguf_f51_v9_smoke.py` | 353 | 2026-06-29 | Treino GGUF v9 smoke test | APAGAR |
| `scripts/train_lora_llama_cpp.py` | 84 | 2026-06-28 | Treino LoRA llama.cpp | APAGAR |
| `scripts/merge_gguf.py` | ? | antigo | Merge de GGUF | APAGAR |
| `scripts/quick_lora_train.py` | ? | antigo | Quick LoRA train | APAGAR |

### 4.2 Scripts de Benchmark/Stress (one-off)

| Script | Propósito | Ação |
|--------|-----------|------|
| `scripts/bench_1M_nitro.ps1` | Benchmark Nitro 1M tokens | APAGAR |
| `scripts/bench_nitro_moe.ps1` | Benchmark MoE | APAGAR |
| `scripts/stress_test_25.py` | Stress test 25 requests | APAGAR |
| `scripts/stress_test_50.py` | Stress test 50 requests | APAGAR |

### 4.3 Scripts de Geração de Dataset (one-off)

| Script | Propósito | Ação |
|--------|-----------|------|
| `scripts/_gen.py` | Geração de dataset (underscore = privado) | APAGAR |
| `scripts/gen_bob_autonomy.py` | Gerar dataset autonomia Bob | APAGAR |
| `scripts/gen_bob_identity.py` | Gerar dataset identidade Bob | APAGAR |
| `scripts/gen_bob_intent.py` | Gerar dataset intenção Bob | APAGAR |
| `scripts/gen_bob_pipeline.py` | Gerar dataset pipeline Bob | APAGAR |
| `scripts/gen_fraud_rag.py` | Gerar dataset fraude RAG | APAGAR |
| `scripts/build_bob_memory.py` | Build memória Bob | APAGAR |
| `scripts/inject_bob_memory.py` | Injetar memória Bob | APAGAR |

### 4.4 Scripts de Broker/Ordem Assistiva (standalone)

| Script | Propósito | Ação |
|--------|-----------|------|
| `scripts/questrade_order_assist.py` | Assistente Questrade (Playwright) | MANTER — ferramenta operacional |
| `scripts/broker_readiness_probe.py` | Sonda de conectividade broker | MANTER — usado em check.ps1 |
| `scripts/_ibkr_order.py` | Ordem IBKR via subprocess | MANTER — usado por ibkr_adapter |
| `scripts/_ibkr_position_check.py` | Check posição IBKR | MANTER — operacional |

### 4.5 Outros Scripts One-off

| Script | Propósito | Ação |
|--------|-----------|------|
| `scripts/cloud_train.sh` | Treino em cloud (Linux) | APAGAR |
| `scripts/estimate_2b_training.py` | Estimar treino 2B params | APAGAR |
| `scripts/build_moe_fix.ps1` | Build fix MoE | APAGAR |
| `scripts/check_vast_5090.py` | Check servidor vast.ai RTX 5090 | APAGAR |
| `scripts/rag_ingest_paper.py` | RAG ingest de paper | APAGAR |
| `scripts/train_lora_bob.ps1` | Treino LoRA Bob (PowerShell) | APAGAR |
| `scripts/train_qwenlong_30b_gguf_f51.ps1` | Treino GGUF PS1 | APAGAR |
| `scripts/run_learning_cycle.py` | Ciclo de aprendizado experimental | APAGAR |
| `scripts/populate_small_caps.py` | Popular small caps watchlist | APAGAR (one-off) |
| `scripts/populate_watchlist.py` | Popular watchlist | APAGAR (one-off) |

### 4.6 Scripts de Produção (MANTER)

| Script | Propósito |
|--------|-----------|
| `scripts/browser_smoke.py` | Smoke test Playwright (mandatório por CLAUDE.md) |
| `scripts/serve_agent_llamacpp.ps1` | Serve llama.cpp (referenciado em runtime.yml) |
| `scripts/backup.ps1` | Backup |
| `scripts/backup_databases.py` | Backup databases |
| `scripts/debut_report.py` | Relatório de debut |
| `scripts/paper_journal_cli.py` | CLI do paper journal |
| `scripts/trace_viewer.py` | Visualizador de traces |
| `scripts/f51_lab_inventory.cmd` | Inventário F51 lab |
| `scripts/f51_storage_scan.cmd` | Scan storage F51 |
| `scripts/verify_zero_garbage_runtime.ps1` | Verificação runtime |
| `scripts/journal_review.py` | Revisão de journal |
| `scripts/bob_watchdog.py` | Watchdog Bob |
| `scripts/qwen_proxy.py` + `qwen_proxy_launcher.py` | Proxy Qwen |
| `scripts/eval_pipeline.py` | Avaliação de pipeline |
| `scripts/invest_api_qa.py` / `invest_qa.py` / `investment_answer_quality.py` | QA de investimento |
| `scripts/grafana_cli.py` | CLI Grafana |
| `scripts/ci_smoke_test.py` | CI smoke test |
| `scripts/nitro_expert_packer.py` | Nitro expert packer |
| `scripts/smoke_datahub_price.py` | Smoke test DataHub price |
| `scripts/smoke_twelve_data.py` | Smoke test Twelve Data |
| `scripts/nitro_scheduler_brainstorm.py` | Brainstorm scheduler Nitro |
| `scripts/f51_lab_bench_README.md` | Doc do lab bench |

---

## 5. ARQUIVOS DE CONFIG PARA FERRAMENTAS NÃO USADAS

### 5.1 `.cfg` — Nenhum arquivo .cfg encontrado

### 5.2 `.ini` — Apenas `pytest.ini` (config de teste, em uso)

### 5.3 `.toml`

| Arquivo | Status | Ação |
|---------|--------|------|
| `pyproject.toml` | ATIVO — fonte de verdade de dependências | MANTER |
| `.codex/agents/recon-researcher.toml` | Codex agent config | MANTER |

### 5.4 `.yaml`

| Arquivo | Status | Ação |
|---------|--------|------|
| `.pre-commit-config.yaml` | Pre-commit hooks config | ATUALIZAR — verificar se pre-commit está em uso |

### 5.5 `config/` directory

| Arquivo | Status | Ação |
|---------|--------|------|
| `config/mandamentos.json` | JSON de mandamentos | MANTER |
| `config/mission_context.json` | Contexto de missão | MANTER |
| `config/model_manifest.json` | Manifesto de modelos | MANTER |
| `config/runtime.yml` | Config runtime (comentário sobre contradição INV-R15) | ATUALIZAR — tem contradição documentada com ENTRYPOINT_MAP.md |

### 5.6 GitHub Workflows

`ci.yml` — **já desativado** conforme F51 Disk Only Policy. Branches setados para `[never]`. Ação: MANTER (já está correto).

---

## 6. DEPENDÊNCIAS MORTAS

### 6.1 Em `pyproject.toml` mas NUNCA importadas

| Dependência | Evidência | Ação |
|-------------|-----------|------|
| `llama-cpp-python>=0.3.23` | `import llama_cpp` não encontrado em src/ (import lazy via gateway talvez) | INVESTIGAR — pode ser import lazy em model_serving/ |
| `bandit>=1.8` | CLI-only, nunca importado | MANTER (dev dep CLI) |
| `vulture>=2.11` | CLI-only, mencionado em skill | MANTER (dev dep CLI) |
| `deptry>=0.20` | CLI-only, mencionado em skill | MANTER (dev dep CLI) |

### 6.2 Em `requirements.txt` mas NÃO em `pyproject.toml` (drifted)

| Dependência | Em código? | Ação |
|-------------|-----------|------|
| `aiohttp>=3.9` | NÃO importado em src/ | APAGAR de requirements.txt (ou adicionar ao pyproject.toml) |
| `statsmodels>=0.14` | NÃO importado em src/ | APAGAR |
| `pandas-ta>=0.3` | NÃO importado em src/ | APAGAR |
| `joblib>=1.3` | NÃO importado em src/ | APAGAR |
| `lxml>=5.0` | NÃO importado em src/ | APAGAR |
| `mem0ai>=0.1` | NÃO importado em src/ | APAGAR |

### 6.3 Em `pyproject.toml` mas NÃO em `requirements.txt` (drifted)

| Dependência | Ação |
|-------------|------|
| `structlog>=24.0` | Adicionar ao requirements.txt |
| `pydantic-settings>=2.0` | Adicionar ao requirements.txt |
| `prometheus-client>=0.21` | Adicionar ao requirements.txt |
| `tenacity>=9.0` | Adicionar ao requirements.txt |
| `pytest-xdist>=3.6` | Adicionar ao requirements.txt |
| `hypothesis>=6.100` | Adicionar ao requirements.txt |
| `coverage>=7.6` | Adicionar ao requirements.txt |
| `vulture>=2.11` | Adicionar ao requirements.txt |
| `deptry>=0.20` | Adicionar ao requirements.txt |
| `bandit>=1.8` | Adicionar ao requirements.txt |

---

## 7. DIRETÓRIOS INTEIROS LEGADOS / EXPERIMENTAIS

| Diretório | Tamanho | Conteúdo | Último toque | Ação |
|-----------|---------|----------|--------------|------|
| `F51-Nitro-MoE/` | 33 MB | Paper PDF, imagens, scripts de build/benchmark, traces | 12a34bb (antigo) | MANTER — paper e evidencias têm valor; scripts de build podem ser APAGADOS |
| `lora_finance_pt/` | 71 MB | Adapter LoRA safetensors (20MB), tokenizer, checkpoint-12 | 2025-12 | MANTER — artifact de treino, pode ser útil para referência |
| `temp_gguf_workspace/` | 103 MB | `train_finance.jsonl` (97MB) + checkpoints | 2026-07-19 | MANTER — dataset de treino grande, ativo |
| `audit/` | Vazio (component_lab subdir vazio) | — | — | APAGAR (vazio) |
| `patches/` | 14 KB | `moe_selective_backward.patch` | Antigo | MANTER — patch pode ser necessário |
| `security/` | 272 KB | 3x bandit_report*.json | Antigo | MANTER — relatórios de auditoria |
| `tools/nitro/` | ? | Ferramentas Nitro | — | INVESTIGAR |
| `output/` | 4.9 MB | `playwright/` screenshots | 2026-07-19 | MANTER — evidência de smoke tests |

---

## 8. ARQUIVOS STANDALONE NA RAIZ

| Arquivo | Propósito | Ação |
|---------|-----------|------|
| `test_live_trading.py` (203 linhas) | Teste manual de live trading | APAGAR — one-off de desenvolvimento, substituído por pytest |
| `start.ps1` | Script de start | MANTER |
| `stop.ps1` | Script de stop | MANTER |
| `start_all.bat` | Start Windows batch | MANTER |
| `launcher.ps1` | Launcher | MANTER |
| `check.ps1` | Health check | MANTER |
| `clean.ps1` | Cleanup | MANTER |
| `config.ps1` | Config | MANTER |
| `create_shortcut.ps1` | Shortcut creation | MANTER |
| `Dockerfile` (raiz) | Docker image (python 3.12) | MANTER |
| `docker-compose.yml` | Docker compose | MANTER |
| `Makefile` | Make commands | MANTER |
| `superezio-final-state.png` | Screenshot evidência | MANTER |
| `superezio-test-1.png` | Screenshot evidência | MANTER |

---

## 9. PADRÕES DE DESIGN LEGADOS (NÃO DEPRECIATION, MAS OBSOLETOS)

| Padrão | Ocorrências | Recomendação |
|--------|-------------|--------------|
| `Dict[str, Any]` retornado como API pública | ~30+ funções | ATUALIZAR — usar TypedDict ou dataclass para contratos públicos |
| Lazy import dentro de funções (try/except) | ~40+ ocorrências | MANTER — padrão intencional para dependências opcionais |
| Subprocesso Python para isolamento (subprocess_collector.py) | 1 adapter | MANTER — solução válida para nested event loops |
| Compat shims (neural_rl.py, collect_experts.py, decision_logger.py) | 3 arquivos | MANTER — protegem contra regressão |

---

## SUMÁRIO EXECUTIVO

### Para APAGAR (~40 arquivos)

**Scripts de treino (11):** todas as variantes `train_qwenlong_30b_*` e `train_lora_llama_cpp.py`
**Scripts de benchmark (4):** `bench_1M_nitro.ps1`, `bench_nitro_moe.ps1`, `stress_test_25.py`, `stress_test_50.py`
**Scripts de geração de dataset (6):** `_gen.py`, `gen_bob_*.py`, `gen_fraud_rag.py`
**Scripts one-off (8):** `cloud_train.sh`, `estimate_2b_training.py`, `build_moe_fix.ps1`, `check_vast_5090.py`, `rag_ingest_paper.py`, `train_lora_bob.ps1`, `train_qwenlong_30b_gguf_f51.ps1`, `run_learning_cycle.py`, `populate_small_caps.py`, `populate_watchlist.py`
**Raiz:** `test_live_trading.py`
**Diretório vazio:** `audit/` (vazio)

### Para ATUALIZAR (~20 arquivos)

**Typing modernization (5 alta prioridade + 17 secundários):** adicionar `from __future__ import annotations` a 5 arquivos, trocar `Optional[X]` por `X | None`, `Dict`/`List` por builtins
**Bug:** remover import morto `adapters.market.market_data_provider` em `trading_engine_live.py:148`
**Dependencies:** sincronizar `pyproject.toml` e `requirements.txt` (6 pacotes a mais em cada)
**Config:** atualizar `config/runtime.yml` para refletir realidade (INV-R15)
**Fallback:** `score_type='legacy_unknown'` em builder.py deveria ser `'unknown'`
**Watchlist:** documentar qual o fallback legacy em `dynamic_watchlist.py:204`

### Para MANTER (restante)

Tudo que está em uso ativo: adapters broker, data providers, configs, scripts operacionais, shims de compatibilidade. Nada foi encontrado que exija ação imediata de segurança.
