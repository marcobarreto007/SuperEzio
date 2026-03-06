"""Smoke tests — PennyLab experts, scoring, veracity gate (deterministico, sem rede)."""

import pytest
from experts.pennylab.schemas import (
    SignalInput,
    PennylabScores,
    PennylabReport,
    Decision,
    DataQuality,
)
from experts.pennylab.experts import (
    VolumeSpikeExpert,
    WhalePrintExpert,
    PumpDumpExpert,
    LiquidityRiskExpert,
    PennylabVeracityGate,
)
from experts.pennylab.scoring import (
    compute_scores,
    compute_confidence,
    make_decision,
    analyze,
)
from experts.pennylab.mathcore_adapter import score_to_alert, build_mathcore_verdict
from experts.pennylab.config import THRESHOLDS


def _signal(**kwargs):
    defaults = {"ticker": "TEST"}
    defaults.update(kwargs)
    return SignalInput(**defaults)


class TestVolumeSpikeExpert:
    def test_missing_data(self):
        expert = VolumeSpikeExpert()
        result = expert.evaluate(_signal())
        assert result.score == 0.0
        assert result.label == "INDISPONÍVEL"

    def test_zero_avg_volume(self):
        expert = VolumeSpikeExpert()
        result = expert.evaluate(_signal(volume=1000, avg_volume_10d=0))
        assert result.score == 0.0

    def test_normal_volume(self):
        expert = VolumeSpikeExpert()
        result = expert.evaluate(_signal(volume=10000, avg_volume_10d=10000))
        assert result.label == "NORMAL"
        assert result.score == 0.10

    def test_moderate_spike(self):
        expert = VolumeSpikeExpert()
        result = expert.evaluate(_signal(volume=50000, avg_volume_10d=20000))
        assert result.label == "MODERADO"
        assert result.score == 0.40

    def test_high_spike(self):
        expert = VolumeSpikeExpert()
        result = expert.evaluate(_signal(volume=50000, avg_volume_10d=8000))
        assert result.label == "ALTO"
        assert result.score == 0.70

    def test_extreme_spike(self):
        expert = VolumeSpikeExpert()
        result = expert.evaluate(_signal(volume=100000, avg_volume_10d=1000))
        assert result.label == "EXTREMO"
        assert result.score == 0.90

    def test_high_spike_has_warning(self):
        expert = VolumeSpikeExpert()
        result = expert.evaluate(_signal(volume=50000, avg_volume_10d=8000))
        evidence_str = " ".join(result.evidence)
        assert "anômalo" in evidence_str


class TestWhalePrintExpert:
    def test_no_data(self):
        expert = WhalePrintExpert()
        result = expert.evaluate(_signal())
        assert result.score == 0.0
        assert result.label == "INDISPONÍVEL"

    def test_micro_float_penny_price_high_volume(self):
        expert = WhalePrintExpert()
        result = expert.evaluate(
            _signal(
                shares_float=1_000_000,
                price=2.50,  # MICRO float, penny price
                volume=100_000,
                avg_volume_10d=10_000,  # 10x spike
            )
        )
        assert result.label in ("FORTE", "PROVÁVEL")
        assert result.score > 0.50

    def test_normal_conditions(self):
        expert = WhalePrintExpert()
        result = expert.evaluate(
            _signal(
                shares_float=50_000_000,
                price=25.0,
                volume=10000,
                avg_volume_10d=10000,
            )
        )
        assert result.label == "IMPROVÁVEL"
        assert result.score < 0.30

    def test_no_float_only_volume_price(self):
        expert = WhalePrintExpert()
        result = expert.evaluate(
            _signal(
                price=0.50,
                volume=200_000,
                avg_volume_10d=10_000,
            )
        )
        assert result.label != "INDISPONÍVEL"
        assert result.score > 0

    def test_forte_has_whale_warning(self):
        expert = WhalePrintExpert()
        result = expert.evaluate(
            _signal(
                shares_float=1_000_000,
                price=0.80,
                volume=200_000,
                avg_volume_10d=15_000,
            )
        )
        if result.label in ("FORTE", "PROVÁVEL"):
            evidence_str = " ".join(result.evidence)
            assert "baleia" in evidence_str


class TestPumpDumpExpert:
    def test_no_data(self):
        expert = PumpDumpExpert()
        result = expert.evaluate(_signal())
        assert result.score == 0.0

    def test_extreme_pump(self):
        expert = PumpDumpExpert()
        result = expert.evaluate(
            _signal(
                price=4.00,
                prev_close=1.00,  # 300% increase
                volume=200_000,
                avg_volume_10d=10_000,  # 20x
                rsi_14=90,
            )
        )
        assert result.score > 0.70
        assert result.phase == "PUMP"

    def test_dump_phase(self):
        expert = PumpDumpExpert()
        result = expert.evaluate(
            _signal(
                price=10.0,
                prev_close=30.0,  # -66%
                volume=200_000,
                avg_volume_10d=15_000,  # 13x → 0.30
                rsi_14=30,
            )
        )
        assert result.phase == "DUMP"

    def test_normal(self):
        expert = PumpDumpExpert()
        result = expert.evaluate(
            _signal(
                price=10.0,
                prev_close=9.80,  # ~2%
                volume=5000,
                avg_volume_10d=5000,
                rsi_14=50,
            )
        )
        assert result.score < 0.30
        assert result.phase == "INCERTO"

    def test_external_signals_contribute(self):
        expert = PumpDumpExpert()
        result_no_ext = expert.evaluate(
            _signal(
                price=15.0,
                prev_close=10.0,
                volume=50000,
                avg_volume_10d=10000,
                rsi_14=75,
            )
        )
        result_with_ext = expert.evaluate(
            _signal(
                price=15.0,
                prev_close=10.0,
                volume=50000,
                avg_volume_10d=10000,
                rsi_14=75,
                external_signals=[
                    "forum pump",
                    "newsletter alert",
                    "social media hype",
                ],
            )
        )
        assert result_with_ext.score >= result_no_ext.score

    def test_high_score_has_warning(self):
        expert = PumpDumpExpert()
        result = expert.evaluate(
            _signal(
                price=4.0,
                prev_close=1.0,
                volume=200000,
                avg_volume_10d=10000,
                rsi_14=95,
            )
        )
        if result.score >= 0.60:
            evidence_str = " ".join(result.evidence)
            assert "pump-and-dump" in evidence_str


class TestLiquidityRiskExpert:
    def test_no_data(self):
        expert = LiquidityRiskExpert()
        result = expert.evaluate(_signal())
        assert result.score == 0.0
        assert result.label == "INDISPONÍVEL"

    def test_critical_spread(self):
        expert = LiquidityRiskExpert()
        result = expert.evaluate(
            _signal(
                bid=1.00,
                ask=1.15,  # 15% spread
                volume=50000,  # critical volume
                shares_float=2_000_000,  # micro float
            )
        )
        assert result.label in ("CRÍTICO", "ALTO")
        assert result.score >= 0.60

    def test_acceptable_liquidity(self):
        expert = LiquidityRiskExpert()
        result = expert.evaluate(
            _signal(
                bid=10.00,
                ask=10.10,  # 1% spread
                volume=5_000_000,  # adequate
                shares_float=50_000_000,  # OK float
            )
        )
        assert result.label == "BAIXO"
        assert result.score < 0.20

    def test_missing_bid_only_volume_float(self):
        expert = LiquidityRiskExpert()
        result = expert.evaluate(
            _signal(
                ask=10.15,
                volume=150000,
                shares_float=10_000_000,
            )
        )
        assert result.label != "INDISPONÍVEL"  # has some data
        assert result.score >= 0

    def test_critical_has_warning(self):
        expert = LiquidityRiskExpert()
        result = expert.evaluate(
            _signal(
                bid=0.90,
                ask=1.20,
                volume=80000,
                shares_float=3_000_000,
            )
        )
        if result.score >= 0.75:
            evidence_str = " ".join(result.evidence)
            assert "LIQUIDEZ CRÍTICO" in evidence_str


class TestPennylabVeracityGate:
    def test_clean_signal(self):
        gate = PennylabVeracityGate()
        result = gate.check(
            _signal(
                price=10.0,
                volume=50000,
                bid=10.0,
                ask=10.05,
                data_quality=DataQuality.REAL,
            )
        )
        assert result.passed is True
        assert result.confidence == 1.0

    def test_negative_price_violation(self):
        gate = PennylabVeracityGate()
        result = gate.check(_signal(price=-5.0, volume=10000))
        assert result.passed is False
        assert result.confidence == 0.0
        assert any("price" in v for v in result.violations)

    def test_negative_volume_violation(self):
        gate = PennylabVeracityGate()
        result = gate.check(_signal(price=10.0, volume=-100))
        assert result.passed is False
        assert any("volume" in v for v in result.violations)

    def test_bid_greater_than_ask(self):
        gate = PennylabVeracityGate()
        result = gate.check(_signal(bid=10.50, ask=10.00))
        assert result.passed is False
        assert any(
            "bid" in v.lower() or "invertido" in v.lower() for v in result.violations
        )

    def test_extreme_price_change(self):
        gate = PennylabVeracityGate()
        result = gate.check(_signal(price=500.0, prev_close=1.0))
        assert result.passed is False

    def test_rsi_out_of_range(self):
        gate = PennylabVeracityGate()
        result_low = gate.check(_signal(rsi_14=-5))
        assert result_low.passed is False
        result_high = gate.check(_signal(rsi_14=150))
        assert result_high.passed is False

    def test_unavailable_data_quality_gets_warning(self):
        gate = PennylabVeracityGate()
        result = gate.check(_signal(data_quality=DataQuality.UNAVAILABLE))
        assert result.confidence < 1.0  # should be 0.6 (has warning)
        assert result.passed is True  # but still passes
        assert len(result.warnings) > 0

    def test_manual_no_source_warning(self):
        gate = PennylabVeracityGate()
        result = gate.check(_signal(data_quality=DataQuality.MANUAL, source=""))
        assert result.confidence < 1.0
        assert any(
            "manual" in w.lower() or "source" in w.lower() for w in result.warnings
        )


class TestComputeScores:
    def test_empty_signal(self):
        scores, evidence = compute_scores(_signal())
        assert isinstance(scores, PennylabScores)
        assert scores.whale_suspicion >= 0
        assert scores.expected_loss >= 0
        assert len(evidence) > 0  # experts generate evidence even on missing data

    def test_full_signal(self):
        scores, evidence = compute_scores(
            _signal(
                price=3.50,
                prev_close=2.00,
                volume=200000,
                avg_volume_10d=20000,
                bid=3.40,
                ask=3.60,
                shares_float=5_000_000,
                rsi_14=80,
            )
        )
        assert all(
            0.0 <= v <= 1.0
            for v in [
                scores.whale_suspicion,
                scores.pump_probability,
                scores.trap_risk,
                scores.liquidity_risk,
                scores.expected_loss,
            ]
        )
        assert len(evidence) > 0


class TestComputeConfidence:
    def test_empty_signal(self):
        confidence = compute_confidence(_signal(), PennylabScores())
        assert confidence == pytest.approx(0.0, abs=0.01)

    def test_full_signal(self):
        signal = _signal(
            price=10.0,
            volume=50000,
            avg_volume_10d=40000,
            bid=9.95,
            ask=10.05,
            shares_float=10_000_000,
            prev_close=9.90,
            data_quality=DataQuality.REAL,
        )
        confidence = compute_confidence(signal, PennylabScores())
        assert confidence > 0.8  # lots of data

    def test_manual_discount(self):
        signal_full = _signal(
            price=10.0,
            volume=50000,
            avg_volume_10d=40000,
            bid=9.95,
            ask=10.05,
            shares_float=10_000_000,
            prev_close=9.90,
            data_quality=DataQuality.MANUAL,
        )
        confidence = compute_confidence(signal_full, PennylabScores())
        # 7/7 * 0.85 = 0.85
        assert confidence == pytest.approx(0.85, abs=0.01)


class TestMakeDecision:
    def test_veracity_failed(self):
        decision, risks, entry, exits = make_decision(
            PennylabScores(),
            confidence=0.8,
            veracity_passed=False,
            signal=_signal(),
        )
        assert decision == Decision.NO_TRADE
        assert len(risks) > 0

    def test_low_confidence_watch_only(self):
        decision, risks, entry, exits = make_decision(
            PennylabScores(),
            confidence=0.1,
            veracity_passed=True,
            signal=_signal(),
        )
        assert decision == Decision.WATCH_ONLY

    def test_critical_liquidity_no_trade(self):
        decision, risks, entry, exits = make_decision(
            PennylabScores(liquidity_risk=0.85),
            confidence=0.8,
            veracity_passed=True,
            signal=_signal(),
        )
        assert decision == Decision.NO_TRADE

    def test_trap_pump_no_trade(self):
        decision, risks, entry, exits = make_decision(
            PennylabScores(pump_probability=0.80, trap_risk=0.85),
            confidence=0.8,
            veracity_passed=True,
            signal=_signal(),
        )
        assert decision == Decision.NO_TRADE

    def test_whale_micro_entry(self):
        decision, risks, entry, exits = make_decision(
            PennylabScores(whale_suspicion=0.75, trap_risk=0.20, liquidity_risk=0.20),
            confidence=0.5,
            veracity_passed=True,
            signal=_signal(price=3.50),
        )
        assert decision == Decision.MICRO_ENTRY

    def test_whale_paper_trade(self):
        decision, risks, entry, exits = make_decision(
            PennylabScores(whale_suspicion=0.80, trap_risk=0.30, liquidity_risk=0.30),
            confidence=0.5,
            veracity_passed=True,
            signal=_signal(price=10.0),
        )
        assert decision == Decision.PAPER_TRADE

    def test_clean_setup_bullish(self):
        decision, risks, entry, exits = make_decision(
            PennylabScores(
                whale_suspicion=0.10,
                pump_probability=0.10,
                trap_risk=0.10,
                liquidity_risk=0.10,
                expected_loss=0.05,
            ),
            confidence=0.6,
            veracity_passed=True,
            signal=_signal(),
        )
        assert decision == Decision.BULLISH

    def test_elevated_risk_bearish(self):
        decision, risks, entry, exits = make_decision(
            PennylabScores(trap_risk=0.55, expected_loss=0.05),
            confidence=0.5,
            veracity_passed=True,
            signal=_signal(),
        )
        assert decision == Decision.BEARISH

    def test_default_watch_only(self):
        decision, risks, entry, exits = make_decision(
            PennylabScores(
                whale_suspicion=0.40,
                pump_probability=0.30,
                trap_risk=0.40,
                liquidity_risk=0.40,
                expected_loss=0.20,
            ),
            confidence=0.5,
            veracity_passed=True,
            signal=_signal(),
        )
        assert decision == Decision.WATCH_ONLY


class TestAnalyze:
    def test_minimal_signal(self):
        report = analyze(_signal())
        assert isinstance(report, PennylabReport)
        assert report.ticker == "TEST"
        assert report.decision in Decision
        assert report.confidence >= 0

    def test_full_signal_generates_complete_report(self):
        report = analyze(
            _signal(
                price=2.50,
                prev_close=2.00,
                volume=150000,
                avg_volume_10d=30000,
                bid=2.45,
                ask=2.55,
                shares_float=8_000_000,
                rsi_14=65,
                data_quality=DataQuality.MANUAL,
                source="manual-test",
            )
        )
        assert report.ticker == "TEST"
        assert report.decision in Decision
        assert len(report.evidence) > 0
        assert len(report.mathcore_verdict) > 0


class TestMathcoreAdapter:
    def test_score_to_alert_green(self):
        assert score_to_alert(0.10) in ("green", "yellow")

    def test_score_to_alert_black(self):
        assert score_to_alert(0.90) in ("red", "black")

    def test_score_to_alert_yellow(self):
        alert = score_to_alert(0.35)
        assert alert in ("green", "yellow")

    def test_build_mathcore_verdict(self):
        scores = PennylabScores(
            whale_suspicion=0.60,
            pump_probability=0.30,
            trap_risk=0.40,
            liquidity_risk=0.20,
            expected_loss=0.30,
        )
        verdict = build_mathcore_verdict(scores)
        assert "mathcore" in verdict
        assert "alert=" in verdict
        assert "dominant_risk=" in verdict


class TestThresholds:
    def test_all_thresholds_in_range(self):
        t = THRESHOLDS
        thresholds = [
            t.LIQUIDITY_NO_TRADE,
            t.TRAP_NO_TRADE,
            t.PUMP_NO_TRADE,
            t.BULLISH_MAX_WHALE,
            t.BULLISH_MAX_PUMP,
            t.BULLISH_MAX_TRAP,
            t.BULLISH_MAX_LIQUIDITY,
            t.BULLISH_MAX_EXPECTED_LOSS,
            t.BULLISH_MIN_CONFIDENCE,
            t.BEARISH_MIN_TRAP,
            t.BEARISH_MIN_EXPECTED_LOSS,
            t.WHALE_PAPER,
            t.TRAP_SAFE,
            t.LIQUIDITY_SAFE,
            t.MIN_REPORT_CONFIDENCE,
        ]
        for v in thresholds:
            assert 0.0 <= v <= 1.0


class TestPennylabScores:
    def test_default_scores(self):
        scores = PennylabScores()
        assert scores.whale_suspicion == 0.0
        assert scores.pump_probability == 0.0
        assert scores.trap_risk == 0.0
        assert scores.liquidity_risk == 0.0
        assert scores.expected_loss == 0.0

    def test_custom_scores(self):
        scores = PennylabScores(
            whale_suspicion=0.5,
            pump_probability=0.3,
            trap_risk=0.4,
            liquidity_risk=0.2,
            expected_loss=0.35,
        )
        assert scores.whale_suspicion == 0.5
        assert scores.expected_loss == 0.35


class TestPennylabReport:
    def test_minimal(self):
        report = PennylabReport(
            ticker="ABCD",
            decision=Decision.WATCH_ONLY,
            scores=PennylabScores(),
            confidence=0.1,
        )
        assert report.ticker == "ABCD"
        assert report.decision == Decision.WATCH_ONLY

    def test_bullish_report(self):
        report = PennylabReport(
            ticker="SNDL",
            decision=Decision.BULLISH,
            scores=PennylabScores(
                whale_suspicion=0.10,
                pump_probability=0.05,
                trap_risk=0.10,
                liquidity_risk=0.15,
                expected_loss=0.05,
            ),
            confidence=0.75,
            evidence=["setup limpo"],
        )
        assert report.decision == Decision.BULLISH
        assert report.confidence == 0.75
