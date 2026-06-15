# SuperEzio — Runbook Operacional

## Iniciar o sistema (ordem correta)

```powershell
# 1. CEO (llama.cpp local)
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082
# Aguardar: http://127.0.0.1:8082/health retornar {"status":"ok"}

# 2. API Server
cd "C:\Users\marco\Desktop\SuperEzio Financeiro"
.venv\Scripts\python -m agent_server.main
# Aguardar: http://127.0.0.1:8002/health retornar {"status":"ok"}

# 3. Cockpit
# Abrir http://127.0.0.1:8002 no navegador
# Status bar deve mostrar CEO: ONLINE
```

## Verificar saúde

```powershell
# Health check rápido
curl http://127.0.0.1:8002/health

# Detalhado (GPU, provedores, IBKR, guardrails)
curl http://127.0.0.1:8002/health/details

# Cockpit data
curl http://127.0.0.1:8002/cockpit/summary
```

## Sinais vitais normais

| Indicador | Normal | Degradado | Crítico |
|---|---|---|---|
| CEO | ONLINE | — | OFFLINE (GPU caiu) |
| Genie | online (<1500 req) | degraded (>1400 req) | offline (cota estourada) |
| Deep | online | degraded (sem key) | offline (API caiu) |
| IBKR | PAPER CONNECTED | — | OFFLINE (TWS fechada) |
| Guardrails | 30/30 | — | <30 (módulo falhou) |
| Latência | <500ms | 500ms-2s | >2s |

## O que fazer quando algo quebra

### CEO offline (llama.cpp caiu)

```
Sintoma: Status bar "CEO: OFFLINE"
Causa: GPU crash, OOM, driver update
Ação:
  1. Fechar llama-server (matar processo)
  2. scripts/serve_agent_llamacpp.ps1 -Port 8082
  3. Se não subir: reiniciar máquina
  4. Se GPU morreu: configurar fallback Code Plan
```

### DeepSeek offline (API caiu)

```
Sintoma: Experts retornam erro
Ação:
  1. Esperar 10min (rate limit temporário)
  2. Se >30min: Gemini assume experts (automático)
  3. Verificar crédito na conta DeepSeek
```

### IBKR offline (TWS caiu)

```
Sintoma: Status bar "IBKR: OFFLINE"
Ação:
  1. Abrir TWS Workstation
  2. Verificar conexão em File > Global Configuration > API > Settings
  3. Porta deve ser 7497, "Enable ActiveX and Socket Clients" marcado
  4. Reiniciar TWS
```

### Browser mostra tela branca

```
Sintoma: Cockpit não carrega
Ação:
  1. F12 > Console. Ver erros JS.
  2. Verificar se API server está rodando: curl http://127.0.0.1:8002/health
  3. Se JS quebrou: limpar cache (Ctrl+Shift+R)
  4. Se API offline: reiniciar agent_server.main
```

## Rotina diária

```
09:00 — Ligar sistema (CEO + API + IBKR)
09:05 — Verificar cockpit: todos ONLINE
09:10 — Checar Genie: sentimento overnight
09:15 — Checar Deep: última análise
09:30 — Operar (papel)
16:00 — Market close. Verificar PnL.
23:00 — Rodar ciclo de aprendizado:
         python scripts/run_learning_cycle.py
23:05 — Verificar lições extraídas
23:10 — Backup:
         powershell -File scripts/backup.ps1
23:15 — Desligar (opcional: sistema pode rodar 24h)
```

## Nunca fazer

```
❌ Fechar TWS durante trade aberto
❌ Desligar máquina sem commitar
❌ Alterar .env com sistema rodando
❌ Executar scripts/ sem ler o que fazem
❌ Conectar IBKR live (porta 7496) — somente paper (7497)
❌ Compartilhar .env com APIs keys
```

## Comandos de emergência

```powershell
# Parar tudo
Get-Process python, llama-server | Stop-Process -Force

# Ver o que está rodando
Get-Process python, llama-server, java | Select Name, Id, CPU

# Backup de emergência
robocopy "data" "D:\backups\emergency\data" /MIR
robocopy "config" "D:\backups\emergency\config" /MIR

# Ver logs
Get-Content runtime\logs\*.log -Tail 50

# Testes rápidos pós-recovery
python -m pytest tests/ -q --tb=short
```
