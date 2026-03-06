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
    ModelProvider,
    GatewayConfig,
    build_default_providers,
)

__all__ = [
    "ModelGateway",
    "ModelProvider",
    "GatewayConfig",
    "create_gateway",
    "create_gateway_from_config",
    "build_default_providers",
]
