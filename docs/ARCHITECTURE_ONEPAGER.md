# SuperEzio - Architecture Overview

> Visão corrente (arquitetura híbrida :8080 local + DeepSeek externo). A
> duplicata histórica é `docs/architecture/SUPEREZIO_DOCS.md`, marcada
> **HISTORICO / SUPERSEDED** (estado de 2026-06-16) — não usar como fonte atual.

## System Diagram

```text
Browser (http://127.0.0.1:8002)
    |
    v
FastAPI Server (:8002)
    |
    +--> Pipeline (LangGraph v4)
    |    +-- orchestrator_primary     passthrough; opens case and tool contract
    |    +-- auto_full_analysis       deterministic analysis/evidence stage
    |    +-- trinity                  deliberation and safety route
    |    +-- agent (Bob)              decides intent and calls tools as needed
    |    |       ^
    |    |       +-- tool_executor    executes allowed tool, then returns to Bob
    |    +-- auto_execute_paper       guarded paper-order submission path
    |    +-- explanation              streaming NDJSON to UI
    |    +-- respond_blocked          fail-closed response path
    |
    +--> DataHub
    |    +-- market/fundamentals      yfinance, Finnhub, Twelve Data, Alpha Vantage, AKShare
    |    +-- macro/quant              BoC Macro, Fed Macro, AlphaSMO, Wolfram
    |    +-- news/social/filings      NewsAPI, News Scout, Reddit Pulse, ApeWisdom,
    |                                 Social Whale, Form4API
    |
    +--> Model Gateway
         +-- Shared local llama-server (:8080)
         |   +-- Bob CEO              Qwen3.8-27B
         |   +-- orchestrator         role prompt on the same model
         +-- Official DeepSeek HTTPS API
             +-- financial experts    deepseek-v4-pro
             +-- judge/auditor        provider-pinned roles
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI + uvicorn + streaming NDJSON responses |
| Pipeline | LangGraph DAG with conditional routing |
| Validation | Pydantic v2 |
| LLM Roles | Qwen3.8-27B local for CEO/orchestrator; deepseek-v4-pro external for experts/judge/auditor |
| Model Serving | llama.cpp locally plus the official DeepSeek OpenAI-compatible HTTPS API |
| Data | DataHub capability routing across 15 providers: AKShare, Alpha Vantage, AlphaSMO, ApeWisdom, BoC Macro, Fed Macro, Finnhub, Form4API, News Scout, NewsAPI, Reddit Pulse, Social Whale, Twelve Data, Wolfram, and yfinance |
| AI/ML | PyTorch, transformers, sentence-transformers, FAISS |
| Observability | Traces, metrics, and structured logs |
| Frontend | Vanilla HTML/CSS/JS with canvas candle rendering |
| Testing | pytest contracts, smoke tests, and browser smoke |
| Lint | ruff |

## Data Flow Per Request

1. The user sends a prompt to `POST /task/submit`.
2. `orchestrator_primary` performs no intent classification: it opens the financial case, derives the cognitive tool contract, and routes the raw request forward as `bob_decides`.
3. `auto_full_analysis` prepares deterministic analysis and evidence; `trinity` deliberates and may route to the blocked response.
4. Bob receives the state, decides how to handle the request, and either produces an answer or calls an allowed tool.
5. `tool_executor` executes the allowed call and returns control to Bob; this loop can repeat.
6. A final answer passes through the guarded paper-order stage and then `explanation`; a safety rejection goes to `respond_blocked`.
7. The UI renders the streamed answer, trace, and available chart context.

## Key Design Decisions

- Hybrid trust boundary: CEO/orchestrator use local `127.0.0.1:8080`; experts/judge/auditor use official DeepSeek. No role crosses tiers as a fallback.
- Fail closed: if the local model server is unavailable, SuperEzio enters `MAN_AT_WORK` and blocks order submission.
- Traceable evidence: collected financial numbers are expected to carry provider/source metadata where available.
- Missing data blocks conclusions: the system prefers STUDY_MORE over guessing.
- Single pipeline: one graph keeps routing predictable instead of splitting behavior across hidden modes.
- Circuit breakers: provider failures are isolated so one bad data source does not collapse the request.
