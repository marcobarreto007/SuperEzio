"""SuperEzio configuration system — Quality Engineering 2026 Edition.

Centralizes:
- Environment variable validation via Pydantic Settings (settings.py)
- Structured logging configuration via structlog (logging_config.py)
- Original schema + secrets (schema.py, secrets.py)
"""

from .secrets import load_local_env as load_env_once  # re-exported for compat
from .schema import (
    ModelConfig,
    GatewayConfig,
    EventHubConfig,
    StorageConfig,
    MemoryConfig,
    ObservabilityConfig,
    ServerConfig,
    TriadeConfig,
    UniversalConfig,
    get_config,
    reload_config,
)

__all__ = [
    "load_env_once",
    "ModelConfig",
    "GatewayConfig",
    "EventHubConfig",
    "StorageConfig",
    "MemoryConfig",
    "ObservabilityConfig",
    "ServerConfig",
    "TriadeConfig",
    "UniversalConfig",
    "get_config",
    "reload_config",
]
