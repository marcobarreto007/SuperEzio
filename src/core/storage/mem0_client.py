"""
Mem0 Memory Wrapper
-------------------
Camada de memÛria persistente com dois modos:
- Remoto: integra com uma API compatÌvel (api_url + api_key)
- Local: fallback simples em JSON para n„o quebrar execuÁ„o
"""

import json
import time
import uuid
import hashlib
import logging

from pathlib import Path
from typing import List, Dict, Any, Optional

import requests

from ..observability.debug_logger import debug_logger, MODULE_MEMORY

logger = logging.getLogger(__name__)


class MemoryNotConfigured(Exception):
    """Levantado quando memÛria est· desabilitada ou sem credenciais."""


class Mem0Memory:
    def __init__(
        self,
        storage_dir: str = "data/memory",
        collection: str = "default",
        api_url: str = "",
        api_key: str = "",
        default_top_k: int = 5,
        redis_url: str = "",
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.storage_dir / f"{collection}_mem0.json"
        self.collection = collection
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.default_top_k = default_top_k
        self.redis_client = None
        self.remote_enabled = bool(self.api_url and self.api_key)
        if not self.file_path.exists():
            self.file_path.write_text("[]", encoding="utf-8")

        # Redis opcional (cache/edge)
        if redis_url:
            try:
                import redis

                self.redis_client = redis.Redis.from_url(redis_url)
                # Teste rápido de conexão
                self.redis_client.ping()
            except Exception as e:
                logger.warning("Mem0 redis disabled (connection error): %s", e)
                self.redis_client = None

    # ========== Public API ==========
    def _dedup_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove entradas duplicadas por conteúdo similar (user + assistant)."""
        seen: set[str] = set()
        unique: List[Dict[str, Any]] = []
        for e in entries:
            # Hash do conteúdo user+assistant+session_id como fingerprint
            content_key = f"{e.get('session_id', '')}:{e.get('user', '')}:{e.get('assistant', '')}"
            content_hash = hashlib.sha256(content_key.encode()).hexdigest()
            if content_hash not in seen:
                seen.add(content_hash)
                unique.append(e)
        return unique

    def _relevance_score(self, query: str, entry: Dict[str, Any]) -> float:
        """
        Calcula score de relevância entre 0.0 e 1.0.
        Usa:
          - Token overlap simples (palavras)
          - Penalidade para entradas muito antigas
          - Bônus para entradas do mesmo session_id
        """
        query_lower = query.lower()
        text = f"{entry.get('user', '')} {entry.get('assistant', '')}".lower()
        query_tokens = set(query_lower.split())
        text_tokens = set(text.split())

        if not query_tokens or not text_tokens:
            return 0.0

        # Jaccard similarity
        intersection = query_tokens & text_tokens
        union = query_tokens | text_tokens
        jaccard = len(intersection) / len(union) if union else 0.0

        # Time decay: entradas mais recentes > 0.5, mais velhas decay linear
        age = time.time() - entry.get("ts", 0)
        time_bonus = max(0.0, 1.0 - age / 86400.0)  # Decai em 24h

        # Bônus exact match de frases inteiras
        exact_bonus = 0.2 if query_lower in text else 0.0

        return min(1.0, jaccard * 0.6 + time_bonus * 0.3 + exact_bonus * 0.1)

    def add(
        self,
        user_message: str,
        assistant_message: str,
        session_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Salva turno de conversa com dedup prévio."""
        payload = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user": user_message,
            "assistant": assistant_message,
            "metadata": metadata or {},
            "ts": time.time(),
        }
        debug_logger.trace(
            MODULE_MEMORY,
            "Mem0.add",
            session_id=session_id,
            mode="local" if not self.remote_enabled else "remote",
            msg_preview=user_message[:50],
        )

        # Dedup no local antes de salvar
        if not self.remote_enabled and not self.redis_client:
            try:
                existing = json.loads(self.file_path.read_text(encoding="utf-8"))
                deduped = self._dedup_entries(existing + [payload])
                # Se depois de dedup o tamanho não mudou, é duplicata — skip
                if len(deduped) == len(existing):
                    debug_logger.trace(MODULE_MEMORY, "Mem0.add: duplicate skipped")
                    return
                self.file_path.write_text(
                    json.dumps(deduped, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                debug_logger.trace(
                    MODULE_MEMORY, "Mem0.add: saved locally", entries=len(deduped)
                )
                return
            except Exception as exc:
                debug_logger.debug(
                    MODULE_MEMORY, "Mem0.add local dedup error", error=str(exc)
                )

        if self.remote_enabled:
            try:
                self._push_remote(payload)
                debug_logger.trace(MODULE_MEMORY, "Mem0.add: pushed remote")
                return
            except Exception as e:
                logger.warning("Mem0 remote failed, falling back to local: %s", e)
                debug_logger.debug(
                    MODULE_MEMORY, "Mem0.add remote fallback", error=str(e)
                )

        if self.redis_client:
            try:
                self._append_redis(payload)
                debug_logger.trace(MODULE_MEMORY, "Mem0.add: appended redis")
                return
            except Exception as e:
                logger.warning("Mem0 redis failed, falling back to local: %s", e)
                debug_logger.debug(
                    MODULE_MEMORY, "Mem0.add redis fallback", error=str(e)
                )

        self._append_local(payload)
        debug_logger.trace(MODULE_MEMORY, "Mem0.add: local fallback done")

    def search(
        self,
        query: str,
        session_id: str = "default",
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Recupera contexto relevante."""
        k = top_k or self.default_top_k
        debug_logger.trace(
            MODULE_MEMORY,
            "Mem0.search",
            session_id=session_id,
            query_preview=query[:50],
            top_k=k,
        )
        if self.remote_enabled:
            try:
                results = self._query_remote(query, session_id, k)
                debug_logger.trace(
                    MODULE_MEMORY, "Mem0.search: remote results", count=len(results)
                )
                return results
            except Exception as e:
                logger.warning("Mem0 remote search failed, using local: %s", e)
                debug_logger.debug(
                    MODULE_MEMORY, "Mem0.search remote fallback", error=str(e)
                )

        if self.redis_client:
            try:
                results = self._query_redis(query, session_id, k)
                debug_logger.trace(
                    MODULE_MEMORY, "Mem0.search: redis results", count=len(results)
                )
                return results
            except Exception as e:
                logger.warning("Mem0 redis search failed, using local: %s", e)
                debug_logger.debug(
                    MODULE_MEMORY, "Mem0.search redis fallback", error=str(e)
                )

        results = self._query_local(query, session_id, k)
        debug_logger.trace(
            MODULE_MEMORY, "Mem0.search: local results", count=len(results)
        )
        return results

    # ========== Remote mode ==========
    def _push_remote(self, payload: Dict[str, Any]) -> None:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.api_url}/collections/{self.collection}/memories"
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()

    def _query_remote(
        self, query: str, session_id: str, top_k: int
    ) -> List[Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.api_url}/collections/{self.collection}/search"
        payload = {"query": query, "session_id": session_id, "top_k": top_k}
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Espera lista de documentos; se formato diferente, devolve raw
        if isinstance(data, list):
            return data
        if "results" in data:
            return data["results"]
        return []

    # ========== Local mode ==========
    def _append_local(self, payload: Dict[str, Any]) -> None:
        try:
            entries = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            entries = []
        entries.append(payload)
        self.file_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _query_local(
        self, query: str, session_id: str, top_k: int
    ) -> List[Dict[str, Any]]:
        """Busca simples por substring (fallback)."""
        try:
            entries = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            entries = []

        filtered = [e for e in entries if e.get("session_id") == session_id]
        if not filtered:
            return []

        # Ranking rudimentar: contagem de tokens compartilhados
        tokens = set(query.lower().split())

        def score(entry):
            text = f"{entry.get('user', '')} {entry.get('assistant', '')}".lower()
            return sum(1 for t in tokens if t in text)

        scored = sorted(filtered, key=score, reverse=True)
        return scored[:top_k]

    # ========== Redis mode ==========
    def _append_redis(self, payload: Dict[str, Any]) -> None:
        key = f"mem0:{self.collection}:{payload.get('session_id', 'default')}"
        self.redis_client.lpush(key, json.dumps(payload, ensure_ascii=False))
        # limita tamanho para evitar crescimento infinito
        self.redis_client.ltrim(key, 0, 499)

    def _query_redis(
        self, query: str, session_id: str, top_k: int
    ) -> List[Dict[str, Any]]:
        key = f"mem0:{self.collection}:{session_id}"
        raw_items = self.redis_client.lrange(key, 0, 499)
        if not raw_items:
            return []
        entries = []
        for raw in raw_items:
            try:
                entries.append(json.loads(raw))
            except Exception:
                continue
        tokens = set(query.lower().split())

        def score(entry):
            text = f"{entry.get('user', '')} {entry.get('assistant', '')}".lower()
            return sum(1 for t in tokens if t in text)

        scored = sorted(entries, key=score, reverse=True)
        return scored[:top_k]
