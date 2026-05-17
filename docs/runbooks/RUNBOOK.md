# Runbook Oficial — SuperEzio Agent Server v4.0.0

> Atualizado: 2026-05-17 | Validado com pipeline test ao vivo

## 1. Servico / Componente

- **Nome**: SuperEzio Agent Server (`agent_server`)
- **Dono**: Marco Barreto / Fuch F51 Labs
- **Criticidade**: Critica (P0) — Portal de entrada de decisoes financeiras e orquestracao de agentes.

## 2. Pre-requisitos e Portas

| Componente | Porta | Descricao |
|-----------|-------|-----------|
| CEO (Qwen3.6-35B) | 8082 | llama-server com GGUF Q4_K_M, MTP speculative decoding |
| API (FastAPI) | 8002 | agent_server.main — A2A protocol, SSE streaming |

- **Variaveis de Ambiente**: `.env` na raiz do projeto (55 variaveis, 12+ API keys)
- **Dependencias**: Python `.venv`, `llama.cpp/bin/llama-server.exe`, `models/qwen36-35b-f51.Q4_K_M.gguf` (20.22GB)

## 3. Inicializacao

### Lancamento com um clique

```cmd
C:\Users\marco\Desktop\SuperEzio\desktop\SuperEzio.bat
```

O launcher:
1. Carrega `.env`
2. Mata processos antigos nas portas 8082 e 8002
3. Inicia CEO (llama-server) em janela separada
4. Aguarda CEO health (:8082/health)
5. Inicia API em janela separada
6. Aguarda API health (:8002/health)
7. Abre navegador em http://127.0.0.1:8002

### Manual

```powershell
# Terminal 1 — CEO
powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082

# Terminal 2 — API
python -m agent_server.main
```

## 4. Health Checks

### API Liveness (publico)
```bash
curl http://127.0.0.1:8002/health
# → {"status":"ok","agent":"generic_agent","version":"3.0.0"}
```

### API Readiness (detalhado)
```bash
curl http://127.0.0.1:8002/health/details
# → {"status":"ok","checks":{"gpu":{...},"local_models":{...},"redis":{...}}}
```

### CEO Liveness
```bash
curl http://127.0.0.1:8082/health
# → {"status":"ok"}
```

## 5. Diagnostico Rapido

### Porta 8002 ocupada
```powershell
Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8002).OwningProcess -Force
```

### Porta 8082 ocupada
```powershell
Get-NetTCPConnection -LocalPort 8082 -ErrorAction SilentlyContinue
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8082).OwningProcess -Force
```

### CEO offline (`degraded_no_backend`)
1. Verificar se `llama-server.exe` esta rodando: `Get-Process llama-server -ErrorAction SilentlyContinue`
2. Verificar se o GGUF existe: `Test-Path models/qwen36-35b-f51.Q4_K_M.gguf`
3. Reiniciar: `powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082`

### API nao sobe
1. Verificar se `.venv` existe: `Test-Path .venv\Scripts\python.exe`
2. Verificar dependencias: `.venv\Scripts\python -c "import fastapi, uvicorn, langgraph"`
3. Verificar se CEO esta rodando primeiro (API depende dele)

## 6. Comandos de Verificacao

```powershell
# Lint
python -m ruff check src tests

# Formato
python -m ruff format --check src tests

# Testes completos
python -m pytest tests/ -q

# Apenas contratos
python -m pytest tests/contracts/ -q
```

## 7. Pipeline Flow Completo

```
POST /task/submit (A2AMessage {from, to, type:TASK.SUBMIT, payload:{ticker, time_horizon}})
  → Orchestrator (classifica intent)
  → DataCollector (ProfessionalCollector, 8 providers)
  → F51Engine (gates, formulas, verdict)
  → Experts (6 DeepSeek agents em paralelo)
  → NeuralDecisionExpert (directional prob, regime)
  → RAG Forensics (historical fraud patterns)
  → CEO Qwen3.6-35B (verdict BUY/SELL/HOLD, target, stop loss)
  → Explanation (gate factors audit)
  → SSE Stream end
```

## 8. Checkpoints

- Operacional: `.f51/checkpoints/latest.json`
- Runtime: `runtime/checkpoints/latest.json`
- Toda acao de recovery deve atualizar ambos.
