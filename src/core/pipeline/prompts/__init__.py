"""Pipeline v4 prompt system — model-aware, clean, no hardcoded model names."""

from .builder import build_ceo_prompt, ceo_system_prompt
from .gemma import GEMMA_SYSTEM_PROMPT, GEMMA_PERSONA

__all__ = [
    "build_ceo_prompt",
    "ceo_system_prompt",
    "GEMMA_SYSTEM_PROMPT",
    "GEMMA_PERSONA",
]
