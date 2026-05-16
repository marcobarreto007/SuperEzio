# SuperEzio v4 — Final Hostile Production Audit

**Data:** 2026-05-15
**Auditor:** Claude Opus 4.7 (modo hostil)
**Escopo:** Produção comercial — demo, venda, entrega

---

## Sumário Executivo

**Veredito: NÃO APROVADO PARA RELEASE** — 1 falha crítica de segurança, 7 falhas HIGH, 6 MEDIUM.

A arquitetura do pipeline v4 está correta. O CEO Gemma-4-26B funciona. 344 testes passam.
Mas o sistema tem **API key vazada no repo**, **dependências não documentadas**, **hardcoded paths**,
**módulos zumbis**, e **config divergente** que impedem uma demo confiável em máquina limpa.

---

## CRITICAL (bloqueia release)

### C1 — API Key Real Commitada no Repositório
- **Arquivos:** `F51_Datasets/grok_transfusion.py:22`, `F51_Datasets/grok_transfusion_python.py:19`
- **Evidência:** `XAI_API_KEY = "xai-Z7IRv4O88J0XDb4fkxZolbrPKh4b5CG7xH7WeAZo5Ndk9STL74QRnNX23Xo3OvXUoLwzYOqZcRiHoGHQ"`
- **Impacto:** Chave xAI Grok exposta publicamente no GitHub. Qualquer um pode consumir créditos.
- **Ação:** Rotacionar a chave IMEDIATAMENTE no console xAI. Substituir por `os.getenv("XAI_API_KEY")`. Rodar `git filter-branch` ou aceitar que a chave velha está queimada.

### C2 — Dependências Críticas Não Documentadas
- **pyproject.toml** omite: `torch`, `llama-cpp-python`, `aiohttp`, `sentence-transformers`, `transformers`, `peft`, `requests`, `pandas-ta`
- **Impacto:** `uv pip install -e .` não instala o necessário para rodar o CEO server nem o ExplainEngine. Sistema quebra silenciosamente.
- **Ação:** Adicionar todas as dependências reais ao `pyproject.toml`.

### C3 — Hardcoded Paths Pessoais
- `scripts/server.py:34`: `/home/marco/models/Huihui-gemma-4-26B-A4B-it-abliterated.Q4_K_M.gguf`
- `scripts/server.py:36`: `C:\Users\marco\models\...`
- `config/model_manifest.json:11`: `/home/marco/models/...`
- **Impacto:** Sistema não encontra o modelo GGUF em nenhuma máquina que não seja a do Marco.
- **Ação:** Usar apenas `SUPEREZIO_CEO_MODEL_PATH` com fallback para `~/models/`. Remover paths hardcoded.

---

## HIGH (quebra demo/venda)

### H1 — DeepSeekProvider Duplicado e Quebrado
- `src/core/model_serving/deepseek_provider.py` (345 linhas) — import quebrado na linha 23, zero callers
- Classe `DeepSeekProvider` + factory `create_deepseek_provider()` — mortos
- `gateway.py` tem método `set_deepseek_provider()` (linha 64) que referencia provider genérico fantasma
- **Ação:** Deletar `deepseek_provider.py`. Remover `set_deepseek_provider()` do gateway.

### H2 — Três Módulos Pipeline Mortos
- `src/core/pipeline/security.py` — zero imports (nós usam `guardrails.py`)
- `src/core/pipeline/cache.py` — zero imports (TTL/LRU nunca instanciado)
- `src/core/pipeline/responses.py` — zero imports (constante duplicada em 2 lugares)
- **Ação:** Deletar ou wire no runtime.

### H3 — Zombie Server (Brain Removed)
- `agent_server/main.py:98`: `app.state.pipeline = None`
- Comentário: "Legacy brain removed: running without pipeline."
- Servidor sobe mas não tem pipeline. Frontend depende dele.
- **Ação:** Rewirear `agent_server` para usar `build_graph()` do pipeline v4.

### H4 — .env.example Divergente e Stale
- 5+ env vars lidas em código mas ausentes do `.env.example`:
  `SUPEREZIO_PROFESSIONAL_COLLECTOR`, `SUPEREZIO_RAG_MODEL`, `SUPEREZIO_RAG_TOP_K`,
  `SUPEREZIO_RAG_CONTEXT_MAX_CHARS`, `SUPEREZIO_RAG_DISABLED`, `SUPEREZIO_INTENT_LLM_*`
- 15+ env vars no `.env.example` nunca lidas: `CEO_LORA_GPU`, `SUPEREZIO_EDGE_*`, `BRAVE_SEARCH_API_KEY`, `TAVILY_API_KEY`, `COINGECKO_API_KEY`, `THE_ODDS_API_KEY`, `UNIVERSAL_SKIP_GATEWAY`
- CEO model path env vars (`SUPEREZIO_CEO_MODEL_PATH`, `SUPEREZIO_CEO_PORT`, `SUPEREZIO_CEO_N_GPU`, `SUPEREZIO_CEO_N_CTX`) — usados por `scripts/server.py` mas ausentes do `.env.example`
- Menção a "Nemotron-Nano-12B" e "nf4 quantization" (linha 42-45) — CEO agora é Gemma GGUF
- **Ação:** Reescrever `.env.example` refletindo apenas vars reais.

### H5 — README Stale
- Versão: "v3.2.0" → deveria ser "v4.0.0"
- Testes: "496" → realidade é "344"
- Arquitetura: menciona `mathcore/` (renomeado), `f51_adapter/`, estrutura antiga
- Não menciona `scripts/server.py` nem o requisito de baixar GGUF
- Não menciona requisito de GPU para performance aceitável
- **Ação:** Reescrever README para v4.

### H6 — 20 Degradações Silenciosas (try/except ImportError)
- RAG cai para keyword search sem aviso se `sentence-transformers` ausente
- Data providers falham silenciosamente (yfinance, pandas_ta, requests, lxml)
- `tools/custom_tools.py:95`: `search_web` retorna `None` silenciosamente
- **Ação:** Logar warnings explícitos. Adicionar health check que reporta quais módulos estão degradados.

### H7 — Config Espalhada
- CEO model nome definido em 6 lugares
- Port numbers em 3+ lugares (8002, 8082)
- Timeout values: 7 valores diferentes em 15+ locations sem constante central
- **Ação:** Centralizar em `core/config/schema.py` com env var override.

---

## MEDIUM

### M1 — Versões Conflitantes
- `README.md`: v3.2.0
- `config/model_manifest.json`: 3.0.0
- `runtime.yml`: 2.1.0
- Git commit: "SuperEzio v4"
- pyproject.toml: 3.0.0
- **Ação:** Unificar para "4.0.0" em todos os lugares.

### M2 — Expert Taxonomy Mismatch
- `model_manifest.json`: fundamental, technical, risk, sentiment, macro, portfolio, fixed_income, quant, esg, derivatives, compliance, sector
- `frontend/index.html:1569`: fraud_hunter, flow_analyst, dark_pool_tracker, quant, macro, technical, fundamental, risk, sentiment, esg, portfolio, compliance
- **Ação:** Alinhar. Escolher uma taxonomia e usá-la em todos os lugares.

### M3 — Stale Nemotron References
- `providers.py:117`: "# CEO — Nemotron-Nano-12B merged (Phase 0 + Phase 1 QLoRA), local."
- `endpoints.py:383-384`: "Local CEO (Nemotron-Nano-12B)", "Local Nemotron-Nano-12B CEO consolidates..."
- `.env.example:42-43`: "# CEO Local: Nemotron-Nano-12B (6.83B params, Hybrid Mamba/MoE) + nf4 quantization"
- **Ação:** Substituir por "Gemma-4-26B-A4B-abliterated Q4_K_M GGUF via llama-cpp".

### M4 — Fresh Clone UX Ruim
- Sem GGUF → cadeia de timeouts (CEO offline → primary_external tenta → falha sem API key → "Error:" vermelho)
- Sem API keys → mesmo cenário
- Frontend não desabilita botão de envio proativamente quando backend offline
- **Ação:** Health check proativo no frontend. Desabilitar submit quando CEO e cloud indisponíveis.

### M5 — VAGUE_FINANCIAL_RESPONSE Triplicado
- `src/core/pipeline/responses.py:8`
- `src/agent_server/endpoints.py:27`
- `src/core/pipeline/nodes/guardrails.py:5`
- **Ação:** Manter apenas em `guardrails.py`. Deletar `responses.py`.

### M6 — CEO GPU Config Fantasma
- `.env.example:112`: `CEO_LORA_GPU=0` — nunca lida por nenhum arquivo
- `scripts/server.py` usa `SUPEREZIO_CEO_N_GPU` (não documentada no .env.example)
- **Ação:** Remover `CEO_LORA_GPU`. Documentar `SUPEREZIO_CEO_N_GPU`.

---

## LOW

- `tests/helpers.py:191`: `FakeProvider.configure_thinking` com corpo `pass` vazio
- `f51_adapter` usa acesso frágil a dict (`hub_risk_score || hub_risk`)
- Frontend não tem docs além de 3 linhas de comentário
- `runtime.yml` menciona CEO como `deepseek-chat` (linha 22)

---

## Evidência de Verificação

```
pytest: 344 passed, 2 skipped, 0 failed
ruff check (src tests): 5 E402 pre-existing (agent_server/main.py)
ruff format check: 32 files with inconsistent formatting
pyproject.toml: missing 8 critical dependencies
.env.example: 15+ dead vars, 5+ missing vars
API key leak: 2 files with hardcoded xAI key
Dead modules: 3 pipeline + 1 deepseek_provider.py
Zombie server: agent_server/main.py (brain removed)
```

---

## Recomendação

**NÃO DEMONSTRAR nem VENDER até resolver C1, C2, C3.**

Após corrigir os 3 críticos + 7 HIGH, o sistema estará pronto para:
- Demo técnica em máquina do Marco (GGUF presente, API keys setadas)
- Demo em máquina limpa (após `uv pip install -e .` com deps corretas + download GGUF + .env configurado)
