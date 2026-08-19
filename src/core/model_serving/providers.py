"""
Provider dataclasses and factory for ModelGateway.

Extracted from gateway.py to keep the gateway class focused on
routing/fallback logic while provider config lives separately.

Zero-cloud policy (operator directive 2026-08-17): every LLM role —
CEO/agent, orchestrator, experts, daytrade judge/auditor — is served by
the shared local llama-server (perfil cc) at http://127.0.0.1:8080/v1.
No provider may point at an external API. Legacy provider names
("deepseek", "daytrade_judge", ...) are routing contracts kept for
compatibility — they are all aliases of the local endpoint now.
"""

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..config.schema import GatewayConfig

if TYPE_CHECKING:
    from ..config import UniversalConfig

logger = logging.getLogger(__name__)

AGENT_PROVIDER_NAME = "agent"
# Model id served by the shared local llama-server (perfil cc). llama-server
# exposes the loaded file name as the model id; confirm via /v1/models on a
# live server before changing this.
AGENT_MODEL_ID = "Qwen3.8-27B-Q4_K_M"
PRIMARY_PROVIDER_NAME = "local_orchestrator"
PRIMARY_MODEL_ID = AGENT_MODEL_ID
DEEPSEEK_PROVIDER_NAME = "deepseek"
DEEPSEEK_MODEL_ID = AGENT_MODEL_ID
GEMINI_PROVIDER_NAME = "gemini"
GEMINI_MODEL_ID = AGENT_MODEL_ID
DAYTRADE_JUDGE_PROVIDER_NAME = "daytrade_judge"
DAYTRADE_AUDITOR_PROVIDER_NAME = "daytrade_auditor"

# Shared local llama-server (perfil cc — 2026-08-18):
# Qwen3.8-27B-Q4_K_M (15.9 GB) on 2 GPUs (RTX 3060 12GB + RTX 2070 8GB, -ts 12,8),
# context 16384 (24576 CUDA OOM), single slot. One server serves Claude Code AND SuperEzio.
LOCAL_QWEN_BASE_URL = "http://127.0.0.1:8080/v1"

# llama-server ignores the API key, but the OpenAI client library refuses to
# build a request without one ("Missing credentials"). Local providers carry
# this placeholder so generation reaches the local endpoint. Zero-cloud: this
# is NOT a credential — it never leaves the machine.
LOCAL_API_KEY_PLACEHOLDER = "local-served"


def _is_local_url(url: str) -> bool:
    return url.startswith("http://127.0.0.1") or url.startswith("http://localhost")


def _local_only_override(env_var: str) -> str:
    """Return the env override only if it points at a local endpoint.

    Cloud URLs are rejected with a warning so a stale .env entry (e.g.
    SUPEREZIO_AGENT_BASE_URL=https://api.deepseek.com, found in this repo on
    2026-08-17) can never silently route the CEO/experts to an external API.
    """
    value = os.getenv(env_var, "").strip()
    if value and not _is_local_url(value):
        logger.warning(
            "ZERO-CLOUD: %s points at a non-local endpoint — ignored by policy.",
            env_var,
        )
        return ""
    return value


@dataclass
class ModelProvider:
    """Configuração de um provedor de modelo (externo)."""

    name: str
    base_url: str
    api_key: str = ""
    model: str = PRIMARY_MODEL_ID
    timeout_s: int = 120
    priority: int = 0
    max_tokens: int = 2048
    temperature: float = 0.7
    is_local: bool = False
    backend: str = "cloud"


def build_default_providers(
    config: "UniversalConfig",
) -> tuple[list[ModelProvider], GatewayConfig]:
    """Build the zero-cloud provider list and gateway config.

    Every provider points at the shared local llama-server on :8080. If that
    server is down, calls must fail so callers can enter MAN_AT_WORK — there
    is no cloud fallback by policy.
    """
    providers: list[ModelProvider] = []

    orchestrator_config = config.models.get("orchestrator") or config.models.get("ceo")

    local_base_url = _local_only_override("SUPEREZIO_PRIMARY_BASE_URL") or LOCAL_QWEN_BASE_URL
    local_model = os.getenv("SUPEREZIO_PRIMARY_MODEL", PRIMARY_MODEL_ID)

    providers.append(
        ModelProvider(
            name=PRIMARY_PROVIDER_NAME,
            base_url=local_base_url,
            api_key=LOCAL_API_KEY_PLACEHOLDER,
            priority=0,  # HIGHEST priority — local model
            model=local_model,
            max_tokens=orchestrator_config.max_tokens if orchestrator_config else 8192,
            temperature=orchestrator_config.temperature if orchestrator_config else 0.4,
            is_local=True,
            backend="openai_compatible",
        )
    )

    # Expert roles. The legacy name "deepseek" is a routing contract
    # (EXPERT_PROVIDERS in pipeline/nodes/experts.py) — the endpoint behind it
    # is the local server. SUPEREZIO_DEEPSEEK_* env vars remain honored, but
    # only for local URLs (see _local_only_override).
    experts_base_url = _local_only_override("SUPEREZIO_DEEPSEEK_BASE_URL") or local_base_url
    experts_model = os.getenv("SUPEREZIO_DEEPSEEK_MODEL", local_model)
    providers.append(
        ModelProvider(
            name=DEEPSEEK_PROVIDER_NAME,
            base_url=experts_base_url,
            api_key=LOCAL_API_KEY_PLACEHOLDER,
            priority=-300,
            model=experts_model,
            timeout_s=int(os.getenv("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", "240")),
            max_tokens=int(os.getenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("SUPEREZIO_DEEPSEEK_TEMPERATURE", "0.2")),
            is_local=True,
            backend="openai_compatible",
        )
    )

    # Daytrade judge and auditor can use independent model ids while sharing
    # the local endpoint.
    judge_model = os.getenv("SUPEREZIO_DAYTRADE_JUDGE_MODEL", experts_model)
    auditor_model = os.getenv("SUPEREZIO_DAYTRADE_AUDITOR_MODEL", experts_model)
    for name, priority, model in (
        (DAYTRADE_JUDGE_PROVIDER_NAME, -304, judge_model),
        (DAYTRADE_AUDITOR_PROVIDER_NAME, -305, auditor_model),
    ):
        providers.append(
            ModelProvider(
                name=name,
                base_url=experts_base_url,
                api_key=LOCAL_API_KEY_PLACEHOLDER,
                priority=priority,
                model=model,
                timeout_s=int(os.getenv("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", "240")),
                max_tokens=int(os.getenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "4096")),
                temperature=float(os.getenv("SUPEREZIO_DEEPSEEK_TEMPERATURE", "0.2")),
                is_local=True,
                backend="openai_compatible",
            )
        )

    # Agent (CEO). Local-only by policy: no cloud fallback exists — the former
    # ceo_fallback_glm provider (api.z.ai) was removed by the zero-cloud
    # directive. If :8080 is down, the gateway must fail (MAN_AT_WORK).
    agent_base_url = _local_only_override("SUPEREZIO_AGENT_BASE_URL") or local_base_url
    agent_model = os.getenv("SUPEREZIO_AGENT_MODEL", AGENT_MODEL_ID)
    providers.append(
        ModelProvider(
            name=AGENT_PROVIDER_NAME,
            base_url=agent_base_url,
            api_key=os.getenv("SUPEREZIO_AGENT_API_KEY", "") or LOCAL_API_KEY_PLACEHOLDER,
            priority=-10,  # HIGH priority — local CEO
            model=agent_model,
            timeout_s=int(os.getenv("SUPEREZIO_AGENT_TIMEOUT_SEC", "600")),
            max_tokens=8192,
            temperature=0.4,
            is_local=True,
            backend="openai_compatible",
        )
    )

    gw_config = GatewayConfig(
        max_fallbacks=config.gateway.max_fallbacks,
        timeout_s=config.gateway.timeout_s,
        retry_attempts=config.gateway.retry_attempts,
        retry_delay_s=config.gateway.retry_delay_s,
    )

    return providers, gw_config


def build_providers() -> tuple[list[ModelProvider], GatewayConfig]:
    """Backward-compatible provider factory using the default runtime config."""
    from ..config import get_config

    return build_default_providers(get_config())
