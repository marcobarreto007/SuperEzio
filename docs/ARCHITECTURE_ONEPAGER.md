# SuperEzio - Architecture Overview

## System Diagram

```text
Browser (http://127.0.0.1:8002)
    |
    v
FastAPI Server (:8002)
    |
    +--> Pipeline (LangGraph v4)
    |    +-- orchestrator_primary     classifies intent, route, data needs
    |    +-- data collector           fetches price, fundamentals, technicals, macro
    |    +-- institutional experts    macro, fundamental, momentum, contrarian
    |    +-- f51_verdict              deterministic scoring engine
    |    +-- pennylab                 optional forensic penny-stock guardrails
    |    +-- neural                   pattern-matching engine
    |    +-- sdca                     cognitive risk firewall
    |    +-- rag                      forensic retrieval
    |    +-- ceo (Bob)                response consolidation
    |    +-- explanation              streaming NDJSON to UI
    |
    +--> DataHub
    |    +-- Finnhub                  price, profile, fundamentals, catalyst
    |    +-- Twelve Data              fallback price
    |    +-- yfinance                 fallback price and candles
    |    +-- Stooq                    emergency keyless price
    |
    +--> Model Gateway
         +-- Local CEO (:8082)        Qwen3-Next-80B IQ4_XS
         +-- Optional cloud experts   configured provider fallback
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI + uvicorn + SSE streaming |
| Pipeline | LangGraph DAG with conditional routing |
| Validation | Pydantic v2 |
| CEO Model | Qwen3-Next-80B-A3B Abliterated IQ4_XS GGUF |
| Model Serving | llama.cpp + F51 Nitro MoE runtime knobs |
| Data | yfinance, Finnhub, Twelve Data, Alpha Vantage, Stooq |
| AI/ML | PyTorch, transformers, sentence-transformers, FAISS |
| Observability | Traces, metrics, and structured logs |
| Frontend | Vanilla HTML/CSS/JS with canvas candle rendering |
| Testing | pytest contracts, smoke tests, and browser smoke |
| Lint | ruff |

## Data Flow Per Request

1. User sends a prompt and the orchestrator classifies intent.
2. If the request is a market scan, DataHub scans US and Canadian equities.
3. Enrichment collects price, profile, fundamentals, technicals, and catalysts where available.
4. Gates reject candidates with missing price, weak thesis, micro-cap risk, or poor data quality.
5. Experts analyze survivors from different perspectives.
6. The SDCA firewall checks FOMO, leverage, slippage, and stale-signal risks.
7. The F51 verdict layer scores confidence and uncertainty.
8. Bob CEO consolidates the evidence into one bounded next step.
9. The UI renders the streaming answer, trace, and chart context.

## Key Design Decisions

- Local CEO first: the final synthesis is designed to run locally when the model/runtime are installed.
- Traceable evidence: collected financial numbers are expected to carry provider/source metadata where available.
- Missing data blocks conclusions: the system prefers STUDY_MORE over guessing.
- Single pipeline: one graph keeps routing predictable instead of splitting behavior across hidden modes.
- Circuit breakers: provider failures are isolated so one bad data source does not collapse the request.
