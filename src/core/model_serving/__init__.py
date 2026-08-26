"""
SuperEzio - Model Serving Package
============================================
Infraestrutura:
- ModelGateway: Fallback automático entre providers externos
- providers: Dataclasses e factory para configuração de providers
"""

from .gateway import (
    ModelGateway,
    create_gateway,
    create_gateway_from_config,
)
from .providers import (
    GatewayConfig,
    ModelProvider,
    build_default_providers,
    build_providers,
)

__all__ = [
    "GatewayConfig",
    "ModelGateway",
    "ModelProvider",
    "build_default_providers",
    "build_providers",
    "create_gateway",
    "create_gateway_from_config",
]
