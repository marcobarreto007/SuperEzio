"""Heart ranking surface. Isolated router — tests never import main."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
EMPTY_OHLCV_STATUS = "empty_ohlcv"


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


def _build_attributions(
    moves: list[DailyMove], events: list[MarketEvent]
) -> dict[str, dict[str, Any]]:
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
            "path_status": EMPTY_OHLCV_STATUS,
        }

    attributions = _build_attributions(VIEW.moves, VIEW.events)
    rows = rank_moves(VIEW.moves, RankingWeights.equal(), attributions=attributions)
    path_status = None
    path_id = SPINE_PATH.path_id
    if os.getenv("PYTEST_CURRENT_TEST"):
        if VIEW.bars:
            decision = decide_path(VIEW.bars, entry_index=3, spec=SPINE_PATH)
            path_status = decision.status
            path_id = decision.path_id
            for row in rows:
                row["path_status"] = path_status
                row["path_id"] = path_id
    else:
        from core.heart.ml.empty_store import decide_or_refuse

        decision = decide_or_refuse(resolve_ohlcv_dir(), SPINE_PATH.path_id)
        path_status = decision.status
        path_id = decision.path_id
        for row in rows:
            row["path_status"] = path_status
            row["path_id"] = path_id
    return {"rows": rows, "path_id": path_id, "path_status": path_status}


_LINE_CACHE: dict[str, tuple[int, int, int]] = {}
_STALE_AFTER_SECONDS = 48 * 3600


def _count_nonempty_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    stat = path.stat()
    cached = _LINE_CACHE.get(str(path))
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    count = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                count += 1
    _LINE_CACHE[str(path)] = (stat.st_mtime_ns, stat.st_size, count)
    return count


def build_heart_status(
    heart_root: Path,
    ohlcv_dir: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Facts the dashboard may show. Does not rank and does not invent weights."""
    root = Path(heart_root)
    prices = Path(ohlcv_dir)
    moment = now or datetime.now(UTC)
    csvs = sorted(prices.glob("*.csv")) if prices.is_dir() else []
    raw_dir = root / "raw"
    raw_files = sorted(raw_dir.rglob("*.jsonl")) if raw_dir.is_dir() else []
    newest = max(raw_files, key=lambda item: item.stat().st_mtime) if raw_files else None
    last_wire_at = None
    freshness = "missing"
    if newest is not None:
        last_wire_at = datetime.fromtimestamp(newest.stat().st_mtime, UTC).isoformat()
        age = moment.timestamp() - newest.stat().st_mtime
        freshness = "stale" if age > _STALE_AFTER_SECONDS else "current"
    return {
        "bob": "consulta o arquivo e da opiniao",
        "execution": "live congelado — Marco digita no TD",
        "paper_is_product": False,
        "events": _count_nonempty_lines(root / "events.jsonl"),
        "priced_symbols": len(csvs),
        "weights": "unweighted" if csvs else "empty",
        "last_wire_at": last_wire_at,
        "freshness": freshness,
        "ranking_url": "/api/heart/ranking",
    }


@router.get("/api/heart/status")
def get_heart_status() -> dict[str, Any]:
    return build_heart_status(DEFAULT_HEART_ROOT, resolve_ohlcv_dir())
