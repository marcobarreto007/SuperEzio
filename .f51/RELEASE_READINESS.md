# SuperEzio v4 — Release Readiness Assessment

**Data:** 2026-05-15
**Gate:** `/f51-release`
**Veredito:** ⚠️ CONDITIONAL PASS — 3 blockers antes de release

---

## 1. Pode Demonstrar?

**⚠️ SIM, mas só na máquina do Marco.**

Na máquina atual (RTX 5060 Ti 16GB, GGUF presente, .env configurado, todas deps instaladas):
- Pipeline v4 compila e roda
- CEO Gemma-4-26B responde via llama-cpp
- Frontend carrega e consome NDJSON stream
- 344/346 testes passam
- Gateway cascade (ceo → deepseek → grok) funciona

**Em máquina limpa: NÃO.**
- pyproject.toml não instala torch, llama-cpp-python, aiohttp, transformers
- GGUF de 16.8 GB não está incluído
- Hardcoded paths quebram em qualquer $HOME que não seja `/home/marco`
- .env.example tem vars mortas e faltam vars essenciais

---

## 2. Pode Vender?

**⚠️ NÃO ainda. 3 blockers:**

1. **API key vazada no repo** — `F51_Datasets/grok_transfusion.py` contém chave xAI real. Isso é risco legal e financeiro. Precisa rotacionar + expurgar do git history.

2. **Dependências não documentadas** — Cliente que seguir o README (`uv pip install -e .`) terá `ModuleNotFoundError: torch`, `ModuleNotFoundError: llama_cpp`. O produto não instala.

3. **Hardcoded paths pessoais** — `/home/marco/models/` e `C:\Users\marco\models\` significam que o sistema só funciona na máquina do Marco. Não é vendável.

**Após resolver esses 3, é vendável como:**
- "AI Financial Analysis Platform" para traders de penny stock
- Demo técnica mostra: pipeline completo, 12 experts, F51 verdict, RAG forense
- Diferencial: CEO 100% local (Gemma-4-26B abliterado, sem censura)
- Preço: $2.50/MTok cloud (Grok) vs $0 local (CEO Gemma)

---

## 3. O Que Falta (3 Itens)

### Item 1: Expurgar API Key e Blindar Secrets
- [ ] Rotacionar chave xAI em https://console.x.ai
- [ ] Substituir `XAI_API_KEY = "xai-..."` por `os.getenv("XAI_API_KEY")` nos 2 arquivos
- [ ] Rodar `git filter-branch` OU aceitar que a chave velha está queimada e seguir
- [ ] Adicionar `F51_Datasets/` ao `.gitignore` (ou remover os arquivos de dataset do repo)
- [ ] Verificar que nenhum outro arquivo tem secrets (`rg 'api_key\s*=\s*"[A-Za-z0-9]'`)

### Item 2: Completar pyproject.toml + .env.example + README
- [ ] Adicionar ao `pyproject.toml`: `torch`, `llama-cpp-python`, `aiohttp`, `sentence-transformers`, `transformers`, `peft`, `requests`, `beautifulsoup4`, `feedparser`, `praw`, `pandas-ta`
- [ ] Reescrever `.env.example`: remover 15+ vars mortas, adicionar 5+ vars faltantes, trocar "Nemotron" por "Gemma-4-26B"
- [ ] Atualizar `README.md`: versão v4.0.0, 344 testes, arquitetura correta, menção a scripts/server.py, requisito GGUF
- [ ] Unificar versão para "4.0.0" em: README.md, pyproject.toml, model_manifest.json

### Item 3: Remover Código Morto e Rewirear Zombie Server
- [ ] Deletar `src/core/model_serving/deepseek_provider.py` (345 linhas, import quebrado, zero callers)
- [ ] Deletar `src/core/pipeline/cache.py` (zero callers)
- [ ] Deletar `src/core/pipeline/security.py` (zero callers)
- [ ] Deletar `src/core/pipeline/responses.py` (constante duplicada)
- [ ] Rewirear `agent_server/main.py:98` — trocar `app.state.pipeline = None` por `build_graph()`
- [ ] Atualizar referências "Nemotron" → "Gemma-4-26B" em providers.py:117, endpoints.py:383-384

---

## Scorecard

| Categoria | Nota | Status |
|-----------|------|--------|
| Segurança | 🔴 2/10 | API key vazada |
| Instalabilidade | 🔴 3/10 | pyproject.toml incompleto |
| Portabilidade | 🔴 4/10 | Hardcoded paths |
| Código limpo | 🟡 6/10 | 4 módulos mortos |
| Documentação | 🟡 5/10 | README/.env stale |
| Testes | 🟢 8/10 | 344/346 passam |
| Pipeline | 🟢 8/10 | v4 funcional |
| CEO Modelo | 🟢 9/10 | Gemma GGUF excelente |

**Nota geral: 5.6/10 — NÃO APROVADO**
**Próximo gate: após resolver 3 blockers → re-auditar com /f51-quality-gate**
