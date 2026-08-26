"""Protocol types shared across layers.

A2A message types live here (not in agent_server) so core/model_serving
does not depend on transport-layer code.
"""

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageType(str, Enum):
    CAPABILITIES_REQUEST = "CAPABILITIES.REQUEST"
    CAPABILITIES_RESPONSE = "CAPABILITIES.RESPONSE"
    TASK_SUBMIT = "TASK.SUBMIT"
    TASK_RESULT = "TASK.RESULT"
    TASK_STREAM = "TASK.STREAM"
    EVENT_PUBLISH = "EVENT.PUBLISH"
    ERROR = "ERROR"


class A2AMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: str = "a2a/1.0"
    msg_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    from_agent: str = Field(alias="from")
    to_agent: str = Field(alias="to")

    type: MessageType

    timestamp: float = Field(default_factory=time.time)
    deadline_ms: int | None = None
    priority: int = 1
    budget: float | None = None

    payload: dict[str, Any] = Field(default_factory=dict)
    attachments: list[Any] = Field(default_factory=list)

    @classmethod
    def create_response(
        cls,
        original_msg: "A2AMessage",
        type: MessageType,
        payload: dict[str, Any],
        from_agent: str,
    ) -> "A2AMessage":
        return cls(
            correlation_id=original_msg.correlation_id,
            trace_id=original_msg.trace_id,
            from_agent=from_agent,
            to_agent=original_msg.from_agent,
            type=type,
            payload=payload,
        )
