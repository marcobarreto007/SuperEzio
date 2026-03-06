"""Ports (contratos) do SuperEzio.

Zero dependências externas. ABCs/Protocols puros.
"""

from .audit_log import AuditLogPort
from .data_collector import DataCollectorPort
from .health_probe import HealthProbePort
from .model_gateway import ModelGatewayPort
from .protocol import A2AMessage, MessageType

__all__ = [
    "A2AMessage",
    "AuditLogPort",
    "DataCollectorPort",
    "HealthProbePort",
    "MessageType",
    "ModelGatewayPort",
]
