# SuperEzio - AI Financial Copilot

**Local-first, evidence-based financial analysis for small investors who want a disciplined second opinion.**

## What It Does

SuperEzio is an AI copilot that:

1. Collects market data: prices, fundamentals, technicals, and macro context from configured sources.
2. Runs expert analysis: specialized agents assess the same data under an anti-guessing contract.
3. Applies a risk firewall: the SDCA firewall blocks FOMO, leverage, and stale-signal decisions.
4. Delivers a bounded verdict: STUDY_MORE, WATCHLIST, WAIT, SMALL_POSITION, or AVOID.
5. Flags missing data instead of fabricating numbers.

The final CEO synthesis runs on a local 80B model when the included runtime is available. Optional market-data and expert providers may call external APIs depending on the keys configured in `.env`.

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

### 1. Check

```powershell
powershell -ExecutionPolicy Bypass -File check.ps1
```

This verifies the machine, model, Python environment, runtime, and ports. If anything fails, it prints the next fix.

### 2. Start

```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

This starts the local CEO model on port 8082 and the API/UI on port 8002. First load can take several minutes because the model is large.

### 3. Open

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

This is an educational framework, not financial advice. It does not execute trades, guarantee returns, or replace a licensed financial advisor.

The local CEO model runs on your machine. External providers are optional and controlled by `.env`; if enabled, they may receive the data required for market-data collection or expert sub-analysis.

## Support

See `docs/` for architecture notes, risk disclosures, and packaging runbooks.
