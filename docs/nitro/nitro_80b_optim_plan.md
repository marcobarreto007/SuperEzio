# F51 Nitro 80B — Optimization Architecture
## From 39 tok/s to the next tier
2026-05-25

---

## BASELINE (where we are)

```
Qwen3-Coder-Next 80B IQ4_XS
llama.cpp --cpu-moe
-ngl 999 -c 262144 -fa on --reasoning off -ctk q8_0 -ctv q8_0

Gen:     39.22 tok/s
Prefill: ~242 tok/s (batch 2048)
VRAM:    6.3 GB (@ 256K context)
RAM:     ~39 GB
Experts: 512 total, 10 active + 1 shared per token, ~59 MB each
```

---

## OPTIMIZATION LAYERS

### Layer 1 — Expert Persistence (VRAM cache)

**Problem:** llama.cpp loads experts per token, likely evicts immediately after.
Each token re-fetches ~10 experts from RAM via PCIe (10 × 3.7ms = 37ms wasted).

**Fix:** Persistent expert buffer in VRAM (8-16 slots).
- After token T computes, experts stay in VRAM
- Token T+1: check if expert already in VRAM → skip transfer
- With 65% inter-token persistence: ~3.5 new experts to load, not 10
- PCIe time drops from 37ms → ~13ms
- Expected: ~55-60 tok/s

**Engineering:** Hook `llama_decode` expert loader.
Track which experts are currently in VRAM slots.
LRU eviction when slots full.

**Risk:** VRAM pressure. 8 slots × 59 MB = 472 MB. Negligible.

---

### Layer 2 — Async Multi-Stream PCIe

**Problem:** Expert loading is synchronous — GPU stalls waiting for PCIe.

**Fix:** 3 CUDA streams operating simultaneously:
- Stream A: Expert H2D transfer (async, pinned memory)
- Stream B: Expert FFN compute (kernel launch)
- Stream C: Attention/DeltaNet compute (kernel launch)

While stream A loads expert for token T+1,
stream B computes expert for token T,
stream C computes attention for token T.

**Engineering:** Modify llama.cpp `ggml_backend_cuda` to use multiple streams.
Pinned memory pool for expert transfers.
CUDA events for intra-stream sync (not global `cudaDeviceSynchronize`).

**Expected:** Hides 50-70% of PCIe latency.
Combined with Layer 1: ~70-80 tok/s.

---

### Layer 3 — Router Lookahead (free prefetch)

**Problem:** We wait for router output before loading experts.
But router output for token T predicts token T+1's first MoE layer with ~70% accuracy.

**Fix:** After token T's router runs, immediately launch prefetch for
predicted experts of T+1. No ML model needed — native router IS the predictor.

**Engineering:** Insert prefetch hook right after `ggml_moe_get_routing_weights`.
Predicted experts go into a prefetch queue.
If prediction correct → expert already in VRAM when GPU needs it.
If wrong → fallback to shared expert (no stall, slight quality loss).

**Expected:** Additional 10-15% throughput. Combined: ~80-90 tok/s.

---

### Layer 4 — KV Cache Tiering

**Problem:** KV cache eats 6.3 GB at 256K context with q8_0.
At 512K+: even more. Limits context scaling on 16 GB VRAM.

**Fix:** Two-tier KV cache:
- Hot pages: recent 32K tokens in GPU VRAM (q8_0)
- Warm pages: older tokens in RAM (q8_0, paged)
- On attention: GPU streams hot pages; background DMA fetches warm pages
- Similar to DUAL-BLADE approach but simpler

**Engineering:** Hook KV cache page table.
`ggml_backend_cuda` manages hot/cold KV page movement.

**Expected:** 256K context in ~4 GB VRAM instead of 6.3 GB.
Or: 512K context in same VRAM budget.

---

### Layer 5 — Expert Cluster Packing (NVMe layout)

**Problem:** Initial model load is random I/O. Expert tensors scattered across GGUF file.

**Fix:** Post-process GGUF to cluster experts by co-activation.
- Profile: run 1000 tokens, record which experts co-activate per layer
- Louvain clustering (or simpler: frequency-based grouping)
- Rewrite GGUF: co-activated experts stored contiguously
- Single mmap read = multiple ready-to-use experts

**Engineering:** Python script: profile → cluster → repack GGUF.
Read-only optimization, model quality unchanged.

**Expected:** Cold start 2-3x faster. Benefits larger models more than 80B.

---

## ROADMAP

```
Phase 1 (day 1-2): Expert Persistence
  └─ Modify llama.cpp expert loader
  └─ Benchmark: before/after at 4K, 32K, 128K, 256K
  └─ Target: 55-60 tok/s

Phase 2 (day 3-4): Async Multi-Stream
  └─ CUDA stream separation
  └─ Pinned memory pool
  └─ Target: 70-80 tok/s

Phase 3 (day 5): Router Lookahead
  └─ Prefetch hook in ggml MOE path
  └─ Shared expert fallback
  └─ Target: 80-90 tok/s

Phase 4 (day 6): KV Cache Tiering
  └─ Hot/warm KV page split
  └─ Target: 256K in 4 GB VRAM or 512K in 6 GB

Phase 5 (day 7): Cluster Packing
  └─ Profile + repack GGUF
  └─ Target: 2-3x faster cold start
```

---

## DEPENDENCY GRAPH

```
Layer 1 (Persistence) ── independent, deployable alone
  │
  ├──► Layer 2 (Multi-Stream) ── depends on 1 for best results
  │      │
  │      └──► Layer 3 (Lookahead) ── depends on 2 (async streams)
  │
  └──► Layer 4 (KV Tiering) ── independent of 2/3, deployable alone

Layer 5 (Cluster Packing) ── fully independent, offline tool
```

---

## ASICs NOTE (Marco's idea — TOMORROW)

> "reaproveitar asics"

Marco mentioned repurposing ASIC hardware. Key directions to explore:
- Old Bitcoin miners (SHA256 ASICs) → limited use for inference (fixed function)
- Edge TPUs / Coral boards → small models only
- Old mining GPUs with custom BIOS → can they run llama.cpp?
- The general idea: "hardware que ninguem quer mais → pipeline Nitro"

**Save for tomorrow session.**

---

## TEST CONTRACT

Each phase must prove:
1. Before/after tok/s at 4K, 128K, 256K
2. VRAM delta
3. Generation quality (same prompt, same answer?)
4. No regression: CPU-only and GPU-all still work
