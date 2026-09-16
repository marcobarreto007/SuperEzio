"""Heart ranking surface. Isolated router — tests never import main."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter

from core.heart.attribution import DailyMove, attribute_move
from core.heart.event_book import MarketEvent
from core.heart.ml.decide import decide_path
from core.heart.paths import SPINE_PATH
from core.heart.ranking import RankingWeights, rank_moves

router = APIRouter(tags=["heart"])


@dataclass
class HeartView:
    moves: list[DailyMove] = field(default_factory=list)
    events: list[MarketEvent] = field(default_factory=list)
    bars: list[dict[str, Any]] = field(default_factory=list)


VIEW = HeartView()


def reset_heart_view_for_test() -> None:
    VIEW.moves = []
    VIEW.events = []
    VIEW.bars = []


@router.get("/api/heart/ranking")
def get_heart_ranking() -> dict[str, Any]:
    if not VIEW.moves:
        return {
            "rows": [],
            "path_id": SPINE_PATH.path_id,
            "path_status": None,
        }
    attributions: dict[str, dict[str, Any]] = {}
    for move in VIEW.moves:
        att = attribute_move(move, VIEW.events)
        attributions[att["move_key"]] = att
    rows = rank_moves(VIEW.moves, RankingWeights.equal(), attributions=attributions)
    path_status = None
    path_id = SPINE_PATH.path_id
    if VIEW.bars:
        decision = decide_path(VIEW.bars, entry_index=3, spec=SPINE_PATH)
        path_status = decision.status
        path_id = decision.path_id
        for row in rows:
            row["path_status"] = path_status
            row["path_id"] = path_id
    return {"rows": rows, "path_id": path_id, "path_status": path_status}
