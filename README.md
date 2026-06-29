# SuperEzio Core
### Local-First Autonomous Algorithmic Investment Platform
*(ðŸ‡§ðŸ‡· Para a versÃ£o em portuguÃªs, role para baixo / Scroll down for the Portuguese version)*

**SuperEzio Core** is a production-grade, offline-first multi-agent decision and execution platform for quantitative portfolio management. It orchestrates deterministic financial experts, an adversarial decision stack, and real-time Interactive Brokers (IBKR) paper execution. The platform runs entirely locally using **Bob Core** with QLoRA adapters.

---

## ðŸ“ Platform Architecture

```text
                     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                     â”‚    Browser UI (http://127.0.0.1:8002)  â”‚
                     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â”‚
                                         â–¼
                     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                     â”‚    FastAPI Server Engine (:8002)       â”‚
                     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â”‚
                                         â–¼
                     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                     â”‚      LangGraph v4 State Machine        â”‚
                     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â”‚
       â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
       â–¼                                                                  â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”                                                  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚ Orchestrator  â”‚ Intent Classification & Conditional Routing      â”‚  Blocked Node â”‚
 â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜                                                  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
         â”‚
         â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚   Auto Full   â”‚
 â”‚   Analysis    â”‚ Parallel Evidence Collection & Evaluation
 â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
         â”œâ”€â–º [1] DataHub: Price, fundamentals, technicals, macro context
         â”œâ”€â–º [2] Expert Committee: Fan-out of 6 quantitative experts
         â”œâ”€â–º [3] Portfolio Snapshot: Real-time IBKR paper positions inject
         â””â”€â–º [4] Decision Stack: F51 Verdict, Neural Decision, SDCA Firewall, ForensicRAG
                 â”‚
                 â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚   Agent Node  â”‚ Bob CEO (ReAct reasoning loop) via Local Bob Core + LoRA
 â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
         â”‚
         â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚  Auto-Execute â”‚ Parses PAPER_TICKET, applies risk-sizing gates (10% max ticket,
 â”‚     Paper     â”‚ 50% concentration limit), and submits orders to IBKR TWS.
 â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
         â”‚
         â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚  Explanation  â”‚ Streams NDJSON analysis and trade execution data to UI
 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

## ðŸ› ï¸ Key Engine Components

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

## ðŸš€ Local Model Engine (Bob Core + LoRA)

SuperEzio runs its core cognitive decisions on a local **Bob Core** model (Q4_K_M, ~17GB) with **F51 LoRA v9** adapter via `llama-server`.

**Architecture:**
- **Base Model:** Bob Core (48 layers, dense, 262K context)
- **Quantization:** Q4_K_M (17.28 GB)
- **LoRA Adapter:** F51 v9 calibration (rank 16, alpha 32, freeze 12 layers)
- **Hardware Target:** RTX 5060 Ti 16GB (24 layers GPU, 12 frozen CPU)

**Training:** QLoRA via llama.cpp, calibrated with 500 samples (train_loss=1.8673, val_loss=1.8782, 2304 steps).

---

## âš¡ Quickstart

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
Start the local model server to host the local model on port `8082`:
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

## ðŸ§ª Testing & Verification

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

## ðŸ“ˆ Environment Reference

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

## ðŸ“œ License
MIT License with Attribution â€” Copyright (c) 2025-2026 Marco Barreto. See [LICENSE](LICENSE) for details.

<br><br><br>

---
---

# ðŸ‡§ðŸ‡· SuperEzio Core (VersÃ£o em PortuguÃªs)
### Plataforma AutÃ´noma de Investimentos AlgorÃ­tmicos Local-First

**SuperEzio Core** Ã© uma plataforma multi-agente offline-first de nÃ­vel de produÃ§Ã£o, focada em decisÃ£o e execuÃ§Ã£o para gestÃ£o quantitativa de portfÃ³lios. Ela orquestra especialistas financeiros determinÃ­sticos, uma stack de decisÃ£o adversÃ¡ria e execuÃ§Ã£o de ordens em tempo real via Interactive Brokers (IBKR) em modo paper. A plataforma foi projetada para rodar de forma totalmente local usando o runtime **F51 Nitro-MoE**, permitindo que modelos locais otimizados executem com alto throughput em hardwares de consumidor.

---

## ðŸ“ Arquitetura da Plataforma

```text
                     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                     â”‚    Browser UI (http://127.0.0.1:8002)  â”‚
                     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â”‚
                                         â–¼
                     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                     â”‚    Motor Servidor FastAPI (:8002)      â”‚
                     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â”‚
                                         â–¼
                     â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                     â”‚   MÃ¡quina de Estado LangGraph v4       â”‚
                     â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                         â”‚
       â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
       â–¼                                                                  â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”                                                  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚ Orquestrador  â”‚ ClassificaÃ§Ã£o de IntenÃ§Ã£o & Roteamento           â”‚  NÃ³ Bloqueado â”‚
 â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜ Condicional                                      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
         â”‚
         â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚ AnÃ¡lise Total â”‚ Coleta Paralela de EvidÃªncias & AvaliaÃ§Ã£o
 â”‚ AutomÃ¡tica    â”‚
 â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
         â”œâ”€â–º [1] DataHub: PreÃ§o, fundamentos, tÃ©cnicos, contexto macro
         â”œâ”€â–º [2] ComitÃª de Especialistas: Fan-out de 6 especialistas quantitativos
         â”œâ”€â–º [3] Snapshot de PortfÃ³lio: InjeÃ§Ã£o em tempo real das posiÃ§Ãµes paper IBKR
         â””â”€â–º [4] Stack de DecisÃ£o: F51 Verdict, DecisÃ£o Neural, Firewall SDCA, ForensicRAG
                 â”‚
                 â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚    NÃ³ do      â”‚ Bob CEO (Ciclo de raciocÃ­nio ReAct) via Local Bob Core
 â”‚   Agente      â”‚
 â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
         â”‚
         â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚ Auto-Executar â”‚ Analisa o PAPER_TICKET, aplica limites de risco (ticket mÃ¡x 10%,
 â”‚     Paper     â”‚ limite concentraÃ§Ã£o 50%), e envia ordens ao IBKR TWS.
 â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
         â”‚
         â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚  ExplicaÃ§Ã£o   â”‚ Faz stream de NDJSON de anÃ¡lise e dados de execuÃ§Ã£o para a UI
 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

## ðŸ› ï¸ Principais Componentes do Motor

### 1. LangGraph Decision & Execution DAG
O pipeline de roteamento central usa um Grafo AcÃ­clico Direcionado (DAG) determinÃ­stico construÃ­do no **LangGraph**. O LLM Ã© restrito a nÃ³s de raciocÃ­nio puro, garantindo que a classificaÃ§Ã£o de intenÃ§Ã£o, coleta de dados e ordens de negociaÃ§Ã£o ocorram sob restriÃ§Ãµes de software determinÃ­sticas e verificÃ¡veis.

### 2. ComitÃª de Especialistas Multi-Perspectiva
Cada anÃ¡lise de ativo dispara um fan-out paralelo atravÃ©s de 6 especialistas quantitativos distintos:
- **Risco Macro:** Examina indicadores de mercado de alto nÃ­vel e tendÃªncias de crÃ©dito.
- **Valor Fundamental:** Pontua mÃ©tricas de valuation (P/E, EV/EBITDA, Free Cash Flow).
- **Momento TÃ©cnico:** Calcula indicadores tÃ©cnicos chave (RSI, MACD, cruzamentos de mÃ©dias mÃ³veis).
- **Oportunidade Contrariante:** Identifica desvios oversold e retornos estruturais.
- **Sentimento:** Analisa sentimento de notÃ­cias e mudanÃ§as nas expectativas de mercado.
- **Forense Social:** Monitora atividade de volume de varejo, short interest e sinais de catalisadores da comunidade.

### 3. F51 Verdict Engine & Stack de DecisÃ£o
Antes de o agente formular sua tese final, os dados passam por um firewall de verificaÃ§Ã£o multi-camadas:
- **F51 Verdict:** Um motor de pontuaÃ§Ã£o determinÃ­stico que mapeia confianÃ§a, anomalias de dados e mÃ©tricas de incerteza.
- **DecisÃ£o Neural:** Um motor de correspondÃªncia de padrÃµes localizado que detecta configuraÃ§Ãµes estruturais.
- **Firewall SDCA:** Uma guarda de risco cognitiva que protege contra FOMO, armadilhas de alavancagem e sinais obsoletos do mercado.
- **ForensicRAG:** Extrai trechos paginados de documentaÃ§Ã£o, prevenindo cÃ¡lculos alucinados.

### 4. Motor de Trading Interactive Brokers (IBKR)
Quando o agente CEO decide executar uma posiÃ§Ã£o, ele emite um `PAPER_TICKET` formatado. A plataforma intercepta este ticket, roda portÃµes de verificaÃ§Ã£o de seguranÃ§a e executa os trades automaticamente:
- **PortÃ£o de ConcentraÃ§Ã£o:** Rejeita ordens se um ativo exceder 50% do valor total de liquidaÃ§Ã£o lÃ­quida do portfÃ³lio.
- **PortÃ£o de Dimensionamento (Sizing):** Limita o valor de ordens individuais a um mÃ¡ximo de 10% do patrimÃ´nio total.
- **ExecuÃ§Ã£o:** Conecta ao IBKR Trader Workstation (TWS) ou IB Gateway para enviar ordens Limit (LMT) ou Market (MKT).
- **Log de Auditoria:** Salva resultados das transaÃ§Ãµes, preÃ§os de preenchimento de execuÃ§Ã£o, rastreamento de PnL e parÃ¢metros de reflexÃ£o pÃ³s-trade em um banco SQLite local auditado via `PaperJournal`.

---

## ðŸš€ Motor de Modelo Local (F51 Nitro-MoE)

O SuperEzio roda suas decisÃµes cognitivas centrais em um modelo local **Bob Core** no formato GGUF usando `llama-server`.

Para rodar um modelo dessa magnitude em hardware de consumidor (ex: RTX 5060 Ti 16GB, 64GB RAM DDR5), a plataforma utiliza a alocaÃ§Ã£o de especialistas em camadas do **F51 Nitro**:
- **MemÃ³ria em Camadas (Tiered):** As camadas de atenÃ§Ã£o e caches KV ficam fixadas na VRAM da GPU (~6.3 GB).
- **PaginaÃ§Ã£o Ativa:** Todos os 512 especialistas ficam na memÃ³ria RAM do sistema (DDR5) e sÃ£o processados na CPU ou enviados Ã  GPU sob demanda.
- **Performance:** AlcanÃ§a **38.7 tok/s com contexto de 256K**â€”evitando a sobrecarga de VRAM que retarda as execuÃ§Ãµes puramente em GPU para 8.4 tok/s devido a loops de page-fault de swap do driver.

---

## âš¡ Quickstart

### 1. ConfiguraÃ§Ã£o de Ambiente
Clone o repositÃ³rio e instale o projeto em modo editÃ¡vel utilizando `uv` (recomendado) ou `pip` padrÃ£o:
```bash
# Utilizando Ambiente Virtual Python
python -m venv .venv
.venv\Scripts\activate

# Instalar dependÃªncias e projeto em modo editÃ¡vel
pip install -e .
```

### 2. ConfiguraÃ§Ã£o
Copie o template de ambiente e configure suas portas e chaves. Se quiser rodar completamente offline, deixe as chaves de API externas em branco:
```bash
cp .env.example .env
```

### 3. Executar o Servidor de Modelo Local (Motor CEO)
Inicie o servidor de modelo local para hospedar o modelo local na porta `8082`:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082
```

### 4. Iniciar o Servidor de AplicaÃ§Ã£o FastAPI
Rode o backend web FastAPI. Por padrÃ£o, o servidor responde na porta `8002`:
```bash
python -m agent_server.main
```

### 5. Acessar a UI da Plataforma
Abra seu navegador e vÃ¡ para:
```text
http://127.0.0.1:8002
```
*(Ou dÃª duplo clique no atalho `OPEN_UI.url` na raiz do projeto).*

---

## ðŸ§ª Testes e VerificaÃ§Ã£o

O SuperEzio impÃµe rigorosos portÃµes de qualidade para garantir um comportamento determinÃ­stico e prevenir vazamentos de memÃ³ria.

```bash
# 1. Rodar toda a suÃ­te pytest (mais de 1.100 testes de contrato, unitÃ¡rios e de integraÃ§Ã£o)
python -m pytest tests/ -q

# 2. Rodar verificaÃ§Ã£o de lint e formataÃ§Ã£o automÃ¡tica
python -m ruff check src tests
python -m ruff format --check src tests

# 3. Executar End-to-End browser UI smoke tests (Playwright)
python scripts/browser_smoke.py --headed

# 4. Acionar o script compreensivo de validaÃ§Ã£o Pre-Delivery Gate
powershell -ExecutionPolicy Bypass -File scripts/verify_zero_garbage_runtime.ps1
```

> [!IMPORTANT]
> O script `verify_zero_garbage_runtime.ps1` roda 12 portÃµes de validaÃ§Ã£o incluindo smoke tests de inicializaÃ§Ã£o, verificaÃ§Ãµes de contrato, cobertura de integraÃ§Ã£o, proteÃ§Ãµes contra vazamento de secrets e validaÃ§Ã£o de footprint de memÃ³ria.

---

## ðŸ“ˆ ReferÃªncia de Ambiente

VariÃ¡veis chave dentro do seu arquivo `.env`:

| VariÃ¡vel | DescriÃ§Ã£o | PadrÃ£o |
|----------|-------------|---------|
| `SUPEREZIO_CEO_BASE_URL` | URL Base do gateway modelo CEO local/cloud | `http://127.0.0.1:8082/v1` |
| `SUPEREZIO_HOST` | EndereÃ§o de bind do FastAPI | `127.0.0.1` |
| `SUPEREZIO_PORT` | Porta do servidor FastAPI | `8002` |
| `SUPEREZIO_DEEPSEEK_API_KEY` | Chave opcional para cloud experts (fallback) | *(Opcional)* |
| `FINNHUB_API_KEY` | Finnhub API Key para catalisadores de mercado | *(Opcional)* |
| `TWELVE_DATA_API_KEY` | Twelve Data API Key para velas (candles) de ativos | *(Opcional)* |

---

## ðŸ“œ LicenÃ§a
MIT License with Attribution â€” Copyright (c) 2025-2026 Marco Barreto. Veja [LICENSE](LICENSE) para mais detalhes.


