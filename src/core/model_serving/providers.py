"""Provider dataclasses and the external cloud provider factory.

The roles that DECIDE — CEO/agent and orchestrator — default to the official
DeepSeek HTTPS API on ``deepseek-v4-pro``; the SUPPORT roles (financial expert
committee, day-trade judge and auditor) stay on ``deepseek-v4-flash`` (decision
of 2026-09-12; before that every role ran flash). The Z.ai Coding Plan endpoint
(glm-5.3) is optional:
SUPEREZIO_PRIMARY_MODEL / SUPEREZIO_AGENT_MODEL switch a role back to it, and
the ``glm`` provider is only built when SUPEREZIO_GLM_CODING_PLAN_API_KEY (or
one of its legacy aliases) is present. Asking for a glm model without the key
degrades that role to its OWN DeepSeek model (brain on pro, support on flash —
``ModelProvider.degrade_model``) so the process still boots without demoting
the roles that decide.

The ModelGateway keeps the automatic credit fallback GLM -> DeepSeek for Bob
(SUPEREZIO_GLM_FALLBACK_TO_DEEPSEEK, default on) for when that path is armed.
Expert calls pin allow_fallback=False, so the committee never silently swaps
provenance. Trust boundaries never substitute for one another except for that
explicit CEO credit fallback.
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

GLM_CODING_PLAN_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
GLM_CODING_PLAN_MODEL = "glm-5.3"
GLM_CODING_PLAN_HOST = "api.z.ai"
GLM_PROVIDER_NAME = "glm"

AGENT_PROVIDER_NAME = "agent"
PRIMARY_PROVIDER_NAME = "local_orchestrator"
DEEPSEEK_PROVIDER_NAME = "deepseek"
# DeepSeek-only default (2026-09-10): every role — Bob, orchestrator, the
# expert committee, judge and auditor — runs on the official DeepSeek HTTPS
# API. GLM-5.3 stays reachable via SUPEREZIO_PRIMARY_MODEL /
# SUPEREZIO_AGENT_MODEL and is only instantiated when its coding-plan key is
# present; requesting a glm model without that key degrades to DeepSeek.
# Base: os papeis de APOIO (comite de experts, judge, auditor) rodam no flash.
DEEPSEEK_MODEL_ID = "deepseek-v4-flash"
# Cerebro: quem DECIDE — CEO (agent) e orquestrador — roda no pro.
# Decisao de 12/09/2026. O modelo mais forte vai no papel que decide; os papeis
# de apoio continuam no flash. Ambos estao em DEEPSEEK_OFFICIAL_MODELS.
BRAIN_MODEL_ID = "deepseek-v4-pro"
AGENT_MODEL_ID = BRAIN_MODEL_ID
PRIMARY_MODEL_ID = BRAIN_MODEL_ID
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
DEEPSEEK_DEFAULT_TIMEOUT_S = 60
# The agent (CEO) keeps the 180s floor the experts used to inherit — a long PT
# answer after deliberation can exceed the 60s expert timeout.
AGENT_DEFAULT_TIMEOUT_S = 180
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


def _is_glm_coding_model(model: str) -> bool:
    return model.strip().lower().startswith("glm-5")


def _normalize_zai_base_url(url: str) -> str:
    """Rewrite the general Z.ai path to the Coding Plan chat endpoint.

    A Coding Plan key fails on ``/api/paas/v4``. Official GLM-5.3 docs pin
    subscribers to OpenAI Chat Completions at ``/api/coding/paas/v4``.
    """
    if not url:
        return url
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host != GLM_CODING_PLAN_HOST:
        return url
    path = (parsed.path or "").rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")].rstrip("/")
    if path in {"/api/paas/v4", "/api/coding/paas/v4"}:
        return GLM_CODING_PLAN_BASE_URL
    return url


def _glm_coding_plan_key() -> str:
    return (
        os.getenv("SUPEREZIO_GLM_CODING_PLAN_API_KEY", "").strip()
        or os.getenv("SUPEREZIO_AGENT_API_KEY", "").strip()
        or os.getenv("SUPEREZIO_PRIMARY_API_KEY", "").strip()
    )


def _optional_glm_or_deepseek(
    *,
    requested_model: str,
    degrade_model: str,
    env_url: str,
    role_api_key_env: str,
    experts_base_url: str,
    experts_api_key: str,
    glm_key: str,
    role_label: str,
) -> tuple[str, bool, str, str]:
    """Resolve a role endpoint. GLM without a coding-plan key falls back to DeepSeek.

    ``degrade_model`` is the DeepSeek model OF THIS ROLE (12/09/2026: the roles
    that decide run the brain model, the support ones run flash). Only the
    caller knows which role it is building, so the degrade target is passed in
    and never hardcoded here — a forgotten ``SUPEREZIO_AGENT_MODEL=glm-5.3``
    without the key must not silently demote the CEO to the support model.
    """
    model = requested_model.strip() or degrade_model
    if _is_glm_coding_model(model):
        if glm_key:
            return (
                _normalize_zai_base_url(env_url or GLM_CODING_PLAN_BASE_URL),
                False,
                glm_key,
                model,
            )
        logger.warning(
            "%s requested GLM model %s without SUPEREZIO_GLM_CODING_PLAN_API_KEY; "
            "booting DeepSeek %s instead",
            role_label,
            model,
            degrade_model,
        )
        model = degrade_model
        env_url = ""
    base_url = env_url or experts_base_url
    is_local = _is_local_url(base_url)
    api_key = (
        os.getenv(role_api_key_env, "").strip()
        or os.getenv("SUPEREZIO_DEEPSEEK_API_KEY", "").strip()
        or (LOCAL_API_KEY_PLACEHOLDER if is_local else experts_api_key)
    )
    return base_url, is_local, api_key, model


def _deepseek_api_key() -> str:
    api_key = os.getenv("SUPEREZIO_DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "SUPEREZIO_DEEPSEEK_API_KEY is required for the day-trade judge, "
            "auditor and GLM credit fallback (set it in the environment or in "
            ".env/.env.local; entrypoints load both via core.config.secrets.load_local_env)"
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
    # Janela real do endpoint, quando conhecida (n_ctx do config). 0 = nao
    # declarada -> o guard de contexto cai em LOCAL_CONTEXT_HARD_TOKEN_CAP.
    # A janela e propriedade do ENDPOINT local, nao do papel: por isso se
    # resolve uma vez em build_providers e se copia para todo provedor local.
    n_ctx: int = 0
    # Modelo DeepSeek para onde ESTE papel degrada quando o GLM e pedido sem
    # chave (build_default_providers) ou quando o endpoint GLM fica sem credito
    # (ModelGateway). So quem monta o papel sabe se ele decide, por isso o alvo
    # viaja com o provedor: papel de cerebro -> BRAIN_MODEL_ID; de apoio ->
    # DEEPSEEK_MODEL_ID (default). Sem isso o fallback rebaixava o CEO a flash.
    degrade_model: str = DEEPSEEK_MODEL_ID


def _local_window_from_config(config: "UniversalConfig | None") -> int:
    """Janela (n_ctx) declarada para o endpoint local no config; 0 se nao houver.

    A janela e propriedade do ENDPOINT (o llama-server), nao do papel: por isso
    e resolvida uma vez e copiada para todo provedor is_local. Sem declaracao,
    devolve 0 e o guard de contexto do gateway cai em
    LOCAL_CONTEXT_HARD_TOKEN_CAP (comportamento anterior, preservado).
    """
    models = getattr(config, "models", None) or {}
    for model_config in models.values():
        if not getattr(model_config, "is_local", False):
            continue
        n_ctx = int(getattr(model_config, "n_ctx", 0) or 0)
        if n_ctx > 0:
            return n_ctx
    return 0


def build_default_providers(
    config: "UniversalConfig",
) -> tuple[list[ModelProvider], GatewayConfig]:
    """Build the provider list with DeepSeek as the default for every role."""
    providers: list[ModelProvider] = []

    # Optional GLM path: an absent key simply means the provider is not built.
    # A role explicitly configured for a glm model degrades to DeepSeek below.
    glm_key = _glm_coding_plan_key()
    glm_experts_base_url = GLM_CODING_PLAN_BASE_URL

    # Judge/auditor and GLM credit fallback remain a DeepSeek trust boundary.
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
    primary_model = os.getenv("SUPEREZIO_PRIMARY_MODEL", PRIMARY_MODEL_ID)
    primary_base_url, primary_is_local, primary_api_key, primary_model = _optional_glm_or_deepseek(
        requested_model=primary_model,
        # Orquestrador DECIDE: degrada para o cerebro, nunca para o flash.
        degrade_model=PRIMARY_MODEL_ID,
        env_url=primary_env_url,
        role_api_key_env="SUPEREZIO_PRIMARY_API_KEY",
        experts_base_url=experts_base_url,
        experts_api_key=experts_api_key,
        glm_key=glm_key,
        role_label="SUPEREZIO_PRIMARY_MODEL",
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
            n_ctx=_local_window_from_config(config) if primary_is_local else 0,
            degrade_model=PRIMARY_MODEL_ID,
            backend="openai_compatible",
        )
    )

    # Built only when the coding-plan key exists: without it no role can reach
    # GLM, and an unauthenticated provider entry would only add a dead target.
    if glm_key:
        providers.append(
            ModelProvider(
                name=GLM_PROVIDER_NAME,
                base_url=glm_experts_base_url,
                api_key=glm_key,
                priority=-300,
                model=GLM_CODING_PLAN_MODEL,
                timeout_s=experts_timeout_s,
                max_tokens=experts_max_tokens,
                temperature=0.2,
                is_local=False,
                backend="openai_compatible",
            )
        )

    providers.append(
        ModelProvider(
            name=DEEPSEEK_PROVIDER_NAME,
            base_url=experts_base_url,
            api_key=experts_api_key,
            priority=-290,
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

    # Agent (CEO) — DeepSeek by default; GLM-5.3 needs the coding-plan key.
    agent_env_url = os.getenv("SUPEREZIO_AGENT_BASE_URL", "").strip()
    agent_model = os.getenv("SUPEREZIO_AGENT_MODEL", AGENT_MODEL_ID)
    agent_base_url, agent_is_local, agent_api_key, agent_model = _optional_glm_or_deepseek(
        requested_model=agent_model,
        # CEO DECIDE: degrada para o cerebro, nunca para o flash.
        degrade_model=AGENT_MODEL_ID,
        env_url=agent_env_url,
        role_api_key_env="SUPEREZIO_AGENT_API_KEY",
        experts_base_url=experts_base_url,
        experts_api_key=experts_api_key,
        glm_key=glm_key,
        role_label="SUPEREZIO_AGENT_MODEL",
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
                    default=AGENT_DEFAULT_TIMEOUT_S if not agent_is_local else LOCAL_TIMEOUT_S,
                    minimum=1,
                    maximum=3600,
                ),
                AGENT_DEFAULT_TIMEOUT_S if not agent_is_local else LOCAL_TIMEOUT_S,
            ),
            max_tokens=experts_max_tokens if not agent_is_local else LOCAL_MAX_TOKENS,
            temperature=0.4,
            is_local=agent_is_local,
            n_ctx=_local_window_from_config(config) if agent_is_local else 0,
            degrade_model=AGENT_MODEL_ID,
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
