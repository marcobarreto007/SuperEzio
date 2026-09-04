"""Provider dataclasses and the hybrid local/DeepSeek provider factory.

The CEO/agent and orchestrator remain pinned to the shared local llama-server
runtime (:8080), today serving Ornith-1.0-9B-Q4_K_M (text-only, no mmproj).
Financial experts, including the day-trade judge and auditor, are pinned to
the official DeepSeek HTTPS API. These two trust boundaries must never
silently substitute for one another.
"""

import ipaddress
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ..config.schema import GatewayConfig

if TYPE_CHECKING:
    from ..config import UniversalConfig

logger = logging.getLogger(__name__)

AGENT_PROVIDER_NAME = "agent"
AGENT_MODEL_ID = "deepseek-v4-pro"
PRIMARY_PROVIDER_NAME = "local_orchestrator"
PRIMARY_MODEL_ID = AGENT_MODEL_ID
DEEPSEEK_PROVIDER_NAME = "deepseek"
DEEPSEEK_MODEL_ID = "deepseek-v4-pro"
DEEPSEEK_OFFICIAL_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_OFFICIAL_MODELS = frozenset({"deepseek-v4-pro", "deepseek-v4-flash"})
DAYTRADE_JUDGE_PROVIDER_NAME = "daytrade_judge"
DAYTRADE_AUDITOR_PROVIDER_NAME = "daytrade_auditor"

# Nome historico: o runtime local :8080 ja serviu Qwen. O endpoint e o mesmo
# llama-server que hoje serve o modelo configurado em
# scripts/serve_agent_llamacpp.ps1 (Ornith-1.0-9B-Q4_K_M). Constante mantida
# para compatibilidade de imports.
LOCAL_QWEN_BASE_URL = "http://127.0.0.1:8080/v1"
LOCAL_MAX_TOKENS = 1800
# Retained for import compatibility with older callers. External expert calls
# use ``get_deepseek_max_tokens`` and are not clamped to this local value.
LOCAL_EXPERT_MAX_TOKENS = 192
LOCAL_TIMEOUT_S = 600

DEEPSEEK_DEFAULT_MAX_TOKENS = 1800
DEEPSEEK_MIN_MAX_TOKENS = 128
DEEPSEEK_MAX_MAX_TOKENS = 8192
DEEPSEEK_DEFAULT_TIMEOUT_S = 180
DEEPSEEK_MIN_TIMEOUT_S = 10
DEEPSEEK_MAX_TIMEOUT_S = 600

# llama-server ignores the API key, but the OpenAI client library refuses to
# build a request without one ("Missing credentials"). Local providers carry
# this placeholder so generation reaches the local endpoint. Zero-cloud: this
# is NOT a credential — it never leaves the machine.
LOCAL_API_KEY_PLACEHOLDER = "local-served"


def _is_local_url(url: str) -> bool:
    """Accept loopback, plus the compose service only in Docker profile.

    Parsing the hostname prevents lookalikes such as ``localhost.example.com``.
    The Docker DNS name is deliberately unavailable unless the compose-only
    runtime profile is explicit, so a host-side stale env cannot widen the
    zero-cloud boundary.
    """
    parsed = urlparse(url)
    if parsed.scheme != "http":
        return False
    if parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return True
    return (
        os.getenv("SUPEREZIO_RUNTIME_PROFILE", "").strip().lower() == "docker"
        and parsed.hostname == "bob-ceo"
        and parsed.port == 8080
    )


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


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int_env(
    names: tuple[str, ...],
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Read the first configured integer and reject invalid unsafe values."""
    selected_name = names[0]
    raw = ""
    for name in names:
        candidate = os.getenv(name, "").strip()
        if candidate:
            selected_name = name
            raw = candidate
            break
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{selected_name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{selected_name} must be between {minimum} and {maximum}")
    return value


def get_deepseek_max_tokens() -> int:
    """Return the external expert output budget without the old 192 clamp."""
    return _bounded_int_env(
        ("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "SUPEREZIO_EXPERT_MAX_TOKENS"),
        default=DEEPSEEK_DEFAULT_MAX_TOKENS,
        minimum=DEEPSEEK_MIN_MAX_TOKENS,
        maximum=DEEPSEEK_MAX_MAX_TOKENS,
    )


def get_deepseek_timeout_s() -> int:
    """Return the external request timeout without imposing a 600s floor."""
    return _bounded_int_env(
        ("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", "SUPEREZIO_EXPERT_TIMEOUT"),
        default=DEEPSEEK_DEFAULT_TIMEOUT_S,
        minimum=DEEPSEEK_MIN_TIMEOUT_S,
        maximum=DEEPSEEK_MAX_TIMEOUT_S,
    )


def _deepseek_api_key() -> str:
    api_key = os.getenv("SUPEREZIO_DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "SUPEREZIO_DEEPSEEK_API_KEY is required for external financial experts "
            "(set it in the environment or in .env/.env.local; entrypoints load "
            "both via core.config.secrets.load_local_env)"
        )
    return api_key


def _validate_custom_deepseek_url(value: str) -> str:
    """Validate an explicitly opted-in custom DeepSeek-compatible endpoint."""
    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise RuntimeError("Custom DeepSeek endpoint must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("Custom DeepSeek endpoint has an invalid authority")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("Custom DeepSeek endpoint has an invalid port") from exc
    if port not in {None, 443}:
        raise RuntimeError("Custom DeepSeek endpoint must use the default HTTPS port")
    if parsed.query or parsed.fragment:
        raise RuntimeError("Custom DeepSeek endpoint cannot contain query or fragment data")

    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise RuntimeError("Custom DeepSeek endpoint cannot target a local host")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise RuntimeError("Custom DeepSeek endpoint cannot target a private network")
    return value.rstrip("/")


def _deepseek_base_url() -> str:
    override = os.getenv("SUPEREZIO_DEEPSEEK_BASE_URL", "").strip()
    if not override or override.rstrip("/") == DEEPSEEK_OFFICIAL_BASE_URL:
        return DEEPSEEK_OFFICIAL_BASE_URL
    if not _env_flag("SUPEREZIO_ALLOW_CUSTOM_DEEPSEEK_BASE_URL"):
        raise RuntimeError(
            "Custom SUPEREZIO_DEEPSEEK_BASE_URL is disabled; use the official endpoint"
        )
    return _validate_custom_deepseek_url(override)


def _deepseek_model(env_name: str, default: str, *, official_endpoint: bool) -> str:
    """Resolve a model without sending local or retired ids to the official API."""
    model = os.getenv(env_name, default).strip()
    if not model:
        raise RuntimeError(f"{env_name} cannot be blank")
    if official_endpoint and model not in DEEPSEEK_OFFICIAL_MODELS:
        allowed = ", ".join(sorted(DEEPSEEK_OFFICIAL_MODELS))
        raise RuntimeError(f"{env_name} must be one of the official DeepSeek models: {allowed}")
    return model


@dataclass
class ModelProvider:
    """Configuração de um provedor de modelo (externo)."""

    name: str
    base_url: str
    api_key: str = field(default="", repr=False)
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
    """Build the provider list with DeepSeek V4 Pro as default external brain and experts."""
    providers: list[ModelProvider] = []

    # Financial experts are an external, provider-pinned trust boundary.
    experts_api_key = _deepseek_api_key()
    experts_base_url = _deepseek_base_url()
    official_endpoint = experts_base_url == DEEPSEEK_OFFICIAL_BASE_URL
    experts_model = _deepseek_model(
        "SUPEREZIO_DEEPSEEK_MODEL",
        DEEPSEEK_MODEL_ID,
        official_endpoint=official_endpoint,
    )
    experts_timeout_s = get_deepseek_timeout_s()
    experts_max_tokens = get_deepseek_max_tokens()

    orchestrator_config = config.models.get("orchestrator") or config.models.get("ceo")

    primary_env_url = os.getenv("SUPEREZIO_PRIMARY_BASE_URL", "").strip()
    primary_base_url = primary_env_url or experts_base_url
    primary_is_local = _is_local_url(primary_base_url)
    primary_model = os.getenv("SUPEREZIO_PRIMARY_MODEL", PRIMARY_MODEL_ID)
    primary_api_key = (
        os.getenv("SUPEREZIO_PRIMARY_API_KEY", "").strip()
        or os.getenv("SUPEREZIO_DEEPSEEK_API_KEY", "").strip()
        or (LOCAL_API_KEY_PLACEHOLDER if primary_is_local else experts_api_key)
    )

    providers.append(
        ModelProvider(
            name=PRIMARY_PROVIDER_NAME,
            base_url=primary_base_url,
            api_key=primary_api_key,
            priority=0,
            model=primary_model,
            timeout_s=max(
                orchestrator_config.timeout_s if orchestrator_config else experts_timeout_s,
                experts_timeout_s if not primary_is_local else LOCAL_TIMEOUT_S,
            ),
            max_tokens=min(
                orchestrator_config.max_tokens if orchestrator_config else experts_max_tokens,
                experts_max_tokens,
            ),
            temperature=orchestrator_config.temperature if orchestrator_config else 0.4,
            is_local=primary_is_local,
            backend="openai_compatible",
        )
    )

    providers.append(
        ModelProvider(
            name=DEEPSEEK_PROVIDER_NAME,
            base_url=experts_base_url,
            api_key=experts_api_key,
            priority=-300,
            model=experts_model,
            timeout_s=experts_timeout_s,
            max_tokens=experts_max_tokens,
            temperature=float(os.getenv("SUPEREZIO_DEEPSEEK_TEMPERATURE", "0.2")),
            is_local=False,
            backend="openai_compatible",
        )
    )

    # Judge and auditor may use independent DeepSeek model ids, but share the
    # same authenticated official endpoint and never fall back to the local runtime.
    judge_model = _deepseek_model(
        "SUPEREZIO_DAYTRADE_JUDGE_MODEL",
        experts_model,
        official_endpoint=official_endpoint,
    )
    auditor_model = _deepseek_model(
        "SUPEREZIO_DAYTRADE_AUDITOR_MODEL",
        experts_model,
        official_endpoint=official_endpoint,
    )
    for name, priority, model in (
        (DAYTRADE_JUDGE_PROVIDER_NAME, -304, judge_model),
        (DAYTRADE_AUDITOR_PROVIDER_NAME, -305, auditor_model),
    ):
        providers.append(
            ModelProvider(
                name=name,
                base_url=experts_base_url,
                api_key=experts_api_key,
                priority=priority,
                model=model,
                timeout_s=experts_timeout_s,
                max_tokens=experts_max_tokens,
                temperature=float(os.getenv("SUPEREZIO_DEEPSEEK_TEMPERATURE", "0.2")),
                is_local=False,
                backend="openai_compatible",
            )
        )

    # Agent (CEO) — DeepSeek V4 Pro external API running the CEO prompt
    agent_env_url = os.getenv("SUPEREZIO_AGENT_BASE_URL", "").strip()
    agent_base_url = agent_env_url or experts_base_url
    agent_is_local = _is_local_url(agent_base_url)
    agent_model = os.getenv("SUPEREZIO_AGENT_MODEL", AGENT_MODEL_ID)
    agent_api_key = (
        os.getenv("SUPEREZIO_AGENT_API_KEY", "").strip()
        or os.getenv("SUPEREZIO_DEEPSEEK_API_KEY", "").strip()
        or (LOCAL_API_KEY_PLACEHOLDER if agent_is_local else experts_api_key)
    )
    providers.append(
        ModelProvider(
            name=AGENT_PROVIDER_NAME,
            base_url=agent_base_url,
            api_key=agent_api_key,
            priority=-10,  # HIGH priority — CEO
            model=agent_model,
            timeout_s=max(
                _bounded_int_env(
                    ("SUPEREZIO_AGENT_TIMEOUT_SEC",),
                    default=experts_timeout_s if not agent_is_local else LOCAL_TIMEOUT_S,
                    minimum=1,
                    maximum=3600,
                ),
                experts_timeout_s if not agent_is_local else LOCAL_TIMEOUT_S,
            ),
            max_tokens=experts_max_tokens if not agent_is_local else LOCAL_MAX_TOKENS,
            temperature=0.4,
            is_local=agent_is_local,
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
