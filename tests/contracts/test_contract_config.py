"""Contract tests for UniversalConfig configuration system."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# UniversalConfig defaults
# ---------------------------------------------------------------------------


def test_universal_config_defaults():
    from core.config.schema import UniversalConfig

    cfg = UniversalConfig()
    assert cfg.project_name == "SuperEzio"
    assert cfg.version == "2.0.0"
    assert cfg.server.host == "127.0.0.1"
    assert cfg.server.port == 8002


def test_universal_config_from_dict_minimal():
    from core.config.schema import UniversalConfig

    cfg = UniversalConfig.from_dict({"project_name": "TestProject", "version": "5.0.0"})
    assert cfg.project_name == "TestProject"
    assert cfg.version == "5.0.0"
    # Defaults preserved
    assert cfg.server.host == "127.0.0.1"


def test_universal_config_from_dict_server():
    from core.config.schema import UniversalConfig

    cfg = UniversalConfig.from_dict(
        {"server": {"host": "0.0.0.0", "port": 9999, "cors_origins": ["http://example.com"]}}
    )
    assert cfg.server.host == "0.0.0.0"
    assert cfg.server.port == 9999
    assert "http://example.com" in cfg.server.cors_origins


def test_universal_config_from_dict_models():
    from core.config.schema import UniversalConfig

    cfg = UniversalConfig.from_dict(
        {
            "models": {
                "agent": {
                    "name": "agent",
                    "path": "models/test.gguf",
                    "is_local": True,
                    "n_gpu_layers": 28,
                    "n_ctx": 8192,
                    "max_tokens": 512,
                }
            }
        }
    )
    assert "agent" in cfg.models
    assert cfg.models["agent"].path == "models/test.gguf"
    assert cfg.models["agent"].is_local is True
    assert cfg.models["agent"].n_gpu_layers == 28


def test_universal_config_from_dict_gateway():
    from core.config.schema import UniversalConfig

    cfg = UniversalConfig.from_dict(
        {"gateway": {"max_fallbacks": 3, "timeout_s": 60, "retry_attempts": 4}}
    )
    assert cfg.gateway.max_fallbacks == 3
    assert cfg.gateway.timeout_s == 60
    assert cfg.gateway.retry_attempts == 4


def test_universal_config_from_dict_none_sections():
    """All config sections must handle None gracefully."""
    from core.config.schema import UniversalConfig

    cfg = UniversalConfig.from_dict(
        {
            "server": None,
            "models": None,
            "gateway": None,
            "event_hub": None,
            "storage": None,
            "memory": None,
            "observability": None,
            "triade": None,
        }
    )
    assert cfg.server.host == "127.0.0.1"
    assert cfg.gateway.max_fallbacks == 2
    assert cfg.triade.use_committee is True


# ---------------------------------------------------------------------------
# Env overrides
# ---------------------------------------------------------------------------


def test_apply_env_overrides_host(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HOST", "192.168.1.1")
    monkeypatch.setenv("SUPEREZIO_PORT", "9999")
    from core.config.schema import UniversalConfig

    cfg = UniversalConfig()
    cfg.apply_env_overrides()
    assert cfg.server.host == "192.168.1.1"
    assert cfg.server.port == 9999


def test_apply_env_overrides_cors(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com,http://b.com")
    from core.config.schema import UniversalConfig

    cfg = UniversalConfig()
    cfg.apply_env_overrides()
    assert "http://a.com" in cfg.server.cors_origins
    assert "http://b.com" in cfg.server.cors_origins


# ---------------------------------------------------------------------------
# get_config singleton
# ---------------------------------------------------------------------------


def test_get_config_returns_universal_config():
    from core.config.schema import get_config

    cfg = get_config()
    from core.config.schema import UniversalConfig

    assert isinstance(cfg, UniversalConfig)
    assert cfg.server.port >= 0


def test_reload_config():
    from core.config.schema import reload_config

    cfg = reload_config()
    from core.config.schema import UniversalConfig

    assert isinstance(cfg, UniversalConfig)


# ---------------------------------------------------------------------------
# Config load from file
# ---------------------------------------------------------------------------


def test_universal_config_load_file():
    from core.config.schema import UniversalConfig

    cfg = UniversalConfig.load("config/runtime.yml")
    assert cfg is not None
    assert cfg.server.host in ("127.0.0.1", "0.0.0.0", "localhost")


# ---------------------------------------------------------------------------
# Secrets loading
# ---------------------------------------------------------------------------


def test_load_local_env_no_error():
    """load_local_env must not raise when .env is missing."""
    from core.config.secrets import load_local_env

    # Should not raise
    load_local_env()


def test_glm_sidecar_overrides_stale_env_local(tmp_path, monkeypatch):
    import os

    from core.config import secrets

    (tmp_path / "secrets").mkdir()
    (tmp_path / ".env.local").write_text("SUPEREZIO_AGENT_MODEL=deepseek-v4-pro\n", encoding="utf-8")
    (tmp_path / "secrets" / "glm_coding_plan.env").write_text(
        "SUPEREZIO_AGENT_MODEL=glm-5.3\n", encoding="utf-8"
    )
    monkeypatch.setattr(secrets, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(secrets, "_LOADED", False)
    monkeypatch.delenv("SUPEREZIO_AGENT_MODEL", raising=False)
    secrets.load_local_env()
    assert os.environ["SUPEREZIO_AGENT_MODEL"] == "glm-5.3"
    monkeypatch.delenv("SUPEREZIO_AGENT_MODEL", raising=False)


def test_env_files_include_glm_coding_plan_sidecar():
    from pathlib import Path

    from core.config.secrets import _env_files

    names = [p.name for p in _env_files(Path("C:/repo"))]
    assert names == ["glm_coding_plan.env", ".env.local", ".env"]
    assert _env_files(Path("C:/repo"))[0] == Path("C:/repo/secrets/glm_coding_plan.env")


# ---------------------------------------------------------------------------
# StorageConfig
# ---------------------------------------------------------------------------


def test_storage_config_defaults():
    from core.config.schema import StorageConfig

    s = StorageConfig()
    assert s.memory_dir == "data/memory"
    assert s.vectors_dir == "data/vectors"
    assert s.trace_dir == "data/traces"


# ---------------------------------------------------------------------------
# ObservabilityConfig
# ---------------------------------------------------------------------------


def test_observability_config_defaults():
    from core.config.schema import ObservabilityConfig

    o = ObservabilityConfig()
    assert o.log_level == "INFO"
    assert o.enable_otel is True
    assert o.otel_exporter == "console"


# ---------------------------------------------------------------------------
# TriadeConfig
# ---------------------------------------------------------------------------


def test_triade_config_defaults():
    from core.config.schema import TriadeConfig

    t = TriadeConfig()
    assert t.max_fallback_attempts == 3
    assert t.enable_review is True
    assert t.stream_responses is True
    assert t.use_committee is True
