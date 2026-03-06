"""
f51 unified core — memória episódica.
Aprendizado cross-domínio via similaridade de padrões.
"""

from __future__ import annotations
import json
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """Um episódio: o que foi decidido, o que aconteceu."""

    key: str  # hash único
    domain: str = ""  # trading, math, code_review, ...
    input_text: str = ""
    features: dict[str, float] = field(default_factory=dict)
    danger_level: float = 0.0
    decision: str = ""
    outcome: float = 0.0  # 1.0 = sucesso, 0.0 = falha, -1 = desconhecido
    outcome_label: str = ""  # "success", "failure", "pending"
    timestamp: str = ""
    pattern_ids: list[str] = field(default_factory=list)

    @staticmethod
    def make_key(text: str, domain: str) -> str:
        raw = f"{domain}:{text.strip()[:200]}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]


class EpisodeMemory:
    """Memória de episódios com busca por similaridade textual.

    Não depende de FAISS/embeddings — usa overlap de palavras-chave
    para ambientes sem GPU. Escalável para ~10k episódios.
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.episodes: dict[str, Episode] = {}
        self._dirty = False
        if self.path and self.path.exists():
            self._load()

    def store(self, episode: Episode):
        self.episodes[episode.key] = episode
        self._dirty = True
        if len(self.episodes) % 10 == 0 and self.path:
            self._save()

    def find_similar(
        self, text: str, domain: str = "", top_k: int = 3
    ) -> list[Episode]:
        """Busca episódios similares por sobreposição de tokens."""
        tokens = set(text.lower().split())
        scored: list[tuple[float, Episode]] = []

        for ep in self.episodes.values():
            if domain and ep.domain != domain:
                continue
            ep_tokens = set(ep.input_text.lower().split())
            if not ep_tokens:
                continue
            overlap = len(tokens & ep_tokens) / max(len(tokens | ep_tokens), 1)
            if overlap > 0.15:
                scored.append((overlap, ep))

        scored.sort(key=lambda x: -x[0])
        return [s[1] for s in scored[:top_k]]

    def find_by_pattern(self, pattern_id: str, top_k: int = 5) -> list[Episode]:
        """Busca episódios pelo mesmo padrão (SpiderSense)."""
        matches = [ep for ep in self.episodes.values() if pattern_id in ep.pattern_ids]
        matches.sort(key=lambda e: abs(e.outcome), reverse=True)
        return matches[:top_k]

    def stats(self) -> dict[str, Any]:
        n_ok = sum(1 for e in self.episodes.values() if e.outcome_label == "success")
        n_fail = sum(1 for e in self.episodes.values() if e.outcome_label == "failure")
        domains = set(e.domain for e in self.episodes.values())
        return {
            "total": len(self.episodes),
            "success": n_ok,
            "failure": n_fail,
            "domains": sorted(domains),
        }

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for item in data:
                ep = Episode(**item)
                self.episodes[ep.key] = ep
        except Exception as exc:
            logger.warning("[F51_MEMORY] failed to load %s: %s", self.path, exc)

    def _save(self):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [vars(ep) for ep in self.episodes.values()]
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._dirty = False

    def flush(self):
        if self._dirty and self.path:
            self._save()
