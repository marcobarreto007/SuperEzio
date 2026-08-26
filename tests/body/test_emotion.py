"""
Tests for PADEngine — Fase 3 (Emotion) da arquitetura CORPO.
"""

from __future__ import annotations

import pytest

from core.body import EMOTION_LABELS, EmotionalState, PADEngine


class TestPADEngine:
    """PAD emotional model."""

    def test_initial_state_is_neutral(self):
        engine = PADEngine()
        state = engine.current_state()
        assert state.pleasure == 0.0
        assert state.arousal == 0.3
        assert state.dominance == 0.0

    def test_update_win_rate_affects_pleasure(self):
        engine = PADEngine()
        state = engine.update(win_rate=0.80)
        # 0.80 -> pleasure = (0.80 - 0.5) * 2 = 0.60
        assert state.pleasure == pytest.approx(0.60, abs=1e-9)

    def test_update_volatility_affects_arousal(self):
        engine = PADEngine()
        state = engine.update(volatility=0.90)
        assert state.arousal == 0.90

    def test_update_capital_ratio_affects_dominance(self):
        engine = PADEngine()
        state = engine.update(capital_vs_initial=2.0)
        # tanh(2.0 - 1.0) * 1.5 = tanh(1.0) * 1.5 ≈ 0.7616 * 1.5 ≈ 1.142 -> clamped to 1.0
        assert state.dominance > 0.5

    def test_negative_capital_ratio_gives_negative_dominance(self):
        engine = PADEngine()
        state = engine.update(capital_vs_initial=0.5)
        # tanh(0.5 - 1.0) * 1.5 = tanh(-0.5) * 1.5 ≈ -0.462 * 1.5 ≈ -0.693
        assert state.dominance < 0.0

    def test_update_returns_state_snapshot(self):
        engine = PADEngine()
        state = engine.update(win_rate=0.70, volatility=0.40, capital_vs_initial=1.2)
        assert isinstance(state, EmotionalState)
        assert isinstance(state.label, str)

    def test_history_accumulates(self):
        engine = PADEngine()
        engine.update(win_rate=0.60)
        engine.update(win_rate=0.40)
        engine.update(win_rate=0.80)
        assert len(engine.history()) == 3

    def test_reset_clears_state_and_history(self):
        engine = PADEngine()
        engine.update(win_rate=0.90, volatility=0.80, capital_vs_initial=2.0)
        assert len(engine.history()) == 1
        engine.reset()
        assert engine.pleasure == 0.0
        assert engine.arousal == 0.3
        assert engine.dominance == 0.0
        assert engine.history() == []

    def test_modulate_dna_euphoria(self):
        engine = PADEngine()
        engine.update(win_rate=0.90, volatility=0.80, capital_vs_initial=1.5)
        dna = {"risk.kelly_multiplier": 0.25, "risk.conviction_threshold": 70.0}
        modulated = engine.modulate_dna(dna)

        # Euphoria: kelly goes up, conviction goes down
        assert modulated["risk.kelly_multiplier"] > 0.25
        assert modulated["risk.conviction_threshold"] < 70.0

    def test_modulate_dna_fear(self):
        engine = PADEngine()
        # Pleasure low, arousal high, dominance low -> "fear"
        engine.update(win_rate=0.20, volatility=0.80, capital_vs_initial=0.80)
        assert engine.current_state().label == "fear"

        dna = {
            "risk.kelly_multiplier": 0.25,
            "risk.max_position_pct": 0.05,
            "mangala.high_conviction": 80.0,
        }
        modulated = engine.modulate_dna(dna)

        # Fear: kelly down, position down, conviction up
        assert modulated["risk.kelly_multiplier"] < 0.25
        assert modulated["risk.max_position_pct"] < 0.05
        assert modulated["mangala.high_conviction"] > 80.0

    def test_eight_emotion_labels_defined(self):
        assert len(EMOTION_LABELS) == 8
        assert "euphoria" in EMOTION_LABELS.values()
        assert "anxiety" in EMOTION_LABELS.values()
        assert "contentment" in EMOTION_LABELS.values()
        assert "serenity" in EMOTION_LABELS.values()
        assert "dominance" in EMOTION_LABELS.values()
        assert "fear" in EMOTION_LABELS.values()
        assert "boredom" in EMOTION_LABELS.values()
        assert "apathy" in EMOTION_LABELS.values()
