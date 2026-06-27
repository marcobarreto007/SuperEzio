#!/usr/bin/env python3
"""
f51_dense_activation_trace.py
-----------------------------
Step 2 do scaffold: instrumenta um modelo DENSO real e mede localidade
de ativação no granularidade de bloco.

Hook: captura a saída do SwiGLU (gate * silu(gate) * up) em cada layer,
fatia em blocos, threshold -> quais blocos estão "hot" por token.

Output: JSON com o trace (layer → token → [blocos ativos]) + métricas.

Modelo default: Qwen/Qwen3.5-2B-Base  (2026, Apache 2.0, ~4GB)
Mas funciona com qualquer modelo LLaMA-style com SwiGLU.

Author: Fuch F51 Labs
"""

import argparse
import json
import os
import time
import numpy as np
from collections import OrderedDict

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "Qwen/Qwen3.5-2B-Base"

# Threshold: fração do max absoluto da layer. Blocos com max(|act|) acima
# de threshold_frac * max_layer são considerados "hot".
# Valores típicos: 0.01-0.05 (DejaVu/PowerInfer usam top-k, mas threshold é
# mais robusto pra medir sparsity real).
THRESHOLD_FRAC = 0.02

# Tamanho do bloco (neurônios do FFN intermediate por pseudo-expert)
BLOCK_SIZE = 64


# ---------------------------------------------------------------------------
# Corpus multi-domínio pra exercitar localidade
# ---------------------------------------------------------------------------
CORPUS = """\
# File: main.py
import torch
import torch.nn as nn

class TransformerBlock(nn.Module):
    def __init__(self, d_model, n_heads, d_ff):
        super().__init__()
        self.attention = nn.MultiheadAttention(d_model, n_heads, batch_first=True)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.GELU(),
            nn.Linear(d_ff, d_model),
        )

    def forward(self, x):
        attn_out, _ = self.attention(self.norm1(x), self.norm1(x), self.norm1(x))
        x = x + attn_out
        ffn_out = self.ffn(self.norm2(x))
        x = x + ffn_out
        return x

# Training loop
model = TransformerBlock(d_model=512, n_heads=8, d_ff=2048)
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
criterion = nn.CrossEntropyLoss()

for epoch in range(10):
    for batch in dataloader:
        optimizer.zero_grad()
        output = model(batch)
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()
    print(f"Epoch {epoch}, Loss: {loss.item():.4f}")

# Test the model
with torch.no_grad():
    test_output = model(test_input)
    print(f"Test shape: {test_output.shape}")

The quick brown fox jumps over the lazy dog. This sentence contains every
letter of the English alphabet at least once. It is often used to test
typewriters and computer keyboards because it provides a quick way to
verify that all characters are functioning properly.

Machine learning has revolutionized the way we approach problem-solving in
computer science. Rather than writing explicit rules, we now collect data,
define a loss function, and let optimization algorithms discover the
underlying patterns. This paradigm shift has enabled breakthroughs in
computer vision, natural language processing, and reinforcement learning.

Le langage est une faculté propre à l'espèce humaine. Il permet la
communication d'idées complexes à travers des symboles arbitraires.
Les linguistes distinguent généralement la compétence linguistique,
qui est la connaissance implicite qu'un locuteur a de sa langue, de
la performance, qui est l'usage effectif de cette langue.

Die Quantenmechanik beschreibt das Verhalten von Materie und Energie
auf atomarer und subatomarer Ebene. Anders als die klassische Physik
arbeitet sie mit Wahrscheinlichkeiten statt deterministischen
Vorhersagen. Das Doppelspaltexperiment zeigt auf eindrucksvolle Weise,
dass Teilchen gleichzeitig mehrere Wege nehmen können.

# Now back to some more code
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key: int) -> int:
        if key not in self.cache:
            return -1
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: int, value: int) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

La física cuántica y la relatividad general son los dos pilares de la
física moderna. Sin embargo, estas dos teorías son fundamentalmente
incompatibles en ciertos regímenes extremos, como el interior de los
agujeros negros o el momento del Big Bang. La búsqueda de una teoría
unificada de la gravedad cuántica sigue siendo uno de los mayores
desafíos de la ciencia contemporánea.

日本語は日本列島で話されている言語であり、約1億2500万人の話者がいます。
仮名と漢字を組み合わせた表記体系を使用し、文法は主に主語-目的語-動詞の
語順をとります。敬語の体系が発達しているのも特徴の一つです。

## Final section: conclusions
# The experiment demonstrates that activation sparsity in dense FFN layers
# follows predictable patterns when measured at block granularity.
# Key findings:
# 1. Block-level sparsity is less extreme than neuron-level sparsity
# 2. Temporal locality emerges from coherent text segments
# 3. Cache efficiency depends on cache_size >= active_blocks

Thank you for reading this comprehensive analysis. We hope it provides
a solid foundation for future work on efficient inference of large
language models through activation-aware caching strategies.
"""


# ---------------------------------------------------------------------------
# Hook infrastructure
# ---------------------------------------------------------------------------
def build_trace(model, tokenizer, corpus, threshold_frac=THRESHOLD_FRAC,
                block_size=BLOCK_SIZE, max_tokens=2048, device="cuda"):
    """
    Run the model, hooking SwiGLU activations per layer, per token.
    Returns:
        trace: list[list[list[int]]]  # [layer][token] = [block_ids that are hot]
        d_ff: int
        n_blocks: int
    """
    # Tokenize
    inputs = tokenizer(corpus, return_tensors="pt", truncation=True,
                       max_length=max_tokens)
    input_ids = inputs["input_ids"].to(device)
    seq_len = input_ids.shape[1]
    print(f"  Sequence length: {seq_len} tokens")

    # Discover geometry from model config
    cfg = model.config
    # Qwen3.5 uses 'intermediate_size', standard HF name
    if hasattr(cfg, 'intermediate_size'):
        d_ff = cfg.intermediate_size
    elif hasattr(cfg, 'ffn_dim'):
        d_ff = cfg.ffn_dim
    else:
        raise ValueError("Cannot find FFN intermediate dim in config")

    # Discover which layers have FFN (some architectures skip FFN on some layers)
    # Qwen3.5 layout: 6 × (3 × DeltaNet→FFN → 1 × Attention→FFN) = 24 layers all with FFN
    n_layers = cfg.num_hidden_layers
    d_model = cfg.hidden_size
    n_blocks = d_ff // block_size

    print(f"  Model: d_model={d_model}, d_ff={d_ff}, n_layers={n_layers}")
    print(f"  Blocks: {n_blocks} blocks/layer (block_size={block_size})")
    print(f"  Threshold: {threshold_frac:.3f} × max_activation")

    # Storage for hooked activations
    # We'll store the SwiGLU activation (gate * up after activation) per layer
    hooked_acts = {}  # layer_idx -> torch.Tensor of shape (seq_len, d_ff)

    # Find all FFN modules and register hooks
    hooks = []
    ffn_layer_map = {}  # maps hook handle -> layer index

    for name, module in model.named_modules():
        # Qwen3.5 uses Qwen3MLP which has .gate_proj, .up_proj, .down_proj
        # We need the SwiGLU activation: silu(gate(x)) * up(x)
        # This is the INPUT to down_proj. Hook down_proj to capture its input.
        if hasattr(module, 'gate_proj') and hasattr(module, 'up_proj') and hasattr(module, 'down_proj'):
            # Extract layer index from name, e.g., "model.layers.5.mlp"
            parts = name.split('.')
            layer_idx = None
            for i, p in enumerate(parts):
                if p == 'layers' and i + 1 < len(parts):
                    try:
                        layer_idx = int(parts[i + 1])
                    except ValueError:
                        pass
            if layer_idx is None:
                continue

            # Hook on down_proj Linear to capture its INPUT (the SwiGLU activation)
            def make_hook(lidx):
                def hook_fn(module, input, output):
                    # input[0] = SwiGLU activation flowing INTO down_proj
                    # Shape: (batch, seq, d_ff) or (batch*d_ff) depending on arch
                    with torch.no_grad():
                        act = input[0].detach()
                        if act.dim() == 3:
                            act = act[0]  # (seq, d_ff)
                        hooked_acts[lidx] = act.cpu()
                return hook_fn

            handle = module.down_proj.register_forward_hook(make_hook(layer_idx))
            hooks.append(handle)
            ffn_layer_map[handle] = layer_idx

    print(f"  Registered {len(hooks)} FFN hooks across {len(set(ffn_layer_map.values()))} layers")

    # Run forward pass
    print("  Running forward pass...")
    t0 = time.time()
    with torch.no_grad():
        # We need to capture ALL layers' activations in a single pass
        # Problem: hook overwrites hooked_acts[layer] on each forward call,
        # but a single model forward processes all layers sequentially.
        # The hook fires for each layer's MLP in order, so we need to
        # accumulate per layer.
        # Actually, the hook fires and stores, then the next layer fires
        # and overwrites... No, hooked_acts is keyed by layer_idx, so each
        # layer stores its own activation. This works because different layers
        # have different layer_idx keys.
        output = model(input_ids)

    elapsed = time.time() - t0
    print(f"  Forward pass done in {elapsed:.2f}s")

    # Remove hooks
    for h in hooks:
        h.remove()

    # Build trace: for each layer, threshold activations and find hot blocks
    trace = []
    total_hot_blocks = 0
    total_checks = 0

    for layer_idx in range(n_layers):
        if layer_idx not in hooked_acts:
            print(f"  WARNING: layer {layer_idx} has no hooked activation, skipping")
            trace.append([])
            continue

        act = hooked_acts[layer_idx]  # shape (seq, d_ff)
        # Reshape into blocks: (seq, n_blocks, block_size)
        act_blocks = act.view(seq_len, n_blocks, block_size)

        # Per token: which blocks are "hot"
        layer_token_blocks = []
        for t in range(seq_len):
            block_max = act_blocks[t].abs().max(dim=1).values  # (n_blocks,)
            threshold = block_max.max().item() * threshold_frac
            hot = (block_max > threshold).nonzero(as_tuple=True)[0].tolist()
            layer_token_blocks.append(hot)
            total_hot_blocks += len(hot)
            total_checks += 1

        trace.append(layer_token_blocks)

    mean_active = total_hot_blocks / max(total_checks, 1)
    print(f"  Mean active blocks/token: {mean_active:.1f}/{n_blocks} "
          f"({mean_active/n_blocks*100:.1f}%)")

    return {
        "trace": trace,
        "d_ff": d_ff,
        "n_blocks": n_blocks,
        "n_layers": n_layers,
        "seq_len": seq_len,
        "block_size": block_size,
        "threshold_frac": threshold_frac,
        "mean_active_blocks": mean_active,
    }


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def measure_locality(trace_data):
    """
    Measure temporal locality from the trace.
    Locality = P(block hot at t+1 | block hot at t)
    Averaged over all consecutive token pairs, all layers.
    """
    trace = trace_data["trace"]
    n_layers = trace_data["n_layers"]
    seq_len = trace_data["seq_len"]

    persistence_counts = 0
    total_pairs = 0

    for layer_idx in range(n_layers):
        layer_trace = trace[layer_idx]
        for t in range(seq_len - 1):
            current = set(layer_trace[t])
            next_set = set(layer_trace[t + 1])
            if len(current) == 0:
                continue
            # How many blocks in current stay active in next?
            persistent = len(current & next_set)
            persistence_counts += persistent
            total_pairs += len(current)

    locality = persistence_counts / max(total_pairs, 1)
    return locality


def simulate_cache(trace_data, cache_sizes):
    """Run LRU cache simulation on the real trace."""
    trace = trace_data["trace"]
    n_blocks = trace_data["n_blocks"]
    n_layers = trace_data["n_layers"]

    results = {}
    for c in cache_sizes:
        layer_hits = []
        for layer_idx in range(n_layers):
            cache = OrderedDict()
            hits = 0
            total = 0
            for token_blocks in trace[layer_idx]:
                for b in token_blocks:
                    total += 1
                    if b in cache:
                        hits += 1
                        cache.move_to_end(b)
                    else:
                        cache[b] = True
                        cache.move_to_end(b)
                        if len(cache) > c:
                            cache.popitem(last=False)
            layer_hits.append(hits / max(total, 1))
        results[c] = np.mean(layer_hits) * 100
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="F51 Dense Activation Trace")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"HF model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--block-size", type=int, default=BLOCK_SIZE,
                        help=f"Neurons per block (default: {BLOCK_SIZE})")
    parser.add_argument("--threshold", type=float, default=THRESHOLD_FRAC,
                        help=f"Activation threshold fraction (default: {THRESHOLD_FRAC})")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="Max tokens to process")
    parser.add_argument("--device", default="cuda",
                        help="Device: cuda or cpu")
    parser.add_argument("--output", default="trace_dense.json",
                        help="Output JSON file")
    parser.add_argument("--corpus-file", default=None,
                        help="Optional text file for input corpus")
    parser.add_argument("--skip-trace", action="store_true",
                        help="Skip trace, load from --output and re-analyze")
    args = parser.parse_args()

    if args.skip_trace:
        with open(args.output) as f:
            data = json.load(f)
        # Convert trace back to list of lists of lists
        trace_data = data["trace_data"]
        trace_data["block_size"] = data["block_size"]
        trace_data["threshold_frac"] = data["threshold_frac"]
    else:
        # Check device
        device = args.device
        if device == "cuda" and not torch.cuda.is_available():
            print("CUDA not available, falling back to CPU")
            device = "cpu"

        print("=" * 70)
        print("  F51 DENSE ACTIVATION TRACE")
        print(f"  Model: {args.model}")
        print(f"  Device: {device}")
        print("=" * 70)

        # Load model
        print(f"\nLoading model {args.model}...")
        t0 = time.time()
        tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            args.model,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map=device if device == "cuda" else None,
            trust_remote_code=True,
        )
        if device == "cpu":
            model = model.to(device)
        model.eval()
        print(f"  Model loaded in {time.time() - t0:.1f}s")

        # Corpus
        corpus = CORPUS
        if args.corpus_file:
            with open(args.corpus_file, encoding="utf-8") as f:
                corpus = f.read()
        print(f"  Corpus: {len(corpus)} chars / ~{len(corpus.split())} words")

        # Run trace
        print()
        trace_data = build_trace(
            model, tokenizer, corpus,
            threshold_frac=args.threshold,
            block_size=args.block_size,
            max_tokens=args.max_tokens,
            device=device,
        )

        # Save
        output = {
            "model": args.model,
            "block_size": args.block_size,
            "threshold_frac": args.threshold,
            "trace_data": {
                "d_ff": trace_data["d_ff"],
                "n_blocks": trace_data["n_blocks"],
                "n_layers": trace_data["n_layers"],
                "seq_len": trace_data["seq_len"],
                "mean_active_blocks": trace_data["mean_active_blocks"],
                "trace": trace_data["trace"],  # serializable (list of list of list)
            }
        }
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nTrace saved to {args.output}")

    # ===================================================================
    # Analysis (runs whether fresh trace or loaded from disk)
    # ===================================================================
    td = trace_data

    print()
    print("=" * 70)
    print("  ANALYSIS")
    print("=" * 70)
    print(f"  d_ff={td['d_ff']}, n_blocks={td['n_blocks']}, "
          f"block_size={td['block_size']}")
    print(f"  n_layers={td['n_layers']}, seq_len={td['seq_len']}")
    print(f"  Mean active blocks/token: {td['mean_active_blocks']:.1f}/{td['n_blocks']} "
          f"({td['mean_active_blocks']/td['n_blocks']*100:.1f}%)")
    print()

    # 1. Locality
    locality = measure_locality(td)
    print(f"  🔑 MEASURED LOCALITY: {locality:.4f}")
    print(f"     (P(block hot at t+1 | block hot at t), avg over all layers)")
    print()

    # 2. Cache simulation
    cache_sizes = [8, 12, 16, 20, 24, 32, 48]
    hr = simulate_cache(td, cache_sizes)

    print("  Cache simulation (LRU, real trace):")
    header = "  cache_size |" + "".join(f"  C={c:<3d}" for c in cache_sizes)
    print(header)
    cells = "  hit rate % |" + "".join(f"  {hr[c]:4.0f}%" for c in cache_sizes)
    print(cells)
    print()

    # 3. Gate
    print("=" * 70)
    print("  GATE:")
    if locality >= 0.80:
        print(f"  ✅ Locality {locality:.3f} >= 0.80 -> Dense musical-chairs VIABLE.")
        print(f"     Hit rate @ C=24: {hr.get(24, 0):.0f}%")
        print(f"     Hit rate @ C=20: {hr.get(20, 0):.0f}%")
        print(f"     Next: build predictor, then grouped GEMM kernel.")
    elif locality >= 0.70:
        print(f"  ⚠️  Locality {locality:.3f} borderline (0.70-0.80).")
        print(f"     Larger cache or better predictor might close the gap.")
        print(f"     Proceed with caution — measure predictor cost first.")
    else:
        print(f"  ❌ Locality {locality:.3f} < 0.70 -> Cache won't capture enough.")
        print(f"     The dense musical-chairs idea dies here, cheaply.")
        print(f"     No CUDA kernel needed. Pivot to another approach.")
    print("=" * 70)


if __name__ == "__main__":
    main()
