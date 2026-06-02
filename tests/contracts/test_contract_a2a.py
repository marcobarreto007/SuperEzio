"""Contract tests for A2A Protocol — MessageType + A2AMessage invariants."""

import time
import pytest
from src.core.ports.protocol import A2AMessage, MessageType


# ---------------------------------------------------------------------------
# MessageType enum
# ---------------------------------------------------------------------------


def test_all_message_types():
    assert MessageType.CAPABILITIES_REQUEST == "CAPABILITIES.REQUEST"
    assert MessageType.CAPABILITIES_RESPONSE == "CAPABILITIES.RESPONSE"
    assert MessageType.TASK_SUBMIT == "TASK.SUBMIT"
    assert MessageType.TASK_RESULT == "TASK.RESULT"
    assert MessageType.TASK_STREAM == "TASK.STREAM"
    assert MessageType.EVENT_PUBLISH == "EVENT.PUBLISH"
    assert MessageType.ERROR == "ERROR"


# ---------------------------------------------------------------------------
# A2AMessage creation
# ---------------------------------------------------------------------------


def test_a2a_message_defaults():
    msg = A2AMessage(
        from_agent="marco",
        to_agent="bob",
        type=MessageType.TASK_SUBMIT,
    )
    assert msg.version == "a2a/1.0"
    assert msg.from_agent == "marco"
    assert msg.to_agent == "bob"
    assert msg.type == MessageType.TASK_SUBMIT
    assert isinstance(msg.msg_id, str)
    assert len(msg.msg_id) > 0
    assert isinstance(msg.correlation_id, str)
    assert isinstance(msg.trace_id, str)
    assert msg.msg_id != msg.correlation_id
    assert msg.priority == 1
    assert msg.payload == {}
    assert msg.attachments == []


def test_a2a_message_with_payload():
    msg = A2AMessage(
        from_agent="ui",
        to_agent="agent",
        type=MessageType.TASK_SUBMIT,
        payload={"ticker": "AAPL", "time_horizon": "14 days", "message": "analyze"},
    )
    assert msg.payload["ticker"] == "AAPL"
    assert msg.payload["time_horizon"] == "14 days"


def test_a2a_message_alias_from_to():
    """from_agent is aliased to 'from' in JSON."""
    msg = A2AMessage(from_agent="a", to_agent="b", type=MessageType.ERROR)
    data = msg.model_dump(by_alias=True)
    assert data["from"] == "a"
    assert data["to"] == "b"


def test_a2a_message_parse_from_alias():
    """JSON with 'from' and 'to' keys must parse correctly."""
    data = {"from": "ui", "to": "bob", "type": "TASK.SUBMIT"}
    msg = A2AMessage.model_validate(data)
    assert msg.from_agent == "ui"
    assert msg.to_agent == "bob"
    assert msg.type == MessageType.TASK_SUBMIT


def test_a2a_message_timestamp_is_recent():
    msg = A2AMessage(from_agent="a", to_agent="b", type=MessageType.ERROR)
    now = time.time()
    assert abs(msg.timestamp - now) < 5.0


def test_a2a_message_priority_range():
    msg = A2AMessage(from_agent="a", to_agent="b", type=MessageType.ERROR, priority=3)
    assert msg.priority == 3


# ---------------------------------------------------------------------------
# A2AMessage.create_response
# ---------------------------------------------------------------------------


def test_create_response_preserves_correlation():
    original = A2AMessage(from_agent="ui", to_agent="agent", type=MessageType.TASK_SUBMIT)
    response = A2AMessage.create_response(
        original_msg=original,
        type=MessageType.TASK_RESULT,
        payload={"result": "HOLD"},
        from_agent="agent",
    )
    assert response.correlation_id == original.correlation_id
    assert response.trace_id == original.trace_id
    assert response.from_agent == "agent"
    assert response.to_agent == original.from_agent
    assert response.type == MessageType.TASK_RESULT
    assert response.payload == {"result": "HOLD"}


def test_create_response_different_type():
    original = A2AMessage(from_agent="ui", to_agent="bob", type=MessageType.TASK_SUBMIT)
    error_resp = A2AMessage.create_response(
        original_msg=original,
        type=MessageType.ERROR,
        payload={"error": "timeout"},
        from_agent="bob",
    )
    assert error_resp.type == MessageType.ERROR


# ---------------------------------------------------------------------------
# Required fields validation
# ---------------------------------------------------------------------------


def test_missing_from_raises():
    with pytest.raises(Exception):
        A2AMessage.model_validate({"to": "bob", "type": "TASK.SUBMIT"})


def test_missing_to_raises():
    with pytest.raises(Exception):
        A2AMessage.model_validate({"from": "ui", "type": "TASK.SUBMIT"})


def test_missing_type_raises():
    with pytest.raises(Exception):
        A2AMessage.model_validate({"from": "ui", "to": "bob"})


def test_invalid_type_raises():
    with pytest.raises(Exception):
        A2AMessage.model_validate({"from": "ui", "to": "bob", "type": "INVALID_TYPE"})
