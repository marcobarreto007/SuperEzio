# SuperEzio Core
### Local-First Autonomous Algorithmic Investment Platform
*(🇧🇷 Para a versão em português, role para baixo / Scroll down for the Portuguese version)*

**SuperEzio Core** is a production-grade, offline-first multi-agent decision and execution platform for quantitative portfolio management. It orchestrates deterministic financial experts, an adversarial decision stack, and real-time Interactive Brokers (IBKR) paper execution. The platform is designed to run entirely locally using the **F51 Nitro-MoE** runtime, enabling massive 80B parameter MoE models to execute at high throughput on consumer-grade hardware.

---

## 📐 Platform Architecture

```text
                     ┌────────────────────────────────────────┐
                     │    Browser UI (http://127.0.0.1:8002)  │
                     └───────────────────┬────────────────────┘
                                         │
                                         ▼
                     ┌────────────────────────────────────────┐
                     │    FastAPI Server Engine (:8002)       │
                     └───────────────────┬────────────────────┘
                                         │
                                         ▼
                     ┌────────────────────────────────────────┐
                     │      LangGraph v4 State Machine        │
                     └───────────────────┬────────────────────┘
                                         │
       ┌─────────────────────────────────┴────────────────────────────────┐
       ▼                                                                  ▼
 ┌───────────────┐                                                  ┌───────────────┐
 │ Orchestrator  │ Intent Classification & Conditional Routing      │  Blocked Node │
 └───────┬───────┘                                                  └───────────────┘
         │
         ▼
 ┌───────────────┐
 │   Auto Full   │
 │   Analysis    │ Parallel Evidence Collection & Evaluation
 └───────┬───────┘
         ├─► [1] DataHub: Price, fundamentals, technicals, macro context
         ├─► [2] Expert Committee: Fan-out of 6 quantitative experts
         ├─► [3] Portfolio Snapshot: Real-time IBKR paper positions inject
         └─► [4] Decision Stack: F51 Verdict, Neural Decision, SDCA Firewall, ForensicRAG
                 │
                 ▼
 ┌───────────────┐
 │   Agent Node  │ Bob CEO (ReAct reasoning loop) via Local Qwen3 80B
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │  Auto-Execute │ Parses PAPER_TICKET, applies risk-sizing gates (10% max ticket,
 │     Paper     │ 50% concentration limit), and submits orders to IBKR TWS.
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │  Explanation  │ Streams NDJSON analysis and trade execution data to UI
 └───────────────┘
```

---

## 🛠️ Key Engine Components

### 1. LangGraph Decision & Execution DAG
The core routing pipeline uses a deterministic Directed Acyclic Graph (DAG) built on **LangGraph**. The LLM is confined to pure reasoning nodes, ensuring that intent classification, data collection, and trading orders run under deterministic, verifiable software constraints.

### 2. Multi-Perspective Expert Committee
Every ticker analysis triggers a parallel fan-out across 6 distinct quantitative experts:
- **Macro Risk:** Examines high-level market indicators and credit trends.
- **Fundamental Value:** Scores valuation metrics (P/E, EV/EBITDA, Free Cash Flow).
- **Momentum Technical:** Computes key technical indicators (RSI, MACD, moving average crossovers).
- **Contrarian Opportunity:** Identifies oversold deviations and structural turnarounds.
- **Sentiment:** Analyzes news sentiment and market expectation shifts.
- **Social Forensics:** Monitors retail volume activity, short interest, and community catalyst signs.

### 3. F51 Verdict Engine & Decision Stack
Before the agent formulates its final thesis, the data passes through a multi-layered verification firewall:
- **F51 Verdict:** A deterministic scoring engine mapping confidence, data anomalies, and uncertainty metrics.
- **Neural Decision:** A localized pattern-matching engine detecting structural setups.
- **SDCA Firewall:** A cognitive risk guard protecting against FOMO, leverage traps, and stale market signals.
- **ForensicRAG:** Extracts paged documentation snippets, preventing hallucinated calculations.

### 4. Interactive Brokers (IBKR) Trading Engine
When the CEO agent decides to execute a position, it outputs a formatted `PAPER_TICKET`. The platform intercepts this ticket, runs safety check gates, and automatically executes trades:
- **Concentration Gate:** Rejects orders if a ticker would exceed 50% of the total portfolio net liquidation value.
- **Sizing Gate:** Limits individual order values to a maximum of 10% of total equity.
- **Execution:** Connects to IBKR Trader Workstation (TWS) or IB Gateway to place Limit (LMT) or Market (MKT) orders.
- **Audit Logging:** Saves transaction outcomes, execution fill prices, PnL tracking, and post-trade reflection parameters to a local SQLite database audited via `PaperJournal`.

---

## 🚀 Local Model Engine (F51 Nitro-MoE)

SuperEzio runs its core cognitive decisions on a local **Qwen3-Next-80B-A3B Instruct Abliterated** model using GGUF format with `llama-server`. 

To run a model of this magnitude on consumer hardware (e.g., RTX 5060 Ti 16GB, 64GB DDR5 RAM), the platform utilizes **F51 Nitro** tiered expert allocation:
- **Tiered Memory:** Attention layers and KV caches are pinned in GPU VRAM (~6.3 GB).
- **Active Paging:** All 512 experts live in system RAM (DDR5) and are processed on the CPU or streamed to the GPU on demand. 
- **Performance:** Achieves **38.7 tok/s at 256K context**—avoiding the VRAM oversubscription that slows naive GPU-only loads down to 8.4 tok/s due to driver page-fault swap loops.

---

## ⚡ Quickstart

### 1. Environment Setup
Clone the repository and install the project in editable mode using `uv` (recommended) or standard `pip`:
```bash
# Using Python Virtual Environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies and project in editable mode
pip install -e .
```

### 2. Configuration
Copy the environment template and configure your ports and keys. If you want to run completely offline, leave external API keys empty:
```bash
cp .env.example .env
```

### 3. Run the Local Model Server (CEO Engine)
Start the local model server to host the 80B model on port `8082`:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082
```

### 4. Start the FastAPI Application Server
Run the FastAPI web backend. The server binds to port `8002` by default:
```bash
python -m agent_server.main
```

### 5. Access the Platform UI
Open your browser and navigate to:
```text
http://127.0.0.1:8002
```
*(Or double-click the `OPEN_UI.url` shortcut in the project root).*

---

## 🧪 Testing & Verification

SuperEzio enforces strict quality gates to guarantee deterministic behavior and prevent memory leaks.

```bash
# 1. Run the entire pytest suite (1,100+ contract, unit, and integration tests)
python -m pytest tests/ -q

# 2. Run lint check and automatic formatting check
python -m ruff check src tests
python -m ruff format --check src tests

# 3. Execute End-to-End browser UI smoke tests (Playwright)
python scripts/browser_smoke.py --headed

# 4. Trigger the comprehensive Pre-Delivery Gate validation script
powershell -ExecutionPolicy Bypass -File scripts/verify_zero_garbage_runtime.ps1
```

> [!IMPORTANT]
> The `verify_zero_garbage_runtime.ps1` script runs 12 validation gates including boot smoke tests, contract checks, integration coverage, secret-leak guard checks, and memory footprint validation.

---

## 📈 Environment Reference

Key variables inside your `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPEREZIO_CEO_BASE_URL` | Base URL of the local/cloud CEO model gateway | `http://127.0.0.1:8082/v1` |
| `SUPEREZIO_HOST` | FastAPI bind address | `127.0.0.1` |
| `SUPEREZIO_PORT` | FastAPI server port | `8002` |
| `SUPEREZIO_DEEPSEEK_API_KEY` | Optional key for cloud experts (fallback) | *(Optional)* |
| `FINNHUB_API_KEY` | Finnhub API Key for real-time market catalysts | *(Optional)* |
| `TWELVE_DATA_API_KEY` | Twelve Data API Key for stock candles | *(Optional)* |

---

## 📜 License
MIT License with Attribution — Copyright (c) 2025-2026 Marco Barreto. See [LICENSE](LICENSE) for details.

<br><br><br>

---
---

# 🇧🇷 SuperEzio Core (Versão em Português)
### Plataforma Autônoma de Investimentos Algorítmicos Local-First

**SuperEzio Core** é uma plataforma multi-agente offline-first de nível de produção, focada em decisão e execução para gestão quantitativa de portfólios. Ela orquestra especialistas financeiros determinísticos, uma stack de decisão adversária e execução de ordens em tempo real via Interactive Brokers (IBKR) em modo paper. A plataforma foi projetada para rodar de forma totalmente local usando o runtime **F51 Nitro-MoE**, permitindo que modelos massivos MoE de 80B de parâmetros executem com alto throughput em hardwares de consumidor.

---

## 📐 Arquitetura da Plataforma

```text
                     ┌────────────────────────────────────────┐
                     │    Browser UI (http://127.0.0.1:8002)  │
                     └───────────────────┬────────────────────┘
                                         │
                                         ▼
                     ┌────────────────────────────────────────┐
                     │    Motor Servidor FastAPI (:8002)      │
                     └───────────────────┬────────────────────┘
                                         │
                                         ▼
                     ┌────────────────────────────────────────┐
                     │   Máquina de Estado LangGraph v4       │
                     └───────────────────┬────────────────────┘
                                         │
       ┌─────────────────────────────────┴────────────────────────────────┐
       ▼                                                                  ▼
 ┌───────────────┐                                                  ┌───────────────┐
 │ Orquestrador  │ Classificação de Intenção & Roteamento           │  Nó Bloqueado │
 └───────┬───────┘ Condicional                                      └───────────────┘
         │
         ▼
 ┌───────────────┐
 │ Análise Total │ Coleta Paralela de Evidências & Avaliação
 │ Automática    │
 └───────┬───────┘
         ├─► [1] DataHub: Preço, fundamentos, técnicos, contexto macro
         ├─► [2] Comitê de Especialistas: Fan-out de 6 especialistas quantitativos
         ├─► [3] Snapshot de Portfólio: Injeção em tempo real das posições paper IBKR
         └─► [4] Stack de Decisão: F51 Verdict, Decisão Neural, Firewall SDCA, ForensicRAG
                 │
                 ▼
 ┌───────────────┐
 │    Nó do      │ Bob CEO (Ciclo de raciocínio ReAct) via Local Qwen3 80B
 │   Agente      │
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │ Auto-Executar │ Analisa o PAPER_TICKET, aplica limites de risco (ticket máx 10%,
 │     Paper     │ limite concentração 50%), e envia ordens ao IBKR TWS.
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │  Explicação   │ Faz stream de NDJSON de análise e dados de execução para a UI
 └───────────────┘
```

---

## 🛠️ Principais Componentes do Motor

### 1. LangGraph Decision & Execution DAG
O pipeline de roteamento central usa um Grafo Acíclico Direcionado (DAG) determinístico construído no **LangGraph**. O LLM é restrito a nós de raciocínio puro, garantindo que a classificação de intenção, coleta de dados e ordens de negociação ocorram sob restrições de software determinísticas e verificáveis.

### 2. Comitê de Especialistas Multi-Perspectiva
Cada análise de ativo dispara um fan-out paralelo através de 6 especialistas quantitativos distintos:
- **Risco Macro:** Examina indicadores de mercado de alto nível e tendências de crédito.
- **Valor Fundamental:** Pontua métricas de valuation (P/E, EV/EBITDA, Free Cash Flow).
- **Momento Técnico:** Calcula indicadores técnicos chave (RSI, MACD, cruzamentos de médias móveis).
- **Oportunidade Contrariante:** Identifica desvios oversold e retornos estruturais.
- **Sentimento:** Analisa sentimento de notícias e mudanças nas expectativas de mercado.
- **Forense Social:** Monitora atividade de volume de varejo, short interest e sinais de catalisadores da comunidade.

### 3. F51 Verdict Engine & Stack de Decisão
Antes de o agente formular sua tese final, os dados passam por um firewall de verificação multi-camadas:
- **F51 Verdict:** Um motor de pontuação determinístico que mapeia confiança, anomalias de dados e métricas de incerteza.
- **Decisão Neural:** Um motor de correspondência de padrões localizado que detecta configurações estruturais.
- **Firewall SDCA:** Uma guarda de risco cognitiva que protege contra FOMO, armadilhas de alavancagem e sinais obsoletos do mercado.
- **ForensicRAG:** Extrai trechos paginados de documentação, prevenindo cálculos alucinados.

### 4. Motor de Trading Interactive Brokers (IBKR)
Quando o agente CEO decide executar uma posição, ele emite um `PAPER_TICKET` formatado. A plataforma intercepta este ticket, roda portões de verificação de segurança e executa os trades automaticamente:
- **Portão de Concentração:** Rejeita ordens se um ativo exceder 50% do valor total de liquidação líquida do portfólio.
- **Portão de Dimensionamento (Sizing):** Limita o valor de ordens individuais a um máximo de 10% do patrimônio total.
- **Execução:** Conecta ao IBKR Trader Workstation (TWS) ou IB Gateway para enviar ordens Limit (LMT) ou Market (MKT).
- **Log de Auditoria:** Salva resultados das transações, preços de preenchimento de execução, rastreamento de PnL e parâmetros de reflexão pós-trade em um banco SQLite local auditado via `PaperJournal`.

---

## 🚀 Motor de Modelo Local (F51 Nitro-MoE)

O SuperEzio roda suas decisões cognitivas centrais em um modelo local **Qwen3-Next-80B-A3B Instruct Abliterated** no formato GGUF usando `llama-server`.

Para rodar um modelo dessa magnitude em hardware de consumidor (ex: RTX 5060 Ti 16GB, 64GB RAM DDR5), a plataforma utiliza a alocação de especialistas em camadas do **F51 Nitro**:
- **Memória em Camadas (Tiered):** As camadas de atenção e caches KV ficam fixadas na VRAM da GPU (~6.3 GB).
- **Paginação Ativa:** Todos os 512 especialistas ficam na memória RAM do sistema (DDR5) e são processados na CPU ou enviados à GPU sob demanda.
- **Performance:** Alcança **38.7 tok/s com contexto de 256K**—evitando a sobrecarga de VRAM que retarda as execuções puramente em GPU para 8.4 tok/s devido a loops de page-fault de swap do driver.

---

## ⚡ Quickstart

### 1. Configuração de Ambiente
Clone o repositório e instale o projeto em modo editável utilizando `uv` (recomendado) ou `pip` padrão:
```bash
# Utilizando Ambiente Virtual Python
python -m venv .venv
.venv\Scripts\activate

# Instalar dependências e projeto em modo editável
pip install -e .
```

### 2. Configuração
Copie o template de ambiente e configure suas portas e chaves. Se quiser rodar completamente offline, deixe as chaves de API externas em branco:
```bash
cp .env.example .env
```

### 3. Executar o Servidor de Modelo Local (Motor CEO)
Inicie o servidor de modelo local para hospedar o modelo de 80B na porta `8082`:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082
```

### 4. Iniciar o Servidor de Aplicação FastAPI
Rode o backend web FastAPI. Por padrão, o servidor responde na porta `8002`:
```bash
python -m agent_server.main
```

### 5. Acessar a UI da Plataforma
Abra seu navegador e vá para:
```text
http://127.0.0.1:8002
```
*(Ou dê duplo clique no atalho `OPEN_UI.url` na raiz do projeto).*

---

## 🧪 Testes e Verificação

O SuperEzio impõe rigorosos portões de qualidade para garantir um comportamento determinístico e prevenir vazamentos de memória.

```bash
# 1. Rodar toda a suíte pytest (mais de 1.100 testes de contrato, unitários e de integração)
python -m pytest tests/ -q

# 2. Rodar verificação de lint e formatação automática
python -m ruff check src tests
python -m ruff format --check src tests

# 3. Executar End-to-End browser UI smoke tests (Playwright)
python scripts/browser_smoke.py --headed

# 4. Acionar o script compreensivo de validação Pre-Delivery Gate
powershell -ExecutionPolicy Bypass -File scripts/verify_zero_garbage_runtime.ps1
```

> [!IMPORTANT]
> O script `verify_zero_garbage_runtime.ps1` roda 12 portões de validação incluindo smoke tests de inicialização, verificações de contrato, cobertura de integração, proteções contra vazamento de secrets e validação de footprint de memória.

---

## 📈 Referência de Ambiente

Variáveis chave dentro do seu arquivo `.env`:

| Variável | Descrição | Padrão |
|----------|-------------|---------|
| `SUPEREZIO_CEO_BASE_URL` | URL Base do gateway modelo CEO local/cloud | `http://127.0.0.1:8082/v1` |
| `SUPEREZIO_HOST` | Endereço de bind do FastAPI | `127.0.0.1` |
| `SUPEREZIO_PORT` | Porta do servidor FastAPI | `8002` |
| `SUPEREZIO_DEEPSEEK_API_KEY` | Chave opcional para cloud experts (fallback) | *(Opcional)* |
| `FINNHUB_API_KEY` | Finnhub API Key para catalisadores de mercado | *(Opcional)* |
| `TWELVE_DATA_API_KEY` | Twelve Data API Key para velas (candles) de ativos | *(Opcional)* |

---

## 📜 Licença
MIT License with Attribution — Copyright (c) 2025-2026 Marco Barreto. Veja [LICENSE](LICENSE) para mais detalhes.
