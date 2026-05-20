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

CEO_PROVIDER_NAME = "ceo"
CEO_MODEL_ID = "superezio-ceo-intent-merged"
PRIMARY_PROVIDER_NAME = "local_orchestrator"
PRIMARY_PROVIDER_LEGACY_NAMES = {"primary_external"}
PRIMARY_MODEL_ID = CEO_MODEL_ID
DEEPSEEK_PROVIDER_NAME = "deepseek"
DEEPSEEK_MODEL_ID = "deepseek-v4-pro"


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
    default_base_url = (
        orchestrator_config.path
        if orchestrator_config and orchestrator_config.path
        else "https://api.deepseek.com"
    )
    default_model = (
        orchestrator_config.model_id
        if orchestrator_config and getattr(orchestrator_config, "model_id", "")
        else PRIMARY_MODEL_ID
    )

    primary_base_url = os.getenv(
        "SUPEREZIO_PRIMARY_BASE_URL",
        os.getenv("SUPEREZIO_DEEPSEEK_BASE_URL", default_base_url),
    )
    primary_model = os.getenv(
        "SUPEREZIO_PRIMARY_MODEL",
        os.getenv("SUPEREZIO_DEEPSEEK_MODEL", default_model),
    )
    primary_api_key = os.getenv(
        "SUPEREZIO_PRIMARY_API_KEY",
        os.getenv("SUPEREZIO_DEEPSEEK_API_KEY", ""),
    )

    # Local orchestrator provider. The old "primary_external" name is kept
    # only as a gateway alias; the canonical runtime route is local.
    providers.append(
        ModelProvider(
            name=PRIMARY_PROVIDER_NAME,
            base_url=primary_base_url,
            api_key=primary_api_key,
            priority=-400,
            model=primary_model,
            max_tokens=orchestrator_config.max_tokens if orchestrator_config else 2048,
            temperature=orchestrator_config.temperature if orchestrator_config else 0.7,
            is_local=orchestrator_config.is_local if orchestrator_config else False,
            backend=orchestrator_config.backend if orchestrator_config else "cloud",
        )
    )

    # DeepSeek provider for expert roles.
    # Keep it decoupled from orchestrator/primary URL to avoid accidentally
    # routing expert traffic to the local CEO endpoint.
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
            timeout_s=int(os.getenv("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", "120")),
            max_tokens=int(os.getenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("SUPEREZIO_DEEPSEEK_TEMPERATURE", "0.2")),
        )
    )

    # CEO — Qwen3.6-35B F51 Q4_K_M GGUF via llama-server, local.
    ceo_base_url = os.getenv(
        "SUPEREZIO_CEO_BASE_URL",
        "http://127.0.0.1:8082/v1",
    )
    providers.append(
        ModelProvider(
            name=CEO_PROVIDER_NAME,
            base_url=ceo_base_url,
            api_key="",
            priority=-670,
            model=CEO_MODEL_ID,
            timeout_s=180,
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
