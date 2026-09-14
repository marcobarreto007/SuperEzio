"""
SuperEzio configuration system.

Runtime configuration comes from config/runtime.yml plus local environment
overrides. Secrets must live in .env or the process environment.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from ..paths import resolve_project_path

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for one model provider."""

    path: str = ""
    role: str = "general"
    # Janela do modelo local (llama-server). Era 8192 (era Qwen3.8); o build de
    # 2 GPUs serve 98304 desde 11/09/2026. Fonte de verdade operacional:
    # config/runtime.yml (entrada local_voice) -> ModelProvider.n_ctx -> guard
    # do gateway. Este default so vale para entrada que nao declare n_ctx.
    n_ctx: int = 98304
    n_gpu_layers: int = 0
    gpu: Any = 0
    vram_budget_gb: float = 0.0
    backend: str = "openai_compatible"
    engine: str = "openai_compatible"
    system_prefix: str = ""
    max_tokens: int = 2048
    timeout_s: int = 600
    temperature: float = 0.7
    n_threads: int = 0
    name: str = ""
    is_local: bool = False
    model_id: str = "boss"


@dataclass
class GatewayConfig:
    """Model gateway configuration."""

    max_fallbacks: int = 2
    timeout_s: int = 300
    retry_attempts: int = 2
    retry_delay_s: float = 1.0
    quality_threshold: float = 0.7


@dataclass
class EventHubConfig:
    """Event hub configuration."""

    type: str = "memory"
    redis_url: str = "redis://localhost:6379"
    stream_key: str = "universal_events"
    consumer_group: str = "universal_consumers"


@dataclass
class StorageConfig:
    """Local storage directories."""

    memory_dir: str = "data/memory"
    vectors_dir: str = "data/vectors"
    trace_dir: str = "data/traces"


@dataclass
class MemoryConfig:
    """Persistent memory / Mem0 configuration."""

    enable_mem0: bool = True
    api_url: str = ""
    api_key: str = ""
    collection: str = "default"
    default_top_k: int = 5
    redis_url: str = ""


@dataclass
class ObservabilityConfig:
    """Observability configuration."""

    log_level: str = "INFO"
    enable_otel: bool = True
    otel_exporter: str = "console"


@dataclass
class ServerConfig:
    """HTTP server configuration.

    ``host`` defaults to ``127.0.0.1`` (loopback only) so the server is not
    accidentally exposed on a multi-interface machine. Production deployments
    that need to bind a public interface should override the host explicitly
    via env / config file.
    """

    host: str = "127.0.0.1"
    port: int = 8002
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:8002"])


@dataclass
class TriadeConfig:
    """Triade / committee configuration."""

    max_fallback_attempts: int = 3
    enable_review: bool = True
    stream_responses: bool = True
    use_committee: bool = True


@dataclass
class UniversalConfig:
    """Complete SuperEzio runtime configuration."""

    project_name: str = "SuperEzio"
    version: str = "2.0.0"

    server: ServerConfig = field(default_factory=ServerConfig)
    models: dict[str, ModelConfig] = field(default_factory=dict)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    event_hub: EventHubConfig = field(default_factory=EventHubConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    triade: TriadeConfig = field(default_factory=TriadeConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UniversalConfig:
        config = cls()
        config.project_name = data.get("project_name", config.project_name)
        config.version = data.get("version", config.version)

        if "server" in data:
            section = data["server"] or {}
            config.server = ServerConfig(
                host=section.get("host", config.server.host),
                port=section.get("port", config.server.port),
                cors_origins=section.get("cors_origins", config.server.cors_origins),
            )

        if "models" in data:
            for name, section in (data["models"] or {}).items():
                section = section or {}
                config.models[name] = ModelConfig(
                    name=section.get("name", name),
                    path=section.get("path", ""),
                    role=section.get("role", "general"),
                    n_ctx=section.get("n_ctx", 98304),
                    n_gpu_layers=section.get("n_gpu_layers", 0),
                    gpu=section.get("gpu", 0),
                    vram_budget_gb=section.get("vram_budget_gb", 0.0),
                    backend=section.get("backend", "openai_compatible"),
                    engine=section.get("engine", "openai_compatible"),
                    system_prefix=section.get("system_prefix", ""),
                    max_tokens=section.get("max_tokens", 2048),
                    timeout_s=section.get("timeout_s", 180),
                    temperature=section.get("temperature", 0.7),
                    n_threads=section.get("n_threads", 0),
                    is_local=section.get("is_local", False),
                    model_id=section.get("model_id", "deepseek-v4-flash"),
                )

        if "gateway" in data:
            section = data["gateway"] or {}
            config.gateway = GatewayConfig(
                max_fallbacks=section.get("max_fallbacks", config.gateway.max_fallbacks),
                timeout_s=section.get("timeout_s", config.gateway.timeout_s),
                retry_attempts=section.get("retry_attempts", config.gateway.retry_attempts),
                retry_delay_s=section.get("retry_delay_s", config.gateway.retry_delay_s),
                quality_threshold=section.get(
                    "quality_threshold", config.gateway.quality_threshold
                ),
            )

        if "event_hub" in data:
            section = data["event_hub"] or {}
            config.event_hub = EventHubConfig(
                type=section.get("type", config.event_hub.type),
                redis_url=section.get("redis_url", config.event_hub.redis_url),
                stream_key=section.get("stream_key", config.event_hub.stream_key),
                consumer_group=section.get("consumer_group", config.event_hub.consumer_group),
            )

        if "storage" in data:
            section = data["storage"] or {}
            config.storage = StorageConfig(
                memory_dir=section.get("memory_dir", config.storage.memory_dir),
                vectors_dir=section.get("vectors_dir", config.storage.vectors_dir),
                trace_dir=section.get("trace_dir", config.storage.trace_dir),
            )

        if "memory" in data:
            section = data["memory"] or {}
            config.memory = MemoryConfig(
                enable_mem0=section.get("enable_mem0", config.memory.enable_mem0),
                api_url=section.get("api_url", config.memory.api_url),
                api_key=section.get("api_key", config.memory.api_key),
                collection=section.get("collection", config.memory.collection),
                default_top_k=section.get("default_top_k", config.memory.default_top_k),
                redis_url=section.get("redis_url", config.memory.redis_url),
            )

        if "observability" in data:
            section = data["observability"] or {}
            config.observability = ObservabilityConfig(
                log_level=section.get("log_level", config.observability.log_level),
                enable_otel=section.get("enable_otel", config.observability.enable_otel),
                otel_exporter=section.get("otel_exporter", config.observability.otel_exporter),
            )

        if "triade" in data:
            section = data["triade"] or {}
            config.triade = TriadeConfig(
                max_fallback_attempts=section.get(
                    "max_fallback_attempts", config.triade.max_fallback_attempts
                ),
                enable_review=section.get("enable_review", config.triade.enable_review),
                stream_responses=section.get("stream_responses", config.triade.stream_responses),
                use_committee=section.get("use_committee", config.triade.use_committee),
            )

        return config

    def apply_env_overrides(self) -> None:
        self.server.host = os.getenv("SUPEREZIO_HOST", self.server.host)
        self.server.port = int(os.getenv("SUPEREZIO_PORT", str(self.server.port)))
        self.memory.api_url = os.getenv("MEM0_API_URL", self.memory.api_url)
        self.memory.api_key = os.getenv("MEM0_API_KEY", self.memory.api_key)
        self.memory.redis_url = os.getenv("MEM0_REDIS_URL", self.memory.redis_url)
        cors = os.getenv("CORS_ORIGINS")
        if cors:
            self.server.cors_origins = [item.strip() for item in cors.split(",") if item.strip()]

    @classmethod
    def load(cls, config_path: str = "config/runtime.yml") -> UniversalConfig:
        from .secrets import load_local_env

        load_local_env()

        path = resolve_project_path(config_path)

        if not path.exists():
            logger.info("[CONFIG] File not found: %s. Using defaults.", config_path)
            config = cls()
            config.apply_env_overrides()
            return config

        try:
            with path.open("r", encoding="utf-8") as file:
                data = yaml.safe_load(file) or {}
            logger.info("[CONFIG] Loaded: %s", path)
            config = cls.from_dict(data)
            config.apply_env_overrides()
            return config
        except Exception as exc:  # noqa: BLE001 — catch amplo deliberado: falha de config nunca derruba o boot, cai para defaults
            logger.warning("[CONFIG] Failed to load %s: %s. Using defaults.", config_path, exc)
            config = cls()
            config.apply_env_overrides()
            return config

    def ensure_directories(self) -> None:
        for directory in [
            self.storage.memory_dir,
            self.storage.vectors_dir,
            self.storage.trace_dir,
        ]:
            resolve_project_path(directory).mkdir(parents=True, exist_ok=True)


_config: UniversalConfig | None = None


def get_config() -> UniversalConfig:
    global _config
    if _config is None:
        _config = UniversalConfig.load()
        _config.ensure_directories()
    if os.getenv("DISABLE_OTEL") == "1":
        _config.observability.enable_otel = False
    return _config


def reload_config(path: str = "config/runtime.yml") -> UniversalConfig:
    global _config
    _config = UniversalConfig.load(path)
    _config.ensure_directories()
    return _config
