# SuperEzio - AI Financial Copilot

**Local-first, evidence-based financial analysis for small investors who want a disciplined second opinion.**

## What It Does

SuperEzio is an AI copilot that:

1. Collects market data: prices, fundamentals, technicals, and macro context from configured sources.
2. Runs expert analysis: specialized agents assess the same data under an anti-guessing contract.
3. Applies a risk firewall: the SDCA firewall blocks FOMO, leverage, and stale-signal decisions.
4. Delivers a bounded verdict: STUDY_MORE, WATCHLIST, WAIT, SMALL_POSITION, or AVOID.
5. Flags missing data instead of fabricating numbers.

The CEO and orchestrator run on the shared local Qwen3.8-27B server. Financial experts, the day-trade judge, and auditor use the official external DeepSeek API with no cross-provider fallback. Market-data providers may also call their documented external data APIs.

## What You Need

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Operating System | Windows 10/11 64-bit | Windows 11 64-bit |
| RAM | 48 GB | 64 GB |
| GPU | NVIDIA with 8 GB VRAM | NVIDIA RTX with 16 GB VRAM |
| Disk Space | 60 GB free | 100 GB free SSD |
| Python | 3.11+ | 3.12.x |
| CUDA | 12.0+ | 12.4+ |

## Quick Start

### 1. Bootstrap

```powershell
$env:SUPEREZIO_ADMIN_PASSWORD = "replace-with-a-unique-long-password"
.\setup_superezio.bat
```

This creates the locked Python environment, local secrets, browser runtime, and first operator account.

### 2. Check

```powershell
powershell -ExecutionPolicy Bypass -File check.ps1
```

This verifies the machine, model, Python environment, runtime, and ports. If anything fails, it prints the next fix.

### 3. Start

```powershell
.\setup_superezio.bat run
```

This starts the shared local Qwen3.8-27B CEO model on port 8080 and the API/UI on port 8002. First load can take several minutes because the model is large.

### 4. Open

Open:

```text
http://127.0.0.1:8002
```

Or double-click `OPEN_UI.url`.

## How to Stop

```powershell
powershell -ExecutionPolicy Bypass -File stop.ps1
```

## Example Questions

- "I have CAD 25,000 to allocate. Build a serious framework with risk limits."
- "MSFT pulled back. What evidence should I study before entering?"
- "NU has strong momentum. What are the risks, data gaps, and safest next step?"

## Important

This is an educational framework, not financial advice. It never submits live/real-capital orders. IBKR paper orders can be transmitted only when explicitly enabled and all safety/readiness gates pass; TD Direct Investing remains a manual workflow with no broker transport. The system does not guarantee returns or replace a licensed financial advisor.

The local CEO and expert roles run on your machine through the same server on port 8080. External market-data providers are optional and controlled by `.env`; if enabled, they receive only the data required for market-data collection. No external provider receives LLM prompts as a fallback.

## Support

See `docs/` for architecture notes, risk disclosures, and packaging runbooks.
