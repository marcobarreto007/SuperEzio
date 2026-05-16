"""Tests for Expert Weight Router — Loop 4."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestExpertWeightRouterInit:
    def test_defaults(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        assert router.min_weight == 0.1
        assert router.max_weight == 3.0
        assert router.decay_factor == 0.95

    def test_unknown_expert_returns_initial_weight(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter(initial_weight=1.0)
        assert router.get_weight("unknown") == 1.0

    def test_empty_weights(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        assert router.get_all_weights() == {}
        assert router.get_normalized_weights() == {}


class TestExpertWeightRouterRecord:
    def test_record_call_creates_expert(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        rec = router.record_call("pennylab", confidence=0.8)
        assert rec.total_calls == 1
        assert rec.name == "pennylab"

    def test_record_correct_call(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        rec = router.record_call("pennylab", confidence=0.8, correct=True)
        assert rec.correct_calls == 1
        assert rec.total_calls == 1

    def test_record_incorrect_call(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        rec = router.record_call("pennylab", confidence=0.6, correct=False)
        assert rec.correct_calls == 0
        assert rec.total_calls == 1

    def test_record_null_correct(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        rec = router.record_call("pennylab", confidence=0.7, correct=None)
        assert rec.correct_calls == 0
        assert rec.total_calls == 1

    def test_multiple_calls_accumulate(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        router.record_call("pennylab", confidence=0.8, correct=True)
        router.record_call("pennylab", confidence=0.7, correct=True)
        router.record_call("pennylab", confidence=0.5, correct=False)
        rec = router.get_record("pennylab")
        assert rec.total_calls == 3
        assert rec.correct_calls == 2


class TestExpertWeightRouterWeights:
    def test_correct_calls_increase_weight(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter(initial_weight=1.0)
        for _ in range(10):
            router.record_call("pennylab", confidence=0.8, correct=True)
        weight = router.get_weight("pennylab")
        assert weight > 1.0  # accuracy_mult = 0.5 + 1.0 = 1.5

    def test_incorrect_calls_decrease_weight(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter(initial_weight=1.0)
        for _ in range(10):
            router.record_call("crisis", confidence=0.6, correct=False)
        weight = router.get_weight("crisis")
        assert weight < 1.0  # accuracy_mult = 0.5 + 0.0 = 0.5

    def test_weight_clamped_min(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter(initial_weight=0.5, min_weight=0.1)
        for _ in range(20):
            router.record_call("bad_expert", confidence=0.3, correct=False)
        assert router.get_weight("bad_expert") >= 0.1

    def test_weight_clamped_max(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter(initial_weight=2.0, max_weight=3.0)
        for _ in range(20):
            router.record_call("great_expert", confidence=0.95, correct=True)
        assert router.get_weight("great_expert") <= 3.0

    def test_normalized_weights_sum_to_one(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        router.record_call("pennylab", confidence=0.8, correct=True)
        router.record_call("crisis", confidence=0.6, correct=False)
        norm = router.get_normalized_weights()
        assert abs(sum(norm.values()) - 1.0) < 0.01

    def test_two_experts_different_weights(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        for _ in range(5):
            router.record_call("pennylab", confidence=0.9, correct=True)
            router.record_call("crisis", confidence=0.5, correct=False)
        weights = router.get_all_weights()
        assert weights["pennylab"] > weights["crisis"]


class TestExpertWeightRouterDecay:
    def test_decay_reduces_weights(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter(decay_factor=0.9)
        router.record_call("pennylab", confidence=0.8, correct=True)
        before = router.get_weight("pennylab")
        router.decay_all()
        after = router.get_weight("pennylab")
        assert after < before

    def test_decay_respects_min(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter(decay_factor=0.5, min_weight=0.1, initial_weight=0.2)
        router.record_call("pennylab", confidence=0.8, correct=False)
        router.decay_all()
        router.decay_all()
        assert router.get_weight("pennylab") >= 0.1


class TestExpertWeightRouterReset:
    def test_reset_specific_expert(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        router.record_call("pennylab", confidence=0.8)
        router.record_call("crisis", confidence=0.7)
        router.reset("pennylab")
        assert router.get_record("pennylab") is None
        assert router.get_record("crisis") is not None

    def test_reset_all(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        router.record_call("pennylab", confidence=0.8)
        router.record_call("crisis", confidence=0.7)
        router.reset()
        assert router.get_all_weights() == {}


class TestExpertWeightRouterGetRecords:
    def test_get_record(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        router.record_call("pennylab", confidence=0.85, correct=True)
        rec = router.get_record("pennylab")
        assert rec is not None
        assert rec.total_calls == 1
        assert rec.correct_calls == 1
        assert rec.total_confidence == pytest.approx(0.85)

    def test_get_all_records(self):
        from core.trading.expert_weights import ExpertWeightRouter

        router = ExpertWeightRouter()
        router.record_call("pennylab", confidence=0.8)
        router.record_call("crisis", confidence=0.7)
        records = router.get_all_records()
        assert len(records) == 2
        assert "pennylab" in records
        assert "crisis" in records
