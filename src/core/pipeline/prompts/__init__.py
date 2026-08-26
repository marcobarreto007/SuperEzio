"""Pipeline v4 prompt system — Bob Core CEO prompts."""

from ._prompts import MODEL_PROMPTS, QWEN_PERSONA, QWEN_SYSTEM_PROMPT
from .builder import agent_system_prompt, build_agent_prompt

__all__ = [
    "MODEL_PROMPTS",
    "QWEN_PERSONA",
    "QWEN_SYSTEM_PROMPT",
    "agent_system_prompt",
    "build_agent_prompt",
]
