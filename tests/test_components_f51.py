"""Component tests: F51 Engine (graph, formulas, detectors, gates, scoring, memory)."""


# ── F51 Formulas ──
def test_decision_factors_validate():
    from src.f51.formulas import DecisionFactors

    factors = DecisionFactors(
        veracity=0.9,
        consensus=0.7,
        proxy_reward=0.6,
        robustness=0.5,
        uncertainty=0.2,
        danger=0.1,
    )
    factors.validate()  # nao deve explodir
    assert factors.veracity == 0.9


def test_unified_decision_clean():
    from src.f51.formulas import DecisionFactors, unified_decision

    factors = DecisionFactors(
        veracity=0.9,
        consensus=0.7,
        proxy_reward=0.6,
        robustness=0.5,
        uncertainty=0.2,
        danger=0.1,
    )
    result = unified_decision(factors)
    assert 0 <= result <= 1


def test_unified_decision_high_danger():
    from src.f51.formulas import DecisionFactors, unified_decision

    factors = DecisionFactors(
        veracity=0.5,
        consensus=0.5,
        proxy_reward=0.5,
        robustness=0.5,
        uncertainty=0.8,
        danger=0.95,
    )
    result = unified_decision(factors)
    assert 0 <= result <= 1


def test_combined_risk():
    from src.f51.formulas import combined_risk

    r = combined_risk(0.7, 0.6, 0.3)
    assert 0 <= r <= 1


def test_combined_risk_empty():
    from src.f51.formulas import combined_risk

    assert combined_risk() == 0.0


def test_proxy_reward():
    from src.f51.formulas import proxy_reward

    r = proxy_reward(consensus=0.8, critic=0.7, sanity=0.6)
    assert 0 <= r <= 1


def test_proxy_reward_with_ground_truth():
    from src.f51.formulas import proxy_reward

    r = proxy_reward(
        consensus=0.8,
        critic=0.7,
        sanity=0.6,
        ground_truth_bonus=1.0,
        has_ground_truth=True,
    )
    assert 0 <= r <= 1


def test_heuristic_uncertainty():
    from src.f51.formulas import heuristic_uncertainty

    u = heuristic_uncertainty(text="what is the market risk of this microcap?")
    assert 0 <= u <= 1


def test_heuristic_uncertainty_complex():
    from src.f51.formulas import heuristic_uncertainty

    u = heuristic_uncertainty(
        text="prove that for all positive integers the triangle congruence holds",
        numeric_features={
            "missing_data_ratio": 0.5,
            "volatility": 0.7,
            "data_points": 10,
        },
    )
    assert 0 <= u <= 1


def test_decision_threshold():
    from src.f51.formulas import decision_threshold

    assert decision_threshold("default") == 0.70
    assert decision_threshold("trading") == 0.75
    assert decision_threshold("math") == 0.85


def test_expand_budget():
    from src.f51.formulas import expand_budget

    assert expand_budget(0.5, "trading") is True
    assert expand_budget(0.9, "trading") is False


# ── F51 Graph + Engine ──
def test_graph_creation():
    from src.f51.graph import F51Engine

    engine = F51Engine()
    assert engine.graph is not None
    assert len(engine.graph.nodes) > 0


def test_node_creation():
    from src.f51.graph import Node

    node = Node(name="test", fn=lambda ctx: None)
    assert node.name == "test"


def test_context_creation():
    from src.f51.graph import Context

    ctx = Context(input={"ticker": "TEST"}, domain="trading")
    assert ctx.domain == "trading"


def test_f51_engine_run():
    from src.f51.graph import F51Engine

    engine = F51Engine()
    result = engine.run({"ticker": "TEST", "message": "analyze fraud"}, domain="default")
    assert isinstance(result, dict)
    for key in ("confidence", "threshold", "passed", "elapsed_ms"):
        assert key in result, f"Missing key: {key}"


def test_f51_engine_run_trading():
    from src.f51.graph import F51Engine

    engine = F51Engine()
    result = engine.run(
        {
            "ticker": "ABC",
            "message": "pump and dump check",
            "features": {
                "price": 2.0,
                "rsi_14": 85,
                "volume_z_score": 4.0,
                "daily_return": -0.05,
            },
        },
        domain="trading",
    )
    assert "factors" in result


# ── F51 Detectors ──
def test_spider_sense_creation():
    from src.f51.detectors import SpiderSense, TrapPattern

    ss = SpiderSense()
    assert len(ss.patterns) > 0
    assert isinstance(ss.patterns[0], TrapPattern)


def test_spider_sense_detect():
    from src.f51.detectors import SpiderSense

    ss = SpiderSense()
    text = "Guaranteed 200% return! All in leverage now! Insider says sell everything!"
    danger, alerts = ss.detect(text)
    assert isinstance(danger, float)
    assert 0 <= danger <= 1
    assert isinstance(alerts, list)


def test_spider_sense_clean():
    from src.f51.detectors import SpiderSense

    ss = SpiderSense()
    danger, alerts = ss.detect("AAPL reported earnings in line with expectations.")
    assert isinstance(danger, float)
    assert 0 <= danger <= 1


def test_trap_pattern_creation():
    from src.f51.detectors import TrapPattern

    tp = TrapPattern(name="test", regex=r"test", danger=0.5)
    assert tp.name == "test"
    assert tp.danger == 0.5


def test_difficulty_estimator():
    from src.f51.detectors import DifficultyEstimator

    estimator = DifficultyEstimator()
    u = estimator.estimate(text="analyze this stock")
    assert 0 <= u <= 1


def test_spider_sense_node_uses_real_danger_not_hardcoded():
    """Regressao 5.1: NodeResult do spider_sense no grafo default deve
    calcular confidence (float) e evidence['danger'] a partir do texto real,
    nao um valor fixo (era evidence={'danger': 1.0} sempre, e confidence
    recebia a lista de alerts por causa de um *unpack errado)."""
    from src.f51.graph import F51Engine

    engine = F51Engine()

    clean = engine.run({"features": {}, "message": "AAPL reported normal earnings."})
    fraud = engine.run(
        {"features": {}, "message": "guaranteed 100x return, buy now, all in leverage!"}
    )

    clean_node = clean["nodes"]["spider_sense"]
    fraud_node = fraud["nodes"]["spider_sense"]

    # confidence deve ser float (nao lista de alerts) e refletir o danger real
    assert isinstance(clean_node["confidence"], float)
    assert isinstance(fraud_node["confidence"], float)
    assert clean_node["confidence"] > fraud_node["confidence"]

    # evidence.danger deve variar com o input, nao ficar fixo em 1.0
    clean_danger = clean["evidence"]["spider_sense"]["danger"]
    fraud_danger = fraud["evidence"]["spider_sense"]["danger"]
    assert clean_danger < fraud_danger
    assert fraud_danger > 0.5


# ── F51 Gates ──
def test_veracity_gate():
    from src.f51.gates import VeracityGate

    gate = VeracityGate()
    result = gate.verify([], {})
    assert result.passed is True
    assert result.confidence == 1.0


def test_veracity_gate_mismatch():
    from src.f51.gates import VeracityGate

    gate = VeracityGate()
    claims = [("price", 10.0, "market"), ("volume", 1000000, "volume")]
    ground_truth = {"price": 5.0, "volume": 950000}
    result = gate.verify(claims, ground_truth)
    assert hasattr(result, "mismatches")


def test_adversarial_critic():
    from src.f51.gates import AdversarialCritic

    critic = AdversarialCritic()
    result = critic.evaluate_finance(
        {
            "market_cap": 30_000_000,
            "price": 15.0,
            "annual_volatility": 0.5,
            "var_95": -0.9,
            "hype_keyword_count": 5,
            "total_revenue": 500_000,
        }
    )
    assert hasattr(result, "confidence")
    assert 0 <= result.confidence <= 1


def test_adversarial_critic_llm_exception_fails_closed():
    """Regressao 5.4: erro no critique adversarial nao pode virar
    'tudo certo com confianca media' (fail-open). Deve falhar fechado:
    is_valid=False e confianca BAIXA, no espirito de f51_trade_gate.py
    ('fails CLOSED. If in doubt, BLOCK.')."""
    from src.f51.gates import AdversarialCritic

    class FailingLLM:
        def generate(self, **kwargs):
            raise RuntimeError("llm indisponivel")

    critic = AdversarialCritic(llm=FailingLLM())
    result = critic.critique("resposta qualquer", "problema qualquer")

    assert result.is_valid is False
    assert result.confidence <= 0.2
    assert result.errors


# ── F51 Scoring ──
def test_platinum_scorer():
    from src.f51.scoring import PlatinumScorer, Candidate

    scorer = PlatinumScorer()
    assert scorer is not None
    candidates = [
        Candidate(final="BUY", check_pass=0.8, refuted=False, confidence=0.9),
        Candidate(final="BUY", check_pass=0.7, refuted=False, confidence=0.85),
        Candidate(final="SELL", check_pass=0.5, refuted=True, confidence=0.3),
    ]
    score = scorer.score(candidates)
    assert 0 <= score <= 1


def test_platinum_scorer_empty():
    from src.f51.scoring import PlatinumScorer

    assert PlatinumScorer.score([]) == 0.0


def test_risk_engine():
    from src.f51.scoring import RiskEngine

    engine = RiskEngine()
    result = engine.evaluate({"price": 5.0, "volume": 1000000})
    assert isinstance(result, dict)
    assert "risk_score" in result


print("F51: ALL TESTS PASSED")
