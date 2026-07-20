"""Tests — Mangala Engine (deterministico, sem rede)."""

from __future__ import annotations

from core.pipeline.nodes.mangala import (
    calculate_mangala_score,
    format_mangala_for_bob,
    _score_volume_anomaly,
    _score_whale_prints,
    _score_momentum,
    _score_rsi,
    _score_catalyst,
    _determine_signal,
    _build_flip_plan,
    HIGH_CONVICTION,
    WATCH_THRESHOLD,
    MEH_THRESHOLD,
)


# ── Fixtures ───────────────────────────────────────────────────────────────


def _stock_data(**overrides) -> dict:
    """Build a complete canned stock_data dict for scoring tests."""
    data = {
        "ticker": "TEST",
        "price": 4.50,
        "volume": 2_000_000,
        "avg_volume_20d": 500_000,
        "momentum_5d": 8.5,
        "rsi": 58.0,
        "news_count": 5,
        "sentiment": {"sentiment_label": "bullish", "sentiment_score": 0.45},
        "news_headlines": [
            "Company reports breakthrough earnings guidance",
            "Analyst upgrade",
        ],
    }
    data.update(overrides)
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 1. Test calculate_mangala_score — complete data
# ═══════════════════════════════════════════════════════════════════════════


class TestCalculateMangalaScore:
    def test_full_data_high_score(self):
        """Complete bullish data should yield MANGALA! signal."""
        result = calculate_mangala_score(
            _stock_data(
                volume=3_000_000,
                avg_volume_20d=500_000,  # 6x = 30 pts
                momentum_5d=12.0,  # 18 pts
                rsi=60.0,  # 15 pts
                news_count=8,
                sentiment={"sentiment_label": "bullish", "sentiment_score": 0.6},
            )
        )
        assert result["score"] >= HIGH_CONVICTION
        assert result["signal"] == "MANGALA!"
        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 100
        assert set(result["factors"].keys()) == {"volume", "whale", "momentum", "rsi", "catalyst"}
        assert result["flip_plan"]["entry"] == 4.50
        assert result["flip_plan"]["target_5pct"] == round(4.50 * 1.05, 2)
        assert result["flip_plan"]["stop_3pct"] == round(4.50 * 0.97, 2)
        assert result["flip_plan"]["max_hold_days"] == 5

    def test_missing_data_low_score(self):
        """Stock with no technical data should get PASS."""
        result = calculate_mangala_score(
            {
                "ticker": "TEST",
                "price": 1.00,
                "volume": 100,
            }
        )
        assert result["score"] < MEH_THRESHOLD
        assert result["signal"] == "PASS"
        assert sum(result["factors"].values()) == result["score"]

    def test_negative_momentum_zero_rsi(self):
        """Declining stock should score low."""
        result = calculate_mangala_score(
            _stock_data(
                momentum_5d=-5.0,
                rsi=25.0,
                volume=1000,
                avg_volume_20d=1000,
                news_count=0,
                sentiment={},
            )
        )
        assert result["score"] < WATCH_THRESHOLD
        assert result["signal"] in ("MEH", "PASS")

    def test_edge_zero_volume(self):
        """Zero volume should not crash and yields low volume score."""
        result = calculate_mangala_score(
            _stock_data(
                volume=0,
                avg_volume_20d=500_000,
            )
        )
        assert result["factors"]["volume"] == 0
        assert isinstance(result["score"], int)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Test signal determination at thresholds
# ═══════════════════════════════════════════════════════════════════════════


class TestSignalDetermination:
    def test_mangala_signal(self):
        for score in [HIGH_CONVICTION, 90, 100]:
            assert _determine_signal(score) == "MANGALA!", f"Failed at {score}"

    def test_watch_signal(self):
        for score in [WATCH_THRESHOLD, 70, 79]:
            assert _determine_signal(score) == "WATCH", f"Failed at {score}"

    def test_meh_signal(self):
        for score in [MEH_THRESHOLD, 50, 59]:
            assert _determine_signal(score) == "MEH", f"Failed at {score}"

    def test_pass_signal(self):
        for score in [0, 20, 39, MEH_THRESHOLD - 1]:
            assert _determine_signal(score) == "PASS", f"Failed at {score}"

    def test_boundary_values(self):
        assert _determine_signal(HIGH_CONVICTION) == "MANGALA!"
        assert _determine_signal(HIGH_CONVICTION - 1) == "WATCH"
        assert _determine_signal(WATCH_THRESHOLD) == "WATCH"
        assert _determine_signal(WATCH_THRESHOLD - 1) == "MEH"
        assert _determine_signal(MEH_THRESHOLD) == "MEH"
        assert _determine_signal(MEH_THRESHOLD - 1) == "PASS"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Test format_mangala_for_bob
# ═══════════════════════════════════════════════════════════════════════════


class TestFormatMangalaForBob:
    def test_empty_list_returns_empty_string(self):
        assert format_mangala_for_bob([]) == ""

    def test_formats_top_5_correctly(self):
        opportunities = [
            {
                "ticker": "SNDL",
                "price": 2.50,
                "volume": 5_000_000,
                "name": "Sundial Growers",
                "score": 85,
                "signal": "MANGALA!",
                "factors": {"volume": 30, "whale": 20, "momentum": 15, "rsi": 12, "catalyst": 8},
                "flip_plan": {
                    "entry": 2.50,
                    "target_5pct": 2.62,
                    "stop_3pct": 2.42,
                    "max_hold_days": 5,
                },
            },
            {
                "ticker": "TLRY",
                "price": 3.20,
                "volume": 3_000_000,
                "name": "Tilray Inc",
                "score": 65,
                "signal": "WATCH",
                "factors": {"volume": 20, "whale": 15, "momentum": 10, "rsi": 12, "catalyst": 8},
                "flip_plan": {
                    "entry": 3.20,
                    "target_5pct": 3.36,
                    "stop_3pct": 3.10,
                    "max_hold_days": 5,
                },
            },
        ]

        formatted = format_mangala_for_bob(opportunities)

        assert formatted != ""
        assert "MANGALA ENGINE" in formatted
        assert "SNDL" in formatted
        assert "TLRY" in formatted
        assert "85" in formatted
        assert "MANGALA!" in formatted
        assert "2.50" in formatted
        assert "Planos de Entrada" in formatted  # has high-conviction

    def test_no_high_conviction_no_flip_plan(self):
        """When no MANGALA! signals, the flip plan section should be absent."""
        opportunities = [
            {
                "ticker": "TEST",
                "price": 5.00,
                "volume": 100_000,
                "name": "Test Inc",
                "score": 50,
                "signal": "MEH",
                "factors": {"volume": 10, "whale": 5, "momentum": 10, "rsi": 15, "catalyst": 10},
                "flip_plan": {
                    "entry": 5.00,
                    "target_5pct": 5.25,
                    "stop_3pct": 4.85,
                    "max_hold_days": 5,
                },
            }
        ]

        formatted = format_mangala_for_bob(opportunities)
        assert "Planos de Entrada" not in formatted
        assert "TEST" in formatted
        assert "50" in formatted


# ═══════════════════════════════════════════════════════════════════════════
# 4. Test scoring sub-functions
# ═══════════════════════════════════════════════════════════════════════════


class TestScoreVolumeAnomaly:
    def test_max_score_at_5x(self):
        assert _score_volume_anomaly({"volume": 500_000, "avg_volume_20d": 100_000}) == 30

    def test_zero_avg_volume(self):
        assert _score_volume_anomaly({"volume": 500_000, "avg_volume_20d": 0}) == 0

    def test_missing_keys(self):
        assert _score_volume_anomaly({}) == 0

    def test_medium_ratio(self):
        assert _score_volume_anomaly({"volume": 300_000, "avg_volume_20d": 200_000}) == 15

    def test_low_ratio(self):
        assert _score_volume_anomaly({"volume": 100_000, "avg_volume_20d": 200_000}) == 0

    def test_all_ratios(self):
        cases = [
            (5.0, 30),
            (4.0, 25),
            (2.5, 20),
            (1.8, 15),
            (1.3, 10),
            (0.9, 5),
            (0.5, 0),
        ]
        for ratio, expected in cases:
            assert (
                _score_volume_anomaly({"volume": ratio * 1000, "avg_volume_20d": 1000}) == expected
            )


class TestScoreWhalePrints:
    def test_forte_whale(self):
        score = _score_whale_prints({"whale_print": {"label": "FORTE", "confidence": 0.8}})
        assert score == 25

    def test_provavel_whale(self):
        score = _score_whale_prints({"whale_print": {"label": "PROVAVEL", "confidence": 0.6}})
        assert score == 20

    def test_moderado_whale(self):
        score = _score_whale_prints({"whale_print": {"label": "MODERADO", "confidence": 0.5}})
        assert score == 12

    def test_no_whale_data_heuristic_high(self):
        score = _score_whale_prints({"volume": 500_000, "avg_volume_20d": 100_000, "price": 2.00})
        assert score == 15  # ratio=5.0, price<5

    def test_no_whale_data_heuristic_medium(self):
        score = _score_whale_prints({"volume": 300_000, "avg_volume_20d": 100_000, "price": 8.00})
        assert score == 8  # ratio=3.0, price>=5

    def test_no_whale_data_low_volume(self):
        score = _score_whale_prints({"volume": 100_000, "avg_volume_20d": 100_000, "price": 5.00})
        assert score == 0  # ratio=1.0, below threshold


class TestScoreMomentum:
    def test_high_momentum(self):
        assert _score_momentum({"momentum_5d": 20}) == 20

    def test_medium_momentum(self):
        assert _score_momentum({"momentum_5d": 6}) == 12

    def test_low_momentum(self):
        assert _score_momentum({"momentum_5d": 2}) == 5

    def test_neutral_momentum(self):
        assert _score_momentum({"momentum_5d": 0}) == 3

    def test_negative_momentum(self):
        assert _score_momentum({"momentum_5d": -2}) == 0

    def test_missing_momentum(self):
        assert _score_momentum({}) == 0


class TestScoreRSI:
    def test_sweet_spot(self):
        assert _score_rsi({"rsi": 60}) == 15

    def test_good_range(self):
        assert _score_rsi({"rsi": 52}) == 12

    def test_acceptable_range(self):
        assert _score_rsi({"rsi": 47}) == 8

    def test_wide_range(self):
        assert _score_rsi({"rsi": 42}) == 5

    def test_marginal(self):
        assert _score_rsi({"rsi": 35}) == 3

    def test_out_of_range(self):
        assert _score_rsi({"rsi": 20}) == 0
        assert _score_rsi({"rsi": 85}) == 0

    def test_missing_rsi(self):
        assert _score_rsi({}) == 0


class TestScoreCatalyst:
    def test_strong_news_and_sentiment(self):
        score = _score_catalyst(
            {
                "news_count": 8,
                "sentiment": {"sentiment_label": "bullish", "sentiment_score": 0.5},
                "news_headlines": ["Company announces major contract win"],
            }
        )
        assert score == 10  # 5+3+2 capped

    def test_no_news_no_sentiment(self):
        assert _score_catalyst({"news_count": 0}) == 0

    def test_neutral_sentiment(self):
        score = _score_catalyst(
            {"news_count": 2, "sentiment": {"sentiment_label": "neutral", "sentiment_score": 0.05}}
        )
        assert score == 3  # 2 for news + 1 for positive sentiment score

    def test_catalyst_keyword_detection(self):
        score = _score_catalyst(
            {
                "news_count": 3,
                "news_headlines": ["Earnings beat expectations"],
            }
        )
        assert score == 5  # 3 for news count + 2 for "earnings"

    def test_capped_at_10(self):
        score = _score_catalyst(
            {
                "news_count": 20,
                "sentiment": {"sentiment_label": "bullish", "sentiment_score": 0.9},
                "news_headlines": ["Earnings guidance upgrade"],
            }
        )
        assert score == 10

    def test_news_count_alone(self):
        cases = [(0, 0), (1, 2), (3, 3), (5, 5), (10, 5)]
        for count, expected in cases:
            score = _score_catalyst({"news_count": count})
            assert score == expected, f"Failed at count={count}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Test build_flip_plan
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildFlipPlan:
    def test_flip_plan_values(self):
        plan = _build_flip_plan({"price": 10.00})
        assert plan["entry"] == 10.00
        assert plan["target_5pct"] == 10.50
        assert plan["stop_3pct"] == 9.70
        assert plan["max_hold_days"] == 5

    def test_flip_plan_with_zero_price(self):
        plan = _build_flip_plan({"price": 0})
        assert plan["entry"] == 0.0
        assert plan["target_5pct"] == 0.0
        assert plan["stop_3pct"] == 0.0

    def test_flip_plan_missing_price(self):
        plan = _build_flip_plan({})
        assert plan["entry"] == 0.0
