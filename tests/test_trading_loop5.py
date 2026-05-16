"""Tests for RL Reward, Dataset Builder, and LoRA Training — Loop 5."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── RewardFunction ──────────────────────────────────────────────────────────


class TestRewardFunctionInit:
    def test_defaults(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        assert rf.pnl_weight == 1.0
        assert rf.risk_weight == 0.5
        assert rf.confidence_weight == 0.3

    def test_custom_weights(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction(pnl_weight=2.0, risk_weight=1.0, confidence_weight=0.5)
        assert rf.pnl_weight == 2.0


class TestRewardCompute:
    def _make_outcome(self, **overrides):
        from core.trading.reward import TradeOutcome

        defaults = dict(
            symbol="AAPL", side="buy", entry_price=100.0, exit_price=110.0,
            qty=10, pnl=100.0, hold_duration_seconds=3600.0,
            confidence_at_entry=0.8, verdict_at_entry=0.7,
        )
        defaults.update(overrides)
        return TradeOutcome(**defaults)

    def test_profitable_trade_positive_reward(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        outcome = self._make_outcome(pnl=500.0)
        reward = rf.compute(outcome)
        assert reward.pnl_reward > 0
        assert reward.total_reward > 0

    def test_loss_trade_negative_reward(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        outcome = self._make_outcome(pnl=-300.0, exit_price=70.0)
        reward = rf.compute(outcome)
        assert reward.pnl_reward < 0
        assert reward.total_reward < 0

    def test_reward_bounded(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        outcome = self._make_outcome(pnl=99999.0)
        reward = rf.compute(outcome)
        assert -1.0 <= reward.total_reward <= 1.0

    def test_zero_pnl(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        outcome = self._make_outcome(pnl=0.0, exit_price=100.0)
        reward = rf.compute(outcome)
        assert reward.pnl_reward == 0.0

    def test_confidence_alignment_high(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        good = self._make_outcome(pnl=100.0, confidence_at_entry=0.95)
        bad = self._make_outcome(pnl=100.0, confidence_at_entry=0.3)
        r_good = rf.compute(good)
        r_bad = rf.compute(bad)
        assert r_good.confidence_alignment > r_bad.confidence_alignment

    def test_duration_penalty(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction(max_duration_seconds=100.0, duration_penalty_rate=0.01)
        short = self._make_outcome(hold_duration_seconds=50.0)
        long = self._make_outcome(hold_duration_seconds=2000.0)
        r_short = rf.compute(short)
        r_long = rf.compute(long)
        assert r_long.duration_penalty > r_short.duration_penalty


# ── DatasetBuilder ──────────────────────────────────────────────────────────


class TestDatasetBuilder:
    def test_add_from_trade(self):
        from core.trading.dataset import DatasetBuilder

        builder = DatasetBuilder()
        ex = builder.add_from_trade(
            symbol="AAPL", side="buy", entry_price=100.0, qty=10,
            verdict=0.8, confidence=0.75,
            expert_signals={"pennylab": 0.85, "crisis": 0.3},
            pnl=50.0, reward=0.6,
        )
        assert "AAPL" in ex.instruction
        assert ex.reward == 0.6
        assert builder.count == 1

    def test_add_manual(self):
        from core.trading.dataset import DatasetBuilder

        builder = DatasetBuilder()
        ex = builder.add_manual(
            instruction="Should I buy AAPL?",
            context="Market is bullish",
            response="APPROVE BUY 10 AAPL at 150.0",
            reward=0.8,
        )
        assert ex.instruction == "Should I buy AAPL?"
        assert ex.source == "manual"

    def test_positive_negative_filters(self):
        from core.trading.dataset import DatasetBuilder

        builder = DatasetBuilder()
        builder.add_manual("q1", "c1", "r1", reward=0.5)
        builder.add_manual("q2", "c2", "r2", reward=-0.3)
        builder.add_manual("q3", "c3", "r3", reward=0.1)
        assert len(builder.get_positive_examples()) == 2
        assert len(builder.get_negative_examples()) == 1

    def test_to_jsonl(self):
        from core.trading.dataset import DatasetBuilder

        with tempfile.TemporaryDirectory() as tmp:
            builder = DatasetBuilder(output_dir=tmp)
            builder.add_manual("q1", "c1", "r1", reward=0.5)
            builder.add_manual("q2", "c2", "r2", reward=-0.2)
            path = builder.to_jsonl()

            assert os.path.exists(path)
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 2
            row = json.loads(lines[0])
            assert "instruction" in row
            assert "response" in row
            assert "reward" in row

    def test_to_jsonl_custom_path(self):
        from core.trading.dataset import DatasetBuilder

        with tempfile.TemporaryDirectory() as tmp:
            builder = DatasetBuilder()
            builder.add_manual("q", "c", "r")
            custom = os.path.join(tmp, "custom.jsonl")
            path = builder.to_jsonl(filepath=custom)
            assert path == custom
            assert os.path.exists(custom)

    def test_clear(self):
        from core.trading.dataset import DatasetBuilder

        builder = DatasetBuilder()
        builder.add_manual("q", "c", "r")
        builder.clear()
        assert builder.count == 0

    def test_profitable_trade_approves(self):
        from core.trading.dataset import DatasetBuilder

        builder = DatasetBuilder()
        ex = builder.add_from_trade(
            symbol="AAPL", side="buy", entry_price=100.0, qty=10,
            verdict=0.8, confidence=0.75,
            expert_signals={}, pnl=50.0, reward=0.6,
        )
        assert "APPROVE" in ex.response

    def test_losing_trade_rejects(self):
        from core.trading.dataset import DatasetBuilder

        builder = DatasetBuilder()
        ex = builder.add_from_trade(
            symbol="AAPL", side="buy", entry_price=100.0, qty=10,
            verdict=0.3, confidence=0.4,
            expert_signals={}, pnl=-100.0, reward=-0.4,
        )
        assert "REJECT" in ex.response


# ── LoRATrainer ─────────────────────────────────────────────────────────────


class TestLoRATrainerConfig:
    def test_defaults(self):
        from core.trading.training import LoRATrainer, TrainingConfig

        trainer = LoRATrainer()
        assert trainer.config.model_name == "Qwen/Qwen2.5-1.5B-Instruct"
        assert trainer.config.lora_r == 16
        assert trainer.config.num_epochs == 3

    def test_custom_config(self):
        from core.trading.training import LoRATrainer, TrainingConfig

        config = TrainingConfig(lora_r=8, num_epochs=1)
        trainer = LoRATrainer(config=config)
        assert trainer.config.lora_r == 8


class TestLoRATrainerCheckDeps:
    def test_check_dependencies(self):
        from core.trading.training import LoRATrainer

        trainer = LoRATrainer()
        missing = trainer.check_dependencies()
        # In this environment, torch/transformers/peft/trl are installed
        assert isinstance(missing, list)


class TestLoRATrainerTrain:
    def test_missing_dataset_returns_error(self):
        from core.trading.training import LoRATrainer

        trainer = LoRATrainer()
        result = trainer.train_from_jsonl("/nonexistent/path.jsonl")
        assert result.success is False
        assert "not found" in result.error

    def test_empty_dataset_returns_error(self):
        from core.trading.training import LoRATrainer

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.jsonl")
            with open(path, "w") as f:
                f.write("")
            trainer = LoRATrainer()
            result = trainer.train_from_jsonl(path)
            assert result.success is False
            assert "No valid samples" in result.error

    def test_load_dataset_valid(self):
        from core.trading.training import LoRATrainer

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({"instruction": "q", "response": "r"}) + "\n")
                f.write(json.dumps({"instruction": "q2", "response": "r2"}) + "\n")
            trainer = LoRATrainer()
            samples = trainer._load_dataset(path)
            assert len(samples) == 2
            assert samples[0]["instruction"] == "q"

    def test_load_dataset_skips_invalid(self):
        from core.trading.training import LoRATrainer

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mixed.jsonl")
            with open(path, "w") as f:
                f.write('{"instruction": "q", "response": "r"}\n')
                f.write("not json\n")
                f.write('{"wrong": "keys"}\n')
                f.write('{"instruction": "q2", "response": "r2"}\n')
            trainer = LoRATrainer()
            samples = trainer._load_dataset(path)
            assert len(samples) == 2


# ── Integration: Reward → Dataset → JSONL ───────────────────────────────────


class TestRewardDatasetIntegration:
    def test_reward_to_dataset(self):
        from core.trading.dataset import DatasetBuilder
        from core.trading.reward import RewardFunction, TradeOutcome

        rf = RewardFunction()
        builder = DatasetBuilder()

        outcome = TradeOutcome(
            symbol="AAPL", side="buy", entry_price=100.0, exit_price=110.0,
            qty=10, pnl=100.0, hold_duration_seconds=3600.0,
            confidence_at_entry=0.8, verdict_at_entry=0.7,
        )
        reward = rf.compute(outcome)

        ex = builder.add_from_trade(
            symbol="AAPL", side="buy", entry_price=100.0, qty=10,
            verdict=0.7, confidence=0.8,
            expert_signals={"pennylab": 0.85},
            pnl=100.0, reward=reward.total_reward,
        )
        assert ex.reward > 0
        assert "APPROVE" in ex.response

        with tempfile.TemporaryDirectory() as tmp:
            path = builder.to_jsonl(filepath=os.path.join(tmp, "test.jsonl"))
            assert os.path.exists(path)
