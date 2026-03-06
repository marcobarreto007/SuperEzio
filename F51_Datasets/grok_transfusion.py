"""
F51 Grok-4.3 Blood Transfusion
===============================
Generate premium SFT dataset using grok-4.3 until xAI credits run out.
Multi-domain, deep responses, max quality. Checkpoint every 100 entries.

Schema: {domain, category, difficulty, messages[system/user/assistant], score, source, metadata}
"""

import os
import sys
import json
import time
import random
import hashlib
import asyncio
import aiohttp
from datetime import datetime, timezone
from collections import Counter

# ── Config ─────────────────────────────────────────────────────
XAI_API_KEY = "xai-Z7IRv4O88J0XDb4fkxZolbrPKh4b5CG7xH7WeAZo5Ndk9STL74QRnNX23Xo3OvXUoLwzYOqZcRiHoGHQ"
XAI_URL = "https://api.x.ai/v1/chat/completions"
MODEL = "grok-4.3"

OUT_DIR = r"C:\Users\marco\Desktop\F51-Dataset-Operacao\datasets\grok_transfusion"
CHECKPOINT_INTERVAL = 100
MAX_CONCURRENT = 40  # xAI rate limit: 1400 req/min = ~23 req/s, 40 workers at ~5.5s each = ~7 req/s safe
TARGET_PER_CALL = 4  # entries per API call

# 13 allowed F51 domains
ALLOWED_DOMAINS = [
    "code", "python", "debugging", "repo_audit", "refactoring",
    "tests", "automation", "finance", "risk", "fraud",
    "critic", "dataset_cleaning", "tool_calling",
]

# Domain-specific context for system prompt generation
DOMAIN_CONTEXTS = {
    "code": "general software engineering, architecture patterns, API design, performance optimization",
    "python": "Python 3.12+ advanced features, asyncio, type hints, pydantic, FastAPI, data processing pipelines",
    "debugging": "systematic debugging, error analysis, root cause investigation, log analysis, memory/CPU profiling",
    "repo_audit": "repository security audit, dependency vulnerability scanning, code quality assessment, technical debt analysis",
    "refactoring": "code refactoring patterns, legacy code modernization, SOLID principles, DRY optimization, design patterns",
    "tests": "pytest, property-based testing, integration tests, test fixtures, mocking strategies, coverage analysis, regression suites",
    "automation": "CI/CD pipeline design, GitHub Actions, task orchestration, cron/scheduled jobs, artifact management, deployment automation",
    "finance": "financial modeling, risk metrics, portfolio optimization, quantitative analysis, market microstructure, option pricing",
    "risk": "risk assessment frameworks, counterparty risk, operational risk, VaR modeling, stress testing, Basel/regulatory compliance",
    "fraud": "fraud detection systems, anomaly detection, transaction monitoring, AML/KYC patterns, machine learning for fraud, graph analysis",
    "critic": "code review, architecture critique, security review, performance analysis, design document review, decision record evaluation",
    "dataset_cleaning": "data validation pipeline, deduplication strategies, schema enforcement, data quality metrics, ETL optimization, tokenization analysis",
    "tool_calling": "function calling API design, multi-tool orchestration, tool schema design, agent-based tool selection, tool output validation",
}

DIFFICULTIES = ["easy", "medium", "hard"]
DIFFICULTY_WEIGHTS = [0.2, 0.5, 0.3]  # favor medium/hard

os.makedirs(OUT_DIR, exist_ok=True)

# ── Stats ──────────────────────────────────────────────────────
stats = {
    "total_entries": 0,
    "total_calls": 0,
    "failed_calls": 0,
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "total_reasoning_tokens": 0,
    "total_cost_ticks": 0,
    "start_time": time.time(),
    "last_checkpoint": 0,
}
domain_counter = Counter()
difficulty_counter = Counter()

stats_lock = asyncio.Lock()
write_lock = asyncio.Lock()
checked_sem = None  # init in main

# ── Prompt Bank ─────────────────────────────────────────────────
def generate_system_prompt(domain, difficulty):
    """Generate a domain-specific system prompt."""
    context = DOMAIN_CONTEXTS[domain]

    depth_instructions = {
        "easy": "Provide clear, educational explanations suitable for learning the fundamentals.",
        "medium": "Provide detailed analysis with practical examples and trade-off discussion.",
        "hard": "Provide expert-level deep analysis with edge cases, performance implications, and production considerations.",
    }

    templates = [
        f"You are a senior {domain} specialist at a tech company. Your expertise: {context}. {depth_instructions[difficulty]} Always provide production-ready, actionable guidance.",
        f"You are a staff engineer specializing in {domain}. {context}. {depth_instructions[difficulty]} Cite real-world scenarios and concrete patterns.",
        f"You are a principal consultant for {domain}. {context}. {depth_instructions[difficulty]} Be thorough, precise, and include code examples where applicable.",
    ]
    return random.choice(templates)


def generate_user_prompt(domain, difficulty):
    """Generate a realistic user prompt for the domain."""
    prompts = {
        "code": [
            "Design a rate limiter that handles distributed traffic across multiple nodes. Include token bucket algorithm, Redis backend, and race condition handling.",
            "How would you implement a circuit breaker pattern for microservice calls? Show me the state machine and thread-safe implementation.",
            "We need to migrate a legacy monolith to an event-driven architecture. What's the step-by-step migration plan with rollback checkpoints?",
            "Design a multi-tenant database schema that supports shared tables with row-level security. Consider indexing and query performance.",
            "How do you implement a distributed lock manager that handles network partitions and clock skew?",
        ],
        "python": [
            "Write an async data pipeline that reads from multiple sources, applies transformations, and writes to a sink with backpressure handling.",
            "How do you implement a fast JSON validator using Pydantic that handles deeply nested polymorphic models? Show me advanced validators.",
            "Design a plugin system using Python's importlib and abc that supports hot-reload. Include error isolation between plugins.",
            "Build a memory-efficient streaming JSONL normalizer that handles files larger than RAM. Include incremental deduplication.",
            "Implement a decorator-based retry system with exponential backoff, jitter, and deadline propagation for async functions.",
        ],
        "debugging": [
            "A production service has a slow memory leak that only manifests under load. Describe your systematic debugging approach and tools.",
            "We're seeing intermittent 502 errors in our API gateway. Walk me through your root cause investigation methodology.",
            "Database connections are being exhausted under peak traffic despite connection pooling. Debug the likely causes and fixes.",
            "A Python asyncio service freezes randomly in production but not in staging. How do you diagnose and fix this?",
            "Our CI pipeline has become 4x slower over the last month. Describe your approach to profiling, identifying, and fixing the bottleneck.",
        ],
        "repo_audit": [
            "Audit a repository that handles financial transactions. Identify security vulnerabilities, hardcoded secrets, injection risks, and dependency issues.",
            "Review this codebase for OWASP Top 10 vulnerabilities. Check authentication, authorization, input validation, and logging practices.",
            "Analyze a Python monorepo for supply chain risks: dependency pinning, unpinned requirements, typosquatting exposure, and SBOM gaps.",
            "Evaluate the data privacy compliance of a codebase that processes PII. Check for data leaks in logs, error messages, and serialization.",
            "Assess a microservice codebase for reliability anti-patterns: missing timeouts, no retry logic, single points of failure, lack of circuit breakers.",
        ],
        "refactoring": [
            "Take a 2000-line monolithic service class and propose a clean refactoring into cohesive modules. Show before/after architecture.",
            "This codebase uses 5 different HTTP client libraries. Propose a unified abstraction with migration strategy and backwards compatibility.",
            "Refactor a synchronous batch processing system to async. Handle rate limits, partial failures, and idempotency.",
            "A codebase has deep coupling between business logic and database access. Design a repository pattern migration with minimal blast radius.",
            "Extract a shared authentication library from 3 services that each implemented auth differently. Plan the consolidation with zero downtime.",
        ],
        "tests": [
            "Design a comprehensive test strategy for an event-driven payment processing system. Include unit, integration, contract, and end-to-end tests.",
            "How do you write property-based tests for a JSON normalization pipeline? Define invariants and use Hypothesis-style generators.",
            "Build a test harness for a REST API that validates OpenAPI spec compliance, performance SLAs, and error response consistency.",
            "Our test suite takes 45 minutes. Design a parallelization and prioritization strategy to get it under 10 minutes with same confidence.",
            "Write integration tests for a distributed saga pattern with compensating transactions. Include failure injection and idempotency verification.",
        ],
        "automation": [
            "Design a self-healing deployment pipeline that detects anomalies post-deploy and auto-rolls back based on metrics thresholds.",
            "Build a multi-stage data pipeline orchestrator with checkpoint/restart, dependency resolution, and parallel stage execution.",
            "Create a release automation system that generates changelogs from conventional commits, tags versions, and publishes artifacts.",
            "Design a cron-based monitoring system that detects stale data, missing files, and pipeline failures with escalation policies.",
            "Automate a canary deployment system that gradually shifts traffic based on error rate, latency, and business metrics.",
        ],
        "finance": [
            "Build a real-time P&L calculation engine for a multi-asset trading desk. Handle corporate actions, currency conversion, and time zones.",
            "Design a portfolio optimization system using Modern Portfolio Theory. Include constraints like sector limits, liquidity, and ESG scores.",
            "Implement a VaR (Value at Risk) model using historical simulation. Discuss assumptions, limitations, and backtesting methodology.",
            "Model the term structure of interest rates using the Nelson-Siegel framework. Show calibration and interpolation techniques.",
            "Build a Monte Carlo simulation for option pricing with variance reduction techniques. Compare with analytical Black-Scholes.",
        ],
        "risk": [
            "Design a counterparty credit risk monitoring system. Include exposure calculation, collateral management, and early warning indicators.",
            "Build an operational risk framework that tracks RCSA (Risk Control Self-Assessment), KRIs, and loss events across business units.",
            "Implement a stress testing engine that simulates market crash scenarios on a multi-asset portfolio. Include correlation breakdown modeling.",
            "Design a model risk management framework with model inventory, validation workflow, and continuous monitoring triggers.",
            "Build a liquidity risk dashboard that tracks LCR, NSFR, and concentration risk. Include what-if scenario modeling.",
        ],
        "fraud": [
            "Design a real-time transaction fraud detection system using feature engineering and gradient boosting. Handle concept drift and adversarial attacks.",
            "Build a graph-based fraud ring detection system. Model entities as nodes (users, accounts, devices, IPs) and detect suspicious subgraphs.",
            "Implement an AML transaction monitoring system with rule-based and ML-based detection. Include SAR filing automation.",
            "Design an identity fraud detection pipeline that analyzes document images, behavioral biometrics, and device fingerprints.",
            "Build a false positive reduction system for fraud alerts using feedback loops and active learning. Target <5% false positive rate.",
        ],
        "critic": [
            "Review this microservice architecture proposal. Identify coupling points, single points of failure, data consistency issues, and scaling bottlenecks.",
            "Critique a team's decision to use MongoDB for a payment ledger. Analyze consistency, durability, and audit requirements they may have overlooked.",
            "Evaluate a proposal to replace REST APIs with gRPC across 50 services. What are the operational, debugging, and organizational costs?",
            "Review an API design for a public SDK. Assess versioning strategy, backwards compatibility, error handling, and documentation quality.",
            "A team proposes using serverless (Lambda) for a latency-sensitive trading system. Critique the cold start, cost, and observability implications.",
        ],
        "dataset_cleaning": [
            "Design a data validation pipeline that checks JSONL entries for schema compliance, duplicates, PII leaks, and quality heuristics.",
            "How do you detect near-duplicate entries in a 500k dataset using embedding similarity vs hash-based approaches? Compare cost and accuracy.",
            "Build a tokenization cost estimator that predicts training cost based on dataset size, average token length, and encoding method.",
            "Design a data lineage system that tracks each entry from source dataset through cleaning, filtering, and splitting stages.",
            "Implement an outlier detection system for dataset entries. Use statistical methods and LLM-based quality scoring.",
        ],
        "tool_calling": [
            "Design a function calling API schema for a code analysis suite. Include tools for linting, type checking, test running, and dependency scanning.",
            "Build a multi-tool orchestrator that chains tool calls based on previous outputs. Include error handling, timeouts, and partial result recovery.",
            "Design a tool registry system with schema validation, versioning, and discovery. Support hot-reload of tool definitions.",
            "Create a tool output validation system that checks JSON schemas, type consistency, and semantic correctness of tool responses.",
            "Build a sandboxed tool execution environment that limits filesystem access, network calls, and CPU/memory per tool invocation.",
        ],
    }

    pool = prompts.get(domain, prompts["code"])
    return random.choice(pool)


def gen_meta_prompt(domain, difficulty, n_entries):
    """Build the system-level instruction for Grok to generate entries."""
    system_prompt = generate_system_prompt(domain, difficulty)

    instructions = f"""You are generating premium SFT (Supervised Fine-Tuning) training data for a code/finance/critic AI model.

Generate {n_entries} DIVERSE training entries for the domain "{domain}" at "{difficulty}" difficulty.

FORMAT: Return a JSON object with key "entries" containing an array of objects:
{{
  "entries": [
    {{
      "system": "A detailed system prompt that sets up the expert persona for this domain. 100-300 chars. Be specific about context and constraints.",
      "user": "A realistic, detailed user query. 200-800 chars. Include concrete requirements, constraints, edge cases, and expected format.",
      "assistant": "Your COMPLETE expert response. THIS IS THE MOST IMPORTANT PART. Must be 800-3000 chars. Include: concrete reasoning, code examples where applicable, trade-off analysis, edge case handling, production considerations. DO NOT use vague endings like 'deliver minimal patch'. Be thorough and specific. This is training data — quality over brevity."
    }},
    ...
  ]
}}

RULES:
- Each entry must be UNIQUE and test different skills within "{domain}"
- Assistant responses MUST be deep and detailed (800-3000 chars minimum)
- Include real code snippets, SQL queries, architecture diagrams (ASCII), or formulas where relevant
- Cover different sub-topics within {domain}: {DOMAIN_CONTEXTS[domain]}
- System prompts must be varied — different personas, contexts, tones
- User queries must read like real engineering/business questions
- DO NOT end responses with "deliver minimal patch" or any template phrase
- WRITE IN ENGLISH — this is EN training data
- Output VALID JSON with proper escaping"""

    return instructions


# ── API Call ────────────────────────────────────────────────────
async def call_grok(session, sem, domain, difficulty, n_entries):
    """Call grok-4.3 to generate entries. Returns (entries_list, usage_dict) or (None, None)."""
    async with sem:
        system_instruction = gen_meta_prompt(domain, difficulty, n_entries)

        payload = {
            "model": MODEL,
            "messages": [
                {"role": "user", "content": system_instruction}
            ],
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
                        # Check for safety refusal
                        if "safety" in text.lower() or "refusal" in text.lower():
                            return [], {"error": "safety_refusal"}
                        # Check for credit exhaustion
                        if "quota" in text.lower() or "insufficient" in text.lower() or "billing" in text.lower():
                            return None, {"error": "quota_exhausted"}
                        await asyncio.sleep(2)
                        continue

                    if resp.status != 200:
                        text = await resp.text()
                        await asyncio.sleep(2 ** attempt)
                        continue

                    data = await resp.json()
                    usage = data.get("usage", {})

                    content = data["choices"][0]["message"]["content"]

                    # Parse JSON response
                    try:
                        parsed = json.loads(content)
                        entries = parsed.get("entries", [])
                    except json.JSONDecodeError:
                        # Try to extract JSON from markdown code blocks
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
            except Exception as e:
                await asyncio.sleep(2 ** attempt)
                continue

    return [], {"error": "max_retries_exceeded"}


# ── Entry Builder ──────────────────────────────────────────────
def build_entry(domain, category, difficulty, system_content, user_content, assistant_content):
    """Build a standard F51 SFT entry."""
    return {
        "domain": domain,
        "category": category,
        "difficulty": difficulty,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
        "score": 10,
        "source": f"grok-4.3-transfusion",
        "needs_expansion": False,
        "metadata": {
            "generated_by": "grok-4.3",
            "generation_date": datetime.now(timezone.utc).isoformat(),
            "quality": "premium",
        },
    }


def quality_check(entry):
    """Validate generated entry quality."""
    assistant = entry["messages"][2]["content"]
    user = entry["messages"][1]["content"]
    system = entry["messages"][0]["content"]

    # Reject if assistant too short
    if len(assistant) < 400:
        return False, f"assistant_too_short({len(assistant)}chars)"

    # Reject if template ending detected
    lower = assistant.lower()
    if "entregue patch mínimo" in lower or "deliver minimal patch" in lower:
        return False, "template_ending"

    # Reject if placeholder
    if "todo" in lower or "[placeholder]" in lower or "add your implementation" in lower:
        return False, "placeholder"

    # Reject if system too short
    if len(system) < 40:
        return False, f"system_too_short({len(system)}chars)"

    # Reject if user too short
    if len(user) < 50:
        return False, f"user_too_short({len(user)}chars)"

    return True, "ok"


def near_dedup_hash(entry, seen_hashes):
    """Check if this entry is a near-duplicate of an existing one."""
    user = entry["messages"][1]["content"]
    h = hashlib.md5(user[:300].encode()).hexdigest()
    if h in seen_hashes:
        return True, h
    return False, h


# ── Worker ─────────────────────────────────────────────────────
async def worker(session, sem, worker_id, train_file, eval_file, seen_hashes):
    """Continuously generate entries until stopped."""
    local_entries = 0
    while True:
        domain = random.choices(ALLOWED_DOMAINS, k=1)[0]
        difficulty = random.choices(DIFFICULTIES, weights=DIFFICULTY_WEIGHTS, k=1)[0]
        n_entries = random.randint(3, TARGET_PER_CALL)

        entries_raw, usage = await call_grok(session, sem, domain, difficulty, n_entries)

        # Check for quota exhaustion
        if usage and usage.get("error") == "quota_exhausted":
            return "QUOTA_EXHAUSTED", local_entries

        # Update stats
        async with stats_lock:
            stats["total_calls"] += 1
            if usage and "prompt_tokens" in usage:
                stats["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
                stats["total_completion_tokens"] += usage.get("completion_tokens", 0)
                stats["total_cost_ticks"] += usage.get("cost_in_usd_ticks", 0)
                if "completion_tokens_details" in usage:
                    stats["total_reasoning_tokens"] += usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)

        if not entries_raw:
            async with stats_lock:
                stats["failed_calls"] += 1
            continue

        # Build and validate entries
        valid_entries = []
        for raw in entries_raw:
            try:
                sys_content = raw.get("system", "")
                usr_content = raw.get("user", "")
                asst_content = raw.get("assistant", "")

                if not all([sys_content, usr_content, asst_content]):
                    continue

                # Derive category from domain (1:1 for simplicity)
                category = domain

                entry = build_entry(domain, category, difficulty, sys_content, usr_content, asst_content)

                ok, reason = quality_check(entry)
                if not ok:
                    continue

                is_dupe, h = near_dedup_hash(entry, seen_hashes)
                if is_dupe:
                    continue

                seen_hashes.add(h)
                valid_entries.append(entry)

            except Exception:
                continue

        if not valid_entries:
            async with stats_lock:
                stats["failed_calls"] += 1
            continue

        # Write entries (90/10 train/eval split)
        async with write_lock:
            for entry in valid_entries:
                is_eval = random.random() < 0.10
                file = eval_file if is_eval else train_file
                file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                file.flush()

            stats["total_entries"] += len(valid_entries)
            local_entries += len(valid_entries)
            domain_counter[domain] += len(valid_entries)
            difficulty_counter[difficulty] += len(valid_entries)

            # Checkpoint
            if stats["total_entries"] - stats["last_checkpoint"] >= CHECKPOINT_INTERVAL:
                stats["last_checkpoint"] = stats["total_entries"]
                save_checkpoint()
                elapsed = time.time() - stats["start_time"]
                rate = stats["total_entries"] / (elapsed / 3600) if elapsed > 0 else 0
                est_cost = stats["total_cost_ticks"] / 100_000_000  # ticks to USD approximate
                print(f"  [worker-{worker_id}] {stats['total_entries']:,} entries | "
                      f"{rate:.0f} e/h | cost ~${est_cost:.2f} | "
                      f"domains: {len(domain_counter)} | failures: {stats['failed_calls']}")


# ── Checkpoint ─────────────────────────────────────────────────
def save_checkpoint():
    """Save stats checkpoint."""
    checkpoint = {
        **stats,
        "total_cost_ticks": int(stats["total_cost_ticks"]),
        "domains": dict(domain_counter.most_common()),
        "difficulties": dict(difficulty_counter.most_common()),
        "elapsed_hours": (time.time() - stats["start_time"]) / 3600,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    checkpoint["start_time"] = checkpoint["start_time"]  # keep float

    path = os.path.join(OUT_DIR, "checkpoint.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


# ── Main ───────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("F51 GROK-4.3 BLOOD TRANSFUSION")
    print(f"Model: {MODEL}")
    print(f"Workers: {MAX_CONCURRENT}")
    print(f"Domains: {len(ALLOWED_DOMAINS)}")
    print(f"Output: {OUT_DIR}")
    print("Run until credits exhausted")
    print("=" * 60)

    # Open output files
    train_path = os.path.join(OUT_DIR, "grok_transfusion_train.jsonl")
    eval_path = os.path.join(OUT_DIR, "grok_transfusion_eval.jsonl")

    train_file = open(train_path, "a", encoding="utf-8")
    eval_file = open(eval_path, "a", encoding="utf-8")

    seen_hashes = set()
    # Pre-load hashes from existing files to avoid cross-duplication
    for path in [train_path, eval_path]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        h = hashlib.md5(entry["messages"][1]["content"][:300].encode()).hexdigest()
                        seen_hashes.add(h)
                    except Exception:
                        pass
    print(f"Loaded {len(seen_hashes):,} existing hashes for dedup")

    global checked_sem
    checked_sem = asyncio.Semaphore(MAX_CONCURRENT)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT + 10, limit_per_host=MAX_CONCURRENT + 10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for i in range(MAX_CONCURRENT):
            t = asyncio.create_task(
                worker(session, checked_sem, i, train_file, eval_file, seen_hashes)
            )
            tasks.append(t)

        print(f"\nLaunched {MAX_CONCURRENT} workers. Generating until credits exhausted...\n")

        # Wait for first quota exhaustion signal
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # A worker returned — check if quota exhausted
        for t in done:
            result, local_count = t.result()
            if result == "QUOTA_EXHAUSTED":
                print(f"\n>>> QUOTA EXHAUSTED signal received! Stopping all workers...")
                for p in pending:
                    p.cancel()

    train_file.close()
    eval_file.close()

    # Final report
    elapsed = time.time() - stats["start_time"]
    train_size = os.path.getsize(train_path) / (1024 * 1024) if os.path.exists(train_path) else 0
    eval_size = os.path.getsize(eval_path) / (1024 * 1024) if os.path.exists(eval_path) else 0

    print("\n" + "=" * 60)
    print("TRANSFUSION COMPLETE")
    print("=" * 60)
    print(f"  Runtime: {elapsed/3600:.1f} hours")
    print(f"  Total calls: {stats['total_calls']:,}")
    print(f"  Failed calls: {stats['failed_calls']:,}")
    print(f"  Total entries: {stats['total_entries']:,}")
    print(f"  Rate: {stats['total_entries']/(elapsed/3600):.0f} entries/hour")
    print(f"  Train: {train_size:.1f} MB")
    print(f"  Eval: {eval_size:.1f} MB")
    print(f"  Prompt tokens: {stats['total_prompt_tokens']:,}")
    print(f"  Completion tokens: {stats['total_completion_tokens']:,}")
    print(f"  Reasoning tokens: {stats['total_reasoning_tokens']:,}")
    print(f"  Total tokens: {stats['total_prompt_tokens'] + stats['total_completion_tokens']:,}")
    print(f"\n--- Domain Distribution ---")
    for d, c in domain_counter.most_common():
        pct = c / max(stats['total_entries'], 1) * 100
        print(f"  {d}: {c:,} ({pct:.1f}%)")
    print(f"\n--- Difficulty Distribution ---")
    for d, c in difficulty_counter.most_common():
        print(f"  {d}: {c:,}")

    save_checkpoint()
    print(f"\nOutput: {OUT_DIR}/")
    print(f"Checkpoint: {OUT_DIR}/checkpoint.json")


if __name__ == "__main__":
    asyncio.run(main())
