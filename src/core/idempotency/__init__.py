"""Idempotency and deduplication for trade orders.

Prevents duplicate order submission across:
- Process restarts (persistent dedup via journal)
- Network retries (deterministic idempotency key)
- Concurrent submissions (dead letter queue for failed writes)

Design contract:
- Idempotency key = sha256(ticker|qty|limit_price|window_5min)
- Same intent → same key → detected as duplicate
- Dead letter queue at journal/dead_letter/ for orders that failed to persist
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.config.logging_config import get_logger
from core.paths import resolve_project_path

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════
# Idempotency Key
# ═══════════════════════════════════════════════════════════════


def make_idempotency_key(
    ticker: str,
    qty: int,
    limit_price: float,
    window_minutes: int = 5,
    *,
    now: datetime | None = None,
) -> str:
    """Generate a deterministic idempotency key for a trade order.

    Same ticker+qty+price within the same time window → same key.
    This prevents duplicate submission across retries and restarts.

    The 5-minute window means if you genuinely want to submit the same
    order again after 5 minutes, it gets a NEW key (it's a new intent).

    NOTE: the window is truncated against the wall clock, so this key alone
    has a boundary hole — 10:04:59 and 10:05:01 land in different windows.
    Callers guarding real submissions must use `make_idempotency_keys` and
    `claim_idempotency_keys`, which cover the previous window too.
    """
    # Truncate timestamp to window boundary
    current = now or datetime.now(UTC)
    window_epoch = int(current.timestamp() / (window_minutes * 60)) * (window_minutes * 60)

    payload = f"{ticker.upper()}|{int(qty)}|{limit_price:.2f}|{window_epoch}"
    key = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"idem-{key}"


def make_idempotency_keys(
    ticker: str,
    qty: int,
    limit_price: float,
    window_minutes: int = 5,
    *,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Return the current-window key plus the previous-window one.

    A retry seconds after the first attempt can straddle a window boundary and
    would otherwise get a brand-new key — defeating dedup exactly when a retry
    is most likely. Checking both windows closes that edge without changing
    what a key means: past two windows it is genuinely a new intent.
    """
    current = now or datetime.now(UTC)
    return (
        make_idempotency_key(ticker, qty, limit_price, window_minutes, now=current),
        make_idempotency_key(
            ticker,
            qty,
            limit_price,
            window_minutes,
            now=current - timedelta(minutes=window_minutes),
        ),
    )


def claim_idempotency_keys(
    keys: tuple[str, ...] | list[str],
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Claim every key that denotes one intent; a lost claim means duplicate.

    Claiming only the current window would leave the boundary race open: two
    concurrent attempts landing either side of it would each win their own key
    and both submit. Requiring all keys means exactly one caller proceeds.
    """
    return all(mark_processed(key, metadata) for key in keys)


# ═══════════════════════════════════════════════════════════════
# Persistent Dedup
# ═══════════════════════════════════════════════════════════════


def _ensure_dedup_dir() -> Path:
    # O default e ancorado na raiz do projeto (via resolve_project_path), nunca
    # no cwd: um boot de outro diretorio criaria um dedup novo e reabriria a
    # janela de duplicata cross-restart. Env continua valendo para testes e
    # para o modo -IsolatedValidation (start.ps1).
    configured = os.getenv("SUPEREZIO_DEDUP_DIR", "").strip()
    directory = Path(configured) if configured else resolve_project_path("journal/dedup")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def is_duplicate(idempotency_key: str) -> bool:
    """Check if this idempotency key has already been processed.

    Returns True if the key was seen before (duplicate), False if new.

    NOTE: this is a plain existence check and is NOT atomic by itself.
    Concurrent callers must use `mark_processed` (which claims the key
    atomically) and treat a claim failure as "duplicate" — see the
    check-then-claim pattern used in `auto_execute_paper.py`.
    """
    dedup_file = _ensure_dedup_dir() / f"{idempotency_key}.json"
    return dedup_file.exists()


def mark_processed(idempotency_key: str, metadata: dict[str, Any] | None = None) -> bool:
    """Atomically claim this idempotency key as processed.

    Writes a marker file to journal/dedup/ for cross-process dedup using
    an exclusive create (O_CREAT|O_EXCL) so two concurrent callers racing
    on the same key cannot both "win" — the loser gets FileExistsError and
    this returns False instead of silently overwriting the winner's record.

    Returns True if this call claimed the key (first writer), False if the
    key was already claimed by another concurrent/prior call (duplicate).
    """
    dedup_file = _ensure_dedup_dir() / f"{idempotency_key}.json"
    record = {
        "idempotency_key": idempotency_key,
        "processed_at": datetime.now(UTC).isoformat(),
        "metadata": metadata or {},
    }
    payload = json.dumps(record, ensure_ascii=False).encode("utf-8")
    try:
        fd = os.open(dedup_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        logger.warning("idempotency_key_race_lost", key=idempotency_key)
        return False
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(fd, payload[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)
    logger.info("idempotency_key_recorded", key=idempotency_key)
    return True


# ═══════════════════════════════════════════════════════════════
# Dead Letter Queue
# ═══════════════════════════════════════════════════════════════


def _ensure_dead_letter_dir() -> Path:
    # Mesma regra do dedup: ancorado na raiz do projeto, nunca no cwd.
    configured = os.getenv("SUPEREZIO_DEAD_LETTER_DIR", "").strip()
    directory = Path(configured) if configured else resolve_project_path("journal/dead_letter")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def enqueue_dead_letter(
    ticker: str,
    qty: int,
    limit_price: float,
    action: str,
    reason: str,
    state_snapshot: dict[str, Any] | None = None,
) -> str:
    """Save a failed/cancelled order to the dead letter queue for manual replay.

    Called when:
    - Journal write fails
    - IBKR submission times out after retries
    - Any order that was ALLOWED by gate but failed execution

    Returns the dead letter file path.
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    filename = f"{timestamp}_{ticker}_{action}.json"
    dead_file = _ensure_dead_letter_dir() / filename

    record = {
        "dead_letter_id": f"dl-{timestamp}-{ticker}",
        "ticker": ticker.upper(),
        "qty": qty,
        "limit_price": limit_price,
        "action": action,
        "failure_reason": reason,
        "failed_at": datetime.now(UTC).isoformat(),
        "state_snapshot": state_snapshot or {},
        "replay_status": "pending",
    }

    dead_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.warning(
        "dead_letter_enqueued",
        ticker=ticker,
        action=action,
        reason=reason,
        path=str(dead_file),
    )
    return str(dead_file)


def list_dead_letters() -> list[dict[str, Any]]:
    """List all pending dead letter entries."""
    entries: list[dict[str, Any]] = []
    dead_dir = _ensure_dead_letter_dir()
    for f in sorted(dead_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("replay_status") == "pending":
                # O arquivo que materializa a entrada — necessario para o replay
                # (o consumidor re-executa a persistencia e marca o status).
                data["file"] = str(f)
                entries.append(data)
        except Exception:  # noqa: BLE001 — catch amplo deliberado: um dead letter corrompido nao pode quebrar a listagem inteira
            logger.warning("dead_letter_corrupted", file=str(f))
    return entries


def count_dead_letters() -> int:
    """Count pending dead letter entries."""
    return len(list_dead_letters())


def update_dead_letter_status(file: str | Path, *, status: str) -> dict[str, Any]:
    """Mark one dead letter file as ``done`` or ``failed`` after a replay attempt.

    Write is atomic (tmp file + os.replace) so a crash mid-update never
    corrupts the queue entry. Callers re-read the updated record.
    """
    if status not in {"done", "failed"}:
        raise ValueError(f"invalid dead letter status: {status!r}")
    path = Path(file)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["replay_status"] = status
    record["replayed_at"] = datetime.now(UTC).isoformat()
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)
    logger.info("dead_letter_status_updated", file=str(path), status=status)
    return record
