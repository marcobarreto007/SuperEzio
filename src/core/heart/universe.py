"""Point-in-time tradable universe. Identity is (mic, symbol, first_seen)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_LISTING_EXCHANGE_TO_MIC = {
    "Q": "XNAS",
    "N": "XNYS",
    "P": "ARCX",
    "A": "XASE",
    "Z": "BATS",
    "V": "IEXG",
}


@dataclass(frozen=True, slots=True)
class ListingRow:
    mic_code: str
    symbol: str
    name: str
    exchange: str
    source: str
    is_etf: bool = False
    is_test: bool = False


@dataclass(frozen=True, slots=True)
class SymbolRecord:
    mic_code: str
    symbol: str
    first_seen: date
    last_seen: date
    name: str
    exchange: str
    source: str
    is_etf: bool = False
    delisting_date: date | None = None

    @property
    def identity(self) -> tuple[str, str, date]:
        return (self.mic_code, self.symbol, self.first_seen)


@dataclass(frozen=True, slots=True)
class IngestResult:
    inserted: int = 0
    updated: int = 0
    delisted: int = 0


def listing_exchange_to_mic(code: str) -> str:
    try:
        return _LISTING_EXCHANGE_TO_MIC[code]
    except KeyError as exc:
        raise KeyError(f"unknown Nasdaq listing exchange code: {code}") from exc


class UniverseRegistry:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_history (
                    mic_code TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    delisting_date TEXT,
                    name TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    source TEXT NOT NULL,
                    is_etf INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (mic_code, symbol, first_seen)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_symbol_history_active
                ON symbol_history(source, mic_code, symbol)
                """
            )

    def ingest_snapshot(
        self,
        rows: Sequence[ListingRow],
        *,
        as_of: date,
        snapshot_ok: bool,
        source: str | None = None,
    ) -> IngestResult:
        eligible = [row for row in rows if not row.is_test]
        resolved_source = source or next((row.source for row in rows if row.source), None)
        if not eligible and not snapshot_ok:
            return IngestResult()
        if snapshot_ok and not resolved_source:
            if not eligible:
                return IngestResult()
            raise ValueError("source is required to close a successful snapshot")

        inserted = 0
        updated = 0
        as_of_text = as_of.isoformat()
        with self._connect() as conn:
            for row in eligible:
                active = conn.execute(
                    """
                    SELECT first_seen FROM symbol_history
                    WHERE mic_code = ? AND symbol = ? AND delisting_date IS NULL
                    """,
                    (row.mic_code, row.symbol),
                ).fetchone()
                if active is None:
                    conn.execute(
                        """
                        INSERT INTO symbol_history (
                            mic_code, symbol, first_seen, last_seen, delisting_date,
                            name, exchange, source, is_etf
                        ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)
                        """,
                        (
                            row.mic_code,
                            row.symbol,
                            as_of_text,
                            as_of_text,
                            row.name,
                            row.exchange,
                            row.source,
                            int(row.is_etf),
                        ),
                    )
                    inserted += 1
                else:
                    conn.execute(
                        """
                        UPDATE symbol_history
                        SET last_seen = ?, name = ?, exchange = ?, source = ?, is_etf = ?
                        WHERE mic_code = ? AND symbol = ? AND first_seen = ?
                        """,
                        (
                            as_of_text,
                            row.name,
                            row.exchange,
                            row.source,
                            int(row.is_etf),
                            row.mic_code,
                            row.symbol,
                            active[0],
                        ),
                    )
                    updated += 1

            delisted = 0
            if snapshot_ok:
                present = {(row.mic_code, row.symbol) for row in eligible}
                missing = conn.execute(
                    """
                    SELECT mic_code, symbol, first_seen FROM symbol_history
                    WHERE source = ? AND delisting_date IS NULL
                    """,
                    (resolved_source,),
                ).fetchall()
                for mic_code, symbol, first_seen in missing:
                    if (mic_code, symbol) in present:
                        continue
                    conn.execute(
                        """
                        UPDATE symbol_history
                        SET delisting_date = ?
                        WHERE mic_code = ? AND symbol = ? AND first_seen = ?
                        """,
                        (as_of_text, mic_code, symbol, first_seen),
                    )
                    delisted += 1

        return IngestResult(inserted=inserted, updated=updated, delisted=delisted)

    def active(self) -> list[SymbolRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT mic_code, symbol, first_seen, last_seen, name, exchange,
                       source, is_etf, delisting_date
                FROM symbol_history
                WHERE delisting_date IS NULL
                ORDER BY symbol, mic_code, first_seen
                """
            ).fetchall()
        return [_record(row) for row in rows]

    def all_records(self) -> list[SymbolRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT mic_code, symbol, first_seen, last_seen, name, exchange,
                       source, is_etf, delisting_date
                FROM symbol_history
                ORDER BY symbol, mic_code, first_seen
                """
            ).fetchall()
        return [_record(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


def _parse_date(value: str) -> date:
    year, month, day = (int(part) for part in value.split("-"))
    return date(year, month, day)


def _record(row: sqlite3.Row | tuple) -> SymbolRecord:
    (
        mic_code,
        symbol,
        first_seen,
        last_seen,
        name,
        exchange,
        source,
        is_etf,
        delisting_date,
    ) = row
    return SymbolRecord(
        mic_code=mic_code,
        symbol=symbol,
        first_seen=_parse_date(first_seen),
        last_seen=_parse_date(last_seen),
        name=name,
        exchange=exchange,
        source=source,
        is_etf=bool(is_etf),
        delisting_date=_parse_date(delisting_date) if delisting_date else None,
    )
