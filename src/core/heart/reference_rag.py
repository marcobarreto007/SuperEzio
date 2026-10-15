"""Dynamic reference RAG over the Heart archive.

Documents are ranking rows (symbol, session, return, linked event). The TF-IDF
index refits when events.jsonl or the OHLCV files change. It is a citation
source for Bob, not an order and not a learned weight.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import Any

from core.heart.attribution import attribute_moves
from core.heart.hydrate import refresh_heart_view
from core.heart.ranking import RankingWeights, rank_moves
from core.paths import resolve_project_path
from core.rag.tfidf_rag import TfidfRetriever

logger = logging.getLogger(__name__)

_HEADER = (
    "HEART_REFERENCE:\n"
    "Arquivo do Coracao: movimento de preco ligado ao evento da mesma sessao. "
    "Referencia, nao ordem. Cite so as linhas abaixo, com simbolo e sessao. "
    "Se o simbolo perguntado nao aparecer, diga que o arquivo nao tem esse nome."
)


class _View:
    def __init__(self) -> None:
        self.moves: list[Any] = []
        self.events: list[Any] = []
        self.bars: list[Any] = []


def default_heart_root() -> Path:
    return Path(resolve_project_path("data/heart"))


def default_ohlcv_dir() -> Path:
    return default_heart_root() / "ohlcv"


def disk_signature(heart_root: Path, ohlcv_dir: Path) -> str:
    """Changes when the event book or any price file changes."""
    digest = hashlib.blake2b(digest_size=12)
    events = Path(heart_root) / "events.jsonl"
    if events.is_file():
        stat = events.stat()
        digest.update(f"events:{stat.st_size}:{stat.st_mtime_ns}".encode())
    else:
        digest.update(b"events:missing")
    folder = Path(ohlcv_dir)
    if folder.is_dir():
        for csv_path in sorted(folder.glob("*.csv")):
            stat = csv_path.stat()
            digest.update(f"{csv_path.name}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


def ranking_documents(heart_root: Path, ohlcv_dir: Path) -> list[dict[str, Any]]:
    """One document per ranked move. Empty when the archive has no prices."""
    view = _View()
    refresh_heart_view(view, heart_root=Path(heart_root), ohlcv_dir=Path(ohlcv_dir))
    if not view.moves:
        return []
    attributions = attribute_moves(view.moves, view.events)
    rows = rank_moves(view.moves, RankingWeights.equal(), attributions=attributions)
    return [_document(row) for row in rows]


def _document(row: dict[str, Any]) -> dict[str, Any]:
    attribution = row.get("attribution") or {}
    evidence = attribution.get("evidence") if isinstance(attribution, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    selected = evidence.get("selected") if isinstance(evidence.get("selected"), dict) else {}
    text = (
        f"symbol={row.get('symbol')} mic={row.get('mic_code')} "
        f"session={row.get('session_date')} "
        f"gross_ret={float(row.get('gross_ret') or 0):.4f} "
        f"abnormal_ret={float(row.get('abnormal_ret') or 0):.4f} "
        f"event={attribution.get('event_identity') or 'none'} "
        f"source={selected.get('source') or 'none'} "
        f"event_type={selected.get('event_type') or 'none'} "
        f"confidence={float(attribution.get('confidence') or 0):.2f}"
    )
    return {"id": str(row.get("move_key") or text), "text": text, "source": "heart"}


class HeartReferenceIndex:
    """TF-IDF over Heart ranking rows. Refits only when the disk signature changes."""

    def __init__(self, heart_root: Path | None = None, ohlcv_dir: Path | None = None) -> None:
        self.heart_root = Path(heart_root) if heart_root is not None else default_heart_root()
        self.ohlcv_dir = Path(ohlcv_dir) if ohlcv_dir is not None else default_ohlcv_dir()
        self._retriever = TfidfRetriever(min_score=0.05)
        self._signature = ""
        self._symbols: set[str] = set()
        self._symbol_signature = ""
        self._lock = threading.Lock()

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            return []
        with self._lock:
            if not self._query_mentions_archive(query):
                return []
            self._ensure_locked()
            return self._retriever.search(query, top_k=top_k)

    def format_for_query(self, query: str, *, top_k: int = 5) -> str:
        try:
            hits = self.search(query, top_k=top_k)
        except Exception as exc:  # noqa: BLE001 — reference must not abort the turn
            logger.warning("heart reference search failed: %s", exc)
            return ""
        if not hits:
            return ""
        lines = [_HEADER]
        for hit in hits:
            lines.append(f"- score={float(hit.get('score') or 0):.2f} {hit.get('text')}")
        return "\n".join(lines)

    def _query_mentions_archive(self, query: str) -> bool:
        """Skip the event-book scan unless the question names a priced symbol."""
        symbols = self._known_symbols_locked()
        if not symbols:
            return False
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9.-]{0,11}", query)
        return any(token.upper() in symbols for token in tokens)

    def _known_symbols_locked(self) -> set[str]:
        folder = self.ohlcv_dir
        digest = hashlib.blake2b(digest_size=8)
        if folder.is_dir():
            for csv_path in sorted(folder.glob("*.csv")):
                stat = csv_path.stat()
                digest.update(f"{csv_path.name}:{stat.st_mtime_ns}".encode())
        signature = digest.hexdigest()
        if signature == self._symbol_signature:
            return self._symbols
        symbols: set[str] = set()
        if folder.is_dir():
            for csv_path in folder.glob("*.csv"):
                stem = csv_path.stem.upper()
                symbols.add(stem)
                stem = stem.removesuffix(".TO")
                symbols.add(stem.replace("-", ".", 1) if "-" in stem else stem)
        self._symbols = symbols
        self._symbol_signature = signature
        return symbols

    def _ensure_locked(self) -> None:
        signature = disk_signature(self.heart_root, self.ohlcv_dir)
        if signature == self._signature and self._retriever.ready:
            return
        docs = ranking_documents(self.heart_root, self.ohlcv_dir)
        self._retriever.fit(docs)
        self._signature = signature


heart_reference = HeartReferenceIndex()
