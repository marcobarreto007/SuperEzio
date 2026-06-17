# Bob Organismo Vivo 24/7 — Roadmap

**Visão:** Transformar Bob em organismo vivo que opera 24/7, aprende por reforço, sofre com perdas, reflete, evolui.

**Data:** 2026-06-17

---

## Fase 1 — Fundação (CURRENT)

### Objetivo
Criar a infraestrutura base para Bob operar 24/7.

### Entregas

#### 1.1 Market Hours Detection
- **Arquivo:** `src/core/trading/market_hours.py`
- **Função:** Detectar horas de trading US (NYSE/NASDAQ)
- **Features:**
  - `is_market_open()` → bool (US/Eastern timezone)
  - `is_pre_market()` → bool (04:00-09:30 ET)
  - `is_after_hours()` → bool (16:00-20:00 ET)
  - `next_market_open()` → datetime
  - `next_market_close()` → datetime
  - Handler para feriados US

#### 1.2 XP System
- **Arquivo:** `src/core/trading/xp_system.py`
- **Função:** Sistema de experiência e níveis
- **Features:**
  - Tabela de XP por nível (1-100)
  - `gain_xp(amount, source, context)` → void
  - `lose_xp(amount, source, context)` → void
  - `get_level()` → int
  - `get_stats()` → dict (xp, level, progress, next_level)
  - **Fator de dor:**
    - Perda <$100: peso 1x
    - Perda $100-500: peso 2x
    - Perda >$500: peso 5x, flag "trauma"
  - **Bonuses:**
    - Win streak: +50 XP a cada 3 wins
    - Lesson applied: +30 XP
    - Thesis correct: +15 XP

#### 1.3 Lifecycle Loop
- **Arquivo:** `src/core/trading/lifecycle.py`
- **Função:** Loop principal 24/7
- **Estados:**
  - `MARKET_CLOSED` → Estudar histórico, refletir, preparar setups
  - `PRE_MARKET` → Scan pré-market, identificar oportunidades
  - `MARKET_OPEN` → Trading ativo com gates
  - `POST_MARKET` → Análise pós-close, feedback loop
  - `SLEEPING` → Dormir fora de horas US (economizar recursos)
- **Features:**
  - `start_lifecycle()` → inicia loop
  - `stop_lifecycle()` → para loop gracefully
  - `get_state()` → estado atual + contexto
  - Transições automáticas baseadas em market_hours

#### 1.4 Integração XP no Feedback Loop
- **Arquivo:** `src/core/trading/feedback_loop.py`
- **Mudanças:**
  - Adicionar `pain_score` nas lições
  - Integrar com XPSystem
  - Registrar "trauma" em perdas grandes
  - Calibrar confiança baseada em XP/nível

### Testes
```bash
# Market hours
python -c "from core.trading.market_hours import is_market_open; print(is_market_open())"

# XP system
python -c "from core.trading.xp_system import XPSystem; xp = XPSystem(); print(xp.get_level())"

# Lifecycle (dry-run)
python scripts/test_lifecycle.py --dry-run

# Health check
curl http://localhost:8002/lifecycle/status
```

### Critérios de Pronto
- [x] market_hours.py criado com testes
- [ ] xp_system.py criado com testes
- [ ] lifecycle.py criado com testes
- [ ] feedback_loop.py integrado com XP
- [ ] Endpoint /lifecycle/status funcional
- [ ] Testes passando
- [ ] Checkpoint atualizado

---

## Fase 2 — Reforço Learning

### Objetivo
Implementar aprendizado por reforço completo.

### Entregas

#### 2.1 Pain Memory System
- **Arquivo:** `src/core/trading/pain_memory.py`
- **Função:** Memória com pesos baseados em dor
- **Features:**
  - `remember_pain(trade, pain_score)` → armazena com peso
  - `recall_similar_pains(setup)` → retorna dores similares
  - `pain_decay_factor` → dores antigas pesam menos
  - Trauma threshold → perdas >$500 ficam "marcadas"

#### 2.2 Auto-Calibração
- **Arquivo:** `src/core/trading/auto_calibration.py`
- **Função:** Ajustar parâmetros baseado em performance
- **Features:**
  - Calibrar `BUY_CONFIDENCE_THRESHOLD` baseado em win_rate
  - Calibrar `MAX_POSITION_PCT` baseado em drawdown
  - Ajustar `STOP_LOSS_PCT` baseado em volatilidade
  - `apply_calibration()` → atualiza env vars/config

#### 2.3 Reinforcement Learning Loop
- **Arquivo:** `src/core/trading/rl_loop.py`
- **Função:** Loop de aprendizado por reforço
- **Features:**
  - Episódios = trades
  - Rewards = XP + PnL - Dor
  - Q-learning simplificado para decisões
  - `update_q_values(outcome)` → atualiza política

### Testes
```bash
# Pain memory
python -c "from core.trading.pain_memory import PainMemory; pm = PainMemory(); print(pm.get_traumas())"

# Auto-calibração
python scripts/run_calibration.py --dry-run

# RL loop
python scripts/test_rl_loop.py --episodes 100
```

### Critérios de Pronto
- [ ] Pain memory implementada
- [ ] Auto-calibração funcional
- [ ] RL loop rodando
- [ ] Testes passando

---

## Fase 3 — Comitê de Reflexão

### Objetivo
Multi-agent deliberação para decisões críticas.

### Entregas

#### 3.1 Reflection Committee
- **Arquivo:** `src/core/trading/committee.py`
- **Função:** Multi-agent para deliberar
- **Membros:**
  - **Cautious (Prudente):** Foca em risco, sempre vê o lado negativo
  - **Optimist (Otimista):** Foca em upside, vê oportunidade
  - **Analyst (Analista):** Dados puros, sem emoção
  - **Historian (Historiador):** Baseado em histórico, lições passadas
- **Features:**
  - `deliberate(trade_setup)` → votos + consenso
  - `vote_breakdown` → ver quem votou o quê
  - `override_threshold` → se X% discorda, para

#### 3.2 Post-Trade Review
- **Arquivo:** `src/core/trading/post_trade_review.py`
- **Função:** Análise automática pós-trade
- **Features:**
  - `review_trade(trade_id)` → análise completa
  - Comparar verdict vs outcome
  - Gerar lição automaticamente
  - Atualizar XP

#### 3.3 Daily Standup
- **Arquivo:** `src/core/trading/daily_standup.py`
- **Função:** Relatório diário do Bob
- **Features:**
  - Resumo do dia (trades, PnL, XP)
  - O que aprendeu
  - O que vai fazer amanhã
  - Nível atual, próximo objetivo

### Testes
```bash
# Committee
python -c "from core.trading.committee import Committee; c = Committee(); print(c.deliberate({'ticker': 'AAPL', 'thesis': '...'}))"

# Post-trade review
python scripts/review_trade.py --trade_id xyz123

# Daily standup
python scripts/daily_standup.py
```

### Critérios de Pronto
- [ ] Committee implementado
- [ ] Post-trade review automático
- [ ] Daily standup gerando relatórios
- [ ] Testes passando

---

## Fase 4 — Auto-Execution

### Objetivo
Execução automática com segurança.

### Entregas

#### 4.1 Auto-Executor
- **Arquivo:** `src/core/trading/auto_executor.py`
- **Função:** Executar ordens automaticamente
- **Gates:**
  - Confidence ≥ threshold
  - Liquidez ≥ minimum
  - Gates da F51 aprovados
  - Comitê ≥ 50% concordância
  - Kill switch OFF
  - Daily PnL não estourou limite
- **Features:**
  - `execute_candidate(candidate)` → order_id ou rejeição
  - `check_all_gates(candidate)` → dict com status de cada gate
  - Rate limiting (max X trades por dia)

#### 4.2 Position Management
- **Arquivo:** `src/core/trading/position_manager.py`
- **Função:** Gerenciar posições abertas
- **Features:**
  - Trailing stop loss
  - Take profit parcial
  - Scale in/out baseado em confirmação
  - `manage_positions()` → revisa todas abertas

#### 4.3 Risk Guard
- **Arquivo:** `src/core/trading/risk_guard.py`
- **Função:** Proteção contra excessos
- **Features:**
  - Max drawdown diário (para se estourar)
  - Max exposure por setor
  - Max correlação entre posições
  - `check_risk()` → verde/amarelo/vermelho

### Testes
```bash
# Auto-executor (dry-run)
python scripts/test_auto_executor.py --dry-run

# Position manager
python -c "from core.trading.position_manager import PositionManager; pm = PositionManager(); print(pm.manage_positions())"

# Risk guard
python scripts/check_risk.py
```

### Critérios de Pronto
- [ ] Auto-executor com gates
- [ ] Position manager funcional
- [ ] Risk guard ativo
- [ ] Testes passando

---

## Fase 5 — Interface & Monitoramento

### Objetivo
Dashboard em tempo real do Bob.

### Entregas

#### 5.1 Frontend Dashboard
- **Arquivo:** `frontend/borg-dashboard.html`
- **Features:**
  - Estado atual (trading, learning, dormindo)
  - XP e nível
  - Trades em tempo real
  - Performance (PnL, win rate)
  - Lições recentes
  - Comitê votes (últimas decisões)
  - Log de atividades

#### 5.2 WebSocket Events
- **Arquivo:** `src/agent_server/endpoints.py` (extensão)
- **Events:**
  - `state_changed` → novo estado
  - `trade_opened` → nova posição
  - `trade_closed` → posição fechada
  - `xp_gained` → XP mudou
  - `committee_vote` → resultado de votação
  - `lesson_learned` → nova lição

#### 5.3 API Endpoints
- **Arquivo:** `src/agent_server/endpoints.py` (extensão)
- **Endpoints:**
  - `GET /borg/state` → estado atual
  - `GET /borg/xp` → XP e nível
  - `GET /borg/trades` → trades recentes
  - `GET /borg/lessons` → lições
  - `POST /borg/manual-override` → intervenção manual
  - `POST /borg/emergency-stop` → para tudo

### Testes
```bash
# Dashboard (server deve estar rodando)
# Abrir http://localhost:8002/frontend/borg-dashboard.html

# WebSocket
wscat -c ws://localhost:8002/ws/borg

# API
curl http://localhost:8002/borg/state
curl http://localhost:8002/borg/xp
```

### Critérios de Pronto
- [ ] Dashboard funcional
- [ ] WebSocket events rodando
- [ ] API endpoints funcionando
- [ ] Testes passando

---

## Cronograma Estimado

| Fase | Duração Estimada | Dependências |
|------|-----------------|--------------|
| Fase 1 | 3-5 dias | — |
| Fase 2 | 5-7 dias | Fase 1 |
| Fase 3 | 5-7 dias | Fase 1, Fase 2 |
| Fase 4 | 7-10 dias | Fase 1, Fase 2, Fase 3 |
| Fase 5 | 3-5 dias | Fase 1, Fase 4 |
| **Total** | **23-34 dias** | — |

---

## Riscos e Mitigações

### Risco 1: Loop Infinito Sem Controle
- **Descrição:** Bob entra em loop de trading sem parar
- **Mitigação:**
  - Kill switch sempre disponível
  - Max trades por dia (configurável)
  - Timeout em cada estado
  - Health check externo

### Risco 2: Market Hours Detection Falhando
- **Descrição:** Bob tradar fora de horas
- **Mitigação:**
  - NTP sync para hora precisa
  - Fallback para API externa
  - Log de toda mudança de estado
  - Manual override

### Risco 3: XP Mal Calibrado
- **Descrição:** Bob "level up" com perdas
- **Mitigação:**
  - Testes extensivos com dados históricos
  - Simulação antes de produção
  - Ajustes baseados em backtesting
  - Rate limiting de XP

### Risco 4: Auto-Execution Sem Gates
- **Descrição:** Ordem acidental em produção
- **Mitigação:**
  - Multi-layer gates
  - Paper mode obrigatório no início
  - Audit log de toda decisão
  - Requer aprovação para trades grandes

---

## Próximos Passos (Imediatos)

1. ✅ Roadmap salvo
2. ⏳ Criar `market_hours.py`
3. ⏳ Criar `xp_system.py`
4. ⏳ Criar `lifecycle.py`
5. ⏳ Integrar XP no `feedback_loop.py`
6. ⏳ Testes da Fase 1
7. ⏳ Atualizar checkpoint

---

**Status:** Fase 1 em andamento
**Última atualização:** 2026-06-17
**Responsável:** Bob (implementador) + Deep (auditor)
