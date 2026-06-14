# SuperEzio Core
### Local-First Autonomous Algorithmic Investment Platform

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

