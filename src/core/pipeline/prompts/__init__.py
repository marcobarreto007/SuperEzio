"""Pipeline v4 prompt system — Bob Core CEO prompts."""

from ._prompts import QWEN_SYSTEM_PROMPT, QWEN_PERSONA, MODEL_PROMPTS
from .builder import build_agent_prompt, agent_system_prompt

__all__ = [
    "build_agent_prompt",
    "agent_system_prompt",
    "QWEN_SYSTEM_PROMPT",
    "QWEN_PERSONA",
    "MODEL_PROMPTS",
]
