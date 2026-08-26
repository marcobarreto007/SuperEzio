"""Memory Lattice — Five-layer SQLite memory for the CORPO layer.

Layer layout
-----------
1  meta_rules         Immutable — seed data (constitutional principles)
2  crystallized_skills Skills with win_rate > 70 % (read-mostly)
3  facts              Individual trades with outcome
4  patterns           Statistical correlations mined from facts
5  raw                Journal JSONL (append-only timeline)

Each layer is a separate table in a single SQLite file.  Layers 2, 3, and 4
have FTS5 virtual tables for textual search.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "memory_lattice.sqlite3"

# ── Layer metadata ──────────────────────────────────────────────────────────
LAYER_NAMES = {
    1: "meta_rules",
    2: "crystallized_skills",
    3: "facts",
    4: "patterns",
    5: "raw",
}
LAYERS_WITH_FTS = {2, 3, 4}  # layers that get an FTS5 virtual table

_META_RULES_SEED: list[dict[str, Any]] = [
    {
        "rule_id": "constitution_1",
        "content": "Never commit capital that the trader cannot afford to lose entirely.",
        "source": "constitution",
        "active": True,
    },
    {
        "rule_id": "constitution_2",
        "content": "Every recommendation must cite at least one verifiable data source.",
        "source": "constitution",
        "active": True,
    },
    {
        "rule_id": "constitution_3",
        "content": "Do not exceed the risk limits defined by the current DNA gene values.",
        "source": "constitution",
        "active": True,
    },
    {
        "rule_id": "constitution_4",
        "content": "All decisions must be auditably traceable to a specific pipeline run.",
        "source": "constitution",
        "active": True,
    },
    {
        "rule_id": "constitution_5",
        "content": "The system shall never fabricate or hallucinate market data.",
        "source": "constitution",
        "active": True,
    },
    {
        "rule_id": "constitution_6",
        "content": "Win rates below 50 % trigger automatic gene exploration (mutation).",
        "source": "constitution",
        "active": True,
    },
    {
        "rule_id": "constitution_7",
        "content": "Crystallized genes require a supermajority override to unlock.",
        "source": "constitution",
        "active": True,
    },
]


# ---------------------------------------------------------------------------
# Memory Lattice
# ---------------------------------------------------------------------------


class MemoryLattice:
    """Five-layer SQLite-based persistent memory with FTS5 search."""

    def __init__(self, db_path: str | Path = _DEFAULT_DB) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        self._seed_meta_rules()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, layer: int, data: dict[str, Any]) -> int:
        """Insert a record into the given layer (1-5).

        Returns the rowid of the inserted row.
        """
        if layer not in LAYER_NAMES:
            raise ValueError(f"Invalid layer: {layer}. Must be 1-5.")
        if layer == 1:
            raise ValueError("Layer 1 (meta_rules) is immutable — cannot store.")

        table = LAYER_NAMES[layer]
        data["_created_at"] = data.get("_created_at", _now_iso())
        json_data = json.dumps(data)

        with self._lock:
            cur = self._conn.execute(
                f"INSERT INTO {table} (data, created_at) VALUES (?, ?)",  # nosec B608 -- constant map
                (json_data, data["_created_at"]),
            )
            rowid = cur.lastrowid

            # Sync FTS index for layers that have FTS
            if layer in LAYERS_WITH_FTS:
                fts_table = f"{table}_fts"
                self._conn.execute(
                    f"INSERT INTO {fts_table} (rowid, data) VALUES (?, ?)",  # nosec B608 -- constant map
                    (rowid, json_data),
                )

            self._conn.commit()
            return rowid  # type: ignore[return-value]

    def query(
        self,
        layer: int,
        filters: dict[str, Any] | None = None,
        *,
        search: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query records from a layer.

        Parameters
        ----------
        layer : int
            Layer number (1-5).
        filters : dict or None
            Simple equality filters applied to the JSON ``data`` column.
        search : str or None
            Full-text search term (only available for layers 2, 3, 4).
        limit : int
            Maximum number of rows to return.
        """
        if layer not in LAYER_NAMES:
            raise ValueError(f"Invalid layer: {layer}. Must be 1-5.")
        table = LAYER_NAMES[layer]

        if search and layer in LAYERS_WITH_FTS:
            return self._fts_search(layer, search, limit)

        sql = f"SELECT rowid, data, created_at FROM {table}"
        params: list[Any] = []
        if filters:
            conditions = []
            for key, value in filters.items():
                conditions.append(f"json_extract(data, '$.{key}') = ?")
                params.append(value)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]

    def crystallize(self, pattern: dict[str, Any]) -> int:
        """Promote a pattern (layer 4) into crystallized_skills (layer 2).

        This is the mechanism by which statistical correlations become frozen
        heuristics.  Returns the rowid in layer 2.
        """
        skill_entry = {
            "name": pattern.get("name", "untitled"),
            "description": pattern.get("description", ""),
            "win_rate": pattern.get("win_rate", 0.0),
            "expression": pattern.get("expression", ""),
            "source_pattern_id": pattern.get("pattern_id"),
            "crystallized_at": _now_iso(),
        }
        rowid = self.store(2, skill_entry)
        return rowid  # type: ignore[return-value]

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Schema & seeds
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._lock:
            for layer_num, table in LAYER_NAMES.items():
                self._conn.execute(
                    f"""CREATE TABLE IF NOT EXISTS {table} (
                        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                        data TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )"""
                )
                if layer_num in LAYERS_WITH_FTS:
                    fts_table = f"{table}_fts"
                    self._conn.execute(
                        f"""CREATE VIRTUAL TABLE IF NOT EXISTS {fts_table}
                        USING fts5(data)"""
                    )
            self._conn.commit()

    def _seed_meta_rules(self) -> None:
        """Populate layer 1 with immutable seed rules if empty."""
        count = self._conn.execute("SELECT COUNT(*) as cnt FROM meta_rules").fetchone()["cnt"]
        if count > 0:
            return
        with self._lock:
            for rule in _META_RULES_SEED:
                self._conn.execute(
                    "INSERT INTO meta_rules (data, created_at) VALUES (?, ?)",
                    (json.dumps(rule), _now_iso()),
                )
            self._conn.commit()

    def _fts_search(self, layer: int, term: str, limit: int) -> list[dict[str, Any]]:
        table = LAYER_NAMES[layer]
        fts_table = f"{table}_fts"
        sql = (
            f"SELECT rowid, data, created_at FROM {table} "
            f"WHERE rowid IN ("
            f"  SELECT rowid FROM {fts_table} WHERE data MATCH ?"
            f") ORDER BY rowid DESC LIMIT ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, (term, limit)).fetchall()
        return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = json.loads(row["data"])
    data["_rowid"] = row["rowid"]
    data["_created_at"] = row["created_at"]
    return data


__all__ = [
    "LAYER_NAMES",
    "MemoryLattice",
]
