from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from core.config.settings import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_deepseek_secret_is_typed_redacted_and_external_ready() -> None:
    secret_value = "sk-deepseek-test-value"
    settings = _settings(superezio_deepseek_api_key=secret_value)

    assert isinstance(settings.superezio_deepseek_api_key, SecretStr)
    assert settings.deepseek_api_key_configured is True
    assert settings.deepseek_external_endpoint is True
    assert settings.deepseek_experts_configured is True
    assert settings.deepseek_configuration_status == "configured"
    assert secret_value not in repr(settings)
    assert secret_value not in str(settings.model_dump())


def test_missing_deepseek_key_is_explicitly_unconfigured_without_invalidating_settings() -> None:
    settings = _settings(superezio_deepseek_api_key="   ")

    assert settings.superezio_deepseek_api_key is None
    assert settings.deepseek_api_key_configured is False
    assert settings.deepseek_experts_configured is False
    assert settings.deepseek_configuration_status == "unconfigured_missing_api_key"


def test_legacy_local_deepseek_endpoint_loads_but_cannot_claim_external_readiness() -> None:
    settings = _settings(
        superezio_deepseek_api_key="test-key",
        superezio_deepseek_base_url="http://127.0.0.1:8080/v1",
    )

    assert settings.deepseek_external_endpoint is False
    assert settings.deepseek_experts_configured is False
    assert settings.deepseek_configuration_status == "misconfigured_non_external_endpoint"


@pytest.mark.parametrize(
    "value",
    ["", "api.deepseek.com/v1", "ftp://api.deepseek.com/v1", "https://user:pw@host/v1"],
)
def test_invalid_deepseek_base_url_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(superezio_deepseek_base_url=value)


def test_unknown_legacy_environment_fields_remain_ignored() -> None:
    settings = _settings(legacy_unmodeled_environment_variable="preserved")

    assert settings.model_config["extra"] == "ignore"
