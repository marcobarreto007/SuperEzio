"""Smoke tests — F51Engine.run() pipeline deterministico."""

from f51.graph import F51Engine, Graph, Node, Context, NodeResult


class TestNodeResult:
    def test_ok(self):
        nr = NodeResult(
            node="test",
            value=0.5,
            confidence=0.9,
            evidence={"src": "test"},
            error="",
            elapsed_ms=10,
        )
        assert nr.ok is True

    def test_not_ok(self):
        nr = NodeResult(
            node="test",
            value=None,
            confidence=0.0,
            evidence={},
            error="failed",
            elapsed_ms=10,
        )
        assert nr.ok is False


class TestContext:
    def test_add_and_get(self):
        ctx = Context(input="hello", domain="math")
        nr = NodeResult(node="n1", value=0.5, confidence=0.8, evidence={}, error="", elapsed_ms=5)
        ctx.add("n1", nr)
        assert ctx.get("n1") is nr
        assert ctx.get("nonexistent") is None

    def test_factor(self):
        ctx = Context(input="test", domain="math")
        nr = NodeResult(node="n1", value=0.7, confidence=0.9, evidence={}, error="", elapsed_ms=5)
        ctx.add("n1", nr)
        v = ctx.factor("n1", "value")
        assert v == 0.7

    def test_factor_missing(self):
        ctx = Context(input="test", domain="math")
        assert ctx.factor("nonexistent", "value") == 0.0

    def test_elapsed(self):
        ctx = Context(input="test", domain="math")
        assert ctx.elapsed >= 0


def _make_node_result(value, node="test", confidence=1.0):
    return NodeResult(
        node=node,
        value=value,
        confidence=confidence,
        evidence={},
        error="",
        elapsed_ms=1.0,
    )


class TestGraph:
    def test_empty_graph(self):
        g = Graph()
        ctx = g.execute("test", domain="math")
        assert isinstance(ctx, Context)
        assert ctx.input == "test"

    def test_single_node(self):
        g = Graph()
        g.add(
            Node(
                name="double",
                fn=lambda ctx: _make_node_result(float(len(str(ctx.input)) * 2), node="double"),
            )
        )
        ctx = g.execute("hello", domain="math")
        assert ctx.get("double").value == 10.0

    def test_dependency_chain(self):
        g = Graph()
        g.add(
            Node(
                name="len",
                fn=lambda ctx: _make_node_result(float(len(str(ctx.input))), node="len"),
            )
        )
        g.add(
            Node(
                name="double",
                fn=lambda ctx: _make_node_result(ctx.get("len").value * 2, node="double"),
                depends_on=["len"],
            )
        )
        ctx = g.execute("hello", domain="math")
        assert ctx.get("len").value == 5.0
        assert ctx.get("double").value == 10.0

    def test_error_captured(self):
        def boom(ctx):
            raise ValueError("fail")

        g = Graph()
        g.add(Node(name="bomb", fn=boom))
        ctx = g.execute("test", domain="math")
        nr = ctx.get("bomb")
        assert not nr.ok
        assert "fail" in nr.error


class TestF51EngineSmoke:
    """Smoke tests — F51Engine.run() com grafo default deterministico."""

    REQUIRED_KEYS = {
        "confidence",
        "threshold",
        "passed",
        "expand_compute",
        "factors",
        "nodes",
        "evidence",
        "elapsed_ms",
    }

    def test_run_string_input(self):
        engine = F51Engine()
        result = engine.run("analyze this stock", domain="math")
        for key in self.REQUIRED_KEYS:
            assert key in result, f"missing key: {key}"
        assert isinstance(result["confidence"], float)
        assert isinstance(result["threshold"], float)
        assert isinstance(result["passed"], bool)
        assert isinstance(result["expand_compute"], bool)
        assert isinstance(result["elapsed_ms"], (int, float))

    def test_run_dict_input(self):
        engine = F51Engine()
        result = engine.run(
            {"ticker": "AAPL", "features": {"price": 187, "rsi_14": 58}},
            domain="trading",
        )
        for key in self.REQUIRED_KEYS:
            assert key in result, f"missing key: {key}"
        assert 0.0 <= result["confidence"] <= 1.0
        assert 0.0 <= result["threshold"] <= 1.0
        assert isinstance(result["nodes"], dict)
        assert isinstance(result["evidence"], dict)

    def test_run_different_domains(self):
        engine = F51Engine()
        for domain in ("trading", "math", "fraud", "crisis", "default"):
            result = engine.run("test", domain=domain)
            assert result["threshold"] > 0
            assert result["elapsed_ms"] >= 0

    def test_run_idempotent(self):
        engine = F51Engine()
        r1 = engine.run("same input text", domain="math")
        r2 = engine.run("same input text", domain="math")
        assert r1["confidence"] == r2["confidence"]
        assert r1["passed"] == r2["passed"]

    def test_factors_dict(self):
        engine = F51Engine()
        result = engine.run("test", domain="math")
        assert isinstance(result["factors"], dict)
        if result["factors"]:
            for v in result["factors"].values():
                assert isinstance(v, (int, float))
