# Twitter/X thread: @fuch_f51_labs
# 8 tweets, each ~280 chars or less

--- TWEET 1 (hook) ---
🧵 I spent weeks measuring where MoE inference actually spends time on a 16 GB consumer GPU.

The result: 4.6× faster than GPU-all, using 15% of the VRAM.

And two "obvious" optimizations that completely failed. Those taught me more than the successes.

Here's everything ↓

--- TWEET 2 (the headline number) ---
Qwen 80B-A3B on RTX 5060 Ti 16GB:

GPU-all:        8.4 tok/s  (15.9 GB VRAM, saturated)
CPU-only:      17.2 tok/s  (0 GB VRAM)
🟢 Nitro:      38.7 tok/s  (2.4 GB VRAM)

That's 4.6× faster with 1/6th the VRAM.

--- TWEET 3 (the physics) ---
The answer is in 3 numbers. Per-expert latency (12.6 MB, MXFP4):

GPU resident:  ~31 µs  (426 GB/s)
CPU compute:  ~164 µs  (80 GB/s DDR5)
PCIe stream:  ~695 µs  (20 GB/s)

PCIe is the bottleneck. If an expert isn't already on GPU, computing it on CPU wins. Always.

--- TWEET 4 (the strategy) ---
The strategy: "musical chairs"

GPU holds: attention + router (always hot) + a pool of hot experts
RAM holds: all experts, computed on CPU when not cached
PCIe: don't use it reactively

LRU keeps the experts that repeat. The cache competes across all layers simultaneously.

--- TWEET 5 (negative result 1) ---
❌ Speculative lookahead predictor

Built a 4-voice ensemble to predict the next expert and pre-warm it.

Gain: +0.0 to +0.8 pp hit rate.

Why: the expert token T-1 used is already in the LRU cache. The predictor chases the same thing. Redundant.

--- TWEET 6 (negative result 2) ---
❌ PCIe streaming on cache miss

Intuition: "copy to GPU, compute fast!"
Reality: 695 µs vs 164 µs CPU.

The PCIe 5.0 x8 pipe (20 GB/s) is 4× narrower than DDR5 (80 GB/s). You move the same bytes through a thinner straw AND still compute.

Dead end on this hardware class.

--- TWEET 7 (reproduce it) ---
Everything is open source. Reproduce in 3 commands:

git clone https://github.com/fuch-f51-labs/F51-Nitro-MoE
python f51_cli.py install
python f51_cli.py serve -m MODEL.gguf -c 4096

Works on any 16 GB consumer GPU.

--- TWEET 8 (close) ---
Paper: [TechRxiv, DOI pending]
Code: github.com/fuch-f51-labs/F51-Nitro-MoE

Built on: llama.cpp · KTransformers (SOSP'25) · Fiddler (ICLR'25)

"O número manda" — the number is the boss.
Results negativos são insight.
