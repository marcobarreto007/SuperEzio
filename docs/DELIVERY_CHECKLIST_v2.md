# SUPEREZIO — Delivery Checklist Final
# Release: Zero-Garbage-Runtime v2 (2026-06-16)
# Alvo: 10/10

---

## ⬜ PRÉ-VOO (antes de ligar qualquer coisa)

- [ ] **M1 — TWS Presets:** desmarcar TIF automático no Global Configuration do TWS
  - Abrir TWS → File → Global Configuration → Orders → uncheck "Use TIF DAY as default"
  - Isso evita que ordens GTC sejam auto-canceladas como DAY
  - Tempo: 2 min

- [ ] Verificar `.env` configurado com todas as chaves:
  - [ ] `FINNHUB_API_KEY`
  - [ ] `SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT=1`
  - [ ] `IBKR_HOST=127.0.0.1`, `IBKR_PORT=7497`, `IBKR_CLIENT_ID`
  - [ ] `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`

- [ ] TWS Paper Trading aberto e conectado na porta 7497
  - [ ] Equity visível (~$100K paper)
  - [ ] Sem posições abertas (limpo para teste)

---

## ⬜ BOOT SEQUENCE

- [ ] Terminal 1: CEO (llama.cpp)
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\serve_agent_llamacpp.ps1 -Port 8082
  ```
  Aguardar `llama.cpp` responder em http://127.0.0.1:8082/health (200 OK)

- [ ] Terminal 2: API + Frontend
  ```powershell
  python -m agent_server.main
  ```
  Aguardar Uvicorn: `Uvicorn running on http://127.0.0.1:8002`

- [ ] Verificar health endpoints:
  ```powershell
  curl.exe -fsS http://127.0.0.1:8082/health   # CEO
  curl.exe -fsS http://127.0.0.1:8002/health   # API
  curl.exe -fsS http://127.0.0.1:8002/health/details
  ```

---

## ⬜ VERIFICAÇÃO PRÉ-TRADE

- [ ] Rodar suíte de testes completa:
  ```powershell
  python -m pytest tests/ -q
  ```
  ✅ Esperado: 1250 passed, 0 failed

- [ ] Rodar smoke test do browser:
  ```powershell
  $env:SUPEREZIO_SMOKE_HEADED = "1"
  python scripts/browser_smoke.py --headed
  ```

- [ ] Verificar cockpit:
  - [ ] Abrir http://127.0.0.1:8002 no browser
  - [ ] Genie panel carregando (sentimento watchlist)
  - [ ] Deep Panel visível (coluna direita, experts + math)
  - [ ] IBKR Mirror mostrando conexão + equity
  - [ ] Bob flutuante funcional

- [ ] Smoke: enviar 1 prompt simples pro Bob:
  ```
  "Oi Bob, como estamos?"
  ```
  - [ ] Bob responde com status do sistema
  - [ ] IBKR status visível na resposta
  - [ ] CALIBRAGEM visível (se houver trades anteriores)

---

## ⬜ TESTE DE INTEGRAÇÃO E CARGA (TRADING LOOPS)

- [ ] Rodar os testes de loop de trading integrados para estresse simulado:
  ```powershell
  python -m pytest tests/test_trading_loop1.py tests/test_trading_loop3.py tests/test_trading_loop4.py tests/test_trading_loop5.py -q
  ```
  Este conjunto testa a análise do Bob sob diferentes condições de loops e submissão simulada.

- [ ] Analisar os resultados dos testes de loop:
  - [ ] Zero falhas nos testes de fluxo de trade e gates de decisão.
  - [ ] Latência monitorada.
  - [ ] Routing validado: correct matching de envelopes.
  - [ ] Zero crashes inesperados de runtime.

- [ ] **M3 — Paper Trading Real (25 ordens):**
  O modo legado `--direct-only` foi aposentado porque contornava a preparação
  adaptativa. Qualquer teste de submissão deve entrar pelo fluxo canônico,
  produzir um `PreparedOrderEnvelope` aprovado e permanecer em paper trading.
  A ativação isolada de uma variável de ambiente não autoriza uma ordem.

- [ ] Verificar TWS após stress:
  - [ ] Ordens aparecem na aba "Orders"
  - [ ] Status: Submitted (fora do horário de mercado) ou Filled (durante)
  - [ ] Equity paper reflete posições

- [ ] Verificar IBKR Mirror no cockpit:
  - [ ] Posições visíveis em tempo real
  - [ ] Ordens ativas listadas
  - [ ] Trade history populado

---

## ⬜ FALLBACK TEST

- [ ] **M2 — CEO Fallback:**
  ```powershell
  # No terminal do CEO, Ctrl+C pra derrubar
  # Verificar se API detecta queda
  curl.exe http://127.0.0.1:8002/health/details
  ```
  - [ ] API reporta CEO offline
  - [ ] Frontend mostra status "CEO: OFFLINE"
  - [ ] Sistema degrada graciosamente (sem crash)

- [ ] Religar CEO e verificar recuperação:
  - [ ] API detecta CEO online novamente
  - [ ] Frontend volta ao normal

---

## ⬜ PÓS-TRADE

- [ ] Verificar métricas no banco:
  ```powershell
  python -c "
  import sqlite3
  conn = sqlite3.connect('runtime/investor.db')
  # Sentiment history
  cnt = conn.execute('SELECT COUNT(*) FROM sentiment_history').fetchone()[0]
  print(f'sentiment_history rows: {cnt}')
  # Decision traces
  cnt2 = conn.execute('SELECT COUNT(*) FROM decision_traces').fetchone()[0]
  print(f'decision_traces rows: {cnt2}')
  conn.close()
  "
  ```
  - [ ] `sentiment_history` > 0 (D3 fix verificado!)
  - [ ] `decision_traces` populado

- [ ] Gerar relatório de performance:
  ```powershell
  python scripts/journal_review.py
  ```

- [ ] Verificar logs de erro:
  ```powershell
  Get-Content runtime/logs/*.log -Tail 50 | Select-String "ERROR|CRITICAL"
  ```
  Esperado: zero ERRORs (só warnings normais de provider)

---

## ⬜ SIGN-OFF FINAL

```
SUPEREZIO DELIVERY v2 — 2026-06-16
===================================
Tests:         1250/1250 passing  [ ]
Stress:        25 ordens pipeline [ ]
IBKR Mirror:   LIVE positions    [ ]
Sentimento DB: rows > 0          [ ]
Deep Panel:    coluna própria    [ ]
CEO Fallback:  testado           [ ]
TWS Presets:   configurado       [ ]
Paper Trades:  25 executados     [ ]

Nota final: _____/10
Assinatura:  ___________________
Data:        ____-__-__
```

---

## 📊 REFERÊNCIA RÁPIDA

| `python -m agent_server.main` | Iniciar API + frontend |
| `scripts/serve_agent_llamacpp.ps1 -Port 8082` | Iniciar CEO |
| `python -m pytest tests/ -q` | Suíte completa |
| `python -m pytest tests/test_trading_loop*.py -q` | Teste dos loops de trading |
| `python scripts/browser_smoke.py --headed` | Smoke visual |
| `python scripts/_ibkr_order.py BUY AAPL 10 150.00` | Transporte aposentado; sempre bloqueia |
| `curl.exe http://127.0.0.1:8002/cockpit/summary` | Status JSON |
| `curl.exe http://127.0.0.1:8002/sentiment/history/AAPL/db?days=7` | Histórico sentimento |
