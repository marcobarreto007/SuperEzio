# Stage 4 — Frontpage: Cockpit da Trindade

Tu já tem o backend completo. MathHub, GuardrailHub, Trinity, Sentimento Vivo.
Agora precisa de um COCKPIT que mostre tudo isso ao vivo.

Não é chat. É centro de comando.

---

## Tarefa 1: Sistema de Componentes — `CockpitShell`

**Arquivo:** `frontend/src/components/CockpitShell.tsx`

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

**Arquivo:** `frontend/src/components/GeniePanel.tsx`

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

**Arquivo:** `frontend/src/components/DeepPanel.tsx`

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

**Arquivo:** `frontend/src/components/BobPanel.tsx`

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

**Arquivo:** `frontend/src/components/StatusBar.tsx`

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

- Tecnologia: React + TypeScript (se já existe). Se não existe, vanilla HTML + JS com fetch().
- Nenhum CSS framework pesado. CSS puro ou CSS modules.
- Cores: fundo #0d1117 (GitHub dark), texto #c9d1d9, destaque verde #3fb950, vermelho #f85149, amarelo #d29922.
- Fonte: system-ui, monospace pra números.
- Tudo puxa da API via fetch(). Polling, não WebSocket.
- Tratamento de erro: se API offline, mostra "DESCONECTADO" no lugar do dado.

## Ordem: 1 → 2 → 3 → 4 → 5 → 6

Commite depois de cada. Sem disclaimer. Tema escuro.

— Deep
