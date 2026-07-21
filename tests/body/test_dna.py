"""
Tests for DNAEngine — Fase 3 (DNA) da arquitetura CORPO.
"""

from __future__ import annotations

from core.body import DNAEngine, Gene


class TestGene:
    """Gene model validation."""

    def test_gene_defaults(self):
        g = Gene(
            name="test.gene",
            current_value=50.0,
            default_value=50.0,
            min=0.0,
            max=100.0,
        )
        assert g.name == "test.gene"
        assert g.current_value == 50.0
        assert g.mutation_rate == 0.15
        assert g.mutation_step == 0.05
        assert g.history == []

    def test_gene_to_dict(self):
        g = Gene(
            name="test.gene",
            current_value=50.0,
            default_value=50.0,
            min=0.0,
            max=100.0,
        )
        d = g.to_dict()
        assert d["name"] == "test.gene"
        assert d["current_value"] == 50.0


class TestDNAEngine:
    """DNA engine creation and gene management."""

    def test_engine_creates_12_genes(self):
        # Fase 3 extended mangala scoring with 3 granular weighting genes
        # (momentum, rsi, catalyst) on top of the original 9.
        engine = DNAEngine()
        genes = engine._genes
        assert len(genes) == 12

        expected_names = {
            "mangala.high_conviction",
            "mangala.watch_threshold",
            "mangala.volume_weight",
            "mangala.whale_weight",
            "mangala.momentum_weight",
            "mangala.rsi_weight",
            "mangala.catalyst_weight",
            "risk.kelly_multiplier",
            "risk.conviction_threshold",
            "risk.max_position_pct",
            "scan.frequency",
            "trade.max_hold_days",
        }
        assert set(genes.keys()) == expected_names

    def test_get_gene_returns_current_value(self):
        engine = DNAEngine()
        val = engine.get_gene("mangala.high_conviction")
        assert val == 80.0

    def test_get_gene_unknown_key_error(self):
        engine = DNAEngine()
        try:
            engine.get_gene("nonexistent.gene")
            assert False, "Expected KeyError"
        except KeyError:
            pass

    def test_mutate_moves_value(self):
        engine = DNAEngine()
        original = engine.get_gene("mangala.high_conviction")
        new_val = engine.mutate("mangala.high_conviction", 0.60)
        # With mutation_rate >= 0.5 in _coin_flip, mutation always applies
        assert new_val != original
        assert len(engine._genes["mangala.high_conviction"].history) >= 1

    def test_crystallized_gene_does_not_mutate(self):
        engine = DNAEngine()
        engine.crystallize("mangala.high_conviction")
        original = engine.get_gene("mangala.high_conviction")
        new_val = engine.mutate("mangala.high_conviction", 0.30)
        assert new_val == original

    def test_crystallize_returns_true_first_time(self):
        engine = DNAEngine()
        assert engine.crystallize("scan.frequency") is True
        assert engine.crystallize("scan.frequency") is False

    def test_evaluate_all_with_trades(self):
        engine = DNAEngine()
        trades = [
            {
                "outcome": "win",
                "genes_used": ["mangala.high_conviction", "risk.kelly_multiplier"],
            },
            {
                "outcome": "win",
                "genes_used": ["mangala.high_conviction"],
            },
            {
                "outcome": "loss",
                "genes_used": ["mangala.high_conviction", "risk.kelly_multiplier"],
            },
            {
                "outcome": "win",
                "genes_used": ["mangala.high_conviction"],
            },
        ]
        results = engine.evaluate_all(trades)
        assert "mangala.high_conviction" in results
        assert "risk.kelly_multiplier" in results
        # scan.frequency has no trades — should stay at default
        assert results["scan.frequency"] == 60.0

    def test_render_dna_report(self):
        engine = DNAEngine()
        engine.crystallize("scan.frequency")
        report = engine.render_dna_report()
        assert "[DNA Report]" in report
        assert "mangala.high_conviction" in report
        assert "CRYSTALLIZED" in report

    def test_snapshot(self):
        engine = DNAEngine()
        snap = engine.snapshot()
        assert len(snap["genes"]) == 12
        assert snap["crystallized"] == []

    def test_seed_custom_gene(self):
        engine = DNAEngine(seed={"custom.param": {"default": 42.0, "min": 0, "max": 100}})
        assert engine.get_gene("custom.param") == 42.0
        assert len(engine._genes) == 13
