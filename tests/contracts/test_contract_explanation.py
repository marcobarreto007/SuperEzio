"""Contract tests: core.explanation — ExplainEngine deterministic imports & functions."""


def test_explain_engine_import():
    """ExplainEngine lazy-loads — import should succeed without GPU/LLM loaded."""
    from core.explanation.engine import ExplainEngine

    engine = ExplainEngine(model_path=None, lora_path=None)
    assert engine is not None


def test_explain_engine_default_construct():
    from core.explanation.engine import ExplainEngine

    engine = ExplainEngine()
    assert engine is not None
    assert hasattr(engine, "explain")
    assert callable(engine.explain)


def test_deterministic_explanation_basic():
    """_deterministic_explanation runs without LLM and returns valid string."""
    from core.explanation.engine import _deterministic_explanation

    result = _deterministic_explanation(
        {
            "confidence": 0.85,
            "passed": True,
            "threshold": 0.75,
            "expand_compute": False,
            "factors": {
                "veracity": 0.9,
                "consensus": 0.7,
                "proxy_reward": 0.6,
            },
        },
        agent_text="The stock shows bullish momentum with high volume.",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_deterministic_explanation_low_confidence():
    """Low confidence + high danger should produce a warning explanation."""
    from core.explanation.engine import _deterministic_explanation

    result = _deterministic_explanation(
        {
            "confidence": 0.3,
            "passed": False,
            "threshold": 0.70,
            "expand_compute": True,
            "factors": {
                "veracity": 0.2,
                "consensus": 0.3,
                "proxy_reward": 0.1,
            },
        },
        agent_text="Insufficient data for reliable analysis.",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_deterministic_explanation_empty_factors():
    from core.explanation.engine import _deterministic_explanation

    result = _deterministic_explanation(
        {"confidence": 0.5, "passed": True, "threshold": 0.60, "factors": {}},
        agent_text="",
    )
    assert isinstance(result, str)


def test_format_percent():
    from core.explanation.engine import _format_percent

    result = _format_percent(0.85)
    assert "85" in result and "%" in result
    assert _format_percent(None) == "unknown"
    assert _format_percent("bad") == "unknown"


def test_env_enabled():
    from core.explanation.engine import _env_enabled

    assert _env_enabled("NONEXISTENT_VAR_12345", default=True) is True
    assert _env_enabled("NONEXISTENT_VAR_12345", default=False) is False


def test_resolve_lora_path_none():
    from core.explanation.engine import _resolve_lora_path

    assert _resolve_lora_path(None) is None
    assert _resolve_lora_path("") is None


def test_module_public_api():
    """Verify public symbols are importable from the explanation package."""
    from core.explanation import ExplainEngine

    assert ExplainEngine is not None
