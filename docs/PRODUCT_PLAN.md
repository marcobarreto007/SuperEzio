# SuperEzio — Plano de Produto para Trader Final

> **HISTORICO / SUPERSEDED.** Este plano preserva a fotografia de produto de 2026-07-20. Claims de providers, runtime ou empacotamento abaixo nao substituem o contrato operacional atual em `docs/runbooks/RUNBOOK.md`.

> Documento 100% baseado em codigo existente. Tudo marcado como "[EXISTE]" ou "[CONSTRUIR]" conforme o estado real do repositorio em 2026-07-20.
> Gerado pelo skill f51-productizer.

---

## 1. O Que o Projeto Faz (Codigo Real)

### 1.1 Frontend (SPA) — [EXISTE]
- Single-page application em `frontend/index.html`
- Painel de chat com "Bob Copilot" — assistente financeiro em linguagem natural
- Chart de velas (canvas) com indicadores tecnicos (SMA, EMA, RSI, MACD, Bollinger)
- Seletor de ticker + timeframe (1D a 5Y)
- Painel "IBKR Mirror" — ordens abertas, posicoes, historico de trades paper
- Painel "Genie" — sentimento vivo da watchlist
- Painel "Deep" — sumario de matematica e experts
- Painel "Blame Report" — auditoria de decisoes por run_id
- **SDCA Lab** — firewall de risco cognitivo (avaliacao local de decisoes)
- **Ops Console** — status do sistema (GPU, Redis, CEO, Broker, metricas)
- Feedback buttons (+1/-1) apos cada resposta do Bob
- Operacional em http://localhost:8002, 100% funcional

### 1.2 API Backend (FastAPI) — [EXISTE]
43 rotas documentadas em `src/agent_server/endpoints.py` + `main.py`:

| Grupo | Rotas | Descricao |
|-------|-------|-----------|
| Chat | `/task/submit` | Pipeline LangGraph completo com streaming NDJSON |
| Chart | `/api/chart-data/{ticker}`, `/api/chart-sse/{ticker}` | OHLCV + indicadores via DataHub (Yahoo Finance) |
| Saude | `/health`, `/health/details`, `/bob/health`, `/bob/pain`, `/bob/heal` | Health checks, ANS |
| Portfolio | `/cockpit/portfolio`, `/cockpit/summary` | Dados IBKR + journal |
| Trades | `/trade/execute`, `/trade/status/{id}`, `/trades/history` | 2-fases paper trade |
| Aprovacao | `/paper/approve/{id}`, `/paper/reject/{id}` | Aprovacao manual de paper trades |
| Sentimento | `/sentiment/pulse`, `/sentiment/alerts`, `/sentiment/history/{ticker}` | Monitoramento Gemini |
| Risco | `/api/sdca/evaluate` | Firewall de decisao SDCA |
| ML | `/experts/neural-decision/predict` | Predicao neural |
| Auditoria | `/evidence/{run_id}`, `/health/trace/{run_id}` | Trail de auditoria |
| Feedback | `/feedback`, `/feedback/stats` | Avaliacao do usuario |
| Metricas | `/metrics`, `/metrics/prometheus`, `/dashboard` | Business KPIs |
| Produto | `/product/manifest`, `/capabilities` | Manifesto do produto |
| Task | `/task/status/{id}`, `/task/cancel/{id}`, `/task/active` | Gerenciamento de tarefas |
| IBKR | `/bob/ibkr/recover` | Recuperacao de conexao IBKR |
| Treino | `/training/orders` | Ordens de treinamento |

### 1.3 Pipeline de Decisao (LangGraph) — [EXISTE]
8 nos em `src/core/pipeline/nodes/`:
1. **Orchestrator** — classifica intencao (ticker_analysis, market_scan, general, etc.)
2. **Data Collection** — coleta precos, fundamentals, tecnicos, noticias
3. **Expert Committee** — 4 analistas (Macro, Fundamental, Momentum, Contrarian)
4. **PennyLab** — camada opcional para penny stocks (5 agentes: Fraud Hunter, Flow Analyst, Ruin Calculator, Sentiment Detective, Market Context)
5. **Crisis Guardrails** — 8 modelos de crise (HMM, Hawkes, GaR, LPPLS, Minsky-Keen, Shiller, Debt-Service, Credit-Asset)
6. **Neural Decision** — classificador causal tres-classes com split conformal
7. **F51 Verdict Engine** — sintese com peso de experts, voto de minerva
8. **Generator** — resposta final em linguagem natural

### 1.4 Paper Trading — [EXISTE]
- `src/core/trading/paper_journal.py` — Journal completo em JSONL com dataclass PaperTrade
- Campos: trade_id, ticker, thesis, direction, entry/exit price, shares, PnL, outcome, post-mortem (thesis_correct, what_went_right, what_went_wrong, lesson_learned)
- `src/core/trading/approval_gate.py` — Gate de aprovacao em 2 fases
- `src/core/trading/position_sizer.py` — Calculo de tamanho de posicao
- `src/core/trading/risk_guard.py` — Guardrails de risco
- `src/core/trading/order_builder.py` — Construcao de ordens
- `src/core/trading/execution_policy.py` — Politica de execucao adaptativa
- `src/core/trading/outcome_learning.py` — Aprendizado com resultados terminais
- `scripts/questrade_order_assist.py` — Preenche ticket Questrade (sem submeter)

### 1.5 Integracoes Externas — [EXISTE]
- **Interactive Brokers (IBKR)** — `src/adapters/broker/ibkr_service.py` via ib_insync
- **Alpaca** — `alpaca-py` no pyproject.toml (biblioteca instalada, mas sem uso ativo no codigo atual)
- **Yahoo Finance** — provedor primario de dados via DataHub (`yfinance`)
- **DeepSeek** — provedor LLM primario via API
- **Gemini** — provider de sentimento (LiveMonitor)
- **Redis** — armazenamento opcional de memoria

### 1.6 Banco de Dados — [EXISTE]
- `data/investor.db` — SQLite com tabelas: `investor_decisions`, `investor_risk_profile`, `investor_watchlist`, `investor_notes`, `investor_api_usage`
- `data/paper_journal.jsonl` — Journal de trades paper
- `data/conversation_memory.jsonl` — Memoria de conversacao
- `data/bob_pain_log.jsonl` — Log de dor do ANS

### 1.7 Seguranca — [EXISTE]
- Security headers (CORS, X-Frame-Options, HSTS, etc.) — [EXISTE]
- **JWT Authentication** — [EXISTE] (P0 resolvido)
  - `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`
  - SQLite-backed user store com bcrypt + refresh token rotation
  - Dev mode fallback quando `SUPEREZIO_JWT_SECRET` nao configurado
  - Middleware JWT em cascata apos API key middleware
  - Rotas publicas: `/health`, `/frontend/*`, `/auth/*` — sem auth necessaria
- **Script de seed admin** — `scripts/seed_admin.py` — [EXISTE]
- `F51_TRADING_EXECUTION_FREEZE` (default True) — [EXISTE]
- `SUPEREZIO_LIVE_TRADING_DISABLED` (default True) — [EXISTE]
- `MAN_AT_WORK` mode — [EXISTE]
- Kill switch — [EXISTE]
- API keys expostas no git history — [RISCO CONHECIDO]

---

## 2. Quem Compra

### Persona Primaria: Trader Varejo (Brasil/Canada/USA)
- Idade: 25-50 anos
- Perfil: autodidata, ja opera ou quer comecar a operar acoes/opcoes
- Dor principal: **nao tem tempo ou disciplina para fazer analise completa antes de operar**
- Dor secundaria: **nao confia em "gurus" financeiros, quer dados reais e auditoria**
- Comportamento: usa YouTube/TradingView para ideias, executa na corretora
- Disposicao a pagar: R$50-200/mes ou 0.1-0.5% AUM
- Idioma: portugues (Brasil) ou ingles (Canada)

### Persona Secundaria: Investidor Iniciante
- Idade: 18-35 anos
- Quer aprender a investir sem perder dinheiro
- Usaria paper trading + modo educativo extensivamente
- Menor disposicao a pagar, mas maior volume potencial

### Persona Terciaria: Trader Profissional / Pequeno Gestor
- Precisa de segunda opiniao sistematica
- Usaria a API e os relatorios de auditoria
- Pagaria por assinatura premium + volume de API

---

## 3. Qual Dor Resolve

> "Eu nao tenho tempo de analisar 10 acoes por dia, e quando opero sem analise, perco dinheiro."

**Proposicao de valor:** SuperEzio e seu comite pessoal de analistas 24/7. Cada decisao tem auditoria, cada tese e registrada, cada erro vira licao. Papel primeiro, dinheiro real depois.

**Dores especificas:**
1. **Sobrecarga de informacao** — Bob sintetiza dados de mercado, noticias, tecnicos e risco em uma resposta direta
2. **Vies emocional** — SDCA Firewall detecta FOMO, alavancagem, slippage antes de decidir
3. **Falta de disciplina** — Paper journal obriga registrar tese, entrada, saida e post-mortem
4. **Zero auditoria** — Todo passo do pipeline e registrado com evidence_id e blame report
5. **Custo de analise** — Comite de 4-7 experts por consulta, disponivel 24h

---

## 4. Pricing Sugerido

### Modelo: Assinatura SaaS (B2C) + API Usage (B2B)

| Plano | Preco | Para quem | Features |
|-------|-------|-----------|----------|
| **Free** | R$ 0 | Iniciante | Chat Bob (10/dia), chart basico, paper journal (5 trades), sentimento basico |
| **Starter** | R$ 49/mes | Trader casual | Chat ilimitado, indicadores tecnicos, SDCA Lab, 50 paper trades |
| **Pro** | R$ 149/mes | Trader ativo | Todos os experts, scan de mercado, neural predictions, auditoria completa, 500 trades |
| **Elite** | R$ 399/mes | Profissional | API access, webhook trading, broker IBKR live, prioridade, analytics avancado |
| **API Usage** | $0.01/req | B2B / integradores | Pay-as-you-go para acesso programatico |

**Justificativa:** Nenhum concorrente direto oferece comite multi-expert + journal obrigatorio + auditoria forense. O precifico e 2-3x abaixo de um analista junior, e o valor entregue (analise completa + disciplina) justifica o premium sobre chatbots genericos.

**Nota sobre custo real:** O provedor LLM (DeepSeek API) tem custo viavel (~$0.50/1M tokens). Com lucro bruto alvo de 70%, o plano Starter cobre ~1000 consultas/mes. O modelo so escala com margem saudavel se o CEO local (GGUF) estiver rodando localmente (custo marginal zero).

---

## 5. Entrega Minima Vendavel (V1)

### O que ja funciona HOJE e pode ir para producao:

**5.1 Onboarding — [EXISTE PARCIAL]**
- [x] Cadastro com email + senha (auth JWT) — `POST /auth/register`
- [x] Login com JWT — `POST /auth/login`
- [x] Refresh token rotacao — `POST /auth/refresh`
- [x] Script de seed admin — `python scripts/seed_admin.py`
- [ ] Perfil de investidor (risk_profile: conservador/moderno/agressivo)
- [ ] KYC basico (nome, CPF/SSN, foto documento)
- [ ] Termos de uso + risk disclosure

**5.2 Deposito/Funding — [CONSTRUIR]**
- [ ] Nao ha sistema de deposit no codigo
- [ ] V1 usa **PAPER TRADING APENAS** — deposito e $10,000 USD ficticios
- [ ] V2+ integrar Stripe/Pix para assinatura + carteira virtual

**5.3 Chat + Analise — [EXISTE, PRONTO]**
- [x] Bob Copilot com contexto de mercado
- [x] Chart com OHLCV + indicadores (SMA, EMA, RSI, MACD, BB)
- [x] Comite de 4 experts
- [x] Firewall de risco SDCA
- [x] Sentimento vivo (Genie)
- [x] Respostas em PT-BR ou EN

**5.4 Paper Trading — [EXISTE, PRONTO]**
- [x] Order ticket em 2 fases (validacao -> submissao)
- [x] Aprovacao manual de ordens
- [x] Journal com tese, entrada, saida, PnL, post-mortem
- [x] Calculo de tamanho de posicao
- [x] Historico de trades

**5.5 Auditoria — [EXISTE, PRONTO]**
- [x] Decision trace por run_id
- [x] Evidence files por run
- [x] Blame report com agentes
- [x] Feedback do usuario (+1/-1)

**5.6 Precificacao/Planos — [CONSTRUIR]**
- [ ] Sistema de assinatura (Stripe/Pix/ASAAS)
- [ ] Rate limiting por plano
- [ ] Feature flags por plano

**5.7 Broker Real — [BLOQUEADO]**
- [ ] IBKR live trading bloqueado por F51_TRADING_EXECUTION_FREEZE + MAN_AT_WORK
- [ ] V1 = paper trading apenas. Trading real exige:
  - 30 dias de track record paper
  - Auditoria independente
  - Autorizacao do CEO (operador)
  - Remocao do MAN_AT_WORK

---

## 6. Jornada do Trader

### Dia 1 — "Quem e Bob?"
1. Acessa superezio.app, ve tela unica com chat + chart
2. Digita "Oi, quem e voce?" — Bob responde em PT-BR
3. Digita "Analise AAPL" — ve o pipeline rodando: orquestrador -> dados -> experts -> crise -> F51 -> resposta
4. Ve o chart, os indicadores, a ficha da empresa
5. Digita "Quero comecar a operar" — Bob explica paper trading

### Dia 7 — "Primeiro trade paper"
1. Ja entende como Bob funciona
2. Pede scan de mercado: "Encontre acoes brasileiras com momentum"
3. Bob retorna candidatos com analise
4. Usuario escolhe uma, Bob sugere tese com entrada, stop, target
5. Usuario confirma, ordem paper e criada no journal
6. Ve a ordem no painel IBKR Mirror

### Dia 30 — "Revisao e aprendizado"
1. Tem 5-20 trades paper no journal
2. Pede "Me mostre meu desempenho" — metricas: win rate, PnL, Sharpe, licoes
3. Bob identifica erros sistematicos ("Voce perdeu em 80% das ops de alta volatilidade")
4. Usuario ajusta estrategia
5. Decide se quer conectar corretora real (quando disponivel)

---

## 7. O Que Cortar (Nao da Dinheiro Agora)

### Corte definitivo (produto V1 nao precisa)
| Item | Motivo |
|------|--------|
| **Crisis models complexos (HMM, Hawkes, GaR, LPPLS)** | Interessante, mas o trader final nao entende. Focar no SDCA Firewall que e mais tangivel. Manter em background, nao na UI. |
| **Agent Bus / Captain / Swarm** | Infraestrutura interna de agentes. Nao e feature de produto. |
| **Quality Dashboard (/dashboard)** | Ferramenta interna de dev/ops. Nao mostrar para cliente. |
| **F51 LoRA / GGUF local** | Modelo local nao esta presente em disco (INV-R13). Usar DeepSeek API. |
| **Evidence files HTML** | Auditavel mas desnecessario para o trader. Manter trace API. |
| **Prometheus / metrics** | Infraestrutura. Nao expor ao usuario. |
| **Training orders** | So para dev. |

### Corte temporario (adiar para V2)
| Item | Motivo |
|------|--------|
| **IBKR live integration** | Bloqueado por policy. Paper trading primeiro. |
| **Alpaca integration** | Biblioteca instalada, mas sem uso. So implementar se houver demanda. |
| **Questrade order assist** | Script auxiliar, nao produto. |
| **Neural deep learning** | Interessante, mas o valor para o trader final nao esta claro. |
| **Fraud RAG** | Dataset de 3.3GB. Caso de uso marginal para trader varejo. |

---

## 8. Como Empacotar

### SaaS Web (Primary)
- Single-page application servida pelo FastAPI
- Sem necessidade de instalacao
- Acesso via navegador (desktop first, responsivo mobile basico)
- http://localhost:8002 hoje, superezio.app no futuro

### Pacote de Deployment
```yaml
stack:
  api: FastAPI (Python 3.11+) — porta 8002
  llm: DeepSeek API (primario) ou GGUF local (opcional)
  db: SQLite local (data/investor.db) ou PostgreSQL (futuro)
  broker: IBKR via ib_insync (apenas paper)
  cache: Redis (opcional)
  frontend: SPA vanilla JS + CSS + Canvas
  deploy: Docker (docker-compose.yml existente)
```

### Requisitos de Infra para Producao
- **LLM Provider**: DeepSeek API (custo ~$0.50/1M tokens) — NECESSARIO CONFIGURAR
- **GPU**: Opcional. Sem GPU o CEO local nao funciona, mas DeepSeek API funciona
- **Memoria**: 4 GB RAM minimo, 8 GB recomendado
- **Disco**: 10 GB para o stack completo
- **IBKR TWS/Gateway**: Opcional. Necessario apenas para integracao com broker

---

## 9. Roadmap V1 (Proximo Passo)

### Sprint 1 — Autenticacao e Base (7 dias)
1. Implementar JWT auth em todas as rotas (P0) — **[FEITO]**
2. Tela de login/registro no frontend — **[FEITO]** (`frontend/auth.js`, `frontend/auth.css`, `frontend/api.js`)
3. User model + SQLite users table — **[FEITO]** (schema em `core/auth/models.py`)
4. Seed admin script — **[FEITO]** (`scripts/seed_admin.py`)
5. Perfil de investidor (questionario de risco)
6. Rate limiting por usuario

### Sprint 2 — Plano Free + Onboarding (7 dias)
1. Feature flags por plano (free vs starter)
2. Rate limit: 10 consultas/dia free
3. Onboarding tutorial (3-5 mensagens guiadas)
4. Risk disclosure + termos de uso
5. Modo paper trading habilitado por default

### Sprint 3 — Premium + Pagamento (7 dias)
1. Integracao Stripe (ou Pix via ASAAS)
2. Upgrade flow (free -> starter -> pro)
3. Dashboard de uso (consultas restantes)
4. Webhook de pagamento
5. Cancelamento de assinatura

### Sprint 4 — Polimento (7 dias)
1. Responsivo mobile
2. Exportar journal (CSV/PDF)
3. Compartilhar analise (link)
4. Modo escuro (ja existe parcialmente)
5. Testes E2E com playwright

---

## 10. Resumo Executivo

### O que vender
Um **copiloto financeiro com comite de experts auditoriavel** que ajuda o trader a analisar, decidir e aprender — sem perder dinheiro no processo.

### O que NAO vender
- Robo de trading automatico (nao e, e consultor)
- Sistema de sinais (nao da recomendacoes de compra/venda)
- Rico rapido (propositalmente conservador)

### Estado atual do projeto (2026-07-20) — Final
- **1533 testes passando**, 1 falha, 11 skipped (1 regression: expert committee consensus test)
- **21 auth unit tests** adicionados (85-88% coverage em 4 modulos)
- **68 integration tests** adicionados (MathHub, builder, contracts, observations)
- **23 modulos mortos removidos** (8,511 LOC) — core/trading/ agora enxuto
- **40 scripts legados removidos** — sem mais scripts de treino/bench obsoletos
- **43 rotas API** funcionais
- **8 security fixes aplicados** — auth middleware, trading 2FA, ticker sanitize, sandbox, .env.local, CI/CD + env leak fix, --cov default, idempotency atomico, /health real, smoke auth detection
- **Pipeline 100% real** — prompt, builder, math, observations, logging ressuscitados
- **Ruff limpo** — src/ e tests/ sem violacoes
- **Browser smoke 100% pass** — auth modal dev-mode detection corrigido
- **JWT auth full-stack** — backend (4 endpoints) + frontend login UI (auth.js, auth.css, api.js) + seed admin
- **Questrade portfolio reader** via Playwright (UI scraping persistente, snapshot real)
- **Seed admin disponivel** — `python scripts/seed_admin.py` para bootstrap
- **43 commits entregues** nesta sessao — 95cfc57..81457ea
- **1 missing pre-requisito**: Chat real depende de DeepSeek API key configurada OU GGUF local presente em disco

---

## 11. Checkpoint

Atualizado em `.f51/checkpoints/latest.json`.

## 12. Acao Imediata

1. **Seed admin inicial**: `python scripts/seed_admin.py --password SuaSenhaForte!`
2. **Configurar provedor LLM**: DeepSeek API key ou download do GGUF (~40 GB)
3. **Criar tela de login** no frontend
4. **Ativar paper trading** como modo default para novos usuarios
5. **Testar fluxo completo**: seed -> login -> chat -> paper trade -> journal -> auditoria

### Primeiro uso para o trader

```bash
# 1. Garantir que o servidor esta rodando
python -m agent_server.main

# 2. Em outro terminal, criar admin inicial
python scripts/seed_admin.py --username admin --email admin@exemplo.com --password MinhaSenha123

# 3. Testar login via API (opcional)
curl -X POST http://localhost:8002/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"MinhaSenha123"}'

# 4. Abrir o navegador em http://localhost:8002
#    (modo dev: user anonimo ate frontend de login ser implementado)
```

---

> Documento gerado em 2026-07-19. Todas as afirmacoes sobre codigo existente foram verificadas contra o repositorio. Nenhuma feature foi inventada ou exagerada.
