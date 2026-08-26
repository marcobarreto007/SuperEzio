# F51 Nitro-MoE — Benchmark Protocol

**Purpose:** Reproducible benchmark suite for validating Nitro claims on any hardware.  
**Version:** 1.0 — 2026-05-25

---

## 1. Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | NVIDIA 8GB VRAM | 16GB VRAM |
| RAM | 48 GB DDR4/DDR5 | 64+ GB DDR5 |
| NVMe | Any SSD | Gen4 NVMe (7 GB/s) |
| CPU | Any modern x86 | Multi-core (not bottleneck) |
| OS | Windows/Linux | Windows 11 / Ubuntu 22+ |

## 2. Software Requirements

- Python 3.11+
- llama.cpp (build with CUDA support)
- Model: Qwen3-Coder-Next-80B IQ4_XS (GGUF)

## 3. Server Configurations

### Mode A: CPU-only
```bash
llama-server -m model.gguf -ngl 0 -c 262144 -ctk q8_0 -ctv q8_0 --port 8084
```

### Mode B: GPU-all
```bash
llama-server -m model.gguf -ngl 999 -c 262144 -ctk q8_0 -ctv q8_0 --port 8084
```

### Mode C: Nitro (F51)
```bash
llama-server -m model.gguf --cpu-moe -ngl 999 -c 262144 -fa on --reasoning off -ctk q8_0 -ctv q8_0 --port 8084
```

## 4. Benchmark Script

```python
"""
F51 Nitro — Benchmark Runner
Run against: http://localhost:8084/v1
"""

import urllib.request, json, time, statistics

API = "http://localhost:8084/v1"

# Context sizes to test
CONTEXT_SIZES = [4096, 8192, 16384, 32768, 65536, 131072, 262144]

# Test prompts (3 themes)
THEMES = [
    (
        "code",
        "Write a Python web scraper for Canadian auction sites with rate limiting and error handling. Include class-based design, async support, and logging.",
    ),
    (
        "creative",
        "Describe in vivid detail a Montreal winter morning. Include sensory details: sounds of snow crunching, smell of maple from the bakery, the way light hits the snow.",
    ),
    (
        "analysis",
        "Analyze the economic impact of DDR5 RAM pricing on consumer AI inference. Compare cost-per-token between GPU-all and tiered placement approaches.",
    ),
]


def measure(prompt: str, max_tokens: int = 200, temperature: float = 0.7) -> dict:
    payload = json.dumps(
        {
            "model": "qwen3-coder-next",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    ).encode()

    req = urllib.request.Request(
        f"{API}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.loads(resp.read())
    elapsed = time.time() - t0

    usage = body.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    gen_tps = completion_tokens / elapsed if elapsed > 0 else 0
    prompt_tps = prompt_tokens / elapsed if elapsed > 0 else 0

    return {
        "elapsed_s": round(elapsed, 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "gen_tok_per_s": round(gen_tps, 2),
        "prompt_tok_per_s": round(prompt_tps, 2),
    }


def run_benchmark():
    results = []
    for ctx_label in CONTEXT_SIZES:
        for theme_name, prompt in THEMES:
            # Pad prompt to reach target context size
            padded = prompt + " " * max(0, ctx_label - len(prompt.split()) * 4)
            r = measure(padded)
            r["context_target"] = ctx_label
            r["theme"] = theme_name
            results.append(r)
            print(
                f"  ctx={ctx_label:>7} theme={theme_name:<10} gen={r['gen_tok_per_s']:>6.1f} t/s  prompt={r['prompt_tok_per_s']:>6.1f} t/s"
            )
    return results


if __name__ == "__main__":
    print("F51 Nitro Benchmark")
    print(f"API: {API}")
    results = run_benchmark()

    # Summary by context size
    print("\n--- SUMMARY ---")
    for ctx in CONTEXT_SIZES:
        runs = [r for r in results if r["context_target"] == ctx]
        gen_tps = [r["gen_tok_per_s"] for r in runs]
        prompt_tps = [r["prompt_tok_per_s"] for r in runs]
        print(
            f"ctx={ctx:>7}: gen={statistics.mean(gen_tps):>6.1f} ± {statistics.stdev(gen_tps):>4.1f} t/s  "
            f"prompt={statistics.mean(prompt_tps):>6.1f} t/s"
        )
```

## 5. Metrics to Record

For each (mode, context_size, theme):

| Metric | How to measure |
|--------|---------------|
| Generation tok/s | `completion_tokens / wall_time` |
| Prompt tok/s | `prompt_tokens / wall_time` |
| VRAM used (peak) | `nvidia-smi` during run |
| RAM used (peak) | Task Manager / `free -h` |
| Total wall time | Python `time.time()` |
| First token latency | Time to first token in streaming mode |

## 6. Validation Criteria

The claim is validated if:

1. **Nitro gen tok/s > GPU-all gen tok/s** at all context sizes ≥4K
2. **Nitro gen tok/s > CPU-only gen tok/s** at all context sizes
3. **Nitro VRAM < 8 GB** at 256K context
4. **GPU-all OOMs** at 256K context (or tok/s collapses below CPU-only)

## 7. Reporting Format

```
MODE: [CPU-only | GPU-all | Nitro]
MODEL: [model name and quant]
HARDWARE: [GPU, RAM, NVMe, CPU]
DATE: [ISO date]

ctx=4096:    gen=X.X t/s  prompt=X.X t/s  vram=X.X GB  ram=X.X GB
ctx=8192:    gen=X.X t/s  prompt=X.X t/s  vram=X.X GB  ram=X.X GB
ctx=16384:   gen=X.X t/s  prompt=X.X t/s  vram=X.X GB  ram=X.X GB
ctx=32768:   gen=X.X t/s  prompt=X.X t/s  vram=X.X GB  ram=X.X GB
ctx=65536:   gen=X.X t/s  prompt=X.X t/s  vram=X.X GB  ram=X.X GB
ctx=131072:  gen=X.X t/s  prompt=X.X t/s  vram=X.X GB  ram=X.X GB
ctx=262144:  gen=X.X t/s  prompt=X.X t/s  vram=X.X GB  ram=X.X GB
```
