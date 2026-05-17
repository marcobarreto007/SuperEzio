# Runbook Oficial — SuperEzio Agent Server

Este runbook define as diretivas de operação, monitoramento, diagnóstico e recuperação do servidor FastAPI (`agent_server`) no ambiente de produção local.

---

## 1. Serviço / Componente

* **Nome**: SuperEzio Agent Server (`agent_server`)
* **Dono**: Marco Barreto / Fuch F51 Labs
* **Criticidade**: **Crítica (P0)** — Portal de entrada de decisões financeiras e orquestração de agentes.

---

## 2. Pré-requisitos e Portas

* **Variáveis de Ambiente Necessárias**:
  * `A2A_PORT` (Porta do servidor local, default: `8002`)
  * `A2A_BIND` (Interface de rede local, default: `127.0.0.1`)
  * `A2A_AGENT_NAME` (Identificador do agente, default: `generic_agent`)
  * `UNIVERSAL_SKIP_GATEWAY` (Ignora verificação inicial do EdgeGateway, default: `1` para testes de integração)
* **Dependências de Infraestrutura**:
  * Python virtualenv ativo (`.venv`)
  * Porta local `8002` livre e acessível.
  * Llama-server local rodando (Qwen3.6-35B em `8000`) para vereditos finais de IA.

---

## 3. Inicialização e Start

### Comando Principal (Canônico)
Para rodar em ambiente Windows local sob PowerShell:
```powershell
python -m agent_server.main
```

### Inicialização em Background (F51-Dev)
Para subir o servidor em segundo plano e persistir logs:
```powershell
Start-Job -Name "SuperEzio_Server" -ScriptBlock { cd c:\Users\marco\Desktop\SuperEzio; .venv\Scripts\python -m agent_server.main }
```

---

## 4. Health Checks e Monitoramento

O servidor FastAPI disponibiliza dois níveis de checagem de saúde operacional:

### A. Health Check Público (Liveness)
* **Endpoint**: `http://127.0.0.1:8002/health`
* **Método**: `GET`
* **Uso**: Checagem rápida de conectividade e status básico da API.
* **Resultado Esperado (200 OK)**:
  ```json
  {
      "status": "ok",
      "app": "SuperEzio A2A Server",
      "health": "/health",
      "details": "/health/details"
  }
  ```

### B. Health Check Profundo (Readiness)
* **Endpoint**: `http://127.0.0.1:8002/health/details`
* **Método**: `GET`
* **Uso**: Checagem profunda. Verifica GPU local, modelos carregados em llama.cpp, conexão com Redis, status do provedor de custos (CostGuard) e APIs de terceiros.
* **Resultado Esperado (200 OK)**:
  ```json
  {
      "status": "ok",
      "checks": {
          "gpu": { "driver_version": "...", "gpus": [...] },
          "local_models": { "active": true, "list": [...] },
          "redis": { "reachable": true },
          "cost_guard": { "status": "active", "total_spent_today": 0.0 }
      }
  }
  ```

---

## 5. Diagnóstico Rápido e Recovery

### Erro 1: `OSError: [Errno 98] Address already in use` (Porta 8002 ocupada)
* **Sintoma**: O servidor falha ao iniciar e desliga imediatamente.
* **Ação de Recuperação (PowerShell)**:
  1. Identifique o processo que ocupa a porta `8002`:
     ```powershell
     Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue
     ```
  2. Finalize o processo ocupante de forma forçada:
     ```powershell
     Stop-Process -Id (Get-NetTCPConnection -LocalPort 8002).OwningProcess -Force -ErrorAction SilentlyContinue
     ```
  3. Re-inicie o servidor com:
     ```powershell
     python -m agent_server.main
     ```

### Erro 2: `degraded_no_backend` (Llama-Server inacessível)
* **Sintoma**: O endpoint `/health/details` retorna status degradado e o modelo de IA falha ao gerar vereditos.
* **Ação de Recuperação**:
  1. Verifique se o Llama-server local na porta `8000` está ativo.
  2. Se inativo, inicialize o servidor do modelo local usando o runbook de IA.

---

## 6. Checkpoints de Operação
Toda ação de reinicialização ou recuperação executada em produção local pelo operador ou agente deve atualizar a trilha em `.f51/checkpoints/latest.json` e registrar o status na pasta `runtime/checkpoints/`.
