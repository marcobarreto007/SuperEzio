"""Normalization utilities — extracted from intents.py."""

import re
import unicodedata


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_message(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.translate(str.maketrans("", "", ".,!?;:\"'()[]{}"))
    text = _strip_accents(text)
    return text.strip()


def normalize_for_match(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = text.translate(str.maketrans("", "", ".,!?;:\"'()[]{}"))
    text = re.sub(r"\s+", " ", text)
    text = _strip_accents(text)
    return text.strip()


def has_hint(message: str, hints: tuple[str, ...]) -> bool:
    if not message:
        return False
    normalized = normalize_message(message)
    for hint in hints:
        normalized_hint = normalize_message(hint).strip()
        if normalized_hint and normalized_hint in normalized:
            return True
    return False
