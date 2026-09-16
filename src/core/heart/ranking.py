"""Adaptive ranking weights. Start equal; learning comes later (P5)."""

from __future__ import annotations

from dataclasses import dataclass

from core.heart.attribution import DailyMove, move_key


@dataclass(frozen=True, slots=True)
class RankingAxes:
    abnormal_return: float
    gross_return: float
    lifetime_score: float
    surprise: float


@dataclass(frozen=True, slots=True)
class RankingWeights:
    abnormal_return: float
    gross_return: float
    lifetime_score: float
    surprise: float

    def __post_init__(self) -> None:
        total = (
            self.abnormal_return
            + self.gross_return
            + self.lifetime_score
            + self.surprise
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError("ranking weights must sum to 1")

    @classmethod
    def equal(cls) -> RankingWeights:
        return cls(0.25, 0.25, 0.25, 0.25)

    def as_dict(self) -> dict[str, float]:
        return {
            "abnormal_return": self.abnormal_return,
            "gross_return": self.gross_return,
            "lifetime_score": self.lifetime_score,
            "surprise": self.surprise,
        }


def composite_score(axes: RankingAxes, weights: RankingWeights) -> float:
    return (
        axes.abnormal_return * weights.abnormal_return
        + axes.gross_return * weights.gross_return
        + axes.lifetime_score * weights.lifetime_score
        + axes.surprise * weights.surprise
    )


def _identity_key(move: DailyMove) -> str:
    return f"{move['mic_code']}:{move['symbol']}:{move['first_seen']}"


def compute_lifetime_scores(rows: list[DailyMove]) -> dict[str, float]:
    """Cumulative abnormal return per identity up to each session."""
    grouped: dict[str, list[DailyMove]] = {}
    for row in rows:
        grouped.setdefault(_identity_key(row), []).append(row)

    scores: dict[str, float] = {}
    for moves in grouped.values():
        cumulative = 0.0
        for move in sorted(moves, key=lambda item: item["session_date"]):
            cumulative += float(move["abnormal_ret"])
            scores[move_key(move)] = cumulative
    return scores


def rank_moves(
    rows: list[DailyMove],
    weights: RankingWeights,
    *,
    lifetime_scores: dict[str, float] | None = None,
    attributions: dict[str, dict] | None = None,
) -> list[dict]:
    """Rank moves by weighted composite score (weights are caller input, not learned)."""
    if not rows:
        return []

    lifetime = lifetime_scores if lifetime_scores is not None else compute_lifetime_scores(rows)
    attributions = attributions or {}

    ranked: list[dict] = []
    for row in rows:
        key = move_key(row)
        axes = RankingAxes(
            abnormal_return=float(row["abnormal_ret"]),
            gross_return=float(row["gross_ret"]),
            lifetime_score=float(lifetime.get(key, 0.0)),
            surprise=float(row["surprise_q"]),
        )
        score = composite_score(axes, weights)
        entry: dict = {
            "move_key": key,
            "mic_code": row["mic_code"],
            "symbol": row["symbol"],
            "first_seen": row["first_seen"],
            "session_date": row["session_date"],
            "abnormal_ret": float(row["abnormal_ret"]),
            "gross_ret": float(row["gross_ret"]),
            "surprise_q": float(row["surprise_q"]),
            "ewma_vol": float(row["ewma_vol"]),
            "axes": {
                "abnormal_return": axes.abnormal_return,
                "gross_return": axes.gross_return,
                "lifetime_score": axes.lifetime_score,
                "surprise": axes.surprise,
            },
            "composite_score": score,
        }
        if key in attributions:
            entry["attribution"] = attributions[key]
        ranked.append(entry)

    ranked.sort(key=lambda item: item["composite_score"], reverse=True)
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked
