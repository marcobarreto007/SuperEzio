# SuperEzio v3.0.0 — AI Financial Analysis Platform

```
  ███████╗██╗   ██╗██████╗ ███████╗██████╗ ███████╗███████╗██╗ ██████╗
  ██╔════╝██║   ██║██╔══██╗██╔════╝██╔══██╗██╔════╝╚══███╔╝██║██╔═══██╗
  ███████╗██║   ██║██████╔╝█████╗  ██████╔╝█████╗    ███╔╝ ██║██║   ██║
  ╚════██║██║   ██║██╔═══╝ ██╔══╝  ██╔══██╗██╔══╝   ███╔╝  ██║██║   ██║
  ███████║╚██████╔╝██║     ███████╗██║  ██║███████╗███████╗██║╚██████╔╝
  ╚══════╝ ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝ ╚═════╝

  PLATAFORMA DE PESQUISA INSTITUCIONAL
  Pipeline proprietário de análise financeira com IA, experts determinísticos,
  motor de veredito F51, e cascade multi-modelo com tool calling nativo.
```

---

## Índice

1. [Visão Geral](#1-visao-geral)
2. [Hardware](#2-hardware)
3. [Arquitetura do Sistema](#3-arquitetura-do-sistema)
4. [Árvore Decisional](#4-arvore-decisional)
5. [Stack Tecnológica](#5-stack-tecnologica)
6. [Estrutura de Diretórios](#6-estrutura-de-diretorios)
7. [Modelos e Provedores](#7-modelos-e-provedores)
8. [Cascata de Decisão (ModelGateway)](#8-cascata-de-decisao-modelgateway)
9. [F51 Engine — Motor de Veredito](#9-f51-engine--motor-de-veredito)
10. [F51 Behavioral Corpus](#10-f51-behavioral-corpus)
11. [Sistema Dual-Agent (Deep + Sasaki)](#11-sistema-dual-agent-deep--sasaki)
12. [Segurança (SecurityContext)](#12-seguranca-securitycontext)
13. [Setup e Instalação](#13-setup-e-instalacao)
14. [Comandos e Entrypoints](#14-comandos-e-entrypoints)
15. [API Reference](#15-api-reference)
16. [Frontend](#16-frontend)
17. [Testes e Qualidade](#17-testes-e-qualidade)
18. [CI/CD](#18-cicd)
19. [Variáveis de Ambiente](#19-variaveis-de-ambiente)
20. [Atalhos e Launchers](#20-atalhos-e-launchers)
21. [Roadmap e Tarefas Pendentes](#21-roadmap-e-tarefas-pendentes)
22. [Métricas do Projeto](#22-metricas-do-projeto)

---

## 1. Visão Geral

SuperEzio é uma plataforma de análise financeira com inteligência artificial que combina:

- **Pipeline LangGraph** com roteamento condicional e fan-out paralelo de experts
- **Motor de veredito F51** determinístico com grafos, gates, scorers e detectors
- **CEO local** (Qwen3.6-27B GGUF Q4_K_M) sem fallback cloud
- **Providers externos opcionais** para experts/orquestração; veredito CEO final é local-only
- **12 agentes financeiros especializados** (fundamental, technical, risk, macro, sentiment, quantitative, value, growth, momentum, quality, volatility, dividend)
- **4 experts PennyLab** (liquidity_risk, pump_dump, volume_spike, whale_print)
- **12 modelos CrisisMath** para detecção de crises sistêmicas
- **DataCollector multi-fonte** (yfinance, Alpha Vantage, Reddit, BOC, News, Twelve Data)
- **Sistema dual-agent** (Deep arquiteto + Sasaki auditor)

### Propósito

Análise de penny stocks com foco em detecção de fraude, manipulação de mercado,
diluição, risco de liquidez, whale prints, e hype risk. O sistema não dá recomendações
de compra/venda — ele emite vereditos baseados em evidência com scores de confiança
e fatores explicitados.

### Princípios F51

1. **Evidência antes de veredito** — todo claim é verificado contra ground truth
2. **Fato separado de inferência** — `[FACT]` vs `[INFERENCE]` vs `[SPECULATION]`
3. **Incerteza calibrada** — ranges, não pontos; confiança, não certeza
4. **Risk-aware** — VaR, drawdown, tail risk sempre calculados ou declarados ausentes
5. **Explicabilidade** — todo score tem fatores visíveis, todo gate tem evidência
6. **Sem dados inventados** — se falta dado, o sistema pede, não inventa

---

## 2. Hardware

| Componente | Especificação | Uso |
|-----------|---------------|-----|
| **GPU 0** | RTX 5060 Ti 16GB (Blackwell) | CEO Qwen3.6-27B Q4_K_M |
| **GPU 1** | RTX 3060 12GB (Ampere) | Offload auxiliar (KV cache, layers) |
| **RAM** | 64GB DDR5-6000 | Datasets, cache, processamento |
| **CPU** | Intel Core i7-12700K | DataCollector, pipeline, API |
| **OS** | Windows 11 Pro | Host |
| **VRAM Combinada** | 28 GB | Suficiente para modelo 31B Q4_K_M (~17 GB) + KV cache |

---

## 3. Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                        SUPEREZIO v3.0.0                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐  │
│  │ Frontend │   │  FastAPI  │   │ LangGraph │   │ Model      │  │
│  │ (HTML/JS)│◄──┤  Server   │◄──┤ Pipeline  │◄──┤ Gateway    │  │
│  │ :8002    │   │  :8002    │   │ (runtime) │   │ (cascade)  │  │
│  └──────────┘   └──────────┘   └──────────┘   └────────────┘  │
│                      │                │               │         │
│                      ▼                ▼               ▼         │
│               ┌──────────┐   ┌──────────┐   ┌────────────┐    │
│               │ Edge     │   │ F51      │   │ CEO Local   │    │
│               │ Gateway  │   │ Engine   │   │ Qwen3.6-27B │    │
│               │ (auth)   │   │ (verdict)│   │ :8082       │    │
│               └──────────┘   └──────────┘   └────────────┘    │
│                      │               │               │         │
│                      ▼               ▼               ▼         │
│               ┌──────────┐   ┌──────────┐   ┌────────────┐    │
│               │ Security │   │ Experts  │   │ Cloud       │    │
│               │ Context  │   │ (12 agt) │   │ Fallback    │    │
│               │ (input)  │   │ Pennylab │   │ Grok/DS/Gen │    │
│               └──────────┘   └──────────┘   └────────────┘    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Data Layer                                               │   │
│  │ yfinance │ Alpha Vantage │ Reddit │ BOC │ News │ 12 Data │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ F51 Behavioral Corpus (data/corpus/)                      │   │
│  │ Teacher models: Deep + GPT + Gemini → Student: Qwen3.6   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Árvore Decisional

### Fluxo completo do pipeline (StateGraph LangGraph)

```
                         ┌──────────────────────────┐
                         │   Mensagem do usuário     │
                         │  "Analisa AAPL pra mim"   │
                         └────────────┬─────────────┘
                                      │
                                      ▼
              ┌──────────────────────────────────────────────┐
              │  NÓ 1 — orchestrator_primary                 │
              │  HybridIntentClassifier                      │
              │                                              │
              │  ┌─ Determinístico (regex/keyword) ────┐     │
              │  │  parse_user_intent()                  │     │
              │  │  ├─ ticker_analysis (tem ticker)      │     │
              │  │  ├─ market_scan (filtros de mercado)  │     │
              │  │  ├─ needs_scope (vago/inseguro)       │     │
              │  │  └─ general (pergunta/conversa)       │     │
              │  └──────────────────────────────────────┘     │
              │                    │                          │
              │  ┌─ Golden intent match ───────────────┐     │
              │  │  match_golden_intent()                │     │
              │  └──────────────────────────────────────┘     │
              │                    │                          │
              │  ┌─ LLM Fallback (se confiança < 0.76) ─┐    │
              │  │  _ask_intent_classifier() → JSON       │     │
              │  │  validate_intent_candidate()           │     │
              │  └──────────────────────────────────────┘     │
              └───────────────┬──────────────────────────────┘
                              │
                    ┌─────────┼─────────┐
                    │         │         │
                    ▼         ▼         ▼
              ┌─────────┐ ┌──────┐ ┌──────────────┐
              │  data   │ │ ceo  │ │respond_blocked│
              │  (rota  │ │direct│ │  (needs_scope)│
              │ ticker/ │ │(gen.)│ │  → "Preciso   │
              │  scan)  │ │      │ │  de +info"   │
              └────┬────┘ └──┬───┘ └──────┬───────┘
                   │         │            │
     ┌─────────────┤         │            ▼
     │             │         │          END
     ▼             ▼         │
┌─────────┐ ┌──────────┐    │
│  data   │ │ pennylab │    │
│collector│ │ 4 experts│    │
│subprocess│ │          │    │
│         │ │liquidity │    │
│yfinance │ │pump_dump │    │
│Reddit   │ │vol_spike │    │
│AlphaVant│ │whale_prt │    │
│BOC      │ └────┬─────┘    │
│News     │      │          │
│TwelveD  │      │          │
└────┬────┘      │          │
     │           │          │
     ▼           │          │
┌─────────┐      │          │
│  f51    │      │          │
│ verdict │      │          │
│         │      │          │
│F51Hub   │      │          │
│Adapter  │      │          │
│ ├Spider │      │          │
│ ├Diff   │      │          │
│ ├Platin │      │          │
│ ├Veracid│      │          │
│ ├Critic │      │          │
│ └RiskEng│      │          │
└────┬────┘      │          │
     │           │          │
     └─────┬─────┘          │
           │                │
           ▼                │
   ┌───────────────┐        │
   │ run_expert ×N │        │
   │ (LangGraph    │        │
   │  Send fan-out)│        │
   │               │        │
   │ AgentSelector │        │
   │  ├fundamental │        │
   │  ├technical   │        │
   │  ├risk        │        │
   │  ├macro       │        │
   │  ├sentiment   │        │
   │  ├quantitative│        │
   │  ├value       │        │
   │  ├growth      │        │
   │  ├momentum    │        │
   │  ├quality     │        │
   │  ├volatility  │        │
   │  └dividend    │        │
   └───────┬───────┘        │
           │                │
           ▼                │
   ┌───────────────┐        │
   │collect_experts│        │
   │ agrega N      │        │
   │ resultados    │        │
   │ ok/fail count │        │
   └───────┬───────┘        │
           │                │
           └────────┬───────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │  NÓ 5 — ceo_primary          │
     │  CEO Cascade Decision         │
     │                               │
     │  ┌─ CEO (Qwen3.6-27B) :8082  │
     │  │  └─ offline? ────────┐    │
     │  │                      │    │
     │  ├─ Grok 4.3 Cloud ◄────┘    │
     │  │  └─ offline? ────────┐    │
     │  │                      │    │
     │  ├─ DeepSeek V4 ◄───────┘    │
     │  │  └─ offline? ────────┐    │
     │  │                      │    │
     │  └─ Gemini 2.0 Flash ◄──┘    │
     │                               │
     │  build_ceo_prompt(state,      │
     │    mandamentos)               │
     │  stream_generate_async()      │
     └──────────────┬───────────────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │  NÓ 6 — explanation          │
     │  ExplainEngine               │
     │  stream(verdict, ceo_text)   │
     └──────────────┬───────────────┘
                    │
                    ▼
                  END
```

### Tabela resumo do fluxo decisional

| Etapa | Quem decide | Input | Output | Fallback |
|-------|-------------|-------|--------|----------|
| Roteamento | HybridIntentClassifier | Mensagem usuário | Rota + intent + ticker | Determinístico → Golden → LLM |
| Coleta | SubprocessDataCollector | Ticker/filtros | Trace multi-fonte | Timeout 60s → erro parcial |
| Veredito | F51HubAdapter → F51Engine | Trace + features | Score 0-1 + fatores | Grafo roda com dados parciais |
| PennyLab | 4 experts especializados | Ticker | Decisão + scores | ImportError → WATCH_ONLY |
| Experts | AgentSelector + 12 agentes | AssetProfile | N resultados paral. | Provider offline → skip |
| CEO | Cascade CEO→Grok→DS→Gemini | Prompt completo | Texto final | Todos offline → MODEL_ERROR |
| Explicação | ExplainEngine | Veredito + texto CEO | Stream de chunks | Skip se sem veredito |

---

## 5. Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| **Linguagem** | Python 3.12+ |
| **API Server** | FastAPI + Uvicorn |
| **Pipeline** | LangGraph (StateGraph, conditional edges, Send fan-out) |
| **Tipagem** | Pydantic v2, TypeDict, dataclasses |
| **Modelo Local** | Qwen3.6-27B Q4_K_M via llama-cpp-python |
| **Modelos Cloud** | Grok 4.3 (xAI), DeepSeek V4, Gemini 2.0 Flash |
| **Data Providers** | yfinance, Alpha Vantage, Reddit (PRAW), Twelve Data, Bank of Canada |
| **Storage** | Mem0 (Redis), SQLite, JSONL filesystem |
| **Observabilidade** | OpenTelemetry, Neural Log, Event Hub, métricas custom |
| **Segurança** | SecurityContext (input validation, PII filter, rate limiting), Edge Gateway (JWT/API key) |
| **Frontend** | Vanilla HTML/CSS/JS (+ Chart.js), StaticFiles via FastAPI |
| **Testes** | Pytest (503 testes), Ruff (lint/format), mypy (type check) |
| **CI/CD** | GitHub Actions (Windows runner) |
| **Package Manager** | uv (lock file), setuptools (build) |
| **Corpus** | F51 Behavioral Corpus (Deep + GPT + Gemini como teachers) |

---

## 6. Estrutura de Diretórios

```
SuperEzio/
├── src/
│   ├── core/                    ← Domínio principal
│   │   ├── pipeline/            ← LangGraph StateGraph + nós + prompts
│   │   │   ├── runtime.py       ← UniversalPipeline (classe principal)
│   │   │   ├── nodes.py         ← Implementações dos nós do grafo
│   │   │   ├── state.py         ← PipelineState TypedDict
│   │   │   ├── ceo_prompts.py   ← Construção de prompts do CEO
│   │   │   ├── intents.py       ← Classificador híbrido de intents
│   │   │   ├── security.py      ← SecurityContext (input/output validation)
│   │   │   ├── cache.py         ← Cache de respostas
│   │   │   └── responses.py     ← Respostas padrão
│   │   ├── model_serving/       ← ModelGateway + providers
│   │   │   ├── gateway.py       ← Cascade com fallback e retry
│   │   │   ├── providers.py     ← Definições de providers (CEO, Grok, DS, Gemini)
│   │   │   └── deepseek_provider.py ← Provider específico DeepSeek
│   │   ├── f51_adapter/         ← Ponte entre pipeline e F51 Engine
│   │   ├── mathcore/            ← Funções matemáticas canônicas (sigmoid, clamp, etc.)
│   │   ├── investor/            ← VeracityGate, FraudAnalyst, CostGuard, Committee
│   │   ├── agent_runtime/       ← AgentSelector, FinancialAgentOrchestrator
│   │   │   ├── financial_agents.py ← 12 agentes financeiros
│   │   │   ├── control_plane/   ← ToolRegistry (21 tools)
│   │   │   └── edge/            ← EdgeGateway (auth, rate limit)
│   │   ├── data_collector/      ← SubprocessDataCollector
│   │   ├── observability/       ← Neural Log, Event Hub, Debug Logger, Metrics
│   │   ├── rl/                  ← LinUCB Contextual Bandit
│   │   ├── rag/                 ← Fraud RAG, Macro Dataset
│   │   ├── security/            ← Constantes de segurança
│   │   ├── config/              ← UniversalConfig, secrets
│   │   ├── storage/             ← Mem0 client
│   │   ├── ports/               ← Interfaces (DataCollectorPort, HealthProbePort, etc.)
│   │   └── scanner/             ← MarketScanner (scan_equities)
│   ├── experts/
│   │   ├── pennylab/            ← 4 experts: liquidity, pump_dump, vol_spike, whale_print
│   │   ├── crisis_math/         ← 12 modelos: LPPLS, Hawkes, Markov, Minsky-Keen, etc.
│   │   └── quantum_expert.py    ← Quantum analysis expert
│   ├── f51/                     ← F51 Verdict Engine
│   │   ├── __init__.py          ← F51Engine, Graph, Node, Context, NodeResult
│   │   ├── formulas.py          ← Fórmula decisória F51 (canônica)
│   │   ├── graph/               ← Grafo default (spider_sense, platinum, veracity, critic)
│   │   ├── gates/               ← VeracityGate, AdversarialCritic
│   │   ├── detectors/           ← SpiderSense, DifficultyEstimator
│   │   ├── scoring/             ← RiskEngine, PlatinumScorer
│   │   └── memory/              ← Memória de decisões
│   ├── agent_server/            ← FastAPI + A2A protocol
│   │   ├── main.py              ← Servidor principal (lifespan, middlewares, rotas)
│   │   ├── endpoints.py         ← Router A2A
│   │   └── protocol.py          ← A2A protocol types
│   ├── data/                    ← Providers de dados
│   │   ├── data_hub.py          ← Hub central de dados
│   │   ├── yfinance_provider.py
│   │   ├── alpha_vantage.py
│   │   ├── reddit_provider.py
│   │   ├── boc_provider.py
│   │   ├── fed_provider.py
│   │   ├── news_feed.py
│   │   └── twelve_data.py
│   ├── tools/                   ← Registry de tools LangGraph
│   └── adapters/                ← DataCollector, Gateway, Health, Quantum adapters
├── config/
│   ├── model_manifest.json      ← Manifesto de modelos (CEO + cloud)
│   ├── runtime.yml              ← Config de runtime
│   └── mandamentos.json         ← Regras operacionais do CEO
├── data/
│   ├── corpus/                  ← F51 Behavioral Corpus
│   │   ├── 01_sft/              ← Supervised Fine-Tuning examples
│   │   ├── 02_dpo/              ← Direct Preference Optimization pairs
│   │   ├── 03_critic/           ← Critique examples
│   │   ├── 04_eval_locked/      ← Eval cases (NUNCA usar para treino)
│   │   └── MANIFEST.json        ← Metadados do corpus
│   ├── fraud_patterns/          ← Regras de fraude (red_flag_rules.json)
│   ├── intent_dataset.jsonl     ← Dataset de intents
│   └── eval_questions.jsonl     ← Questões de avaliação
├── models/
│   └── Qwen3.6-27B-Q4_K_M.gguf  ← CEO local (~17 GB, Q4_K_M, 27B params)
├── tests/
│   ├── test_security.py         ← 42 testes de SecurityContext
│   ├── test_pipeline_*.py       ← Testes de pipeline (e2e, integration, edge_cases)
│   ├── test_financial_suite.py  ← Testes da suite financeira
│   ├── test_f51_public_import.py ← Teste de contrato público F51
│   ├── test_f51_adapter_trace.py ← Teste do F51HubAdapter
│   ├── test_fraud_analyst.py    ← Testes de detecção de fraude
│   ├── test_pennylab.py         ← Testes do PennyLab
│   ├── crisis_math/             ← Testes dos 12 modelos CrisisMath
│   └── conftest.py              ← Fixtures globais
├── frontend/
│   ├── index.html               ← UI principal
│   ├── app.js                   ← Lógica do frontend
│   └── styles.css               ← Estilos
├── scripts/
│   ├── serve_ceo_llamacpp.ps1   ← Servidor do CEO (Qwen3.6-27B via llama-server CUDA)
│   ├── serve_ceo.py             ← Compat OpenAI-compatible via llama-cpp-python
│   ├── launch_superezio_ceo.ps1 ← Launcher completo (CEO + API)
│   ├── launch_ui_server_sensei.ps1 ← Launcher Sensei (legacy, substituído)
│   ├── start_superezio.bat      ← Atalho simples (API cloud-only)
│   ├── build_f51_corpus.py      ← Pipeline de geração do corpus F51
│   ├── train_ceo_lora.py        ← Script de fine-tuning QLoRA
│   ├── eval_pipeline.py         ← Avaliação do pipeline
│   └── build_sensei_dataset.py  ← Builder de dataset (legacy)
├── desktop/                     ← Atalhos para área de trabalho
│   ├── SuperEzio.bat            ← API cloud-only
│   └── SuperEzio CEO.bat        ← CEO + API + UI
├── docs/
│   └── decision-tree.txt        ← Árvore decisional completa
├── reports/                     ← Benchmark reports
├── output/                      ← Playwright test output
├── .f51/
│   ├── checkpoints/             ← Checkpoints de sessão
│   └── partner/                 ← Handoff Deep ↔ Sasaki
├── .claude/
│   ├── partner/                 ← Sistema dual-agent
│   │   ├── PARTNER.md           ← Persona do Sasaki
│   │   └── handoff.json         ← Protocolo de handoff
│   ├── skills/                  ← 28 skills (CTF, malware, F51, etc.)
│   └── settings.local.json      ← Config local do Claude Code
├── .github/workflows/ci.yml     ← CI/CD (Windows, pytest + ruff + mypy)
├── CLAUDE.md                    ← Instruções do agente Deep
├── pyproject.toml               ← Build config (setuptools)
├── Dockerfile                   ← Multi-stage (CPU/GPU)
├── .env.example                 ← Template de variáveis de ambiente
├── Makefile                     ← Atalhos Unix
└── README.md                    ← Este arquivo
```

---

## 7. Modelos e Provedores

### CEO Local

| Atributo | Valor |
|----------|-------|
| **Modelo** | Qwen3.6-27B |
| **Quantização** | Q4_K_M (~4.5 bits) |
| **Tamanho** | 18 GB em disco, ~17 GB VRAM |
| **Contexto** | 8,192 tokens (expansível a 32K) |
| **Tool Calling** | OpenAI-compatible; parser legado para `<\|tool_call\|>` |
| **Servidor** | llama-cpp-python + FastAPI na porta 8082 |
| **Carga** | ~13 segundos |
| **GPUs** | 0 (5060 Ti 16GB) + 1 (3060 12GB) = 28 GB combinados |

### Cloud Providers

| Provider | Modelo | Input/MTok | Output/MTok | Prioridade | Role |
|----------|--------|-----------|-------------|------------|------|
| **Grok (xAI)** | grok-4.3 | $1.25 | $2.50 | -500 | Cloud primário |
| Grok Fast | grok-fast | $0.20 | $0.50 | — | Expert roles |
| **DeepSeek** | deepseek-v4-pro | $0.50 | $2.00 | -300 | Experts + fallback |
| **Gemini** | gemini-2.0-flash | — | — | 50 | Último recurso |

### Cascade de Decisão

```
CEO Local (Qwen3.6-27B) :8082    ← prioridade -670, local-only
  │
  └─ offline/sem GPU? ↓
Grok 4.3 Cloud                     ← prioridade -500, mais barato ($1.25/$2.50)
  │
  └─ sem XAI_API_KEY? ↓
DeepSeek V4 Pro                    ← prioridade -300, fallback atual
  │
  └─ sem key? ↓
Gemini 2.0 Flash                   ← prioridade 50, último recurso
```

---

## 8. Cascata de Decisão (ModelGateway)

O `ModelGateway` implementa cascade com retry exponential backoff:

```
1. CEO Local (Qwen3.6)
   ├── ready? → USA (temp=0.4, max_tokens=4096)
   └── falhou/unreachable? ↓

2. Grok 4.3 Cloud
   ├── ready? → USA (temp=0.4, max_tokens=4096)
   └── falhou/sem key? ↓

3. DeepSeek Cloud
   ├── ready? → USA (temp=0.2, max_tokens=4096)
   └── falhou? ↓

4. Gemini (se configurado)
   ├── ready? → USA
   └── falhou? → MODEL_ERROR
```

### Orquestrador (classificação de intents)

O orquestrador usa o `primary_external` (DeepSeek ou o que estiver configurado
em `SUPEREZIO_PRIMARY_MODEL`) para classificação de intents quando o classificador
determinístico não atinge o threshold de confiança (0.76).

---

## 9. F51 Engine — Motor de Veredito

### Contrato público

```python
from f51 import F51Engine, Graph, Node, Context, NodeResult

engine = F51Engine()
result = engine.run({"ticker": "AAPL"}, domain="trading")

# Campos obrigatórios:
assert result.keys() >= {
    "confidence",   # score de confiança 0-1
    "threshold",    # threshold de decisão
    "passed",       # booleano: passou no gate?
    "expand_compute",  # budget computacional expandido
    "factors",      # fatores que influenciaram a decisão
    "nodes",        # resultados de cada nó do grafo
    "evidence",     # evidências coletadas
    "elapsed_ms"    # tempo de execução
}
```

### Grafo interno F51

```
Input (trace + features + claims)
  │
  ├─ spider_sense ──────────────┐
  │   perigo textual (0-1)      │
  │                              │
  ├─ difficulty_estimator ──────┤
  │   incerteza heurística      │
  │                              │
  ├─ platinum_scorer ◄──────────┤ (depende dos 2 acima)
  │   qualidade/consistência    │
  │   dos dados (7 campos)      │
  │                              │
  ├─ veracity_gate              │
  │   claims vs ground_truth    │
  │   (VeracityGate.verify())   │
  │                              │
  └─ adversarial_critic ◄───────┘ (depende de veracity + difficulty)
      consistência lógica
      dos indicadores financeiros

  → RiskEngine (6 regras reais de red_flag_rules.json)
  → VeracityGate explícito (claims numéricas)
  → output: confidence, threshold, passed, factors, evidence
```

### Componentes F51

| Componente | Função |
|-----------|--------|
| **SpiderSense** | Detecta perigo textual no input do usuário (0-1) |
| **DifficultyEstimator** | Estima incerteza com base em missing_data_ratio + volatilidade |
| **PlatinumScorer** | Score de qualidade de dados: completude × consistência |
| **VeracityGate** | Verifica claims contra ground_truth com tolerância |
| **AdversarialCritic** | Crítica lógica: inconsistências grotescas nos indicadores |
| **RiskEngine** | Avalia 6 regras de fraude (volume spike, microcap, hype, revenue, etc.) |
| **ProxyReward** | Recompensa por consistência entre fontes de dados |
| **HeuristicUncertainty** | Incerteza calibrada baseada em features |

### F51HubAdapter

Conecta o motor F51 aos dados reais do pipeline:

```python
from core.f51_adapter import F51HubAdapter

adapter = F51HubAdapter()
verdict = adapter.run_on_trace(trace_data)
# verdict["confidence"]  → score 0-1
# verdict["hub_risk"]    → avaliação do RiskEngine
# verdict["passed"]      → gate decision
```

---

## 10. F51 Behavioral Corpus

Dataset sintético para fine-tuning do CEO, gerado por 3 professores independentes.

### Estrutura

```
data/corpus/
├── MANIFEST.json          ← Metadados, licença (MIT), proveniência
├── 01_sft/                ← Supervised Fine-Tuning
│   └── sft_batch_001.jsonl    pergunta → resposta perfeita estilo F51
├── 02_dpo/                ← Direct Preference Optimization
│   └── dpo_batch_001.jsonl    pergunta → resposta boa vs ruim
├── 03_critic/             ← Critique examples (em construção)
└── 04_eval_locked/        ← CASOS TRANCADOS — nunca usar para treino
    ├── eval_cases.jsonl
    └── README.md           ← "NUNCA USE PARA TREINO"
```

### Teacher Models

| Professor | Modelo | Papel |
|-----------|--------|-------|
| **Bob** (primário) | DeepSeek V4 Pro via Claude Code | Arquiteto F51, expertise profunda no domínio |
| **GPT/Codex** (secundário) | OpenAI | Variantes, verificação cruzada, diversidade de estilo |
| **Gemini** (terciário) | Google | Triangulação, fact-checking, perspectiva alternativa |

### Protocolo de Consenso

Para exemplos críticos (eval, DPO), 2+ professores devem concordar.
Divergência → revisão manual ou descarte.

### Estratégia de Escala

```
100 exemplos → validar → 500 → 1500 → 5000 → 10000
   ↑                        ↑
Batch 001 (pronto)     Cada etapa validada
                       nos primeiros 20 exemplos
```

### Quality Gates

- `min_evidence_citations`: 1 por resposta
- `no_invented_numbers`: proibido inventar preço, P/E, volume
- `fact_inference_separated`: `[FACT]` vs `[INFERENCE]` vs `[SPECULATION]`
- `risk_explicit`: VaR, drawdown, ou declaração de ausência
- `source_stated`: fonte de cada dado citada
- `format_operational`: estrutura padronizada F51

### Categorias

| Categoria | Descrição | Exemplos |
|-----------|-----------|----------|
| fraud_detection | Identificar pump-and-dump, manipulação | 1 SFT, 1 DPO, 1 Eval |
| risk_assessment | Avaliar riscos com VaR, drawdown, tail risk | 1 SFT, 1 Eval |
| penny_stock_screening | Screen com filtros fundamentais e técnicos | 1 SFT |
| veracity_check | Verificar claims contra dados reais | 1 SFT |
| sizing | Calcular posição F51 (Kelly modificado) | 1 SFT, 1 Eval |
| missing_data | Reconhecer falta de dados (não inventar) | 1 Eval |
| tool_usage | Usar ferramentas antes de responder | 1 DPO, 1 Eval |
| uncertainty | Expressar incerteza calibrada | 1 DPO |
| rejection | Rejeitar pedidos perigosos (all-in, garantia) | 1 DPO |
| evidence_grounding | Responder com evidência, não opinião | 1 DPO |

---

## 11. Sistema Dual-Agent (Deep + Sasaki)

```
Deep (arquiteto)                    Sasaki (auditor)
─────────────────                    ─────────────────
Planeja patches                      ─
Decide arquitetura                   ─
Cria código                          ─
Escreve .f51/partner/diff.txt        ─
Invoca Sasaki ─────────────────────→ Lê PARTNER.md + diff.txt
                                     Roda pytest (503 testes)
                                     Roda ruff check
                                     Verifica contrato F51
                                     Escreve .f51/partner/review.md
Lê review.md ←────────────────────── Emite veredito
Decide se commita                    ─
```

### Regras do Sasaki

1. **Nunca edita código** — só audita, testa e reporta
2. **Sempre duvida** — prefere 10 falsos positivos a 1 falso negativo
3. **Sempre roda testes** — antes de qualquer veredito
4. **Sempre checa contrato F51** — `F51Engine.run()` com 8 campos obrigatórios
5. **Emito veredito** — APROVADO / REPROVADO / APROVADO COM RESSALVAS

### Handoff

- **Input**: `.f51/partner/diff.txt` (git diff do patch)
- **Output**: `.f51/partner/review.md` (veredito com evidências)
- **Persona**: `.claude/partner/PARTNER.md`
- **Protocolo**: `.claude/partner/handoff.json`

---

## 12. Segurança (SecurityContext)

Todo input do usuário passa por validação antes de entrar no pipeline.
Todo output do CEO é sanitizado antes de chegar ao usuário.

### Input Validation

| Check | O que faz |
|-------|-----------|
| **Tamanho** | Mensagem ≤ 10K chars, contexto ≤ 100K chars |
| **Injeção XSS** | `<script>`, `javascript:`, event handlers |
| **Injeção SQL** | `SELECT...FROM`, `DROP TABLE`, `UNION SELECT` |
| **Code Execution** | `exec()`, `eval()`, `system()`, `os.system`, `subprocess` |
| **Null bytes** | `\x00` |
| **Control chars** | `\x00-\x08`, `\x0B`, `\x0C`, `\x0E-\x1F`, `\x7F` |
| **Rate Limiting** | 30 chamadas por 60s por session_id |

### Output Sanitization

| Check | O que faz |
|-------|-----------|
| **PII Filter** | Email, CPF, CNPJ, CEP, cartão de crédito, telefone, IP → `[REDACTED]` |
| **Forbidden Phrases** | Frases de garantia de retorno, promessas de lucro → log + marcação |
| **Truncation** | Output > 50K chars → truncado com aviso |

### Edge Gateway

- Autenticação via API key ou JWT
- Rate limiting: RPM, RPH, burst configuráveis
- Production gate: `SUPEREZIO_PRODUCTION=true` exige auth habilitada + secret configurada
- Dev mode: `SUPEREZIO_EDGE_AUTH=false` (padrão nos launchers locais)

---

## 13. Setup e Instalação

### Pré-requisitos

- Python 3.12+
- 2 GPUs NVIDIA com 28 GB VRAM combinados (ou 1 GPU com 16 GB)
- 64 GB RAM recomendado
- ~50 GB de espaço em disco (modelo + código + dados)

### Instalação rápida

```bash
# 1. Clone
git clone <repo-url> SuperEzio
cd SuperEzio

# 2. Ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# 3. Dependências
pip install -e .

# 4. Configurar .env
cp .env.example .env
# Editar .env com suas API keys

# 5. Baixar modelo CEO
# Download local do GGUF:
python scripts/download_ceo_model.py
```

### API Keys necessárias

| Variável | Provedor | Onde conseguir |
|----------|----------|---------------|
| `XAI_API_KEY` | Grok (xAI) | https://console.x.ai |
| `SUPEREZIO_DEEPSEEK_API_KEY` | DeepSeek | https://platform.deepseek.com |
| `GEMINI_API_KEY` | Gemini (opcional) | https://aistudio.google.com |
| `SUPEREZIO_EDGE_SECRET` | Auth local | `python -c "import secrets; print(secrets.token_hex(32))"` |

---

## 14. Comandos e Entrypoints

### Produção

```bash
# Servidor CEO local (Qwen3.6-27B via llama-server CUDA)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082

# API Server (FastAPI + frontend)
python -m agent_server.main

# Tudo junto (PowerShell)
.\scripts\launch_superezio_ceo.ps1
```

### Desenvolvimento

```bash
# Testes
python -m pytest tests/ -q                    # Suite completa
python -m pytest tests/ -q --tb=short         # Com traceback
python -m pytest tests/test_fdb.py tests/test_financial_suite.py -q  # Focados

# Lint e formato
python -m ruff check src tests                # Lint
python -m ruff format src tests --check       # Formato

# Type check (opcional, continue-on-error no CI)
mypy src/ --ignore-missing-imports

# Corpus
python scripts/build_f51_corpus.py --stats    # Estatísticas do corpus
```

### Atalhos Desktop

| Atalho | Função |
|--------|--------|
| `SuperEzio.bat` | API cloud-only (rápido, sem GPU) |
| `SuperEzio CEO.bat` | CEO local + API + UI (completo) |

---

## 15. API Reference

### Endpoints principais

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Frontend (index.html) |
| `GET` | `/health` | Health check (GPU, Redis, modelos, providers) |
| `GET` | `/metrics` | Métricas de negócio (latência, erro rate, tokens) |
| `GET` | `/neural/logs` | SSE stream de logs |
| `POST` | `/task/submit` | Submeter tarefa de análise |
| `GET` | `/product/manifest` | Manifesto do produto |

### Health Check Response

```json
{
  "status": "ok",
  "agent": "superezio",
  "version": "3.0.0",
  "checks": {
    "gpu": {
      "available": true,
      "devices": [
        {"id": 0, "name": "NVIDIA GeForce RTX 5060 Ti", "vram_mb": 16384},
        {"id": 1, "name": "NVIDIA GeForce RTX 3060", "vram_mb": 12288}
      ],
      "status": "ok"
    },
    "local_models": {
      "ceo": {"url": "http://127.0.0.1:8082/v1", "reachable": true, "status": "ok"}
    },
    "redis": {"status": "skipped"},
    "providers_summary": {
      "primary": {"configured": true, "provider": "grok", "model": "grok-4.3"},
      "deepseek": {"configured": true, "model": "deepseek-v4-pro"}
    },
    "cost_guard": {"status": "ok"}
  }
}
```

---

## 16. Frontend

Interface web servida em `http://127.0.0.1:8002/`:

- **Penny Stock CEO Desk**: console operacional para penny stocks
- **Ticker input**: símbolo do ticker + botão "Load market data"
- **CEO focus**: pergunta livre + botão "Run CEO verdict"
- **Sizing**: cash available, position size, horizon, risk tolerance
- **Chart evidence**: gráfico de preço com RSI e moving averages
- **Proof/Evidence**: stream de eventos do pipeline em tempo real
- **CEO Verdict**: resposta final do CEO com análise completa

Stack: Vanilla HTML/CSS/JS + Chart.js + SSE (Server-Sent Events)

---

## 17. Testes e Qualidade

### Cobertura

| Métrica | Valor |
|---------|-------|
| Test functions | 476 |
| Assertions | 1,075 |
| Assert/test ratio | 2.3 |
| Testes ocos (0 asserts) | 0 |
| Passed | 503 |
| Skipped | 6 (IO real não mockado) |
| Tempo de execução | ~30 segundos |

### Categorias de teste

| Arquivo | O que testa |
|---------|------------|
| `test_security.py` | SecurityContext (42 testes) — XSS, SQLi, PII, rate limit |
| `test_pipeline_e2e.py` | Pipeline end-to-end |
| `test_pipeline_integration.py` | Integração entre módulos |
| `test_pipeline_edge_cases.py` | Casos limite do pipeline |
| `test_pipeline_ceo_cascade.py` | Cascade do CEO (local → cloud) |
| `test_pipeline_intents.py` | Classificação de intents |
| `test_financial_suite.py` | Suite financeira completa |
| `test_f51_public_import.py` | Contrato público F51 |
| `test_f51_adapter_trace.py` | F51HubAdapter.run_on_trace() |
| `test_fraud_analyst.py` | Detecção de fraude |
| `test_pennylab.py` | PennyLab (4 experts) |
| `test_veracity_gate.py` | VeracityGate |
| `test_hardening.py` | Hardening de segurança |
| `test_production_gate.py` | Gate de produção |
| `test_fdb.py` | Financial Database |
| `crisis_math/test_*.py` | 12 modelos CrisisMath |

---

## 18. CI/CD

GitHub Actions (`.github/workflows/ci.yml`):

```yaml
Triggers: push/pull_request na main
Runner: windows-latest
Python: 3.12

Steps:
  1. Checkout
  2. Setup Python
  3. Instalar dependências (pip install -e .)
  4. Lint (ruff check src tests)
  5. Format check (ruff format src tests --check)
  6. Type check (mypy src/ --ignore-missing-imports) [continue-on-error]
  7. Testes com coverage (pytest --cov=src --cov-fail-under=60)
```

---

## 19. Variáveis de Ambiente

### Obrigatórias (pelo menos uma cloud)

```bash
# Grok (xAI) — recomendado: mais barato do mercado
XAI_API_KEY=xai-...

# DeepSeek — opcional para experts/orquestração
SUPEREZIO_DEEPSEEK_API_KEY=sk-...
```

### CEO Local

```bash
SUPEREZIO_CEO_MODEL_PATH=models/Qwen3.6-27B-Q4_K_M.gguf
SUPEREZIO_CEO_PORT=8082
SUPEREZIO_CEO_BASE_URL=http://127.0.0.1:8082/v1
```

### Auth e Segurança

```bash
SUPEREZIO_EDGE_AUTH=false          # true em produção
SUPEREZIO_EDGE_SECRET=            # obrigatório se EDGE_AUTH=true
SUPEREZIO_PRODUCTION=false        # true em produção
SUPEREZIO_API_KEYS=               # comma-separated
```

### Observabilidade

```bash
SUPEREZIO_ENABLE_OTEL=true
```

### Pipeline Tuning

```bash
SUPEREZIO_ORCHESTRATOR_TIMEOUT=12
SUPEREZIO_CEO_TIMEOUT=120
SUPEREZIO_DATA_TIMEOUT=60
SUPEREZIO_EXPERT_TIMEOUT=60
SUPEREZIO_EXPERT_CONCURRENCY=4
SUPEREZIO_INTENT_LLM_FALLBACK=auto
SUPEREZIO_INTENT_LLM_THRESHOLD=0.76
```

### Memória (Mem0)

```bash
MEM0_API_KEY=
MEM0_REDIS_URL=
```

Veja `.env.example` para a lista completa.

---

## 20. Atalhos e Launchers

### Na Área de Trabalho

| Atalho | Conteúdo |
|--------|----------|
| `SuperEzio.bat` | API cloud-only. Sobe `python -m agent_server.main` na porta 8002. |
| `SuperEzio CEO.bat` | CEO local + API + UI. Roda `launch_superezio_ceo.ps1`. |

### No Projeto

| Script | O que faz |
|--------|-----------|
| `scripts/start_superezio.bat` | API cloud-only (simples, dev local) |
| `scripts/launch_superezio_ceo.ps1` | CEO (Qwen3.6) + API juntos |
| `scripts/serve_ceo_llamacpp.ps1` | Servidor standalone do CEO na porta 8082 via llama-server CUDA |

---

## 21. Roadmap e Tarefas Pendentes

### Concluído (sessão 2026-05-11/12)

- [x] SecurityContext wired no pipeline runtime
- [x] Migração CEO para Qwen3.6-27B local
- [x] Tool calling nativo no CEO
- [x] Limpeza de identidade (Bob → Sensei → CEO)
- [x] Sistema dual-agent Deep + Sasaki
- [x] Grafo F51 sem mocks (platinum_scorer, veracity_gate, adversarial_critic)
- [x] Integração Grok (xAI) como cloud provider primário
- [x] F51 Behavioral Corpus batch 001
- [x] Atalhos na área de trabalho
- [x] Scanner expandido com mercado CA (Canadá)
- [x] 21 tools registradas e expostas ao modelo
- [x] .gitattributes (LF/CRLF unificado)

### Pendente (prioridade)

| ID | Tarefa | Impacto |
|----|--------|---------|
| P5 | Teste formal pytest para F51HubAdapter.run_on_trace() | +0.3 |
| P4 | Edge auth default true (produção) | +0.2 |
| P6 | Normalizar LF/CRLF nos arquivos restantes | +0.1 |
| P7 | Black format drift em 3 arquivos f51 | +0.1 |
| P8 | Relatório de cobertura de testes | +0.2 |

### Corpus (próximos batches)

- [ ] Batch 002: +5 SFT, +5 DPO, +3 Critic
- [ ] Batch 003: +10 SFT (GPT como teacher secundário)
- [ ] Validar batch 001-003 contra eval_locked
- [ ] Escalar para 500 exemplos

---

## 22. Métricas do Projeto

| Métrica | Valor |
|---------|-------|
| **Versão** | 3.0.0 |
| **Source files** | 148 (.py) |
| **Test files** | 44 (.py) |
| **Lines of code** | 21,476 |
| **Total commits** | 89 |
| **Testes** | 503 passed, 6 skipped |
| **Assert/Test ratio** | 2.3 |
| **Lint issues** | 0 |
| **Modelo local** | Qwen3.6-27B Q4_K_M (~17 GB) |
| **VRAM uso** | ~20 GB (2 GPUs) |
| **Carga do modelo** | ~13 segundos |
| **Cloud providers** | 4 (Grok, DeepSeek, Gemini, primary_external) |
| **Experts financeiros** | 12 agentes |
| **PennyLab experts** | 4 especialistas |
| **CrisisMath modelos** | 12 modelos |
| **Tools registradas** | 21 |
| **Nós no grafo** | 8 (orchestrator, data, f51_verdict, pennylab, run_expert, collect_experts, ceo_primary, explanation) |
| **Skills Claude Code** | 28 registradas |
| **Corpus examples** | 15 (5 SFT + 5 DPO + 5 Eval) |
| **Segurança** | SecurityContext wired, Edge Gateway com auth |

---

## Licença

MIT — SuperEzio v3.0.0

## Contato

Marco Barreto / Fuch F51 Labs

---

*"Não existe investimento com retorno garantido. Todo veredito requer evidência.
Incerteza não é fraqueza — é precisão."* — Protocolo F51
