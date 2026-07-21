# F51 PRODUCTIZER REPORT — SuperEzio v4.0.0
## Análise de produto baseada em código real. 2026-07-20.

---

## 1. O QUE O PROJETO FAZ (CÓDIGO REAL)

**Pipeline financeiro determinístico:**
- Coleta dados de 10+ providers (TwelveData, yfinance, AlphaVantage, NewsAPI, ApeWisdom, AlphaSMO, SocialWhale, Reddit)
- MathHub: 13 módulos de cálculo (RSI, MACD, Sharpe, Sortino, VaR, CVaR, Kelly, DCF, Bootstrap, HRP, Momentum, Crisis, Drawdown)
- Expert Committee: 6 LLMs analisam em paralelo (macro, fundamental, técnico, contrarian, sentimento, social)
- F51 Verdict Engine: score 0-100, veracity gate, adversarial critic
- SDCA Cognitive Firewall: ALLOW/BLOCK/REVIEW com detecção de FOMO
- Neural Decision: regime bull/bear, direction UP/DOWN, drawdown risk
- Trinity Deliberation: Genie (sentimento) + Deep (fundamental) → consenso
- 30 Guardrails em 8 camadas
- Pennylab: whale detection, pump & dump detection, volume spike
- Mangala Engine: scanner de oportunidades < $10, score 0-100, flip plan

**Bob — LLM porta-voz:**
- DeepSeek V4 Flash como primary, Gemini/GLM fallback
- Responde com dados REAIS do pipeline (RSI, MACD, Sharpe, F51)
- 5 camadas de defesa contra alucinação
- Fast path: queries simples pulam Trinity (< 60s resposta)

**Infraestrutura:**
- FastAPI na porta 8002, JWT auth (register/login/refresh/me)
- Frontend SPA: WebGL chart (Lightweight Charts), dark/light theme
- Pipeline progress visível (7 dots animados), trust score 0-100
- Docker Compose, PyInstaller .exe (244MB), setup script
- 14 agentes Claude Code em .claude/agents/
- Circuit breakers, graceful degradation, health dashboard

**Paper trading:**
- Journal com 1600+ trades, compound tracker ($20 → $X)
- Trade button nos cards, formulário inline, POST /trade/execute
- IBKR adapter (não configurado), Questrade portfolio reader (Playwright)

---

## 2. QUEM COMPRA

### Persona Primária: Trader Varejo Autônomo
- **Quem é:** Pessoa física que investe o próprio dinheiro. Não é profissional de Wall Street. Opera no home office, pelo celular ou notebook.
- **Capital:** $500 - $50,000
- **Nível:** Iniciante a intermediário. Sabe o que é RSI mas não sabe calcular. Quer ajuda para decidir.
- **Dor:** "Não tenho tempo de analisar 10 ações por dia. Quando opero sem análise, perco dinheiro. Não confio em dica de YouTube."

### Persona Secundária: Entusiasta de Tecnologia Financeira
- **Quem é:** Dev que investe. Gosta de dados, automação, APIs. Quer uma ferramenta que ele entende como funciona.
- **Dor:** "As plataformas são caixas-pretas. Quero ver o pipeline, auditar as decisões, hackear o sistema."

### Persona Terciária: Pequeno Gestor/Consultor
- **Quem é:** Assessor de investimento com 5-20 clientes. Precisa de análises rápidas e consistentes para recomendar.
- **Dor:** "Não tenho equipe de research. Preciso de um 'time' de analistas que trabalhe 24/7."

### QUEM NÃO COMPRA
- Day trader profissional (precisa de latência de milissegundos, não de análise)
- Institutional investor (precisa de compliance, SOC2, SLA)
- Quem quer "dica quente" ou "sinal milagroso"

---

## 3. QUAL DOR RESOLVE

**"Análise financeira de qualidade é cara e demorada. SuperEzio é um comitê de investimento pessoal por uma fração do custo."**

Evidência do código:
- 6 experts + F51 + SDCA + Trinity = 9 "analistas" trabalhando em cada consulta
- MathHub calcula 13 métricas quantitativas em < 1 segundo
- Mangala caça oportunidades automaticamente (sem o trader precisar garimpar)
- Tudo auditável: decision trace, evidence files, journal

---

## 4. PRICING SUGERIDO

### Modelo: SaaS com assinatura mensal

| Plano | Preço | O que inclui |
|-------|-------|-------------|
| **Free** | $0 | 5 análises/dia, 1 ticker, dados yfinance, sem paper trading |
| **Starter** | $29/mês | 50 análises/dia, 5 tickers, paper trading, journal, email alerts |
| **Pro** | $79/mês | Análises ilimitadas, todos providers, Mangala scan, multi-ticker, API key |
| **Elite** | $199/mês | IBKR paper trading, Questrade integration, priority support, custom experts |

### Justificativa:
- **Free** existe para experimentar. Cobre custo de API (~$0.01/request).
- **Starter** compete com TradingView Premium ($12.95) + Benzinga ($27). Margem: ~80%.
- **Pro** compete com Bloomberg Terminal ($2,000/mês) para o trader que não precisa de Bloomberg.
- **Elite** é para o pequeno gestor. Custa menos que 1 hora de consultoria.

### E se ninguém pagar?
- Corta os planos pagos. Mantém Free + doações (Buy Me a Coffee).
- Ou: vira open-core. Código aberto, SaaS hospedado pago.
- Ou: licença para corretoras (white-label). B2B em vez de B2C.

---

## 5. ENTREGA MÍNIMA VENDÁVEL (V1)

**O que JÁ ESTÁ PRONTO (código real, testado):**
- ✅ Pipeline MathHub + Experts + F51 + SDCA + Trinity + Bob
- ✅ WebGL chart com RSI, MACD, SMA, Bollinger
- ✅ Bob responde com dados reais do pipeline
- ✅ Paper trading com journal e compound tracker
- ✅ JWT auth (register/login)
- ✅ Frontend com expert cards, pipeline progress, trust score
- ✅ 10+ data providers (gratuitos e pagos)
- ✅ Docker + PyInstaller .exe
- ✅ Mangala Engine (score 0-100, flip plan)

**O que FALTA para alguém PAGAR:**
1. ✏️ Onboarding: wizard de primeiro uso → análise guiada em < 5 minutos
2. ✏️ IBKR paper trading REAL (conexão TWS/IB Gateway, não simulação interna)
3. ✏️ Stripe/PayPal integration no frontend (plano pago)
4. ✏️ Email de boas-vindas + tutorial
5. ✏️ Rate limiting por tier (Free: 5/dia, Starter: 50/dia)

**Escopo V1: 5 itens. Estimativa: 2-3 semanas.**

---

## 6. O QUE CORTAR (NÃO DÁ DINHEIRO AGORA)

| Feature | Por que cortar |
|---------|---------------|
| Crypto trading | Mercado diferente, outro compliance, outro público |
| Mobile app nativo | Web responsivo cobre 80%. App nativa é 3 meses extra |
| Fine-tuning do Bob (LoRA) | DeepSeek API é suficiente. Custo de treino > retorno |
| Multi-broker (Alpaca, Questrade execução) | Só IBKR importa para V1 |
| Execução com dinheiro REAL | 3 meses de paper trading validado ANTES de live |
| Agent army autônomo 24/7 | Mangala já cobre o ciclo proativo. Resto é reativo |
| Relatórios PDF | HTML/evidence já existe. PDF é nice-to-have |
| Agentes externos (AlphaSMO, Form4API) | Funcionais mas não essenciais para V1. Deixar como bônus |

---

## 7. COMO EMPACOTAR

### Opção A: SaaS hospedado (recomendado para V1)
- superezio.com → frontend + backend na nuvem
- $20-40/mês servidor (Hetzner, DigitalOcean)
- Usuário acessa pelo browser, zero instalação
- Cobrança via Stripe

### Opção B: Desktop app (PyInstaller)
- SuperEzio.exe (244MB) → download + double-click
- Roda localmente, dados não saem da máquina
- Cobrança via license key

### Opção C: Docker self-hosted
- docker-compose up → tudo sobe
- Para empresas/consultores que querem controle total
- Cobrança via license key ou contrato

**Recomendação V1: Opção A (SaaS) + Opção B (desktop) como alternativa.**

---

## 8. AÇÃO SEGUINTE

1. **Esta semana:** Consertar o último bug do frontend (auth fetch no browser)
2. **Semana que vem:** Integrar Stripe no frontend + rate limiting por tier
3. **Depois:** Configurar IBKR paper trading real
4. **Antes de lançar:** 10 amigos testam. Coletar feedback. Corrigir.
5. **Lançamento:** Post no Reddit (r/algotrading, r/investing). 100 free users.

---

## 9. CHECKPOINT

**Arquivo:** `.f51/checkpoints/latest.json`
**Timestamp:** 2026-07-20
**Decisão:** GO para V1. Escopo: 5 itens. Tempo: 2-3 semanas. Pricing: $0/$29/$79/$199.
**Risco:** Billings não validados. Precisa de 10 beta testers antes de cobrar.
**Gate:** Se 10 beta testers não usarem por 7 dias consecutivos → reavaliar V1.
