"""Local deterministic experience retrieval for SDCA-Lite."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from core.paths import project_path

from .sdca_contracts import DecisionCandidate, ExperienceEpisode, ExperienceMatch, GhostTokenReport

DEFAULT_MEMORY_PATH = project_path("data", "sdca_experience_memory.jsonl")
FRAUD_PATTERNS_DIR = project_path("data", "fraud_patterns")
EMBEDDING_DIMS = 128


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


def _embedding_text(value: Any) -> str:
    return " ".join(sorted(_tokenize(value)))


def _hashed_embedding(value: Any, dims: int = EMBEDDING_DIMS) -> list[float]:
    """Cheap local embedding: hashed token vector, no model download or network."""

    vector = [0.0] * dims
    for token in _tokenize(value):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return _clamp(sum(a * b for a, b in zip(left, right)))


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


_RED_FLAG_TO_GHOST = {
    "wide_spread": "spread_expansion",
    "extreme_volume_spike": "fake_breakout_possible",
    "price_spike_high_volatility": "fake_breakout_possible",
    "social_media_pump_language": "fomo_pattern_detected",
    "unusual_volume_without_clear_news": "flow_toxicity_high",
    "microcap_concentration": "liquidity_trap_possible",
    "vague_hype_sector_description": "overconfidence_detected",
    "no_revenue_with_operations": "data_quality_low",
    "insider_selling_near_promotion": "flow_toxicity_high",
}


def _map_red_flags(flags: Iterable[Any]) -> list[str]:
    tags: list[str] = []
    for raw in flags:
        flag = str(raw)
        tags.append(flag)
        mapped = _RED_FLAG_TO_GHOST.get(flag)
        if mapped:
            tags.append(mapped)
    return sorted(dict.fromkeys(tags))


def _load_fraud_pattern_episodes() -> list[ExperienceEpisode]:
    """Convert existing local fraud/manipulation knowledge into SDCA episodes."""

    episodes: list[ExperienceEpisode] = []
    patterns_path = FRAUD_PATTERNS_DIR / "fraud_patterns.json"
    cases_path = FRAUD_PATTERNS_DIR / "enforcement_cases.jsonl"

    if patterns_path.exists():
        try:
            data = json.loads(patterns_path.read_text(encoding="utf-8"))
            for item in data.get("patterns", []):
                pattern_id = str(item.get("pattern_id") or item.get("name") or "").strip()
                if not pattern_id:
                    continue
                flags = item.get("typical_red_flags") or []
                risk_weight = float(item.get("risk_weight") or 0.55)
                description = str(item.get("description") or item.get("name") or "")
                episodes.append(
                    ExperienceEpisode(
                        id=f"fraud-pattern-{pattern_id}",
                        vector_text=" ".join([str(item.get("name") or pattern_id), description]),
                        root_cause="Known fraud/manipulation pattern from local fraud_patterns corpus",
                        consequence=description[:500] or "Pattern can distort decision quality.",
                        learned_rule=(
                            "If candidate evidence overlaps this fraud/manipulation pattern, "
                            "raise SDCA uncertainty and require review or block."
                        ),
                        delta_r=_clamp(risk_weight, 0.1, 1.0),
                        tags=_map_red_flags(flags),
                        regime="fraud_pattern",
                    )
                )
        except Exception:  # noqa: BLE001, S110 — corpus local de fraude corrompido não pode quebrar o carregamento; módulo sem logger
            pass

    if cases_path.exists():
        with cases_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                case_id = str(item.get("case_id") or "").strip()
                if not case_id:
                    continue
                confidence = str(item.get("confidence") or "").lower()
                delta_r = 0.85 if confidence == "high" else 0.65 if confidence == "medium" else 0.5
                flags = item.get("known_red_flags") or []
                summary = str(item.get("summary") or "")
                episodes.append(
                    ExperienceEpisode(
                        id=f"fraud-case-{case_id}",
                        vector_text=summary,
                        root_cause=str(item.get("case_type") or "fraud_pattern"),
                        consequence=summary[:500] or "Case indicates known decision risk.",
                        learned_rule=(
                            "If candidate signals match this local enforcement/pattern case, "
                            "treat the decision as latent-risk until reviewed."
                        ),
                        delta_r=delta_r,
                        tags=_map_red_flags(flags),
                        regime=str(item.get("market") or item.get("asset_class") or "fraud_case"),
                    )
                )

    return episodes


def load_experience_memory(memory_path: str | Path | None = None) -> list[ExperienceEpisode]:
    """Load local JSONL episodes plus existing project fraud knowledge."""

    path = Path(memory_path) if memory_path else DEFAULT_MEMORY_PATH
    episodes: list[ExperienceEpisode] = []
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    episodes.append(ExperienceEpisode.model_validate_json(raw))
                except Exception:  # noqa: BLE001, S112 — linha JSONL inválida é pulada por contrato de resiliência; módulo sem logger
                    continue
    if memory_path is None:
        seen = {episode.id for episode in episodes}
        for episode in _load_fraud_pattern_episodes():
            if episode.id not in seen:
                episodes.append(episode)
                seen.add(episode.id)
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
    query_embedding = _hashed_embedding(
        {
            "ghost_tokens": tokens,
            "candidate": _embedding_text(
                {
                    "asset": candidate.asset,
                    "action": candidate.action,
                    "thesis": candidate.thesis,
                    "risk_context": candidate.risk_context,
                    "raw_signals": candidate.raw_signals,
                }
            ),
        }
    )
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
            embedding_similarity = _cosine(
                query_embedding, _hashed_embedding(_embedding_text(episode))
            )
            similarity = _clamp(
                (0.45 * ghost_overlap) + (0.20 * word_overlap) + (0.35 * embedding_similarity)
            )

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
