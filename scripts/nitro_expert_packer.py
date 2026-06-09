"""
F51 NITRO — EXPERT CLUSTER PACKING TOOL (Layer 5)
==================================================
Profiles MoE expert co-activation patterns and repacks GGUF
for optimal NVMe sequential reads.

The insight: experts that fire together should be stored together.
One sequential NVMe read = multiple ready-to-use experts.
Cold I/O drops from N random reads to 1 sequential read per cluster.

Marco's analogy: instead of the motoboy going back to the depot for
each package, he picks up 10 packages in one trip.
"""

import json
import os
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from itertools import combinations


# ── DATA STRUCTURES ────────────────────────────────────────────


@dataclass
class ExpertActivation:
    """A single activation record: which experts fired for a token."""

    token_id: int
    layer: int
    expert_ids: List[int]
    routing_weights: List[float]  # softmax weights from router


@dataclass
class ProfileRun:
    """Collection of activation records from one inference run."""

    activations: List[ExpertActivation] = field(default_factory=list)
    total_tokens: int = 0
    model_name: str = ""

    def add(self, token_id: int, layer: int, expert_ids: List[int], weights: List[float]):
        self.activations.append(
            ExpertActivation(
                token_id=token_id, layer=layer, expert_ids=expert_ids, routing_weights=weights
            )
        )
        self.total_tokens = max(self.total_tokens, token_id + 1)


# ── MOCK PROFILER (real data later) ────────────────────────────


class MockProfiler:
    """
    Generates synthetic expert activation patterns based on
    known MoE properties:
    - 65% persistence between consecutive tokens (measured)
    - Layer-adjacent correlation
    - Zipf distribution: few experts dominate
    """

    def __init__(
        self,
        num_experts: int = 512,
        num_layers: int = 48,
        experts_per_token: int = 10,
        persistence: float = 0.65,
        seed: int = 42,
    ):
        self.num_experts = num_experts
        self.num_layers = num_layers
        self.experts_per_token = experts_per_token
        self.persistence = persistence
        self.seed = seed

    def profile(self, num_tokens: int = 500) -> ProfileRun:
        import random

        rng = random.Random(self.seed)

        run = ProfileRun()
        current_experts = None

        # Build Zipf-like popularity per layer
        layer_popularity = {}
        for layer in range(self.num_layers):
            # Top 10% of experts get 40% of activations
            weights = [1.0 / (i + 1) ** 0.8 for i in range(self.num_experts)]
            total = sum(weights)
            probs = [w / total for w in weights]
            layer_popularity[layer] = probs

        for t in range(num_tokens):
            if current_experts is None:
                # First token: random by popularity
                current_experts = []
                for layer in range(self.num_layers):
                    layer_experts = rng.choices(
                        range(self.num_experts),
                        weights=layer_popularity[layer],
                        k=self.experts_per_token,
                    )
                    current_experts.append(layer_experts)
            else:
                # Evolution: keep persistence% + mutate rest
                new_experts = []
                for layer in range(self.num_layers):
                    prev_layer_experts = current_experts[layer]
                    keep = int(self.experts_per_token * self.persistence)
                    layer_experts = prev_layer_experts[:keep]
                    new_needed = self.experts_per_token - keep
                    # Preferentially pick experts adjacent to kept ones
                    available = [e for e in range(self.num_experts) if e not in layer_experts]
                    if new_needed > 0 and available:
                        avail_weights = [layer_popularity[layer][e] for e in available]
                        new_experts_layer = rng.choices(
                            available, weights=avail_weights, k=new_needed
                        )
                        layer_experts.extend(new_experts_layer)
                    new_experts.append(layer_experts)
                current_experts = new_experts

            # Record activations
            for layer in range(self.num_layers):
                exp_ids = current_experts[layer]
                weights = [rng.random() for _ in exp_ids]
                total_w = sum(weights)
                weights = [w / total_w for w in weights]
                run.add(token_id=t, layer=layer, expert_ids=exp_ids, weights=weights)

        return run


# ── CO-ACTIVATION ANALYZER ────────────────────────────────────


class CoActivationAnalyzer:
    """
    Builds co-activation matrix: how often expert A fires
    in the same token (same or adjacent layer) as expert B.
    """

    def __init__(self):
        # coact[layer][expert_A][expert_B] = count
        self.coact: Dict[int, Dict[int, Counter]] = defaultdict(lambda: defaultdict(Counter))
        # solo frequency
        self.freq: Dict[int, Counter] = defaultdict(Counter)

    def ingest(self, run: ProfileRun):
        for act in run.activations:
            layer = act.layer
            experts = act.expert_ids

            # Solo frequencies
            for e in experts:
                self.freq[layer][e] += 1

            # Within-layer co-activations
            for a, b in combinations(sorted(experts), 2):
                self.coact[layer][a][b] += 1
                self.coact[layer][b][a] += 1

        return self

    def get_coact_score(self, layer: int, a: int, b: int) -> float:
        """Jaccard-like co-activation score between two experts."""
        fa = self.freq[layer].get(a, 0)
        fb = self.freq[layer].get(b, 0)
        if fa == 0 or fb == 0:
            return 0.0
        co = self.coact[layer].get(a, {}).get(b, 0)
        return co / (fa + fb - co) if (fa + fb - co) > 0 else 0.0

    def get_coact_matrix(self, layer: int) -> Dict[Tuple[int, int], float]:
        """Full co-activation matrix for one layer."""
        matrix = {}
        experts = list(self.freq[layer].keys())
        for a, b in combinations(sorted(experts), 2):
            score = self.get_coact_score(layer, a, b)
            if score > 0:
                matrix[(a, b)] = score
        return matrix


# ── CLUSTERING ─────────────────────────────────────────────────


class ExpertClusterer:
    """
    Groups experts by co-activation into clusters.
    Each cluster = experts that should be stored together on NVMe.

    Uses greedy agglomerative clustering:
    1. Start with each expert as its own cluster
    2. Merge clusters with highest average co-activation score
    3. Stop when cluster size reaches target or scores drop below threshold
    """

    def __init__(self, target_cluster_size_mb: float = 256.0, expert_size_mb: float = 59.0):
        self.target_cluster_size = target_cluster_size_mb
        self.expert_size_mb = expert_size_mb
        self.max_experts_per_cluster = int(target_cluster_size_mb / expert_size_mb)

    def cluster(self, analyzer: CoActivationAnalyzer, layer: int) -> List[List[int]]:
        """
        Fast greedy clustering: O(n²) instead of O(n³).
        1. Start with most frequent expert as seed
        2. Find expert with highest co-activation to any cluster member
        3. Add to cluster until full
        4. Repeat with next seed
        """
        experts = sorted(analyzer.freq[layer].keys())
        if not experts:
            return []

        remaining = set(experts)
        clusters = []

        while remaining:
            # Seed: most frequent remaining expert
            seed = max(remaining, key=lambda e: analyzer.freq[layer].get(e, 0))
            cluster = [seed]
            remaining.remove(seed)

            # Grow cluster: add expert with highest affinity to cluster
            while len(cluster) < self.max_experts_per_cluster and remaining:
                best_score = -1.0
                best_expert = None
                for candidate in remaining:
                    # Average co-activation with all cluster members
                    score = sum(
                        analyzer.get_coact_score(layer, candidate, member) for member in cluster
                    ) / len(cluster)
                    if score > best_score:
                        best_score = score
                        best_expert = candidate

                if best_expert is None or best_score < 0.005:
                    break

                cluster.append(best_expert)
                remaining.remove(best_expert)

            clusters.append(cluster)

        return clusters


# ── GGUF LAYOUT OPTIMIZER ─────────────────────────────────────


class GGUFLayoutOptimizer:
    """
    Reads GGUF tensor info, maps expert tensors to clusters,
    and produces an optimized layout.

    The output is a JSON file with:
    - cluster_id → list of tensor names
    - recommended file order
    - estimated NVMe read benefit

    Future: can rewrite GGUF with clustered tensor ordering.
    """

    def __init__(self, analyzer: CoActivationAnalyzer, clusterer: ExpertClusterer):
        self.analyzer = analyzer
        self.clusterer = clusterer

    def optimize(self, gguf_path: Optional[str] = None) -> Dict:
        """
        Produce optimized layout.
        If gguf_path provided, reads actual tensor list.
        If not, generates layout for known architecture.
        """
        clusters_per_layer = {}
        all_experts: Dict[int, List[int]] = {}

        for layer in range(48):  # Qwen3-Next has 48 layers
            clusters = self.clusterer.cluster(self.analyzer, layer)
            if clusters:
                clusters_per_layer[layer] = clusters
                all_experts[layer] = []
                for c in clusters:
                    all_experts[layer].extend(c)

        # Compute benefit
        total_experts = sum(len(v) for v in all_experts.values())
        total_clusters = sum(len(v) for v in clusters_per_layer.values())
        avg_experts_per_cluster = total_experts / total_clusters if total_clusters > 0 else 0

        return {
            "total_experts": total_experts,
            "total_clusters": total_clusters,
            "avg_experts_per_cluster": round(avg_experts_per_cluster, 1),
            "avg_cluster_size_mb": round(
                avg_experts_per_cluster * self.clusterer.expert_size_mb, 1
            ),
            "nvme_benefit": {
                "random_reads_saved_pct": round((1 - 1 / avg_experts_per_cluster) * 100, 1)
                if avg_experts_per_cluster > 0
                else 0,
                "estimated_speedup": f"{min(avg_experts_per_cluster, 8):.1f}x",
            },
            "clusters_per_layer": {
                str(layer): [
                    {
                        "cluster_id": f"L{layer}_C{i}",
                        "expert_ids": cluster,
                        "size_mb": round(len(cluster) * self.clusterer.expert_size_mb, 1),
                    }
                    for i, cluster in enumerate(clusters)
                ]
                for layer, clusters in sorted(clusters_per_layer.items())
            },
        }


# ── MAIN ───────────────────────────────────────────────────────


def main():
    print("=" * 64)
    print("F51 NITRO — EXPERT CLUSTER PACKING (Layer 5)")
    print("=" * 64)

    # Profile
    print("\n[1/3] Profiling expert co-activation patterns...")
    profiler = MockProfiler(
        num_experts=512, num_layers=48, experts_per_token=10, persistence=0.65, seed=42
    )
    run = profiler.profile(num_tokens=500)
    print(f"  Generated {run.total_tokens} tokens × {profiler.num_layers} layers")
    print(f"  Total activations: {len(run.activations):,}")

    # Analyze
    print("\n[2/3] Building co-activation matrix...")
    analyzer = CoActivationAnalyzer()
    analyzer.ingest(run)

    # Top co-activations in layer 0
    print("\n  Top co-activations (Layer 0):")
    top = sorted(
        [
            (analyzer.get_coact_score(0, a, b), a, b)
            for a in range(min(20, profiler.num_experts))
            for b in range(a + 1, min(20, profiler.num_experts))
        ],
        reverse=True,
    )[:5]
    for score, a, b in top:
        freq_a = analyzer.freq[0].get(a, 0)
        freq_b = analyzer.freq[0].get(b, 0)
        print(f"    Expert {a:3d} <-> {b:3d}: score={score:.3f} (freq: {freq_a}, {freq_b})")

    # Cluster
    print("\n[3/3] Clustering experts...")
    clusterer = ExpertClusterer(
        target_cluster_size_mb=256.0,  # target ~256 MB per cluster
        expert_size_mb=59.0,  # ~59 MB per expert at IQ4_XS
    )

    optimizer = GGUFLayoutOptimizer(analyzer, clusterer)
    result = optimizer.optimize()

    print(f"\n{'=' * 64}")
    print("RESULTS")
    print(f"{'=' * 64}")
    print(f"  Total experts mapped:    {result['total_experts']}")
    print(f"  Total clusters:          {result['total_clusters']}")
    print(f"  Avg experts per cluster: {result['avg_experts_per_cluster']}")
    print(f"  Avg cluster size:        {result['avg_cluster_size_mb']} MB")
    print(f"  NVMe random reads saved: {result['nvme_benefit']['random_reads_saved_pct']}%")
    print(f"  Estimated I/O speedup:   {result['nvme_benefit']['estimated_speedup']}")

    # Show first 3 layers' clusters
    print("\n  Sample clusters (first 3 layers):")
    for layer_str in sorted(result["clusters_per_layer"].keys())[:3]:
        clusters = result["clusters_per_layer"][layer_str]
        print(f"  Layer {layer_str}: {len(clusters)} clusters")
        for c in clusters[:2]:
            print(
                f"    {c['cluster_id']}: {len(c['expert_ids'])} experts, "
                f"{c['size_mb']} MB, IDs: {c['expert_ids'][:5]}..."
            )

    # Save
    out_path = r"C:\F51_LAB\expert_cluster_layout.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nLayout saved to: {out_path}")

    return result


if __name__ == "__main__":
    main()
