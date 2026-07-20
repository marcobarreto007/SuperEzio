# F51 Nitro-MoE — Agent Reference Index

**Purpose:** Quick navigation for any AI agent working on the F51 Nitro project.  
**Last updated:** 2026-05-25

---

## Documents (read these first)

| Priority | File | Content |
|----------|------|---------|
| 1 | `docs/F51_NITRO_MOE_WHITEPAPER.md` | Complete whitepaper: abstract, methodology, results, architecture, roadmap, related work |
| 2 | `docs/F51_NITRO_BENCHMARK_PROTOCOL.md` | Reproducible benchmark suite — how to run, what to measure, validation criteria |
| 3 | `docs/VAST_ABLITERATED.md` | Vast.ai training + deployment for the Arbitro model |
| 4 | `docs/F51_COLD_LAYER_SSD.md` | Hardware thermal map (GPU/RAM/SSD) and storage inventory |

## Scripts (tools)

| File | Language | Purpose |
|------|----------|---------|
| `scripts/nitro_scheduler_brainstorm.py` | Python | Predictive scheduler simulation — lead times, hit rates, slack equation |
| `scripts/nitro_expert_packer.py` | Python | Expert cluster packing tool — profile co-activation, cluster, optimize GGUF layout |
| `scripts/nitro_comparison.md` | Markdown | Raw comparison tables (35B/80B/236B × 3 modes) |
| `scripts/nitro_80b_optim_plan.md` | Markdown | 5-layer optimization plan with targets and dependency graph |
| `scripts/bench_1M_nitro.ps1` | PowerShell | 1M token benchmark harness (Arquivado/Removido) |
| `scripts/bench_1M_runner.py` | Python | 1M token benchmark runner |
| `scripts/gen_1M_prompts.py` | Python | Prompt generator for benchmarks |
| `scripts/serve_local.ps1` | PowerShell | Start llama-server with local GGUF |
| `scripts/serve_qwen_9b.ps1` | PowerShell | Start Qwen 9B server |

## Key Numbers (memorize these)

```
80B Nitro:  38.7 tok/s at 256K, 6.3 GB VRAM, 39 GB RAM
80B CPU:    17.2 tok/s, 0 GB VRAM, 40 GB RAM
80B GPU-all: 8.4 tok/s, 15.9 GB VRAM — WORSE than CPU

NVMe read:  3,367 MB/s (measured)
PCIe x8:    16,000 MB/s (theoretical)
DDR5:       60,000 MB/s

Expert size 80B:  59 MB (IQ4_XS)
Expert size 236B: 644 MB (IQ4_XS)

RAM→GPU transfer: 3.7ms (80B), 40.2ms (236B)
NVMe→RAM transfer: 17.4ms (80B), 189.4ms (236B)

Expert persistence: ~65% between consecutive tokens
Active experts per token: 10 of 512 (80B), 6 of 160 (236B)
```

## Claims to Defend

1. **GPU-all is counterproductive** for MoE ≥35B — proven with measurements
2. **Nitro 80B = 4.6x GPU-all, 2.3x CPU-only** at 256K context
3. **6.3 GB VRAM runs 80B MoE at 256K** — consumer hardware
4. **DDR5 > GDDR6X for MoE** — RAM investment, not VRAM
5. **236B at 12-20 tok/s projected** with cold tier + optimizations

## Optimization Layers (ordered by priority)

1. Expert Persistence (VRAM cache) — 39→55 tok/s — independent
2. Async Multi-Stream PCIe — 55→70 tok/s — depends on 1
3. Router Lookahead — 70→80 tok/s — depends on 2
4. KV Cache Tiering — 256K in 4GB VRAM — independent
5. Expert Cluster Packing — cold start 2-3x — independent

## Open Tasks

- [ ] Complete 12-test baseline benchmark (64K-256K, 3 themes, 3 modes)
- [ ] Cross-family validation (DeepSeek-V3, GLM-5, Mixtral)
- [ ] Layer 1 implementation (modify llama.cpp expert loader)
- [ ] ASIC repurposing exploration
- [ ] arXiv preprint

## Terminology

| Term | Definition |
|------|-----------|
| Nitro | F51's tiered placement protocol — experts in RAM, attention in GPU |
| GPU-all | Naive approach — all model weights in VRAM |
| Cold tier | NVMe-backed expert storage for models that exceed RAM |
| Slack | `deadline - lead_time`; when slack=0, fire transfer NOW |
| Lead time | Time to transfer expert from current tier to GPU |
| Expert persistence | % of experts that stay active between consecutive tokens |
| Cluster packing | Grouping co-activated experts contiguously on disk |
