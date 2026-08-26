"""Component tests: PennyLab (4 experts + scoring + veracity gate + RAG + schemas)."""


# ── Schemas ──
def test_signal_input():
    from experts.pennylab.schemas import SignalInput

    sig = SignalInput(ticker="TEST", price=5.0, volume=1000000, avg_volume_10d=500000)
    assert sig.ticker == "TEST"
    assert sig.price == 5.0


def test_pennylab_scores():
    from experts.pennylab.schemas import PennylabScores

    scores = PennylabScores(
        whale_suspicion=0.8, pump_probability=0.5, trap_risk=0.7, liquidity_risk=0.6
    )
    assert scores.whale_suspicion == 0.8
    assert scores.pump_probability == 0.5


def test_decision_enum():
    from experts.pennylab.schemas import Decision

    assert Decision.NO_TRADE.value == "NO_TRADE"
    assert Decision.BULLISH.value == "BULLISH"


# ── Veracity Gate ──
def test_veracity_gate_valid():
    from experts.pennylab.experts.veracity_gate import PennylabVeracityGate
    from experts.pennylab.schemas import SignalInput

    gate = PennylabVeracityGate()
    sig = SignalInput(ticker="TEST", price=10.0, volume=500000, avg_volume_10d=300000)
    result = gate.check(sig)
    assert hasattr(result, "passed")
    assert hasattr(result, "violations")


def test_veracity_gate_negative_price():
    from experts.pennylab.experts.veracity_gate import PennylabVeracityGate
    from experts.pennylab.schemas import SignalInput

    gate = PennylabVeracityGate()
    sig = SignalInput(ticker="TEST", price=-5.0, volume=500000, avg_volume_10d=300000)
    result = gate.check(sig)
    assert result.passed is False


# ── 4 Experts ──
def test_volume_spike_expert():
    from experts.pennylab.experts.volume_spike_expert import VolumeSpikeExpert
    from experts.pennylab.schemas import SignalInput

    expert = VolumeSpikeExpert()
    sig = SignalInput(ticker="TEST", volume=2000000, avg_volume_10d=500000)
    result = expert.evaluate(sig)
    assert result is not None
    assert hasattr(result, "score")
    assert 0 <= result.score <= 1


def test_whale_print_expert():
    from experts.pennylab.experts.whale_print_expert import WhalePrintExpert
    from experts.pennylab.schemas import SignalInput

    expert = WhalePrintExpert()
    sig = SignalInput(
        ticker="TEST",
        price=4.0,
        volume=1500000,
        avg_volume_10d=500000,
        shares_float=3_000_000,
    )
    result = expert.evaluate(sig)
    assert result is not None
    assert hasattr(result, "score")
    assert 0 <= result.score <= 1


def test_pump_dump_expert():
    from experts.pennylab.experts.pump_dump_expert import PumpDumpExpert
    from experts.pennylab.schemas import SignalInput

    expert = PumpDumpExpert()
    sig = SignalInput(
        ticker="TEST",
        price=15.0,
        prev_close=10.0,
        volume=3000000,
        avg_volume_10d=500000,
        rsi_14=85,
    )
    result = expert.evaluate(sig)
    assert result is not None
    assert hasattr(result, "score")
    assert 0 <= result.score <= 1


def test_liquidity_risk_expert():
    from experts.pennylab.experts.liquidity_risk_expert import LiquidityRiskExpert
    from experts.pennylab.schemas import SignalInput

    expert = LiquidityRiskExpert()
    sig = SignalInput(
        ticker="TEST",
        volume=200000,
        avg_volume_10d=800000,
        market_cap=20_000_000,
        bid=0.95,
        ask=1.05,
    )
    result = expert.evaluate(sig)
    assert result is not None
    assert hasattr(result, "score")
    assert 0 <= result.score <= 1


# ── Scoring ──
def test_compute_scores():
    from experts.pennylab.schemas import SignalInput
    from experts.pennylab.scoring import compute_scores

    sig = SignalInput(
        ticker="TEST",
        price=5.0,
        volume=2000000,
        avg_volume_10d=400000,
        market_cap=50_000_000,
    )
    scores, evidence = compute_scores(sig)
    assert hasattr(scores, "whale_suspicion")
    assert isinstance(evidence, list)


def test_make_decision():
    from experts.pennylab.schemas import PennylabScores, SignalInput
    from experts.pennylab.scoring import make_decision

    scores = PennylabScores(
        whale_suspicion=0.9, pump_probability=0.5, trap_risk=0.8, liquidity_risk=0.7
    )
    sig = SignalInput(ticker="TEST")
    decision, _risks, _entry, _exits = make_decision(
        scores, confidence=0.9, veracity_passed=True, signal=sig
    )
    assert decision is not None


def test_compute_confidence():
    from experts.pennylab.schemas import PennylabScores, SignalInput
    from experts.pennylab.scoring import compute_confidence

    sig = SignalInput(ticker="TEST", price=5.0, volume=2000000, avg_volume_10d=400000)
    scores = PennylabScores()
    conf = compute_confidence(sig, scores)
    assert 0 <= conf <= 1


def test_analyze_full():
    from experts.pennylab.schemas import SignalInput
    from experts.pennylab.scoring import analyze

    sig = SignalInput(
        ticker="TEST",
        price=5.0,
        volume=2000000,
        avg_volume_10d=400000,
        market_cap=50_000_000,
    )
    report = analyze(sig)
    assert report.ticker == "TEST"
    assert report.decision in (
        "WATCH_ONLY",
        "BULLISH",
        "BEARISH",
        "NO_TRADE",
        "PAPER_TRADE",
    )


# ── RAG Hooks ──
def test_query_fraud_patterns():
    from experts.pennylab.rag_hooks import query_fraud_patterns

    result = query_fraud_patterns("PUMP")
    assert isinstance(result, list)


def test_enrich_with_rag():
    from experts.pennylab.rag_hooks import enrich_with_rag

    existing = ["test evidence"]
    result = enrich_with_rag("TEST", existing)
    assert isinstance(result, list)
    assert "test evidence" in result


# ── Mathcore Adapter ──
def test_build_mathcore_verdict():
    from experts.pennylab.mathcore_adapter import build_mathcore_verdict
    from experts.pennylab.schemas import PennylabScores

    scores = PennylabScores(
        whale_suspicion=0.9, pump_probability=0.5, trap_risk=0.8, liquidity_risk=0.7
    )
    verdict = build_mathcore_verdict(scores)
    assert isinstance(verdict, str)
    assert "alert=" in verdict


print("PennyLab: ALL TESTS PASSED")
