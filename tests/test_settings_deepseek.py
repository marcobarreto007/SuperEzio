from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from core.config.settings import Settings


@pytest.fixture(autouse=True)
def _clean_deepseek_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SUPEREZIO_DEEPSEEK_API_KEY",
        "SUPEREZIO_DEEPSEEK_BASE_URL",
        "SUPEREZIO_DEEPSEEK_MODEL",
        "SUPEREZIO_ALLOW_CUSTOM_DEEPSEEK_BASE_URL",
        "SUPEREZIO_DEEPSEEK_MAX_TOKENS",
        "SUPEREZIO_DEEPSEEK_TIMEOUT_SEC",
        "SUPEREZIO_DEEPSEEK_TEMPERATURE",
        "SUPEREZIO_DAYTRADE_JUDGE_MODEL",
        "SUPEREZIO_DAYTRADE_AUDITOR_MODEL",
        "SUPEREZIO_EXPERT_MAX_TOKENS",
        "SUPEREZIO_EXPERT_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)


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


def test_deepseek_operational_defaults_match_provider_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SUPEREZIO_DEEPSEEK_BASE_URL",
        "SUPEREZIO_DEEPSEEK_MODEL",
        "SUPEREZIO_ALLOW_CUSTOM_DEEPSEEK_BASE_URL",
        "SUPEREZIO_DEEPSEEK_MAX_TOKENS",
        "SUPEREZIO_DEEPSEEK_TIMEOUT_SEC",
        "SUPEREZIO_DEEPSEEK_TEMPERATURE",
        "SUPEREZIO_DAYTRADE_JUDGE_MODEL",
        "SUPEREZIO_DAYTRADE_AUDITOR_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = _settings()

    assert settings.superezio_deepseek_base_url == "https://api.deepseek.com"
    assert settings.superezio_deepseek_model == "deepseek-v4-flash"
    assert settings.superezio_allow_custom_deepseek_base_url is False
    assert settings.superezio_deepseek_max_tokens == 1800
    assert settings.superezio_deepseek_timeout_sec == 180
    assert settings.superezio_deepseek_temperature == 0.2
    assert settings.superezio_daytrade_judge_model == "deepseek-v4-flash"
    assert settings.superezio_daytrade_auditor_model == "deepseek-v4-flash"


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


def test_custom_deepseek_endpoint_requires_explicit_opt_in() -> None:
    denied = _settings(
        superezio_deepseek_api_key="test-key",
        superezio_deepseek_base_url="https://gateway.example.test/v1",
    )
    allowed = _settings(
        superezio_deepseek_api_key="test-key",
        superezio_deepseek_base_url="https://gateway.example.test/v1",
        superezio_allow_custom_deepseek_base_url=True,
    )

    assert denied.deepseek_experts_configured is False
    assert denied.deepseek_configuration_status == "misconfigured_custom_endpoint_not_allowed"
    assert allowed.deepseek_experts_configured is True
    assert allowed.deepseek_configuration_status == "configured"


def test_official_deepseek_rejects_retired_or_local_model_ids_from_readiness() -> None:
    settings = _settings(
        superezio_deepseek_api_key="test-key",
        superezio_deepseek_model="deepseek-chat",
    )

    assert settings.deepseek_experts_configured is False
    assert settings.deepseek_configuration_status == "misconfigured_unsupported_model"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("superezio_deepseek_max_tokens", 127),
        ("superezio_deepseek_max_tokens", 8193),
        ("superezio_deepseek_timeout_sec", 9),
        ("superezio_deepseek_timeout_sec", 601),
        ("superezio_deepseek_temperature", -0.01),
        ("superezio_deepseek_temperature", 2.01),
        ("superezio_expert_max_tokens", 127),
        ("superezio_expert_timeout", 601),
    ],
)
def test_deepseek_operational_limits_are_validated(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


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
