"""
Investor Storage â€” SQLite para persistÃªncia de decisÃµes de investimento
======================================================================
Tabelas:
  investor_decisions      â†’ anÃ¡lises e respostas finais
  investor_risk_profile   â†’ perfil de risco por sessÃ£o/usuÃ¡rio
  investor_watchlist      â†’ tickers monitorados
  investor_notes          â†’ notas livres do usuÃ¡rio
  investor_api_usage      â†’ auditoria de uso do DeepSeek

REGRAS DE SEGURANÃ‡A:
  - Nunca salvar API key.
  - Nunca salvar dados de corretora ou credenciais.
  - Apenas dados analiticos e de decisao.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading as _threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.paths import resolve_project_path


def _db_path() -> Path:
    base = resolve_project_path(os.getenv("SUPEREZIO_DATA_DIR", "data"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "investor.db"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class InvestorStorage:
    """
    Armazena decisoes analiticas de investimento em SQLite local.
    Nunca persiste API keys, credenciais ou ordens de corretora.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _db_path()
        self._init_db()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS investor_decisions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker      TEXT NOT NULL,
                    asset_type  TEXT,
                    user_input  TEXT,          -- JSON com parÃ¢metros do usuÃ¡rio
                    response    TEXT,          -- JSON da resposta completa
                    decision    TEXT,          -- study_more|wait|small_position|avoid
                    confidence  TEXT,
                    model_used  TEXT,
                    cost_usd    REAL,
                    risk_flags  TEXT,          -- JSON com flags de risco
                    has_fomo    INTEGER DEFAULT 0,
                    no_emergency_fund INTEGER DEFAULT 0,
                    created_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS investor_risk_profile (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   TEXT,
                    risk_level   TEXT,
                    time_horizon TEXT,
                    goal         TEXT,
                    has_emergency_fund INTEGER,
                    created_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS investor_watchlist (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker     TEXT NOT NULL,
                    notes      TEXT,
                    added_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS investor_notes (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker     TEXT,
                    note       TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS investor_api_usage (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    model            TEXT,
                    prompt_tokens    INTEGER,
                    completion_tokens INTEGER,
                    cost_usd         REAL,
                    endpoint         TEXT,
                    status           TEXT,
                    created_at       TEXT NOT NULL
                );
            """)

    # ------------------------------------------------------------------
    # investor_decisions
    # ------------------------------------------------------------------

    def save_decision(
        self,
        ticker: str,
        user_input: dict[str, Any],
        response: dict[str, Any],
        model_used: str = "deepseek-v4-flash",
        cost_usd: float = 0.0,
    ) -> int:
        """
        Persiste uma anÃ¡lise completa.
        Retorna o ID do registro criado.
        """
        decision = response.get("suggested_next_step", "")
        options = response.get("decision_options", [])
        if options:
            decision = options[0] if isinstance(options, list) else str(options)

        risk_flags = {
            "has_fomo": response.get("fomo_check", "").lower().count("fomo") > 0,
            "no_emergency_fund": not user_input.get("has_emergency_fund", True),
            "high_concentration": "concentra" in response.get("diversification_check", "").lower(),
        }

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO investor_decisions
                    (ticker, asset_type, user_input, response, decision,
                     model_used, cost_usd, risk_flags,
                     has_fomo, no_emergency_fund, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker,
                    response.get("asset_type", "unknown"),
                    json.dumps(user_input, ensure_ascii=False),
                    json.dumps(response, ensure_ascii=False),
                    decision,
                    model_used,
                    cost_usd,
                    json.dumps(risk_flags),
                    int(risk_flags["has_fomo"]),
                    int(risk_flags["no_emergency_fund"]),
                    _now_iso(),
                ),
            )
            return cur.lastrowid

    def list_decisions(self, ticker: str | None = None, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            if ticker:
                rows = conn.execute(
                    "SELECT * FROM investor_decisions WHERE ticker=? ORDER BY id DESC LIMIT ?",
                    (ticker, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM investor_decisions ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # investor_api_usage
    # ------------------------------------------------------------------

    def record_api_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        endpoint: str = "/task/submit",
        status: str = "ok",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO investor_api_usage
                    (model, prompt_tokens, completion_tokens, cost_usd, endpoint, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    endpoint,
                    status,
                    _now_iso(),
                ),
            )

    def usage_today(self) -> dict[str, Any]:
        today = datetime.now(UTC).date().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) as runs,
                       COALESCE(SUM(prompt_tokens),0)     as prompt_tokens,
                       COALESCE(SUM(completion_tokens),0) as completion_tokens,
                       COALESCE(SUM(cost_usd),0.0)        as cost_usd
                FROM investor_api_usage
                WHERE created_at LIKE ?
                """,
                (f"{today}%",),
            ).fetchone()
        return dict(row) if row else {}

    # ------------------------------------------------------------------
    # investor_watchlist
    # ------------------------------------------------------------------

    def add_to_watchlist(self, ticker: str, notes: str = "") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO investor_watchlist (ticker, notes, added_at) VALUES (?, ?, ?)",
                (ticker, notes, _now_iso()),
            )
            return cur.lastrowid

    def get_watchlist(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM investor_watchlist ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # investor_notes
    # ------------------------------------------------------------------

    def add_note(self, note: str, ticker: str | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO investor_notes (ticker, note, created_at) VALUES (?, ?, ?)",
                (ticker, note, _now_iso()),
            )
            return cur.lastrowid

    def list_notes(self, ticker: str | None = None, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            if ticker:
                rows = conn.execute(
                    "SELECT * FROM investor_notes WHERE ticker=? ORDER BY id DESC LIMIT ?",
                    (ticker, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM investor_notes ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]


# Singleton (thread-safe)
_storage: InvestorStorage | None = None
_storage_lock: _threading.Lock = _threading.Lock()


def get_investor_storage() -> InvestorStorage:
    global _storage
    if _storage is None:
        with _storage_lock:
            if _storage is None:
                _storage = InvestorStorage()
    return _storage
