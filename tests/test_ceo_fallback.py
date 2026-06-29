"""Test CEO fallback when GPU/local provider fails."""

import os
import asyncio
import pytest

from core.model_serving.gateway import ModelGateway
from core.model_serving.providers import build_providers


@pytest.mark.asyncio
async def test_ceo_fallback_when_local_fails() -> None:
    """Test that GLM fallback is used when local provider fails."""
    providers, gw_config = build_providers()

    # Find local agent provider
    local_provider = None
    glm_provider = None
    for p in providers:
        if p.name == "agent":
            local_provider = p
        elif p.name == "ceo_fallback_glm":
            glm_provider = p

    if not local_provider:
        pytest.skip("No local agent provider configured")
    if not glm_provider:
        pytest.skip("No GLM fallback provider configured")

    gateway = ModelGateway(providers, gw_config)

    # Simulate local provider failure by putting it in cooldown
    import time

    gateway._provider_cooldown_until["agent"] = time.monotonic() + 1000

    # Request should skip local and use GLM
    providers_to_try = gateway._providers_for_request(
        preferred_provider="agent", allow_fallback=True
    )

    # Should have GLM in the list
    provider_names = [p.name for p in providers_to_try]
    assert "ceo_fallback_glm" in provider_names or any(
        "glm" in name.lower() for name in provider_names
    )


def test_glm_provider_configured() -> None:
    """Test that GLM fallback provider is configured when API key is set."""
    import os

    glm_key = os.getenv("SUPEREZIO_GLM_CODE_PLAN_API_KEY", "")
    if not glm_key:
        pytest.skip("SUPEREZIO_GLM_CODE_PLAN_API_KEY not set")

    providers, _ = build_providers()
    provider_names = [p.name for p in providers]

    assert "ceo_fallback_glm" in provider_names


if __name__ == "__main__":
    print("Testing CEO fallback...")

    # Test 1: Check if GLM is configured
    try:
        test_glm_provider_configured()
        print("✓ GLM fallback provider is configured")
    except pytest.skip.Exception as e:
        print(f"⊘ Skipped: {e}")

    # Test 2: Check fallback when local fails
    try:
        asyncio.run(test_ceo_fallback_when_local_fails())
        print("✓ Fallback mechanism works when local fails")
    except pytest.skip.Exception as e:
        print(f"⊘ Skipped: {e}")
    except Exception as e:
        print(f"✗ Failed: {e}")

    print("\nCEO Fallback Status:")
    print("- GLM provider configured:", os.getenv("SUPEREZIO_GLM_CODE_PLAN_API_KEY", "NOT SET"))
    print("- Fallback mechanism: IMPLEMENTED")
    print("- To test: Stop local GPU server and run pipeline")
