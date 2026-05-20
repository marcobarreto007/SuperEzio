# Prompt: Auditoria UI ↔ Backend — SuperEzio

Você é um auditor frontend sênior. Sua missão é verificar se a UI representa fielmente o backend, se está conectada de verdade (sem mock), e sugerir melhorias.

## Contexto do Projeto

O SuperEzio é um assistente de análise financeira com IA. Stack: FastAPI (backend) + HTML/CSS/JS vanilla monolítico (frontend). Arquivo único: `frontend/index.html` (~2465 linhas, CSS+HTML+JS inline). Backend em `src/agent_server/`.

## Sua Missão

### PARTE 1 — Representação: A UI reflete o backend?

Para cada endpoint do backend, verifique se a UI:

| # | Endpoint Backend | Método | O que faz | UI correspondente? | Representa corretamente? |
|---|------------------|--------|-----------|---------------------|--------------------------|
| 1 | `GET /health` | GET | Health check (status do servidor) | ? | ? |
| 2 | `GET /health/details` | GET | Deep health: GPU, modelos, Redis, providers, cost guard | ? | ? |
| 3 | `GET /metrics` | GET | Métricas de negócio: latência, erros, tokens, cache | ? | ? |
| 4 | `GET /api/chart-data/{ticker}` | GET | Dados OHLCV + indicadores (SMA, EMA, RSI, MACD, Bollinger) | ? | ? |
| 5 | `GET /api/chart-sse/{ticker}` | SSE | Stream de candles em tempo real | ? | ? |
| 6 | `POST /task/submit` | POST | Chat/pipeline principal — envelope A2A, response NDJSON stream | ? | ? |
| 7 | `GET /capabilities` | GET | Manifesto de capacidades do agente | ? | ? |
| 8 | `GET /product/manifest` | GET | Metadata: papéis do comitê, workflow, modos de decisão | ? | ? |
| 9 | `POST /api/sdca/evaluate` | POST | Avaliação de risco cognitivo (firewall SDCA-Lite) | ? | ? |
| 10 | `POST /experts/neural-decision/predict` | POST | Predição do expert neural | ? | ? |
| 11 | `GET /neural/logs` | SSE | Stream de logs em tempo real | ? | ? |

Para cada endpoint, responda:
- **Visível na UI?** (Sim/Não/Parcial)
- **O que está faltando?** (campos, estados, indicadores que o backend retorna mas a UI ignora)
- **O que está errado?** (dado exibido de forma diferente do backend)

### PARTE 2 — Conexão real vs mock

Verifique cada chamada de API no `frontend/index.html`:

```javascript
// Chamadas encontradas no frontend:
const API = window.location.protocol === "file:" ? "http://127.0.0.1:8002" : "";

// 1. fetchJson("/health") — health check periódico (30s)
// 2. fetch("/api/chart-data/" + ticker + "?timeframe=" + tf) — dados do gráfico
// 3. new EventSource(url) para /api/chart-sse/{ticker} — stream em tempo real
// 4. fetch(API + "/api/sdca/evaluate", {method: "POST"}) — lab SDCA
// 5. fetch(API + "/task/submit", {method: "POST"}) — chat principal (NDJSON stream)
```

Para cada chamada:
- **É chamada real?** (fetch/EventSource para endpoint verdadeiro = OK)
- **Tem fallback mock?** (dados hardcoded, resposta fake, simulação local = PROBLEMA)
- **Trata erro corretamente?** (timeout, falha de rede, resposta inesperada)

### PARTE 3 — Endpoints do backend SEM representação na UI

Liste todos os endpoints que o backend expõe mas que a UI NÃO consome:

- `GET /metrics` — métricas de negócio. A UI mostra isso em algum lugar?
- `GET /capabilities` — capacidades do agente. O usuário consegue ver?
- `GET /product/manifest` — manifesto do produto. Visível?
- `POST /experts/neural-decision/predict` — predição neural. Explicado na UI?
- `GET /neural/logs` — logs neurais. Onde aparecem?

### PARTE 4 — Sugestões

Para cada gap encontrado, sugira:

1. **Prioridade** (Crítica / Alta / Média / Baixa)
2. **O que fazer** (ação concreta — "adicionar painel X que mostra Y do endpoint Z")
3. **Impacto** (o que o usuário ganha)
4. **Esforço estimado** (pequeno/médio/grande)

## Arquivos a analisar

- **Frontend:** `frontend/index.html` (arquivo único, ~2465 linhas)
- **Backend routes:** `src/agent_server/main.py` e `src/agent_server/endpoints.py`
- **Backend config:** `config/runtime.yml` e `config/model_manifest.json`

## Formato da resposta

```
== AUDITORIA UI ↔ BACKEND ==

## 1. Representação
- [endpoint]: [VISÍVEL/PARCIAL/AUSENTE] — [o que falta/erro]

## 2. Mock Check
- [chamada]: [REAL/MOCK/PARCIAL] — [evidência]

## 3. Endpoints sem UI
- [endpoint]: [descrição do que o usuário perde]

## 4. Sugestões (ordenadas por prioridade)
| # | Prioridade | Gap | Ação | Impacto | Esforço |
|---|-----------|-----|------|---------|---------|

## 5. Score
- Representação: [X/10]
- Conexão real: [X/10]
- Qualidade percebida pelo usuário: [X/10]
- Score geral: [X/10]
```
