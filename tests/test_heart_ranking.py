"""Peça 4: combinação dos quatro eixos. Pesos começam iguais e somam 1."""

from __future__ import annotations

from core.heart.ranking import RankingAxes, RankingWeights, composite_score


def test_equal_weights_average_the_four_axes():
    score = composite_score(
        RankingAxes(
            abnormal_return=1.0,
            gross_return=0.0,
            lifetime_score=0.5,
            surprise=0.5,
        ),
        RankingWeights.equal(),
    )
    assert score == 0.5


def test_weights_must_sum_to_one():
    import pytest

    with pytest.raises(ValueError, match="sum to 1"):
        RankingWeights(
            abnormal_return=0.5,
            gross_return=0.5,
            lifetime_score=0.5,
            surprise=0.5,
        )
