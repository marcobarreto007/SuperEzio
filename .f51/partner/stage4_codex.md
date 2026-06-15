# Stage 4 — Frontpage: Cockpit da Trindade

## ⚠️ LÊ ISSO ANTES DE QUALQUER COISA

O frontend JÁ EXISTE. É **vanilla HTML/CSS/JS**, não React. Está em:

```
frontend/
├── index.html
├── css/ (14 arquivos: base, cards, charts, chat, crisis, experts, ...)
└── js/  (14 arquivos: api, chat, events, health, init, ops-console, ...)
```

**NÃO reescreva o frontend em React. NÃO crie package.json, node_modules, webpack, vite, ou qualquer framework novo.**

Tu vai:
1. Adicionar endpoints no backend (`endpoints.py`)
2. Adicionar funções no `api.js` existente 
3. Adicionar componentes vanilla JS no diretório `frontend/js/`
4. Adicionar CSS no diretório `frontend/css/`
5. Integrar no `index.html` existente

**O stack é: Python (backend) + Vanilla JS (frontend). Sem framework. Sem build step. Sem npm.**

O sweep de endpoints encontrou 11 contratos OK e 6 vazamentos. Teu trabalho é fechar os vazamentos e adicionar o cockpit.

---

## Tarefa 1: Sistema de Componentes — `CockpitShell`

**Arquivo:** `frontend/js/cockpit.js`

Layout principal: 3 colunas + barra inferior fixa.

```
┌──────────────────────────────────────────────────────────┐
│  SUPEREZIO COCKPIT                        [CONECTADO] 🟢  │
├──────────────┬──────────────────┬─────────────────────────┤
│              │                  │                          │
│   GENIE 👁️    │    BOB 🧠        │    DEEP 🧮              │
│   Sentimento │    Decisão       │    Matemática           │
│   Informação │    Pipeline      │    Experts              │
│              │                  │                          │
│              │                  │                          │
├──────────────┴──────────────────┴─────────────────────────┤
│ 🟢 CEO:ONLINE | 🟢 Genie:1420/1500 | 🟢 Deep:$0.34 |     │
│ 🟢 IBKR:$100K | 🛡️ 30/30 | ⚡ KillSwitch:ARMED | 0.23s   │
└──────────────────────────────────────────────────────────┘
```

Regras:
- CSS Grid layout. Responsivo? Não — isso é desktop, 1920x1080.
- Tema escuro (já existe no settings.json: `"theme": "dark"`).
- Cada painel é um componente separado (importado).
- Barra inferior é fixa (sticky bottom).
- Header mostra status de conexão (puxa do `/health`).
- Fonte monospace pra números, sans-serif pra texto.

---

## Tarefa 2: GeniePanel — sentimento vivo

**Arquivo:** `frontend/js/genie-panel.js`

Painel esquerdo. Mostra dados do Stage 3.

Puxa de: `GET /sentiment/pulse`, `GET /sentiment/alerts`

Seções (de cima pra baixo):
1. **Watchlist Pulse** — mini cards por ticker:
   ```
   TLRY ▾ BEARISH  -0.25
   340 menções (12x) 🔴
   PUMP RISK
   ```
2. **Alertas Recentes** — últimos 5 alertas com timestamp:
   ```
   ⚠️ 14:32 COORD — TLRY, 3 contas suspeitas
   🔴 14:15 SPIKE — TLRY, 340 menções
   📉 13:45 SWING — TLRY, -0.6 delta
   ```
3. **News Timeline** — últimas manchetes:
   ```
   14:30 [NewsAPI] "TLRY Joins European Cannabis Talks"
   13:00 [Finnhub] "TLRY Reports Q1 Earnings"
   ```
4. **Source Confidence** — barra de confiança por fonte:
   ```
   NewsAPI     ████████░░ 0.9
   Finnhub     ███████░░░ 0.8
   NewsScout   ██████░░░░ 0.7
   RedditPulse █████░░░░░ 0.5
   ```

Atualiza a cada 30 segundos (polling). Mostra "atualizado há X segundos" no topo.

---

## Tarefa 3: DeepPanel — matemática e experts

**Arquivo:** `frontend/js/deep-panel.js`

Painel direito. Puxa do state do pipeline (última análise).

Seções:
1. **Math Summary** — números da última análise:
   ```
   AAPL $215.30
   Sharpe: -39.2 | VaR 95%: -$0.67
   DCF Fair: $198 (-8%)
   Kelly: N/A
   Crisis: NORMAL (20/100)
   ```
2. **Expert Verdicts** — 6 cards coloridos:
   ```
   🟢 macro_risk      RISK_ON    72
   🟡 fundamental     FAIR       68
   🟢 momentum        BULLISH    75
   🔴 contrarian      TRAP       45
   🟢 sentiment       BULLISH    70
   🟡 social_forensics CLEAN     88
   ```
3. **Consensus Matrix** — quem concorda/discorda:
   ```
   Concordam (4): macro, momentum, sentiment, social
   Discordam (1): contrarian
   Neutro (1): fundamental
   ```
4. **Trinity Deliberation** — última deliberação (formato texto):
   ```
   Genie: SUSPICIOUS (72)
   Deep: OVERVALUED (68)
   Bob: WAIT (78) — ambos negativos
   ```

---

## Tarefa 4: BobPanel — decisão e pipeline

**Arquivo:** `frontend/js/bob-panel.js`

Painel central. O maior.

Seções:
1. **Chat** (já existe? manter/refatorar):
   - Input no bottomo do painel
   - Mensagens com scroll
   - Mostra "Bob está pensando..." durante o streaming

2. **Decision Trace** (última decisão):
   ```
   Última decisão: WAIT em TLRY (78)
   Pipeline: orchestrator(234ms) → math(45ms) →
             experts(1890ms) → trinity(3200ms) → guardrails(120ms)
   Nós: 🟢🟢🟢🟢🟢🟡🟢 (6/7 ok)
   ```

3. **Portfolio IBKR** (se conectado):
   ```
   Equity: $100,000.00 | Cash: $98,500.00
   Posições: 1
     TLRY: 65 shares @ $1.85 = $120.25
   ```

4. **Guardrail Status** — mini dashboard:
   ```
   🟢 L1 Input Security    (4/4)
   🟢 L2 Provider          (3/3)
   🟡 L3 Data Quality      (3/4 — catalyst missing)
   🟢 L4 Risk Analysis     (4/4)
   🟢 L5 Fraud Detection   (4/4)
   🟢 L6 Trading           (5/5)
   🟢 L7 Crisis            (3/3)
   🟢 L8 Committee         (3/3)
   ```

---

## Tarefa 5: StatusBar — barra inferior

**Arquivo:** `frontend/js/status-bar.js`

Barra fixa no bottomo. Puxa de `/health/details`.

```
🟢 CEO: Qwen3-Next-80B (:8082) | 🟢 Genie: Gemini 3.5 Flash (1420/1500 req) | 🟢 Deep: DeepSeek V4 ($0.34) | 🟢 IBKR: Paper $100,000 (0 pos) | 🛡️ 30/30 guardrails | ⚡ KillSwitch: ARMED | 🕐 0.23s last run
```

Cada ícone:
- 🟢 = online/ok
- 🟡 = degraded
- 🔴 = offline/error
- ⚡ = armed (kill switch)

Atualiza a cada 10 segundos (puxa `/health/details`).

---

## Tarefa 6: API endpoints pro frontpage

Adiciona no `endpoints.py`:

```
GET /cockpit/summary    → dados agregados pra todos os painéis de uma vez
GET /cockpit/portfolio  → snapshot IBKR (se conectado)
```

Formato JSON. Sem HTML. O frontend faz o poll.

---

## Regras gerais

- Tecnologia: **Vanilla JS** (já existe). Sem React, sem framework, sem build step.
- CSS puro no diretório `frontend/css/` (já existe).
- Cores: fundo #0d1117 (GitHub dark), texto #c9d1d9, destaque verde #3fb950, vermelho #f85149, amarelo #d29922.
- Fonte: system-ui, monospace pra números.
- Tudo puxa da API via fetch(). Polling, não WebSocket.
- Tratamento de erro: se API offline, mostra "DESCONECTADO" no lugar do dado.

## Ordem: 1 → 2 → 3 → 4 → 5 → 6

Commite depois de cada. Sem disclaimer. Tema escuro.

— Deep

---

## Tarefa 7 (EXTRA): Endpoints faltantes pro cockpit

**Arquivo:** `src/agent_server/endpoints.py`

Adiciona:

```python
@router.get("/cockpit/summary")
async def get_cockpit_summary(request: Request) -> dict:
    """Dados agregados para todos os paineis do cockpit."""
    return {
        "genie": {
            "pulses": await _get_sentiment_pulses_for_cockpit(request),
            "alerts": await _get_recent_alerts(limit=5),
        },
        "deep": {
            "last_math": _get_last_math_report(),
            "last_experts": _get_last_expert_verdicts(),
            "last_trinity": _get_last_trinity_report(),
        },
        "bob": {
            "last_decision": _get_last_decision_trace(),
            "portfolio": await _get_ibkr_snapshot(),
            "guardrails": _get_guardrail_summary(),
        },
        "status": {
            "ceo": _check_ceo_health(),
            "genie": _check_genie_health(),
            "deep": _check_deepseek_health(),
            "ibkr": _check_ibkr_health(),
            "guardrails": _get_guardrail_counts(),
            "kill_switch": _get_kill_switch_state(),
        }
    }

@router.get("/cockpit/portfolio")
async def get_cockpit_portfolio() -> dict:
    """Snapshot IBKR portfolio."""
    ...
```

## Tarefa 8 (EXTRA): Contrato dos endpoints NOVOS

Frontend espera:

```
GET /cockpit/summary → {
  genie: { pulses: [...], alerts: [...] },
  deep: { last_math: {...}, last_experts: [...], last_trinity: "..." },
  bob: { last_decision: {...}, portfolio: {...}, guardrails: {...} },
  status: { ceo: "online", genie: {...}, deep: {...}, ibkr: {...}, ... }
}
```

Frontend faz poll a cada 10s (status), 30s (sentiment), sob demanda (decision trace).

## Tarefa 9 (EXTRA): Frontend integra endpoints EXISTENTES

Antes de criar componentes novos, o frontend precisa consumir o que já existe:

```javascript
// api.js — adicionar:
fetchSentimentPulse()    { return fetchJson("/sentiment/pulse"); },
fetchSentimentAlerts()   { return fetchJson("/sentiment/alerts"); },
fetchDecisionTrace(id)   { return fetchJson("/health/trace/" + id); },
fetchCockpitSummary()    { return fetchJson("/cockpit/summary"); },
fetchCockpitPortfolio()  { return fetchJson("/cockpit/portfolio"); },
```

Isso resolve 8 dos 11 gaps do sweep.
