"""Tests for reward scoring and dataset builder."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# â”€â”€ RewardFunction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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

        defaults = {
            "symbol": "AAPL",
            "side": "buy",
            "entry_price": 100.0,
            "exit_price": 110.0,
            "qty": 10,
            "pnl": 100.0,
            "hold_duration_seconds": 3600.0,
            "confidence_at_entry": 0.8,
            "verdict_at_entry": 0.7,
        }
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

    def test_confident_wrong_forecast_is_penalized_more(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        high_confidence_loss = self._make_outcome(pnl=-100.0, confidence_at_entry=0.95)
        low_confidence_loss = self._make_outcome(pnl=-100.0, confidence_at_entry=0.20)
        high = rf.compute(high_confidence_loss)
        low = rf.compute(low_confidence_loss)
        assert high.confidence_alignment < low.confidence_alignment

    def test_missing_ex_ante_risk_is_unknown_not_one_percent_default(self):
        from core.trading.reward import RewardFunction

        reward = RewardFunction().compute(self._make_outcome(risk_at_entry=None))
        assert reward.risk_adjusted_reward == 0.0

    def test_pnl_reward_is_scale_invariant(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        small = rf.compute(
            self._make_outcome(entry_price=10.0, qty=10, pnl=10.0, risk_at_entry=5.0)
        )
        large = rf.compute(
            self._make_outcome(entry_price=100.0, qty=100, pnl=1000.0, risk_at_entry=500.0)
        )
        assert small.pnl_reward == large.pnl_reward

    def test_uncalibrated_probability_absence_has_neutral_alignment(self):
        from core.trading.reward import RewardFunction

        reward = RewardFunction().compute(self._make_outcome(confidence_at_entry=None))
        assert reward.confidence_alignment == 0.0

    def test_duration_penalty(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction(max_duration_seconds=100.0, duration_penalty_rate=0.01)
        short = self._make_outcome(hold_duration_seconds=50.0, pnl=-10.0)
        long = self._make_outcome(hold_duration_seconds=2000.0, pnl=-10.0)
        r_short = rf.compute(short)
        r_long = rf.compute(long)
        assert r_long.duration_penalty > r_short.duration_penalty

    def test_coverage_penalty_all_present(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        # Mock pipeline state where only price and technical are present
        state = {"data": {"price": {"value": 100}, "technicals": {"rsi": 50}}, "ticker": "AAPL"}
        # Response mentions both modules
        text = "The close price is 100, and the MACD index shows bullish trend."
        outcome = self._make_outcome(ceo_response_text=text, pipeline_state=state)
        reward = rf.compute(outcome)
        assert reward.coverage_penalty == 0.0

    def test_coverage_penalty_missing(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction(coverage_penalty_weight=0.2)
        # Mock pipeline state where price and technical are present
        state = {"data": {"price": {"value": 100}, "technicals": {"rsi": 50}}, "ticker": "AAPL"}
        # Response only mentions price terms, misses technical terms
        text = "The close price is 100."
        outcome = self._make_outcome(ceo_response_text=text, pipeline_state=state)
        reward = rf.compute(outcome)
        # 1 module missing ("technical") -> penalty should be 1 * 0.2 = 0.2
        assert reward.coverage_penalty == 0.2

    def test_coverage_penalty_no_input(self):
        from core.trading.reward import RewardFunction

        rf = RewardFunction()
        outcome = self._make_outcome()  # No ceo_response_text or pipeline_state
        reward = rf.compute(outcome)
        assert reward.coverage_penalty == 0.0
