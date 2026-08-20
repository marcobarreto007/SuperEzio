# SuperEzio V1 — Product Delivery Contract

Status: active roadmap  
Updated: 2026-08-20  
Owner of capital/go-live: Marco (human, never an agent)

## Product boundary

The first transferable product is a **local Windows financial research copilot**. It provides
an authenticated cockpit, Canadian chart data, Bob chat, evidence and risk explanations.

V1 does **not** transmit orders, automate TD WebBroker, claim profitable alpha or expose IBKR,
Questrade, TD live-manual, training or background trading as user-facing product features.

Initial buyer/operator: one Canadian self-directed investor running locally. External SaaS,
multi-tenancy and sale are deferred until quality and temporal benchmarks exist.

## P0 — blocks a V1 release candidate

1. Freeze the public contract to research-only and prove no order transport is reachable.
2. Replace machine-specific startup/install paths with one canonical Windows flow using the lock.
3. Unify auth so bootstrap, login and middleware use one contract and no known default password.
4. Synchronize inventory, runtime/API contracts and onboarding to Qwen 27B on `:8080` + API `:8002`.
5. Make response-quality probe fail closed on latency, empty output, internal template leakage,
   language drift and ticker/company mismatch.
6. Build a clean ZIP candidate with manifest, SHA-256, exclusions and rollback instructions.
7. Rehearse install/start/login/chart/chat/logout/stop on a clean Windows VM.
8. Rotate previously exposed provider credentials before transferring any historical tree.

## P1 — after clean-machine startup

- Separate liveness from readiness and set explicit latency/SLO limits.
- Correct remaining language, intent and ticker/company response defects.
- Finish onboarding, evidence index, disaster recovery and buyer checklist.
- Keep the TD commission-free research universe dated and fail closed when stale.

## P2 — cut from V1

- Docker, Linux/macOS and one-file PyInstaller.
- Broker automation and live-capital UI.
- Multi-user SaaS, model training, new experts and premium visual redesign.
- Claims such as “best in the world”, guaranteed return or real-money readiness.

## Definition of done

- A clean Windows VM extracts one ZIP and follows one official setup/start/stop flow.
- No developer-specific absolute path; secrets/passwords are generated uniquely.
- Login -> Canadian chart -> Bob question -> answer -> logout passes in the packaged copy.
- Greeting is under 2 seconds; chart is under 15 seconds; analysis has a declared timeout.
- Full pytest, Ruff, contracts, security, browser smoke with chat and quality eval pass.
- Tests leave operator journals, memory, RAG, databases and traces byte-identical.
- Package excludes `.env`, secrets, databases, WAL/SHM, logs and operator data.
- Restore/restart and rollback are rehearsed; manifest and checksum are recorded.
- TD remains `NO_GO_REAL_CAPITAL` and no agent can change that status.

## Delivery workflow

`orchestrator -> implementer -> independent verifiers -> SRE/runtime -> release -> savekeeper`

Official references:

- Anthropic: https://www.anthropic.com/engineering/building-effective-agents
- Anthropic multi-agent system: https://www.anthropic.com/engineering/multi-agent-research-system
- OpenAI Agents orchestration: https://openai.github.io/openai-agents-python/multi_agent/
- OpenAI human-in-the-loop: https://openai.github.io/openai-agents-python/human_in_the_loop/
- Microsoft Magentic-One: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/magentic-one.html
- Google SRE canary releases: https://sre.google/workbook/canarying-releases/
