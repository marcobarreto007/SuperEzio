"""Heart ranking surface. Isolated router — tests never import main."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from core.heart.attribution import DailyMove, attribute_move
from core.heart.event_book import MarketEvent
from core.heart.hydrate import refresh_heart_view
from core.heart.ml.decide import decide_path
from core.heart.paths import SPINE_PATH
from core.heart.ranking import RankingWeights, rank_moves

try:
    from core.heart.attribution import attribute_moves as _attribute_moves
except ImportError:  # pragma: no cover — batch helper optional
    _attribute_moves = None

router = APIRouter(tags=["heart"])

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HEART_ROOT = _ROOT / "data" / "heart"
# Heart bars live next to EventBook. DataHub/TD ETF cache is a different river.
DEFAULT_OHLCV_DIR = _ROOT / "data" / "heart" / "ohlcv"


def resolve_ohlcv_dir() -> Path:
    override = os.getenv("SUPEREZIO_HEART_OHLCV_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_OHLCV_DIR


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


def _build_attributions(moves: list[DailyMove], events: list[MarketEvent]) -> dict[str, dict[str, Any]]:
    if _attribute_moves is not None:
        batch = _attribute_moves(moves, events)
        if isinstance(batch, dict):
            return batch
        return {att["move_key"]: att for att in batch}
    attributions: dict[str, dict[str, Any]] = {}
    for move in moves:
        att = attribute_move(move, events)
        attributions[att["move_key"]] = att
    return attributions


@router.get("/api/heart/ranking")
def get_heart_ranking() -> dict[str, Any]:
    if not os.getenv("PYTEST_CURRENT_TEST"):
        refresh_heart_view(
            VIEW,
            heart_root=DEFAULT_HEART_ROOT,
            ohlcv_dir=resolve_ohlcv_dir(),
        )

    if not VIEW.moves:
        return {
            "rows": [],
            "path_id": SPINE_PATH.path_id,
            "path_status": None,
        }

    attributions = _build_attributions(VIEW.moves, VIEW.events)
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
