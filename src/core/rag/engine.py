"""
Semantic Forensic RAG — Embedding-based fraud intelligence retrieval.
Indexes fraud patterns, red-flag rules, and enforcement cases.
Falls back to keyword search if sentence-transformers is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from core.paths import resolve_project_path
from core.storage.atomic import atomic_write_bytes, atomic_write_text

logger = logging.getLogger(__name__)

# ── Config from env ────────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("SUPEREZIO_RAG_MODEL", "all-MiniLM-L6-v2")
TOP_K = int(os.getenv("SUPEREZIO_RAG_TOP_K", "5"))
MAX_CONTEXT_CHARS = int(os.getenv("SUPEREZIO_RAG_CONTEXT_MAX_CHARS", "2500"))
RAG_DISABLED = os.getenv("SUPEREZIO_RAG_DISABLED", "0").lower() in {"1", "true", "yes"}
FAISS_INDEX_DIR = os.getenv("SUPEREZIO_RAG_INDEX_DIR", "data/faiss_index")

# ── Singleton state ────────────────────────────────────────────────────
_embedder: Any = None  # SentenceTransformer | None
_embeddings_cache: np.ndarray | None = None  # (N, dim) normalized
_documents_cache: list[dict[str, Any]] = []
_faiss_index: Any = None  # faiss.Index | None
_faiss_available: bool | None = None  # tri-state: None=unchecked, True/False
_index_data_dir: str | None = None  # which data_dir the cache was built for


class ForensicRAG:
    """Semantic forensic RAG for fraud, scams, insider trading, and manipulation patterns.

    Also ingests paper trading journal entries from data/paper_trades_rag/
    so Bob can query real paper trading history.
    """

    def __init__(self, data_dir: str = "data/fraud_patterns"):
        self.data_dir = str(resolve_project_path(data_dir))
        # Additional data sources scanned alongside the main directory
        self._extra_dirs: list[str] = []
        paper_trades_dir = str(resolve_project_path("data/paper_trades_rag"))
        if Path(paper_trades_dir).exists():
            self._extra_dirs.append(paper_trades_dir)
        self._loaded = False

    # ── Document ingestion ─────────────────────────────────────────────

    def _load_documents(self) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        dirs_to_scan = [self.data_dir] + self._extra_dirs

        for directory in dirs_to_scan:
            if not os.path.exists(directory):
                continue
            for fname in sorted(os.listdir(directory)):
                fpath = os.path.join(directory, fname)
                try:
                    if fname.endswith(".json"):
                        docs.extend(self._ingest_json(fpath))
                    elif fname.endswith(".jsonl"):
                        docs.extend(self._ingest_jsonl(fpath))
                except (json.JSONDecodeError, OSError, ValueError):
                    pass
        return docs

    def _ingest_json(self, path: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return docs

        for pattern in payload.get("patterns", []):
            if not isinstance(pattern, dict):
                continue
            text = (
                f"[PATTERN] {pattern.get('name', '')}: {pattern.get('description', '')} "
                f"Red flags: {' '.join(pattern.get('typical_red_flags') or [])}. "
                f"Regulatory basis: {' '.join(pattern.get('regulatory_references') or [])}. "
                f"Asset classes: {' '.join(pattern.get('asset_classes') or [])}. "
                f"Risk weight: {pattern.get('risk_weight', 'N/A')}."
            )
            docs.append(
                {
                    "id": pattern.get("pattern_id", ""),
                    "text": text,
                    "source": os.path.basename(path),
                }
            )

        for rule in payload.get("rules", []):
            if not isinstance(rule, dict):
                continue
            text = (
                f"[RULE] {rule.get('name', '')}: {rule.get('description', '')} "
                f"Condition: {rule.get('condition', '')}. "
                f"Weight: {rule.get('weight', 'N/A')}. "
                f"Patterns: {' '.join(rule.get('matched_patterns') or [])}. "
                f"{rule.get('note', '')}"
            )
            docs.append(
                {
                    "id": rule.get("rule_id", ""),
                    "text": text,
                    "source": os.path.basename(path),
                }
            )
        return docs

    def _ingest_jsonl(self, path: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                text = (
                    f"[CASE] {row.get('case_type', '')}: {row.get('summary', '')} "
                    f"Red flags: {' '.join(row.get('known_red_flags') or [])}. "
                    f"Notes: {row.get('notes', '')}"
                )
                docs.append(
                    {
                        "id": row.get("case_id", row.get("case_type", "")),
                        "text": text,
                        "source": os.path.basename(path),
                    }
                )
        return docs

    # ── Embedding model ────────────────────────────────────────────────

    def _get_embedder(self):
        global _embedder
        if _embedder is not None:
            return _embedder
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
        except ImportError:
            logger.warning("sentence-transformers not installed — RAG will use keyword fallback")
            _embedder = None
            return None
        try:
            _embedder = SentenceTransformer(EMBEDDING_MODEL)
            _embedder.to("cpu")
            logger.info("ForensicRAG embedder loaded: %s (CPU)", EMBEDDING_MODEL)
        except Exception as exc:
            logger.warning("Failed to load embedding model: %s — keyword fallback active", exc)
            _embedder = None
        return _embedder

    # ── FAISS helpers ─────────────────────────────────────────────────

    @staticmethod
    def _faiss_available() -> bool:
        global _faiss_available
        if _faiss_available is not None:
            return _faiss_available
        try:
            import faiss  # noqa: F401  # tested via availability flag

            _faiss_available = True
        except ImportError:
            logger.info("faiss-cpu not installed — using numpy brute-force search")
            _faiss_available = False
        return _faiss_available

    # ── Index ──────────────────────────────────────────────────────────

    def _ensure_index(self) -> bool:
        global _embeddings_cache, _documents_cache, _faiss_index, _index_data_dir
        if _embeddings_cache is not None and _index_data_dir == self.data_dir:
            return True

        embedder = self._get_embedder()
        docs = self._load_documents()
        _documents_cache = docs
        _index_data_dir = self.data_dir

        if not docs:
            logger.info("ForensicRAG: no documents to index")
            return False

        if embedder is None:
            return False

        texts = [d["text"] for d in docs]
        try:
            vecs = embedder.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            _embeddings_cache = vecs
            logger.info("ForensicRAG indexed %d documents (%d-dim)", len(docs), vecs.shape[1])

            if self._faiss_available():
                import faiss  # type: ignore[import]

                dim = vecs.shape[1]
                _faiss_index = faiss.IndexFlatIP(dim)
                _faiss_index.add(vecs.astype(np.float32))
                logger.info("ForensicRAG FAISS index built: %d vectors", _faiss_index.ntotal)

            return True
        except Exception as exc:
            logger.warning("Embedding failed: %s — keyword fallback active", exc)
            _embeddings_cache = None
            return False

    # ── Search ─────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = TOP_K) -> list[dict[str, Any]]:
        """Semantic search. Falls back to keyword if embeddings unavailable."""
        if os.getenv("SUPEREZIO_RAG_DISABLED", "0").lower() in {"1", "true", "yes"}:
            return []
        query = (query or "").strip()
        if not query:
            return []

        if not self._ensure_index():
            return self._keyword_search(query, top_k)

        embedder = self._get_embedder()
        try:
            qvec = embedder.encode(
                [query],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception:
            return self._keyword_search(query, top_k)

        global _faiss_index
        if _faiss_index is not None:
            qvec_f32 = qvec.astype(np.float32)
            scores, indices = _faiss_index.search(qvec_f32, min(top_k, _faiss_index.ntotal))
            results = []
            for i in range(len(indices[0])):
                idx = int(indices[0][i])
                score = float(scores[0][i])
                if idx < 0 or score <= 0.1:
                    continue
                results.append(
                    {
                        "id": _documents_cache[idx]["id"],
                        "text": _documents_cache[idx]["text"],
                        "source": _documents_cache[idx]["source"],
                        "score": score,
                    }
                )
            return results

        scores = (qvec @ _embeddings_cache.T)[0]  # cosine similarity (normalized vectors)
        top_idx = np.argsort(scores)[::-1][:top_k]
        return [
            {
                "id": _documents_cache[i]["id"],
                "text": _documents_cache[i]["text"],
                "source": _documents_cache[i]["source"],
                "score": float(scores[i]),
            }
            for i in top_idx
            if scores[i] > 0.1
        ]

    def _keyword_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Degradation path: pure keyword overlap search."""
        global _documents_cache
        if not _documents_cache:
            _documents_cache = self._load_documents()
        docs = _documents_cache
        if not docs:
            return []

        kw = [k.lower() for k in query.replace(",", " ").split() if len(k) > 3]
        if not kw:
            return []

        scored = []
        for d in docs:
            t = d["text"].lower()
            s = sum(1 for k in kw if k in t)
            if s > 0:
                scored.append({**d, "score": float(s)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # ── Format ─────────────────────────────────────────────────────────

    def format_context(
        self, results: list[dict[str, Any]], max_chars: int = MAX_CONTEXT_CHARS
    ) -> str:
        """Format search results as a CEO-readable RAG_FORENSICS block."""
        if not results:
            return "[RAG_FORENSICS]\nNo forensic pattern matches found for this query."

        lines = ["[RAG_FORENSICS] — Historical fraud intelligence:"]
        used = len(lines[0])
        for i, r in enumerate(results, 1):
            snippet = r["text"][:400]
            entry = f"\n{i}. [{r['id']}] (src={r['source']}, sim={r['score']:.2f})\n   {snippet}"
            if used + len(entry) > max_chars:
                lines.append(f"\n... truncated ({len(results) - i + 1} results omitted)")
                break
            lines.append(entry)
            used += len(entry)
        return "".join(lines)

    # ── Runtime expansion ──────────────────────────────────────────────

    def add_document(self, doc_id: str, text: str, source: str = "runtime"):
        """Add a document at runtime. Updates FAISS index incrementally if available."""
        global _embeddings_cache, _faiss_index
        _documents_cache.append({"id": doc_id, "text": text, "source": source})

        embedder = self._get_embedder()
        if embedder is not None and _faiss_index is not None:
            try:
                vec = embedder.encode(
                    [text],
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ).astype(np.float32)
                _faiss_index.add(vec)
                if _embeddings_cache is not None:
                    _embeddings_cache = np.vstack([_embeddings_cache, vec])
                logger.debug("ForensicRAG: document %s added to FAISS index", doc_id)
                return
            except Exception:
                pass

        _embeddings_cache = None
        logger.debug("ForensicRAG: added document %s, cache invalidated", doc_id)

    # ── Index persistence ──────────────────────────────────────────────

    def save_index(self, path: str | None = None):
        """Persist a safe immutable generation and atomically publish it."""
        global _faiss_index, _documents_cache

        target = Path(resolve_project_path(path or FAISS_INDEX_DIR))
        generation_id = uuid.uuid4().hex
        generation = target / "generations" / generation_id
        generation.mkdir(parents=True, exist_ok=False)

        documents = [
            {
                "id": str(document.get("id") or ""),
                "text": str(document.get("text") or ""),
                "source": str(document.get("source") or ""),
            }
            for document in _documents_cache
        ]
        documents_bytes = "".join(
            json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n"
            for document in documents
        ).encode("utf-8")
        atomic_write_bytes(generation / "documents.jsonl", documents_bytes)

        index_hash: str | None = None

        if _faiss_index is not None:
            try:
                import faiss  # type: ignore[import]

                index_bytes = faiss.serialize_index(_faiss_index).tobytes()
                atomic_write_bytes(generation / "index.faiss", index_bytes)
                index_hash = hashlib.sha256(index_bytes).hexdigest()
            except Exception as exc:
                logger.warning("Failed to save FAISS index: %s", exc)

        manifest = {
            "schema_version": 1,
            "generation": generation_id,
            "created_at": datetime.now(UTC).isoformat(),
            "document_count": len(documents),
            "documents_sha256": hashlib.sha256(documents_bytes).hexdigest(),
            "index_sha256": index_hash,
            "embedding_model": EMBEDDING_MODEL,
        }
        atomic_write_text(
            generation / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        )
        atomic_write_text(target / "CURRENT", generation_id + "\n")
        logger.info("ForensicRAG: index generation %s saved to %s", generation_id, target)

    def load_index(self, path: str | None = None):
        """Load and verify the atomically published safe generation."""
        global _faiss_index, _documents_cache, _embeddings_cache

        target = Path(resolve_project_path(path or FAISS_INDEX_DIR))
        current_path = target / "CURRENT"
        if not current_path.exists():
            logger.info("ForensicRAG: no persisted index at %s", target)
            return False

        try:
            generation_id = current_path.read_text(encoding="utf-8").strip()
            if not generation_id or any(char not in "0123456789abcdef" for char in generation_id):
                raise ValueError("invalid RAG generation id")
            generation = target / "generations" / generation_id
            manifest = json.loads((generation / "manifest.json").read_text(encoding="utf-8"))
            if manifest.get("schema_version") != 1 or manifest.get("generation") != generation_id:
                raise ValueError("unsupported or mismatched RAG manifest")

            documents_bytes = (generation / "documents.jsonl").read_bytes()
            if hashlib.sha256(documents_bytes).hexdigest() != manifest.get("documents_sha256"):
                raise ValueError("RAG documents hash mismatch")
            documents = [
                json.loads(line)
                for line in documents_bytes.decode("utf-8").splitlines()
                if line.strip()
            ]
            if len(documents) != manifest.get("document_count") or any(
                not isinstance(document, dict) or not {"id", "text", "source"}.issubset(document)
                for document in documents
            ):
                raise ValueError("RAG document manifest count/schema mismatch")
            _documents_cache = documents

            index_path = generation / "index.faiss"
            if index_path.exists() and self._faiss_available():
                import faiss  # type: ignore[import]

                index_bytes = index_path.read_bytes()
                if hashlib.sha256(index_bytes).hexdigest() != manifest.get("index_sha256"):
                    raise ValueError("RAG FAISS index hash mismatch")
                _faiss_index = faiss.deserialize_index(np.frombuffer(index_bytes, dtype=np.uint8))
                _embeddings_cache = None  # re-computed on demand
                logger.info(
                    "ForensicRAG: loaded index from %s (%d docs, %d vectors)",
                    generation,
                    len(_documents_cache),
                    _faiss_index.ntotal,
                )
            else:
                _embeddings_cache = None  # re-compute on next search
                logger.info(
                    "ForensicRAG: loaded %d documents (no FAISS index)",
                    len(_documents_cache),
                )
            return True
        except Exception as exc:
            logger.warning("Failed to load index: %s", exc)
            return False


# ── Module-level singleton ─────────────────────────────────────────────
forensic_rag = ForensicRAG()
