"""Pure-Python sanity checks for generated finance answers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class SanityVerdict:
    passed: bool = True
    warnings: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)


def _ascii_lower(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


class SanityCheck:
    """Lightweight post-generation checks with no model dependency."""

    _MAGNITUDE_WORDS: dict[str, int] = {
        "mil": 1_000,
        "milhar": 1_000,
        "milhao": 1_000_000,
        "milhoes": 1_000_000,
        "bilhao": 1_000_000_000,
        "bilhoes": 1_000_000_000,
        "trilhao": 1_000_000_000_000,
        "trilhoes": 1_000_000_000_000,
    }

    def verify(self, user_query: str, answer: str, *, min_answer_chars: int = 50) -> SanityVerdict:
        verdict = SanityVerdict()
        stripped = (answer or "").strip()

        if not stripped:
            verdict.passed = False
            verdict.blocks.append("empty_answer")
            return verdict

        if len(stripped) < min_answer_chars:
            verdict.passed = False
            verdict.blocks.append(f"answer_too_short ({len(stripped)} < {min_answer_chars} chars)")
            return verdict

        answer_ascii = _ascii_lower(stripped)
        json_like = stripped.count('{"tool"') + stripped.count('"tool":')
        if json_like >= 3 and not re.search(r"[a-z]{4,}", answer_ascii):
            verdict.passed = False
            verdict.blocks.append("tool_call_json_no_natural_language")
            return verdict

        user_ascii = _ascii_lower(user_query)
        self._check_magnitude(user_ascii, answer_ascii, verdict)

        pt_user = bool(
            re.search(r"\b(tenho|quero|investir|reais|risco|prazo|dividendo)\b", user_ascii)
        )
        if pt_user:
            pt_markers = r"\b(com|para|voce|reais|mil|risco|mercado|acoes|renda|seguro)\b"
            if not re.search(pt_markers, answer_ascii) and len(stripped) > 100:
                verdict.warnings.append("answer_not_in_portuguese_though_query_is_pt")

        return verdict

    def _check_magnitude(self, user: str, answer: str, verdict: SanityVerdict) -> None:
        user_numbers = self._extract_number_word_pairs(user)
        answer_numbers = self._extract_number_word_pairs(answer)

        for user_number, user_word in user_numbers:
            user_magnitude = self._MAGNITUDE_WORDS.get(user_word)
            if user_magnitude is None:
                continue
            for answer_number, answer_word in answer_numbers:
                answer_magnitude = self._MAGNITUDE_WORDS.get(answer_word)
                if answer_magnitude is None:
                    continue
                if user_number == answer_number and user_magnitude != answer_magnitude:
                    ratio = answer_magnitude / user_magnitude if user_magnitude > 0 else 999
                    if ratio >= 100 or ratio <= 0.01:
                        verdict.warnings.append(
                            "magnitude_mismatch: "
                            f"user '{user_number} {user_word}' -> "
                            f"answer '{answer_number} {answer_word}' ({ratio:.0f}x)"
                        )

    @staticmethod
    def _extract_number_word_pairs(text: str) -> list[tuple[int, str]]:
        pairs: list[tuple[int, str]] = []
        pattern = (
            r"(\d+[.,]?\d*)\s*"
            r"(milhar|milhoes|milhao|bilhoes|bilhao|trilhoes|trilhao|mil)"
        )
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                number = int(float(match.group(1).replace(",", ".")))
            except ValueError:
                continue
            pairs.append((number, match.group(2).lower()))
        return pairs


sanity_check = SanityCheck()
