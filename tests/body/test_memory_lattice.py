"""
Tests for MemoryLattice — Fase 4 (Memoria) da arquitetura CORPO.
"""

from __future__ import annotations

from core.body import LAYER_NAMES, MemoryLattice


class TestMemoryLattice:
    """Memory lattice layer operations."""

    def test_layer_names_defined(self):
        assert LAYER_NAMES[1] == "meta_rules"
        assert LAYER_NAMES[2] == "crystallized_skills"
        assert LAYER_NAMES[3] == "facts"
        assert LAYER_NAMES[4] == "patterns"
        assert LAYER_NAMES[5] == "raw"
        assert len(LAYER_NAMES) == 5

    def test_meta_rules_are_seeded(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        rules = lattice.query(1)
        lattice.close()
        assert len(rules) == 7  # 7 seed constitutional rules

    def test_store_and_query_layer_2(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        rowid = lattice.store(2, {"name": "skill_a", "win_rate": 0.85})
        assert isinstance(rowid, int) and rowid > 0

        results = lattice.query(2, filters={"name": "skill_a"})
        assert len(results) == 1
        assert results[0]["name"] == "skill_a"
        lattice.close()

    def test_store_and_query_layer_3(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        lattice.store(3, {"trade_id": "t1", "outcome": "win", "ticker": "AAPL"})
        lattice.store(3, {"trade_id": "t2", "outcome": "loss", "ticker": "GOOG"})

        results = lattice.query(3, filters={"outcome": "win"})
        assert len(results) == 1
        assert results[0]["trade_id"] == "t1"
        lattice.close()

    def test_store_and_query_layer_4(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        lattice.store(4, {"pattern_id": "p1", "description": "gap_up_momentum", "lift": 1.5})

        results = lattice.query(4, filters={"pattern_id": "p1"})
        assert len(results) == 1
        assert results[0]["lift"] == 1.5
        lattice.close()

    def test_store_and_query_layer_5(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        lattice.store(5, {"event": "scan_completed", "tickers": ["AAPL"]})

        results = lattice.query(5)
        assert len(results) == 1
        assert results[0]["event"] == "scan_completed"
        lattice.close()

    def test_layer_1_is_immutable(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        try:
            lattice.store(1, {"rule": "test"})
            assert False, "Expected ValueError"
        except ValueError:
            pass
        lattice.close()

    def test_invalid_layer_raises(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        try:
            lattice.store(99, {"x": 1})
            assert False, "Expected ValueError"
        except ValueError:
            pass
        lattice.close()

    def test_fts_search_on_layer_2(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        lattice.store(
            2, {"name": "momentum_breakout", "description": "price breaks 20-day high with volume"}
        )
        lattice.store(2, {"name": "mean_reversion", "description": "rsi oversold bounce"})

        results = lattice.query(2, search="momentum")
        assert len(results) >= 1
        assert results[0]["name"] == "momentum_breakout"
        lattice.close()

    def test_crystallize_promotes_pattern_to_skill(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        pattern = {
            "pattern_id": "p42",
            "name": "gap_up_continuation",
            "description": "Gap up with increasing volume continues trend",
            "win_rate": 0.82,
            "expression": "close > vwap AND volume > avg(volume,20)",
        }
        skill_rowid = lattice.crystallize(pattern)
        assert isinstance(skill_rowid, int) and skill_rowid > 0

        skills = lattice.query(2, filters={"name": "gap_up_continuation"})
        assert len(skills) == 1
        assert skills[0]["win_rate"] == 0.82
        lattice.close()

    def test_multiple_layers_independent(self, tmp_path):
        db = tmp_path / "test_lattice.sqlite3"
        lattice = MemoryLattice(db)
        lattice.store(2, {"item": "skill_1"})
        lattice.store(3, {"item": "fact_1"})
        lattice.store(4, {"item": "pattern_1"})
        lattice.store(5, {"item": "raw_1"})

        assert len(lattice.query(2)) == 1
        assert len(lattice.query(3)) == 1
        assert len(lattice.query(4)) == 1
        assert len(lattice.query(5)) == 1
        lattice.close()
