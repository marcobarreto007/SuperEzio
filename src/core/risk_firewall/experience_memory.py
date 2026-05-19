"""Local deterministic experience retrieval for SDCA-Lite."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from core.paths import project_path

from .sdca_contracts import DecisionCandidate, ExperienceEpisode, ExperienceMatch, GhostTokenReport

DEFAULT_MEMORY_PATH = project_path("data", "sdca_experience_memory.jsonl")


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{k} {_flatten(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten(v) for v in value)
    return str(value)


def _tokenize(value: Any) -> set[str]:
    text = _flatten(value).lower()
    tokens = {text} if text and len(text) <= 80 else set()
    tokens.update(t for t in re.split(r"[^a-z0-9_]+", text) if len(t) >= 2)
    tokens.update(part for token in list(tokens) for part in token.split("_") if len(part) >= 2)
    return tokens


def _candidate_terms(candidate: DecisionCandidate) -> set[str]:
    return _tokenize(
        {
            "asset": candidate.asset,
            "action": candidate.action,
            "thesis": candidate.thesis,
            "risk_context": candidate.risk_context,
            "raw_signals": candidate.raw_signals,
        }
    )


def _episode_terms(episode: ExperienceEpisode) -> set[str]:
    return _tokenize(
        {
            "vector_text": episode.vector_text,
            "root_cause": episode.root_cause,
            "consequence": episode.consequence,
            "learned_rule": episode.learned_rule,
            "tags": episode.tags,
            "regime": episode.regime,
        }
    )


def _extract_regime(candidate: DecisionCandidate) -> str | None:
    for source in (candidate.risk_context, candidate.raw_signals):
        for key in ("regime", "market_regime", "liquidity_regime", "volatility_regime"):
            raw = source.get(key)
            if raw not in (None, ""):
                return str(raw).lower()
    return None


def load_experience_memory(memory_path: str | Path | None = None) -> list[ExperienceEpisode]:
    """Load local JSONL episodes. Invalid rows are skipped, never fatal."""

    path = Path(memory_path) if memory_path else DEFAULT_MEMORY_PATH
    if not path.exists():
        return []

    episodes: list[ExperienceEpisode] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            try:
                episodes.append(ExperienceEpisode.model_validate_json(raw))
            except Exception:
                continue
    return episodes


def _normalise_ghost_tokens(
    ghost_tokens: Iterable[str] | Iterable[GhostTokenReport],
) -> list[str]:
    tokens: list[str] = []
    for item in ghost_tokens:
        if isinstance(item, GhostTokenReport):
            tokens.extend(item.ghost_tokens)
        else:
            tokens.append(str(item))
    return sorted({t for t in tokens if t})


def _regime_similarity(candidate_regime: str | None, episode_regime: str | None) -> float:
    if not candidate_regime or not episode_regime:
        return 0.75
    if candidate_regime == episode_regime.lower():
        return 1.0
    if candidate_regime in episode_regime.lower() or episode_regime.lower() in candidate_regime:
        return 0.85
    return 0.45


def _evidence_quality(
    candidate: DecisionCandidate,
    episode: ExperienceEpisode,
    ghost_set: set[str],
    candidate_terms: set[str],
) -> float:
    episode_tag_terms = _tokenize(episode.tags)
    overlap = len((ghost_set | candidate_terms) & episode_tag_terms)
    quality = 0.55 + min(0.25, overlap * 0.08)
    if candidate.asset:
        quality += 0.05
    if candidate.amount_cad is not None:
        quality += 0.05
    if candidate.raw_signals:
        quality += 0.05
    if candidate.risk_context:
        quality += 0.05
    return _clamp(quality)


def retrieve_experiences(
    ghost_tokens: Iterable[str] | Iterable[GhostTokenReport],
    candidate: DecisionCandidate,
    top_k: int = 3,
    memory_path: str | Path | None = None,
) -> list[ExperienceMatch]:
    """Retrieve similar SDCA episodes with conservative deterministic scoring."""

    episodes = load_experience_memory(memory_path)
    if not episodes:
        return []

    tokens = _normalise_ghost_tokens(ghost_tokens)
    ghost_set = set(tokens)
    query_terms = _candidate_terms(candidate) | _tokenize(tokens)
    candidate_regime = _extract_regime(candidate)

    matches: list[ExperienceMatch] = []
    for episode in episodes:
        terms = _episode_terms(episode)
        if not query_terms:
            similarity = 0.0
        else:
            ghost_overlap = len((ghost_set | _tokenize(tokens)) & terms) / max(
                len(ghost_set | _tokenize(tokens)),
                1,
            )
            word_overlap = len(query_terms & terms) / max(len(query_terms), 1)
            similarity = _clamp((0.70 * ghost_overlap) + (0.30 * word_overlap))

        regime_similarity = _regime_similarity(candidate_regime, episode.regime)
        evidence_quality = _evidence_quality(candidate, episode, ghost_set, query_terms)
        weighted_score = similarity * abs(episode.delta_r) * regime_similarity * evidence_quality
        if weighted_score <= 0:
            continue
        matches.append(
            ExperienceMatch(
                episode_id=episode.id,
                similarity=round(similarity, 4),
                delta_r=episode.delta_r,
                weighted_score=round(weighted_score, 4),
                learned_rule=episode.learned_rule,
                consequence=episode.consequence,
            )
        )

    matches.sort(key=lambda item: item.weighted_score, reverse=True)
    return matches[: max(0, top_k)]
