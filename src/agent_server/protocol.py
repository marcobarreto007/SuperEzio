"""A2A protocol facade — re-exporta tipos canônicos de core.ports.protocol.

Mantido para compatibilidade com callers que fazem
    from agent_server.protocol import A2AMessage
"""

from core.ports.protocol import A2AMessage, MessageType

__all__ = ["A2AMessage", "MessageType"]
