"""
Provider dataclasses and factory for ModelGateway.

Extracted from gateway.py to keep the gateway class focused on
routing/fallback logic while provider config lives separately.
"""

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..config.schema import GatewayConfig

if TYPE_CHECKING:
    from ..config import UniversalConfig

AGENT_PROVIDER_NAME = "agent"
AGENT_MODEL_ID = "bob-core-local"
PRIMARY_PROVIDER_NAME = "local_orchestrator"
PRIMARY_MODEL_ID = AGENT_MODEL_ID
DEEPSEEK_PROVIDER_NAME = "deepseek"
DEEPSEEK_MODEL_ID = "deepseek-v4-pro"
GEMINI_PROVIDER_NAME = "gemini"
GEMINI_MODEL_ID = "gemini-3.5-flash"
DAYTRADE_JUDGE_PROVIDER_NAME = "daytrade_judge"
DAYTRADE_AUDITOR_PROVIDER_NAME = "daytrade_auditor"


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
    """Build the default provider list and gateway config from env + config.

    Returns (providers, gateway_config) ready to pass to ModelGateway().
    """
    providers: list[ModelProvider] = []

    orchestrator_config = config.models.get("orchestrator") or config.models.get("ceo")
    # Primary local Bob core on :8082.
    # Falls back to DeepSeek cloud ONLY if local is unreachable.
    primary_base_url = os.getenv(
        "SUPEREZIO_PRIMARY_BASE_URL",
        "http://127.0.0.1:8082/v1",  # LOCAL FIRST
    )
    primary_model = os.getenv(
        "SUPEREZIO_PRIMARY_MODEL",
        PRIMARY_MODEL_ID,
    )
    primary_api_key = os.getenv("SUPEREZIO_PRIMARY_API_KEY", "")

    providers.append(
        ModelProvider(
            name=PRIMARY_PROVIDER_NAME,
            base_url=primary_base_url,
            api_key=primary_api_key,
            priority=0,  # HIGHEST priority — local model
            model=primary_model,
            max_tokens=orchestrator_config.max_tokens if orchestrator_config else 8192,
            temperature=orchestrator_config.temperature if orchestrator_config else 0.4,
            is_local=True,
            backend="openai_compatible",
        )
    )

    # DeepSeek provider for expert roles.
    # Keep it decoupled from orchestrator/primary URL to avoid accidentally
    # routing expert traffic to the local agent endpoint.
    deepseek_key = os.getenv("SUPEREZIO_DEEPSEEK_API_KEY", primary_api_key)
    deepseek_base_url = os.getenv("SUPEREZIO_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    experts_config = config.models.get("experts")
    deepseek_model = os.getenv(
        "SUPEREZIO_DEEPSEEK_MODEL",
        experts_config.model_id if experts_config else DEEPSEEK_MODEL_ID,
    )
    providers.append(
        ModelProvider(
            name=DEEPSEEK_PROVIDER_NAME,
            base_url=deepseek_base_url,
            api_key=deepseek_key,
            priority=-300,
            model=deepseek_model,
            timeout_s=int(os.getenv("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", "240")),
            max_tokens=int(os.getenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("SUPEREZIO_DEEPSEEK_TEMPERATURE", "0.2")),
        )
    )

    # Daytrade judge and auditor providers can use independent model IDs,
    # while still sharing DeepSeek credentials/base URL.
    judge_model = os.getenv("SUPEREZIO_DAYTRADE_JUDGE_MODEL", deepseek_model)
    auditor_model = os.getenv("SUPEREZIO_DAYTRADE_AUDITOR_MODEL", deepseek_model)
    providers.append(
        ModelProvider(
            name=DAYTRADE_JUDGE_PROVIDER_NAME,
            base_url=deepseek_base_url,
            api_key=deepseek_key,
            priority=-305,
            model=judge_model,
            timeout_s=int(os.getenv("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", "240")),
            max_tokens=int(os.getenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("SUPEREZIO_DEEPSEEK_TEMPERATURE", "0.2")),
        )
    )
    providers.append(
        ModelProvider(
            name=DAYTRADE_AUDITOR_PROVIDER_NAME,
            base_url=deepseek_base_url,
            api_key=deepseek_key,
            priority=-304,
            model=auditor_model,
            timeout_s=int(os.getenv("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", "240")),
            max_tokens=int(os.getenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("SUPEREZIO_DEEPSEEK_TEMPERATURE", "0.2")),
        )
    )

    # Gemini 2.5 Flash — sentiment and market narrative expert (cloud).
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    gemini_base_url = os.getenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    if gemini_key:
        providers.append(
            ModelProvider(
                name=GEMINI_PROVIDER_NAME,
                base_url=gemini_base_url,
                api_key=gemini_key,
                priority=-290,
                model=os.getenv("GEMINI_MODEL", GEMINI_MODEL_ID),
                timeout_s=int(os.getenv("GEMINI_TIMEOUT_SEC", "240")),
                max_tokens=int(os.getenv("GEMINI_MAX_TOKENS", "4096")),
                temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.3")),
            )
        )

    # Agent — local Bob core via llama-server.
    agent_base_url = os.getenv(
        "SUPEREZIO_AGENT_BASE_URL",
        "http://127.0.0.1:8082/v1",
    )
    providers.append(
        ModelProvider(
            name=AGENT_PROVIDER_NAME,
            base_url=agent_base_url,
            api_key="",
            priority=-10,  # HIGH priority — local Bob CEO
            model=AGENT_MODEL_ID,
            timeout_s=int(os.getenv("SUPEREZIO_AGENT_TIMEOUT_SEC", "600")),
            max_tokens=8192,
            temperature=0.4,
            is_local=True,
            backend="openai_compatible",
        )
    )

    # CEO Fallback — GLM Code Plan (glm-5.2) via api.z.ai
    # Assume se o Qwen local :8082 cair. Mesmo provedor do Bob implementador.
    glm_fallback_key = os.getenv("SUPEREZIO_GLM_CODE_PLAN_API_KEY", "")
    if glm_fallback_key:
        providers.append(
            ModelProvider(
                name="ceo_fallback_glm",
                base_url="https://api.z.ai/api/coding/paas/v4",
                api_key=glm_fallback_key,
                priority=-680,  # abaixo do agente local (-670), mas disponível
                model="glm-5.2",
                timeout_s=int(os.getenv("SUPEREZIO_GLM_FALLBACK_TIMEOUT_SEC", "300")),
                max_tokens=8192,
                temperature=0.3,
                is_local=False,
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
