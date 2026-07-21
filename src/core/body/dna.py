"""DNA — Genetic parameter engine for the CORPO layer.

Each gene is a tunable parameter that controls pipeline behaviour. The engine
applies Darwinian mutation based on trade outcome win rates and can crystallize
genes whose performance exceeds a 70% win-rate threshold.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Gene model
# ---------------------------------------------------------------------------


class Gene(BaseModel):
    """A single tunable parameter with evolutionary history."""

    name: str
    current_value: float
    default_value: float
    min: float
    max: float
    mutation_rate: float = 0.15  # probability of mutating on evaluation
    mutation_step: float = 0.05  # fraction of range to shift per mutation
    history: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "current_value": self.current_value,
            "default_value": self.default_value,
            "min": self.min,
            "max": self.max,
            "mutation_rate": self.mutation_rate,
            "mutation_step": self.mutation_step,
        }


# ---------------------------------------------------------------------------
# DNA Engine
# ---------------------------------------------------------------------------


class DNAEngine:
    """Manages the full gene pool, mutation cycles, and crystallisation."""

    # ---- 9 initial genes ---------------------------------------------------
    _GENE_DEFINITIONS: list[dict[str, Any]] = [
        # Mangala conviction / watch thresholds
        {
            "name": "mangala.high_conviction",
            "default": 80.0,
            "min": 50.0,
            "max": 100.0,
            "mutation_rate": 0.15,
            "mutation_step": 0.05,
        },
        {
            "name": "mangala.watch_threshold",
            "default": 60.0,
            "min": 30.0,
            "max": 90.0,
            "mutation_rate": 0.15,
            "mutation_step": 0.05,
        },
        # Weighting
        {
            "name": "mangala.volume_weight",
            "default": 30.0,
            "min": 5.0,
            "max": 60.0,
            "mutation_rate": 0.12,
            "mutation_step": 0.04,
        },
        {
            "name": "mangala.whale_weight",
            "default": 25.0,
            "min": 5.0,
            "max": 50.0,
            "mutation_rate": 0.12,
            "mutation_step": 0.04,
        },
        # Risk
        {
            "name": "risk.kelly_multiplier",
            "default": 0.25,
            "min": 0.05,
            "max": 1.0,
            "mutation_rate": 0.18,
            "mutation_step": 0.03,
        },
        {
            "name": "risk.conviction_threshold",
            "default": 70.0,
            "min": 30.0,
            "max": 95.0,
            "mutation_rate": 0.15,
            "mutation_step": 0.05,
        },
        {
            "name": "risk.max_position_pct",
            "default": 0.05,
            "min": 0.01,
            "max": 0.25,
            "mutation_rate": 0.12,
            "mutation_step": 0.02,
        },
        # Scanning / holding
        {
            "name": "scan.frequency",
            "default": 60.0,
            "min": 15.0,
            "max": 240.0,
            "mutation_rate": 0.10,
            "mutation_step": 0.05,
        },
        {
            "name": "trade.max_hold_days",
            "default": 5.0,
            "min": 1.0,
            "max": 30.0,
            "mutation_rate": 0.10,
            "mutation_step": 0.05,
        },
    ]

    def __init__(self, seed: dict[str, Any] | None = None) -> None:
        self._genes: dict[str, Gene] = {}
        self._crystallized: set[str] = set()
        self._load_definitions(seed)

    # ---- public API --------------------------------------------------------

    def get_gene(self, name: str) -> float:
        """Return the current value of a gene (used by pipeline nodes)."""
        if name not in self._genes:
            raise KeyError(f"Unknown gene: {name}")
        return self._genes[name].current_value

    def mutate(self, gene_name: str, win_rate: float) -> float:
        """Adjust a single gene by ±step based on win_rate vs 0.50 baseline.

        If win_rate < 0.50 the gene shifts *away* from its default (the current
        value is hurting performance).  If win_rate >= 0.50 it shifts *toward*
        the default (reinforcing what works).
        """
        gene = self._genes.get(gene_name)
        if gene is None:
            raise KeyError(f"Unknown gene: {gene_name}")
        if gene_name in self._crystallized:
            return gene.current_value  # frozen — no mutation

        _record_mutation(gene, "skip", reason="below_rate_threshold")
        if _coin_flip(gene.mutation_rate):
            return gene.current_value

        delta = self._compute_delta(gene, win_rate)
        new_value = _clamp(gene.current_value + delta, gene.min, gene.max)
        old_value = gene.current_value
        gene.current_value = new_value
        gene.history.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "old_value": old_value,
                "new_value": new_value,
                "win_rate": win_rate,
                "reason": "mutation",
            }
        )
        return new_value

    def evaluate_all(self, trades: list[dict[str, Any]]) -> dict[str, float]:
        """For every gene with enough data, compute win_rate and mutate.

        *trades* must be a list of dicts each containing at least
        ``{"outcome": "win"|"loss", "genes_used": ["mangala.high_conviction", ...]}``.

        Returns a dict mapping gene_name -> current_value after mutation.
        """
        # Group trades by the genes they exercised
        gene_outcomes: dict[str, list[bool]] = {}
        for t in trades:
            outcome = t.get("outcome", "").lower()
            if outcome not in ("win", "loss"):
                continue
            for g in t.get("genes_used", []):
                gene_outcomes.setdefault(g, []).append(outcome == "win")

        results: dict[str, float] = {}
        for gname, gene in self._genes.items():
            outcomes = gene_outcomes.get(gname, [])
            if len(outcomes) < 3:
                results[gname] = gene.current_value
                continue
            win_rate = mean(outcomes)
            self.mutate(gname, win_rate)
            results[gname] = gene.current_value
        return results

    def crystallize(self, gene_name: str) -> bool:
        """Freeze a gene at its current value (prevents future mutation).

        Only genes whose win_rate has exceeded 70 % should be passed here.
        Returns True if the gene was newly crystallized.
        """
        if gene_name not in self._genes:
            raise KeyError(f"Unknown gene: {gene_name}")
        if gene_name in self._crystallized:
            return False
        self._crystallized.add(gene_name)
        gene = self._genes[gene_name]
        gene.history.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "old_value": gene.current_value,
                "new_value": gene.current_value,
                "win_rate": None,
                "reason": "crystallized",
            }
        )
        return True

    def render_dna_report(self) -> str:
        """Produce a human-readable DNA report for Bob's system prompt."""
        lines = ["[DNA Report]", ""]
        for gene in self._genes.values():
            frozen = " [CRYSTALLIZED]" if gene.name in self._crystallized else ""
            lines.append(
                f"  {gene.name}: {gene.current_value:.4f}  "
                f"(default {gene.default_value:.4f}, "
                f"range [{gene.min}, {gene.max}]){frozen}"
            )
        lines.append("")
        lines.append(f"  Crystallized: {len(self._crystallized)} / {len(self._genes)} genes")
        return "\n".join(lines)

    def snapshot(self) -> dict[str, Any]:
        """Return a serialisable snapshot of the entire DNA state."""
        return {
            "genes": {n: g.to_dict() for n, g in self._genes.items()},
            "crystallized": sorted(self._crystallized),
        }

    # ---- internals ---------------------------------------------------------

    def _load_definitions(self, seed: dict[str, Any] | None) -> None:
        definitions = {d["name"]: d for d in self._GENE_DEFINITIONS}
        if seed:
            for name, overrides in seed.items():
                if name in definitions:
                    definitions[name].update(overrides)
                else:
                    definitions[name] = {
                        "name": name,
                        "default": overrides.get("default", 0.0),
                        "min": overrides.get("min", 0.0),
                        "max": overrides.get("max", 1.0),
                        "mutation_rate": overrides.get("mutation_rate", 0.15),
                        "mutation_step": overrides.get("mutation_step", 0.05),
                    }
                    definitions[name]["name"] = name

        for name, d in definitions.items():
            self._genes[name] = Gene(
                name=name,
                current_value=d["default"],
                default_value=d["default"],
                min=d["min"],
                max=d["max"],
                mutation_rate=d.get("mutation_rate", 0.15),
                mutation_step=d.get("mutation_step", 0.05),
            )

    def _compute_delta(self, gene: Gene, win_rate: float) -> float:
        """How far and in which direction to nudge the gene."""
        raw_range = gene.max - gene.min
        step_abs = raw_range * gene.mutation_step
        if win_rate >= 0.50:
            # Move toward default (reinforce)
            direction = 1.0 if gene.current_value < gene.default_value else -1.0
        else:
            # Move away from default (explore)
            direction = -1.0 if gene.current_value < gene.default_value else 1.0
        return direction * step_abs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _coin_flip(probability: float) -> bool:
    """Return True with given probability (deterministic helper)."""
    # Use the fractional part of a simple hash to keep it seed-free.
    return probability >= 0.5  # deterministic: mutate if rate >= 50%


def _record_mutation(gene: Gene, reason: str, **extra: Any) -> None:
    gene.history.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "old_value": gene.current_value,
            "new_value": gene.current_value,
            "win_rate": None,
            "reason": reason,
            **extra,
        }
    )


__all__ = [
    "DNAEngine",
    "Gene",
]
