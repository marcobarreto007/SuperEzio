"""
F51 Grok-4.3 Blood Transfusion — PYTHON ONLY
==============================================
100% Python domain. Beat GPT-4 on LMSYS Arena Coding category.
Generate premium Python SFT data until xAI credits run out.
"""

import os
import json
import time
import random
import hashlib
import asyncio
import aiohttp
from datetime import datetime, timezone
from collections import Counter

# ── Config ─────────────────────────────────────────────────────
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_URL = "https://api.x.ai/v1/chat/completions"
MODEL = "grok-4.3"
DOMAIN = "python"

OUT_DIR = r"C:\Users\marco\Desktop\F51-Dataset-Operacao\datasets\grok_transfusion"
CHECKPOINT_INTERVAL = 100
MAX_CONCURRENT = 40
TARGET_PER_CALL = 5  # generate 5 entries per API call

# Python sub-categories for diversity
PYTHON_CATEGORIES = [
    "async_concurrency",      # asyncio, threading, multiprocessing
    "performance_optimization",  # profiling, memory, vectorization
    "api_design",             # REST, FastAPI, Flask, pydantic
    "testing_quality",        # pytest, property-based, coverage
    "data_engineering",       # pandas, polars, streaming, ETL
    "security_safety",        # input validation, secrets, sandbox
    "debugging_diagnostics",  # root cause, profiling, tracing
    "architecture_patterns",  # design patterns, SOLID, clean arch
    "type_system",            # generics, protocols, overloads, mypy
    "packaging_deployment",   # wheels, docker, pip, poetry
    "cli_tools",              # argparse, click, typer, rich
    "metaprogramming",        # decorators, descriptors, metaclasses
]

DIFFICULTIES = ["medium", "hard", "easy"]
DIFFICULTY_WEIGHTS = [0.45, 0.40, 0.15]  # heavy on medium/hard

os.makedirs(OUT_DIR, exist_ok=True)

# ── Massive Python Prompt Bank ─────────────────────────────────
PYTHON_PROMPTS = [
    # === async_concurrency ===
    {
        "cat": "async_concurrency",
        "sys": "You are a senior Python async/concurrency engineer. You specialize in asyncio, threading, multiprocessing, and distributed task queues for high-throughput production systems.",
        "usr": "Design a producer-consumer pipeline with asyncio.Queue that handles 10k messages/sec from Kafka, transforms them with CPU-bound operations, and writes to PostgreSQL. Include backpressure, graceful shutdown, and error recovery.",
    },
    {
        "cat": "async_concurrency",
        "sys": "You are a Python backend architect at a fintech company. Your expertise is in building reliable async services that handle financial transactions with exactly-once semantics.",
        "usr": "Implement a distributed rate limiter using asyncio and Redis that supports sliding window, token bucket, and concurrent request limiting. Must handle Redis connection failures gracefully with fallback to local limiting.",
    },
    {
        "cat": "async_concurrency",
        "sys": "You are a concurrency expert reviewing Python services. You find deadlocks, race conditions, and starvation bugs before they hit production.",
        "usr": "Our asyncio web scraper with 500 concurrent tasks freezes after ~30 minutes with no errors. Memory usage is stable, CPU is low, but new tasks stop being created. Walk through the systematic debugging approach and likely root causes.",
    },
    {
        "cat": "async_concurrency",
        "sys": "You are a staff engineer designing Python microservices for low-latency trading systems.",
        "usr": "Compare asyncio.gather vs asyncio.TaskGroup (Python 3.11+) vs trio-style nurseries for managing concurrent API calls to 20 external services with different timeouts. Include error propagation semantics and cancellation behavior.",
    },
    {
        "cat": "async_concurrency",
        "sys": "You are a Python performance engineer optimizing a real-time analytics pipeline processing 1M events/minute.",
        "usr": "We use ThreadPoolExecutor for I/O and ProcessPoolExecutor for CPU. Profiling shows 40% time spent in thread synchronization and pickling overhead. Redesign using asyncio + uvloop + shared memory (multiprocessing.shared_memory). Include benchmark methodology.",
    },
    # === performance_optimization ===
    {
        "cat": "performance_optimization",
        "sys": "You are a Python performance wizard. You profile, benchmark, and optimize Python code to C-level speeds using vectorization, JIT compilation, and native extensions.",
        "usr": "A pandas pipeline processing 5M rows takes 45 seconds. Profile the bottleneck and rewrite using polars + numpy vectorization + numba JIT. Target: under 3 seconds. Show the profiling methodology and before/after code.",
    },
    {
        "cat": "performance_optimization",
        "sys": "You are a memory optimization specialist for Python data pipelines. You squeeze maximum throughput from constrained RAM budgets.",
        "usr": "A JSONL cleaning pipeline loads 2GB files into memory, causing OOM on 8GB containers. Refactor to use memory-mapped I/O, streaming parsers (ijson/orjson), and incremental deduplication. Show memory profiling with fil-profile and tracemalloc.",
    },
    {
        "cat": "performance_optimization",
        "sys": "You optimize Python compilation and startup for CLI tools and lambda functions. Milliseconds matter.",
        "usr": "A Python CLI tool takes 800ms just to show --help. Profile the import graph and apply lazy imports, __slots__, dataclass optimization, and pre-compiled .pyc strategies. Target: under 150ms cold start.",
    },
    {
        "cat": "performance_optimization",
        "sys": "You are a Python-C integration expert building native extensions for hot paths.",
        "usr": "A tight loop doing string parsing and integer conversion is the bottleneck. Compare cython vs mypyc vs Rust/PyO3 for rewriting the hot path. Include build setup, type annotations, and benchmark harness code.",
    },
    # === api_design ===
    {
        "cat": "api_design",
        "sys": "You are a senior API architect specializing in FastAPI, Pydantic, and OpenAPI. You design REST and GraphQL APIs that scale to millions of requests.",
        "usr": "Design a FastAPI service with Pydantic v2 models for a multi-tenant SaaS platform. Include: dependency injection for tenant context, request ID propagation, structured logging, rate limiting per tenant, and automatic OpenAPI docs with examples. Show the middleware stack and error handling strategy.",
    },
    {
        "cat": "api_design",
        "sys": "You design versioned, backwards-compatible APIs for platforms with thousands of clients. Breaking changes are not an option.",
        "usr": "We need to add a new required field to our payment API request body without breaking existing clients. Design a versioning strategy using FastAPI with content negotiation, deprecation headers, and a 6-month sunset policy. Include request/response transformation for each version.",
    },
    {
        "cat": "api_design",
        "sys": "You are a Python web framework expert who has built APIs at every scale — from startups to FAANG.",
        "usr": "Compare FastAPI vs Litestar vs Django-Ninja for a new project with 50+ endpoints, WebSocket support, background tasks, and dependency on SQLAlchemy async. Evaluate: performance (req/s), type safety, OpenAPI quality, testing ergonomics, and ecosystem maturity.",
    },
    {
        "cat": "api_design",
        "sys": "You specialize in resilient API patterns: circuit breakers, retries, timeouts, idempotency keys.",
        "usr": "Implement a Python HTTP client wrapper with: exponential backoff + jitter, circuit breaker (half-open probe), connection pooling, automatic retry for idempotent methods, deadline propagation via headers, and Prometheus metrics. Use httpx as the underlying client.",
    },
    # === testing_quality ===
    {
        "cat": "testing_quality",
        "sys": "You are a testing architect who designs test strategies for complex Python systems. You believe comprehensive testing is a competitive advantage.",
        "usr": "Design a complete testing strategy for a FastAPI payment service: pytest fixtures for database (testcontainers-postgres), contract tests with Pact for external APIs, property-based tests with Hypothesis for amount validation, load tests with Locust for 1000 RPS targets, and chaos testing for dependency failures.",
    },
    {
        "cat": "testing_quality",
        "sys": "You are a property-based testing expert. You use Hypothesis to find edge cases that example-based tests miss.",
        "usr": "Write property-based tests for a JSON normalization pipeline that takes arbitrary nested JSON and flattens it to {key: value} pairs. Define invariants: no keys lost, no values modified, roundtrip reversibility where possible, and handling of edge cases (empty objects, arrays, nulls, Unicode keys, deep nesting).",
    },
    {
        "cat": "testing_quality",
        "sys": "You are a senior QA engineer building test infrastructure for a Python monorepo with 200+ packages.",
        "usr": "Our test suite takes 40 minutes. Design a parallelization strategy using pytest-xdist, test splitting by file-level coverage history, flaky test quarantine, and a 'smoke' subset (under 2 minutes) for pre-commit. Include CI configuration for GitHub Actions.",
    },
    {
        "cat": "testing_quality",
        "sys": "You specialize in testing async Python code. You know every pitfall of asyncio testing.",
        "usr": "Write comprehensive tests for an async WebSocket service using pytest-asyncio. Test: connection lifecycle, message ordering, reconnection with exponential backoff, concurrent broadcasts to 1000 clients, and graceful degradation when downstream services fail. Mock asyncio event loop time for timeout tests.",
    },
    # === data_engineering ===
    {
        "cat": "data_engineering",
        "sys": "You are a data engineer building petabyte-scale Python ETL pipelines. Streaming, batch, and lambda architectures are your daily tools.",
        "usr": "Design a Python ETL pipeline that ingests 50GB/day of nested JSON from S3, validates schema with Pydantic, deduplicates by business key, enriches with API lookups (rate-limited), and writes to Delta Lake with Z-ordering. Use PyArrow, DuckDB, and Ray for distributed processing.",
    },
    {
        "cat": "data_engineering",
        "sys": "You are a Python data specialist optimizing pandas/polars workflows for financial time series.",
        "usr": "We process 10 years of tick-level trading data (50B rows) stored in Parquet. Need to resample to 1-minute OHLCV bars with VWAP. Compare polars lazy vs DuckDB SQL vs PySpark for this workload. Include partition pruning, predicate pushdown, and memory budget constraints.",
    },
    {
        "cat": "data_engineering",
        "sys": "You build streaming data systems in Python. Kafka, Flink, and Bytewax are your tools.",
        "usr": "Implement a real-time fraud detection feature pipeline: consume from Kafka (JSON transactions), compute rolling window aggregations (count, sum, avg, std over 5min/1h/24h windows), join with user profile from Redis, and output feature vectors to a model serving endpoint. Use Bytewax for stateful streaming.",
    },
    # === security_safety ===
    {
        "cat": "security_safety",
        "sys": "You are a Python security engineer. You audit code for vulnerabilities, implement secure defaults, and build security tooling.",
        "usr": "Audit this Python code pattern for security issues: subprocess.run(f'git clone {repo_url} /tmp/repo', shell=True). Explain the injection vector, demonstrate a working exploit payload, and show 3 secure alternatives with increasing safety guarantees.",
    },
    {
        "cat": "security_safety",
        "sys": "You secure Python applications against OWASP Top 10 vulnerabilities. You think like an attacker.",
        "usr": "Describe how Python's pickle deserialization can lead to RCE. Show a working proof-of-concept exploit class that executes code on deserialization. Then explain safe alternatives: JSON Schema validation, protobuf, and restricted unpicklers. Include detection strategies for production.",
    },
    {
        "cat": "security_safety",
        "sys": "You are a DevSecOps engineer integrating security scanning into Python CI/CD pipelines.",
        "usr": "Design a security scanning pipeline for a Python codebase: bandit for static analysis, safety + pip-audit for dependency CVEs, detect-secrets for credential scanning, and custom AST-based rules for business logic vulnerabilities. Include severity thresholds that block merges.",
    },
    # === debugging_diagnostics ===
    {
        "cat": "debugging_diagnostics",
        "sys": "You are a Python debugging specialist. You find bugs that other engineers give up on. You use every tool available: pdb, tracebacks, logging, tracing, and profiling.",
        "usr": "Production FastAPI service returns 500 errors for 0.1% of requests with no stack trace (generic Exception caught). The error only happens under concurrent load >100 req/s. Describe your systematic approach: add structured logging context, use asyncio debug mode, enable tracemalloc, and narrow down with binary search on code paths.",
    },
    {
        "cat": "debugging_diagnostics",
        "sys": "You diagnose memory leaks in long-running Python services. You dream in objgraph and gc.get_objects().",
        "usr": "A Python service slowly grows from 200MB to 2GB over 24 hours before OOM. Describe the debugging procedure: tracemalloc snapshot comparison, objgraph for reference cycle detection, gc debugging flags, and identifying the leaking object type. Show code for automated leak detection in CI.",
    },
    {
        "cat": "debugging_diagnostics",
        "sys": "You are an observability expert instrumenting Python services with OpenTelemetry, Prometheus, and structured logging.",
        "usr": "Design a Python observability setup for 20 microservices: distributed tracing with OpenTelemetry (context propagation across HTTP/gRPC/Kafka), custom Prometheus metrics for business KPIs, structured logging with structlog in JSON format, and SLO-based alerting with burn rate calculations.",
    },
    # === architecture_patterns ===
    {
        "cat": "architecture_patterns",
        "sys": "You are a software architect who designs Python systems using SOLID principles, DDD, and clean architecture. You fight coupling and champion cohesion.",
        "usr": "Refactor a 3000-line Django views.py file that mixes business logic, ORM queries, email sending, and PDF generation. Apply clean architecture: separate domain layer (pure Python, no dependencies), application layer (use cases), infrastructure layer (Django ORM, email, PDF), and presentation layer (views). Show the directory structure and key interfaces.",
    },
    {
        "cat": "architecture_patterns",
        "sys": "You design event-driven architectures in Python. You understand sagas, event sourcing, CQRS, and eventual consistency.",
        "usr": "Design an order processing system using event-driven architecture: OrderPlaced → PaymentReserved → InventoryAllocated → OrderConfirmed (or OrderFailed with compensating transactions). Use asyncio, a message broker (Redis Streams/NATS), and implement the saga pattern with compensation handlers.",
    },
    {
        "cat": "architecture_patterns",
        "sys": "You are a Python architect specializing in modular monoliths that can split into microservices when needed.",
        "usr": "Design a Python monolith with bounded contexts separated by in-process message bus. Each context has its own models, repository interfaces, and service layer. Show how the same interfaces can be replaced with HTTP/gRPC when extracting a service. Include dependency injection container setup.",
    },
    # === type_system ===
    {
        "cat": "type_system",
        "sys": "You are a Python typing expert. You push mypy --strict to its limits with generics, protocols, overloads, and TypeGuard.",
        "usr": "Design a generic Repository[T] protocol with async methods, a SQLAlchemy implementation, and an in-memory implementation for tests. Use Protocol for the interface, TypeVar with bounds, and ensure mypy catches type mismatches at the call site. Show CRUD operations with proper typing.",
    },
    {
        "cat": "type_system",
        "sys": "You specialize in Python's advanced typing features: TypedDict, Literal, overload, and recursive types.",
        "usr": "Build a type-safe JSON:API response builder using TypedDict, Literal, and overloaded functions. The response shape must vary by included relationships — if 'author' is included, the response type must include the author relationship. Use @overload so the caller gets correct return types without casting.",
    },
    {
        "cat": "type_system",
        "sys": "You write Python library APIs with perfect type hints. Users of your libraries get autocomplete and type checking for free.",
        "usr": "Design a Python library's public API with __init__.py re-exports, @typing.overload for different call signatures, TypeAlias for complex types, and py.typed marker. Show how to structure the package so users get excellent IDE support and mypy/pyright validation without reading docs.",
    },
    # === packaging_deployment ===
    {
        "cat": "packaging_deployment",
        "sys": "You are a Python packaging and deployment expert. You build reproducible builds, optimized Docker images, and smooth CI/CD pipelines.",
        "usr": "Design a production Docker setup for a FastAPI service: multi-stage build, non-root user, health checks, graceful shutdown signal handling, layer caching optimized for pip dependencies, and secrets injection via environment (never in image). Target image: under 150MB.",
    },
    {
        "cat": "packaging_deployment",
        "sys": "You manage Python monorepos with 50+ packages, shared dependencies, and complex build graphs.",
        "usr": "Design a Python monorepo structure using pip-tools or Poetry with a shared lockfile strategy. Packages: core (models, utils), api (FastAPI), workers (Celery), cli (Click). Each has separate pyproject.toml but shared dev dependencies. Show CI pipeline that only tests changed packages.",
    },
    # === cli_tools ===
    {
        "cat": "cli_tools",
        "sys": "You build beautiful, fast, and tested Python CLI tools. Rich, Typer, and Click are your paintbrushes.",
        "usr": "Build a CLI tool for managing a dataset pipeline: 'f51 dataset validate/score/split/export' subcommands. Use Typer for CLI, Rich for progress bars and tables, and Pydantic for config validation. Each subcommand should have --help with examples, --verbose flag, and JSON output mode for scripting.",
    },
    {
        "cat": "cli_tools",
        "sys": "You optimize Python CLI startup time. Every millisecond between the user pressing Enter and seeing output matters.",
        "usr": "A Python CLI built with Click takes 600ms to show any output. Profile with python -X importtime and optimize: lazy imports, frozen modules, zipapp packaging, and pre-compiled .pyc. Compare strategies and their tradeoffs. Target: under 100ms to first output.",
    },
    # === metaprogramming ===
    {
        "cat": "metaprogramming",
        "sys": "You are a Python metaprogramming wizard. Decorators, descriptors, metaclasses, and __init_subclass__ are your building blocks.",
        "usr": "Build a registration-based plugin system using __init_subclass__: define a Plugin base class where any subclass automatically registers itself. Add plugin discovery from entry_points (pyproject.toml), lazy loading, and isolated error handling so one broken plugin doesn't crash the host. Include type-safe plugin interfaces.",
    },
    {
        "cat": "metaprogramming",
        "sys": "You design Python DSLs and fluent APIs using operator overloading, context managers, and descriptor protocol.",
        "usr": "Build a pandas-like query DSL: `table.where(col('age') > 18).select(col('name'), col('email')).limit(10)`. Implement using __getattr__ for column references, __gt__/__eq__ for comparisons, and lazy evaluation that compiles to SQL or pandas operations. Show how the query tree is built and executed.",
    },
    # === extra diverse prompts ===
    {
        "cat": "async_concurrency",
        "sys": "You are a Python systems engineer building high-performance network services with socket programming and asyncio transports.",
        "usr": "Implement a custom asyncio Protocol for a binary TCP protocol with length-prefixed frames, heartbeat/ping-pong, and reconnection with message replay. Compare asyncio.Protocol vs asyncio.StreamReader/StreamWriter for this use case. Include buffer management for partial frames.",
    },
    {
        "cat": "performance_optimization",
        "sys": "You optimize Python for GPU-accelerated computing. CuPy, Numba CUDA, and PyTorch tensors are your tools.",
        "usr": "A numpy Monte Carlo simulation (1M paths, 1000 time steps, Cholesky decomposition) takes 30 minutes on CPU. Port to GPU using CuPy/Numba-CUDA. Show the conversion steps: identify parallelizable loops, manage GPU memory transfers, and batch operations. Target: under 30 seconds.",
    },
    {
        "cat": "data_engineering",
        "sys": "You validate and clean messy real-world data in Python. Nothing surprises you — not even \\0 bytes in CSV files.",
        "usr": "Design a robust CSV ingestion pipeline that handles: encoding detection (chardet/cchardet), BOM markers, inconsistent quoting, embedded newlines in quoted fields, mixed date formats, and NULL sentinel values (\\N, NULL, N/A, empty). Use Python's csv module with custom dialect detection. Show edge case tests.",
    },
    {
        "cat": "architecture_patterns",
        "sys": "You design Python systems using the actor model for concurrency. Pykka, Thespian, or custom asyncio-based actors.",
        "usr": "Design an actor-based trading system: MarketDataActor subscribes to websocket feeds, SignalActor computes indicators, RiskActor enforces position limits, OrderActor manages exchange orders. Use asyncio queues as actor mailboxes. Show supervision strategy: what happens when an actor crashes?",
    },
    {
        "cat": "debugging_diagnostics",
        "sys": "You debug Python garbage collection issues. You understand reference counting, cycle detection, and generational GC intimately.",
        "usr": "A FastAPI endpoint allocates 50MB per request but only 5MB is needed for the response. Use tracemalloc and objgraph to identify the allocation source. The culprit: a library caches large intermediate objects in closures. Show how to find the specific closure holding references and fix with weakref.",
    },
    {
        "cat": "type_system",
        "sys": "You enforce strict typing in large Python codebases. You write custom mypy plugins when the type system needs extension.",
        "usr": "Build a type-safe dependency injection container: register(Type, factory_function) and resolve(Type) must be fully typed. resolve(Database) returns a Database instance with mypy knowing the exact type. Use TypeVar, Generic, and __class_getitem__. No casts or Any in user code.",
    },
]

# ── System Prompt Generation ───────────────────────────────────
def generate_system_prompt(category, difficulty):
    """Generate a domain-specific system prompt with varied personas."""
    depth = {
        "easy": "Provide clear, educational Python explanations with runnable examples. Focus on understanding the fundamentals deeply.",
        "medium": "Provide detailed Python analysis with production-ready code, trade-off discussion, and performance considerations.",
        "hard": "Provide expert-level Python deep dives: edge cases, CPython internals where relevant, performance implications, and battle-tested production patterns. Assume the reader is a senior engineer.",
    }

    company = random.choice(["a FAANG company", "a high-frequency trading firm", "a cybersecurity startup", "an AI research lab", "a fintech unicorn", "an open-source foundation"])
    specialist = random.choice(["backend engineer", "systems programmer", "data engineer", "ML infrastructure engineer", "security researcher", "library author", "performance engineer", "architect"])
    years = random.choice(["8", "10", "12", "15", "20"])
    context = random.choice(["mission-critical financial systems", "high-throughput data pipelines", "security-sensitive applications", "developer tools used by millions", "scientific computing at scale", "latency-sensitive microservices"])

    personas = [
        f"You are a Python expert at {company}. {depth[difficulty]}",
        f"You are a Python {specialist} with {years} years of experience. {depth[difficulty]}",
        f"You write Python for {context}. {depth[difficulty]}",
    ]

    return random.choice(personas)


def generate_user_prompt(category):
    """Get a user prompt for the given category, or generate dynamically."""
    pool = [p for p in PYTHON_PROMPTS if p["cat"] == category]
    if pool:
        chosen = random.choice(pool)
        return chosen["usr"]

    # Fallback: dynamic prompt
    fallbacks = [
        f"Write a detailed Python guide on {category.replace('_', ' ')}. Include production-ready code examples, common pitfalls, testing strategies, and performance considerations.",
        f"I need to implement {category.replace('_', ' ')} in a Python production system. Show me the architecture, key code patterns, error handling, and how to test it thoroughly.",
        f"Review the best practices for {category.replace('_', ' ')} in Python 3.12+. Include code examples, anti-patterns to avoid, and how to integrate with existing codebases.",
    ]
    return random.choice(fallbacks)


# ── Meta Prompt ────────────────────────────────────────────────
def gen_meta_prompt(category, difficulty, n_entries):
    """Build the system-level instruction for Grok to generate Python entries."""
    sys_prompt = generate_system_prompt(category, difficulty)

    instructions = f"""You are generating premium SFT (Supervised Fine-Tuning) training data to beat GPT-4 at Python coding.

Domain: python | Category: {category} | Difficulty: {difficulty}

Generate {n_entries} DIVERSE Python training entries.

FORMAT: Return a JSON object with key "entries" containing an array:
{{
  "entries": [
    {{
      "system": "A detailed system prompt setting up the Python expert persona. 100-300 chars. Be specific about the Python context.",
      "user": "A realistic, detailed user query about Python. 200-800 chars. Include concrete requirements, constraints, edge cases. Read like a real engineering question from a senior developer.",
      "assistant": "Your COMPLETE Python expert response. THIS IS THE CRITICAL PART. Must be 1000-3000 chars. Include: working Python 3.12+ code with type hints, detailed explanation of the approach, trade-off analysis, edge case handling, performance considerations, testing strategy. Use pydantic, asyncio, FastAPI, polars, or other modern Python libraries where relevant. This is training data to beat GPT-4 — depth and correctness matter more than brevity."
    }},
    ...
  ]
}}

RULES:
- Each entry must test DIFFERENT Python skills within {category}
- Code must be RUNNABLE Python 3.12+ with type hints
- Include imports, error handling, and docstrings
- Cover sub-topics: CPython internals, memory model, GIL implications, async patterns, typing system, packaging
- System prompts must be varied across entries
- User queries must read like real-world engineering problems, not textbook exercises
- NEVER end with vague platitudes — always be specific and actionable
- Output VALID JSON with proper escaping (escape quotes inside strings)
- WRITE IN ENGLISH — this is EN training data"""

    return instructions


# ── API Call ────────────────────────────────────────────────────
async def call_grok(session, sem, category, difficulty, n_entries):
    """Call grok-4.3. Returns (entries_list, usage_dict) or (None, None)."""
    async with sem:
        system_instruction = gen_meta_prompt(category, difficulty, n_entries)

        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": system_instruction}],
            "max_tokens": 8192,
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
        }

        for attempt in range(3):
            try:
                async with session.post(
                    XAI_URL,
                    headers={
                        "Authorization": f"Bearer {XAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After", "30")
                        await asyncio.sleep(float(retry_after) + random.uniform(1, 5))
                        continue
                    if resp.status == 402:
                        return None, {"error": "quota_exhausted"}
                    if resp.status == 400:
                        text = await resp.text()
                        if "safety" in text.lower() or "refusal" in text.lower():
                            return [], {"error": "safety_refusal"}
                        if "quota" in text.lower() or "insufficient" in text.lower() or "billing" in text.lower():
                            return None, {"error": "quota_exhausted"}
                        await asyncio.sleep(2)
                        continue
                    if resp.status != 200:
                        await asyncio.sleep(2 ** attempt)
                        continue

                    data = await resp.json()
                    usage = data.get("usage", {})
                    content = data["choices"][0]["message"]["content"]

                    try:
                        parsed = json.loads(content)
                        entries = parsed.get("entries", [])
                    except json.JSONDecodeError:
                        if "```json" in content:
                            block = content.split("```json")[1].split("```")[0]
                            parsed = json.loads(block)
                            entries = parsed.get("entries", [])
                        elif "```" in content:
                            block = content.split("```")[1].split("```")[0]
                            parsed = json.loads(block)
                            entries = parsed.get("entries", [])
                        else:
                            return [], {"error": "json_parse_failure"}

                    return entries, usage

            except asyncio.TimeoutError:
                await asyncio.sleep(5)
                continue
            except Exception:
                await asyncio.sleep(2 ** attempt)
                continue

    return [], {"error": "max_retries_exceeded"}


# ── Entry Builder ──────────────────────────────────────────────
def build_entry(category, difficulty, system_content, user_content, assistant_content):
    """Build a standard F51 SFT Python entry."""
    return {
        "domain": "python",
        "category": category,
        "difficulty": difficulty,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
        "score": 10,
        "source": "grok-4.3-transfusion-python",
        "needs_expansion": False,
        "metadata": {
            "generated_by": "grok-4.3",
            "generation_date": datetime.now(timezone.utc).isoformat(),
            "quality": "premium",
            "target": "beat-gpt4-coding-arena",
        },
    }


def quality_check(entry):
    """Validate Python entry quality."""
    assistant = entry["messages"][2]["content"]
    user = entry["messages"][1]["content"]
    system = entry["messages"][0]["content"]

    if len(assistant) < 600:
        return False, f"assistant_too_short({len(assistant)}chars)"
    if len(system) < 40:
        return False, f"system_too_short({len(system)}chars)"
    if len(user) < 80:
        return False, f"user_too_short({len(user)}chars)"


    lower = assistant.lower()
    bad_phrases = ["entregue patch mínimo", "deliver minimal patch", "todo", "[placeholder]", "add your implementation"]
    for bp in bad_phrases:
        if bp in lower:
            return False, f"bad_phrase:{bp}"

    # Python entries should have some code
    if "```python" not in assistant and "import " not in assistant[:200]:
        # Allow if it's a pure architecture/design discussion
        if len(assistant) < 1000:
            return False, "no_code_and_short"

    return True, "ok"


# ── Worker ─────────────────────────────────────────────────────
async def worker(session, sem, worker_id, train_file, eval_file, seen_hashes, stats, stats_lock, write_lock, domain_counter, diff_counter, cat_counter, failed_lock):
    """Continuously generate Python entries until stopped."""
    local_count = 0
    while True:
        category = random.choice(PYTHON_CATEGORIES)
        difficulty = random.choices(DIFFICULTIES, weights=DIFFICULTY_WEIGHTS, k=1)[0]
        n_entries = random.randint(3, TARGET_PER_CALL)

        entries_raw, usage = await call_grok(session, sem, category, difficulty, n_entries)

        if usage and usage.get("error") == "quota_exhausted":
            return "QUOTA_EXHAUSTED", local_count

        async with stats_lock:
            stats["total_calls"] += 1
            if usage and "prompt_tokens" in usage:
                stats["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
                stats["total_completion_tokens"] += usage.get("completion_tokens", 0)
                detail = usage.get("completion_tokens_details", {})
                stats["total_reasoning_tokens"] += detail.get("reasoning_tokens", 0)

        if not entries_raw:
            async with failed_lock:
                stats["failed_calls"] += 1
            continue

        valid_entries = []
        for raw in entries_raw:
            try:
                sys_content = raw.get("system", "")
                usr_content = raw.get("user", "")
                asst_content = raw.get("assistant", "")
                if not all([sys_content, usr_content, asst_content]):
                    continue

                entry = build_entry(category, difficulty, sys_content, usr_content, asst_content)
                ok, reason = quality_check(entry)
                if not ok:
                    continue

                h = hashlib.md5(usr_content[:300].encode()).hexdigest()
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                valid_entries.append(entry)
            except Exception:
                continue

        if not valid_entries:
            async with failed_lock:
                stats["failed_calls"] += 1
            continue

        async with write_lock:
            for entry in valid_entries:
                is_eval = random.random() < 0.10
                f = eval_file if is_eval else train_file
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()

            stats["total_entries"] += len(valid_entries)
            local_count += len(valid_entries)
            domain_counter["python"] += len(valid_entries)
            diff_counter[difficulty] += len(valid_entries)
            cat_counter[category] += len(valid_entries)

            if stats["total_entries"] - stats.get("last_checkpoint", 0) >= CHECKPOINT_INTERVAL:
                stats["last_checkpoint"] = stats["total_entries"]
                elapsed = time.time() - stats["start_time"]
                rate = stats["total_entries"] / (elapsed / 3600) if elapsed > 0 else 0
                pt = stats.get("total_prompt_tokens", 0)
                ct = stats.get("total_completion_tokens", 0)
                cost = (pt / 1e6 * 1.25) + (ct / 1e6 * 2.50)
                print(f"  [w{worker_id}] {stats['total_entries']:,} entries | {rate:.0f} e/h | ${cost:.2f} | cats: {len(cat_counter)} | fails: {stats['failed_calls']}")


# ── Checkpoint ─────────────────────────────────────────────────
def save_checkpoint(stats, domain_counter, diff_counter, cat_counter):
    checkpoint = {
        "total_entries": stats["total_entries"],
        "total_calls": stats["total_calls"],
        "failed_calls": stats["failed_calls"],
        "total_prompt_tokens": stats.get("total_prompt_tokens", 0),
        "total_completion_tokens": stats.get("total_completion_tokens", 0),
        "total_reasoning_tokens": stats.get("total_reasoning_tokens", 0),
        "domains": dict(domain_counter.most_common()),
        "difficulties": dict(diff_counter.most_common()),
        "categories": dict(cat_counter.most_common()),
        "elapsed_hours": (time.time() - stats["start_time"]) / 3600,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    path = os.path.join(OUT_DIR, "checkpoint_python.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


# ── Main ───────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("F51 GROK-4.3 PYTHON TRANSFUSION")
    print(f"Model: {MODEL}")
    print("Domain: PYTHON ONLY (beat GPT-4 on Coding Arena)")
    print(f"Categories: {len(PYTHON_CATEGORIES)}")
    print(f"Prompt templates: {len(PYTHON_PROMPTS)}")
    print(f"Workers: {MAX_CONCURRENT}")
    print(f"Output: {OUT_DIR}")
    print("=" * 60)

    train_path = os.path.join(OUT_DIR, "grok_transfusion_train.jsonl")
    eval_path = os.path.join(OUT_DIR, "grok_transfusion_eval.jsonl")

    train_file = open(train_path, "a", encoding="utf-8")
    eval_file = open(eval_path, "a", encoding="utf-8")

    seen_hashes = set()
    for path in [train_path, eval_path]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line.strip())
                        h = hashlib.md5(e["messages"][1]["content"][:300].encode()).hexdigest()
                        seen_hashes.add(h)
                    except Exception:
                        pass

    initial_train = sum(1 for _ in open(train_path, encoding='utf-8')) if os.path.exists(train_path) else 0
    initial_eval = sum(1 for _ in open(eval_path, encoding='utf-8')) if os.path.exists(eval_path) else 0
    print(f"Existing entries: {initial_train:,} train + {initial_eval:,} eval")
    print(f"Existing hashes: {len(seen_hashes):,}")

    stats = {
        "total_entries": 0,
        "total_calls": 0,
        "failed_calls": 0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_reasoning_tokens": 0,
        "start_time": time.time(),
        "last_checkpoint": 0,
    }
    domain_counter = Counter()
    diff_counter = Counter()
    cat_counter = Counter()

    stats_lock = asyncio.Lock()
    write_lock = asyncio.Lock()
    failed_lock = asyncio.Lock()
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT + 10, limit_per_host=MAX_CONCURRENT + 10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for i in range(MAX_CONCURRENT):
            t = asyncio.create_task(
                worker(session, sem, i, train_file, eval_file, seen_hashes, stats, stats_lock, write_lock, domain_counter, diff_counter, cat_counter, failed_lock)
            )
            tasks.append(t)

        print(f"\nLaunched {MAX_CONCURRENT} Python workers. Generating until credits exhausted...\n")

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for t in done:
            result, _ = t.result()
            if result == "QUOTA_EXHAUSTED":
                print("\n>>> QUOTA EXHAUSTED! Stopping all workers...")
                for p in pending:
                    p.cancel()

    train_file.close()
    eval_file.close()

    # Final report
    elapsed = time.time() - stats["start_time"]
    train_size = os.path.getsize(train_path)/(1024*1024) if os.path.exists(train_path) else 0
    eval_size = os.path.getsize(eval_path)/(1024*1024) if os.path.exists(eval_path) else 0
    pt = stats["total_prompt_tokens"]
    ct = stats["total_completion_tokens"]
    cost = (pt / 1e6 * 1.25) + (ct / 1e6 * 2.50)

    print("\n" + "=" * 60)
    print("PYTHON TRANSFUSION COMPLETE")
    print("=" * 60)
    print(f"  Runtime: {elapsed/3600:.1f}h")
    print(f"  Calls: {stats['total_calls']:,} | Failed: {stats['failed_calls']:,}")
    print(f"  New entries this run: {stats['total_entries']:,}")
    total_all = initial_train + initial_eval + stats['total_entries']
    print(f"  Total in dataset: {total_all:,}")
    print(f"  Size: {train_size + eval_size:.1f} MB")
    print(f"  Rate: {stats['total_entries']/(elapsed/3600):.0f} e/h")
    print(f"  Tokens: {pt + ct:,}")
    print(f"  Cost: ${cost:.2f}")
    print("\n--- Categories ---")
    for c, n in cat_counter.most_common():
        pct = n / max(stats['total_entries'], 1) * 100
        print(f"  {c}: {n:,} ({pct:.1f}%)")
    print("\n--- Difficulty ---")
    for d, n in diff_counter.most_common():
        print(f"  {d}: {n:,}")

    save_checkpoint(stats, domain_counter, diff_counter, cat_counter)
    print(f"\nCheckpoint: {OUT_DIR}/checkpoint_python.json")


if __name__ == "__main__":
    asyncio.run(main())
