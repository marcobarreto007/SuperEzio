# Reddit post: r/LocalLLaMA
# Title: "I measured where MoE inference actually spends time on a 16GB GPU — here's what worked and what didn't"

---

I spent the last few weeks benchmarking Mixture-of-Experts models on a single RTX 5060 Ti (16GB). The goal was simple: what's the optimal placement when the model is 3-7× larger than your VRAM?

**The answer surprised me.** Full paper linked at the bottom. Here's the short version:

---

## The headline number

**Qwen3-Coder-Next 80B-A3B** (80B total, 3B active per token):

| Mode | tok/s | VRAM |
|---|---|---|
| GPU-all (everything on GPU) | 8.4 | 15.9 GB (maxed out) |
| CPU-only | 17.2 | 0 GB |
| **Nitro (`--cpu-moe`)** | **38.7** | **2.4 GB** |

That's **4.6× faster than GPU-all** while using **15% of the VRAM**. On a $400 GPU.

---

## Why this happens (the "musical chairs" insight)

MoE models only activate 2-4 experts per token. The rest (~96%) stay idle. So cramming everything into VRAM is wasteful — you're paying for 128 experts per layer but using 4.

The trick: treat VRAM as a **hot-expert cache**, not as model storage.

I measured the three possible paths for expert computation:

| Path | Bandwidth | Latency (12.6 MB expert) |
|---|---|---|
| GPU resident (already cached) | ~426 GB/s | **~31 µs** |
| CPU compute (from DDR5) | ~80 GB/s | **~164 µs** |
| PCIe streaming (copy RAM→GPU) | ~20 GB/s | **~695 µs** |

PCIe streaming is the trap. It *feels* like it should help ("copy to GPU, compute fast!") but the PCIe 5.0 x8 pipe is 4× narrower than DDR5. You're moving the same bytes through a thinner straw and still have to compute. CPU wins every time on a cache miss.

---

## What didn't work (the part I'm proudest of)

I tried two "obvious" optimizations. Both failed. Both taught me more than the successes:

**1. Speculative expert prefetch ("lookahead predictor")**
Built a 4-voice ensemble to predict which expert the next token needs and pre-warm it.
**Gain: +0.0 to +0.8 pp** of hit rate. Why? The expert token T-1 used is already in the LRU cache. The predictor is chasing the same expert the cache already holds. Redundant. Saved myself months of work by measuring this early.

**2. PCIe streaming on cache miss**
695 µs vs 164 µs. Dead on arrival. This hardware class cannot stream expert weights reactively.

---

## GPT-OSS 120B: pushing the limit

A much harder case — 59 GB model, needs 59 GB of RAM just to load (mmap'd from NVMe otherwise). Sustained **~6.2 tok/s** with 4 expert layers GPU-resident + 32 layers on CPU with F51 cache.

Also found and fixed a llama.cpp prompt-cache bug (checkpoint seq_id wasn't rebased when cache entry moved to a different slot). PR-ready patch.

---

## How to reproduce

```bash
# Clone the repo
git clone https://github.com/fuch-f51-labs/F51-Nitro-MoE

# Build (auto-clones and patches llama.cpp)
python f51_cli.py install

# Run server (auto-calibrates for your hardware)
python f51_cli.py serve -m MODEL.gguf -c 4096
```

Or just the comparison:
```bash
llama-cli -m model.gguf -ngl 0   -n 100  # CPU baseline
llama-cli -m model.gguf -ngl 99  -n 100  # GPU baseline
llama-cli -m model.gguf -ngl 99 --cpu-moe -n 100  # Nitro (winner)
```

---

**Paper:** [TechRxiv link pending] · **Code:** github.com/fuch-f51-labs/F51-Nitro-MoE

Happy to answer questions. If you try this on your hardware, I'd love to see your numbers — the more data points the better.

*"O número manda." — the number is the boss.*
