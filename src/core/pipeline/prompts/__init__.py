"""Pipeline v4 prompt system — Qwen3.6-35B CEO prompts."""

from .builder import build_ceo_prompt, ceo_system_prompt
from .gemma import GEMMA_SYSTEM_PROMPT, GEMMA_PERSONA, QWEN_SYSTEM_PROMPT, QWEN_PERSONA

__all__ = [
    "build_ceo_prompt",
    "ceo_system_prompt",
    "GEMMA_SYSTEM_PROMPT",
    "GEMMA_PERSONA",
    "QWEN_SYSTEM_PROMPT",
    "QWEN_PERSONA",
]
