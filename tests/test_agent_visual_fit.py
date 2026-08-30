"""Tests for agent visual context trimming and chart-visual error handling.

This module tests:
1. Multimodal messages are never trimmed from context
2. Text-only trimming behavior is preserved
3. Chart-visual errors are differentiated (ValueError vs technical errors)
"""

from unittest.mock import patch

import pytest

from src.core.pipeline.chart_image import build_chart_visual_message
from src.core.pipeline.nodes.agent import _fit_messages_to_local_context


class TestMultimodalTrimmingExemption:
    """Tests for multimodal message exemption from context trimming."""

    def test_multimodal_message_preserved_when_budget_forces_trim(self):
        """A multimodal message in the middle of the list survives when budget forces text trimming."""
        # Create messages that exceed budget (24000 chars)
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Pipeline Report:\n" + "X" * 15000},
            # Multimodal message with image
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Chart caption"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                        },
                    },
                ],
            },
            {"role": "user", "content": "Final instruction"},
        ]

        fitted = _fit_messages_to_local_context(messages, char_budget=10000)

        # Find the multimodal message
        multimodal_msg = None
        for msg in fitted:
            if isinstance(msg.get("content"), list):
                multimodal_msg = msg
                break

        assert multimodal_msg is not None, "Multimodal message should not be removed"
        assert isinstance(multimodal_msg["content"], list), (
            "Multimodal content should remain a list"
        )
        assert len(multimodal_msg["content"]) == 2, (
            "Multimodal content should preserve both text and image parts"
        )

    def test_text_only_messages_still_get_trimmed(self):
        """Text-only messages are still trimmed when budget is exceeded."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Pipeline Report:\n" + "X" * 15000},
            {"role": "user", "content": "Observations so far:\n" + "Y" * 15000},
            {"role": "user", "content": "Final instruction"},
        ]

        fitted = _fit_messages_to_local_context(messages, char_budget=10000)

        # Check that text messages were trimmed
        for msg in fitted:
            if isinstance(msg.get("content"), str) and msg["content"].startswith(
                "Pipeline Report:"
            ):
                assert "[TRUNCATED TO FIT LOCAL CONTEXT]" in msg["content"]
                assert len(msg["content"]) < len(messages[1]["content"])

    def test_multimodal_message_does_not_consume_text_budget(self):
        """Multimodal messages should not consume character budget (or only count text parts)."""
        # Use a realistic scenario where trimming is possible
        messages = [
            {"role": "system", "content": "System prompt"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Chart caption"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABC..."}},
                ],
            },
            {"role": "user", "content": "Pipeline Report:\n" + "X" * 15000},
        ]

        # The multimodal message should be preserved (exempt from budget)
        # but the large Pipeline Report should be trimmed to fit
        fitted = _fit_messages_to_local_context(messages, char_budget=10000)

        # Multimodal message should still be present and intact
        multimodal_msg = None
        for msg in fitted:
            if isinstance(msg.get("content"), list):
                multimodal_msg = msg
                break

        assert multimodal_msg is not None, "Multimodal message should be preserved"
        assert multimodal_msg["content"][0]["text"] == "Chart caption"
        assert len(multimodal_msg["content"]) == 2  # Both text and image preserved

        # Pipeline Report should be trimmed (it's a trimmable prefix)
        pipeline_msg = None
        for msg in fitted:
            if isinstance(msg.get("content"), str) and msg["content"].startswith(
                "Pipeline Report:"
            ):
                pipeline_msg = msg
                break

        assert pipeline_msg is not None, "Pipeline Report message should be present (but trimmed)"
        assert "[TRUNCATED" in pipeline_msg["content"]
        assert len(pipeline_msg["content"]) < len(messages[2]["content"])

    def test_text_behavior_preserved_exactly(self):
        """Text-only trimming behavior must be preserved exactly as before."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Pipeline Report:\n" + "X" * 15000},
            {"role": "user", "content": "Observations so far:\n" + "Y" * 15000},
            {"role": "user", "content": "Final instruction"},
        ]

        fitted = _fit_messages_to_local_context(messages, char_budget=10000)

        # Pipeline Report should be trimmed to prefix + 512 chars
        pipeline_msg = None
        for msg in fitted:
            if isinstance(msg.get("content"), str) and msg["content"].startswith(
                "Pipeline Report:"
            ):
                pipeline_msg = msg
                break

        assert pipeline_msg is not None
        assert pipeline_msg["content"].startswith("Pipeline Report:\n")
        assert "[TRUNCATED TO FIT LOCAL CONTEXT]" in pipeline_msg["content"]


class TestChartVisualErrorHandling:
    """Tests for chart-visual error differentiation."""

    def test_value_error_data_insufficient(self):
        """ValueError with 'need_at_least' should return fail-closed message."""
        state = {
            "ticker": "TEST",
            "data": {"ohlcv": []},  # No candles
        }

        # When candles < MIN_CANDLES, build_chart_visual_message returns fail-closed
        result = build_chart_visual_message(state)

        # Should return fail-closed message about insufficient data
        assert result is not None
        assert result["role"] == "user"
        content = result["content"]
        assert isinstance(content, str)
        assert "nao ha velas reais" in content.lower() or "no real candles" in content.lower()

    def test_render_error_raises_exception(self):
        """Technical errors in render_ohlcv_png should raise exceptions (caught by agent)."""
        # Create state with sufficient candles to pass the initial check
        state = {
            "ticker": "TEST",
            "data": {
                "ohlcv": [
                    {"open": 100, "high": 105, "low": 99, "close": 102, "volume": 1000}
                    for _ in range(25)  # 25 candles (>= MIN_CANDLES=20)
                ]
            },
        }

        with patch("src.core.pipeline.chart_image.render_ohlcv_png") as mock_render:
            mock_render.side_effect = RuntimeError("OOM during render")

            # build_chart_visual_message should raise (agent catches it)
            with pytest.raises(RuntimeError, match="OOM during render"):
                build_chart_visual_message(state, attach_image=True)

    def test_successful_chart_generation(self):
        """Successful chart generation is text-only for the local mouth."""
        state = {
            "ticker": "TEST",
            "data": {
                "ohlcv": [
                    {"open": 100, "high": 105, "low": 99, "close": 102, "volume": 1000}
                    for _ in range(25)  # 25 candles (>= MIN_CANDLES=20)
                ]
            },
        }

        result = build_chart_visual_message(state)

        assert result is not None
        assert result["role"] == "user"
        content = result["content"]
        assert isinstance(content, str)
        assert "CONTRATO DE EVIDENCIA" in content
        assert "image_url" not in content

    def test_insufficient_candles_before_render(self):
        """When candles < MIN_CANDLES, should return fail-closed before render."""
        state = {
            "ticker": "TEST",
            "data": {
                "ohlcv": [
                    {"open": 100, "high": 105, "low": 99, "close": 102, "volume": 1000}
                    for _ in range(10)  # Only 10 candles (< MIN_CANDLES=20)
                ]
            },
        }

        result = build_chart_visual_message(state)

        # Should return fail-closed message
        assert result is not None
        assert result["role"] == "user"
        content = result["content"]
        assert isinstance(content, str)
        assert "nao ha velas reais" in content.lower() or "no real candles" in content.lower()


class TestMessageTextHelper:
    """Tests for _message_text helper function."""

    def test_message_text_with_multimodal_content(self):
        """_message_text should extract text from multimodal content."""
        from src.core.pipeline.nodes.agent import _message_text

        content = [
            {"type": "text", "text": "Hello world"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABC..."}},
        ]
        result = _message_text(content)
        assert result == "Hello world"

    def test_message_text_with_string_content(self):
        """_message_text should return string content as-is."""
        from src.core.pipeline.nodes.agent import _message_text

        content = "Plain text message"
        result = _message_text(content)
        assert result == "Plain text message"

    def test_message_text_with_empty_content(self):
        """_message_text should handle empty content."""
        from src.core.pipeline.nodes.agent import _message_text

        result = _message_text("")
        assert result == ""

        result = _message_text(None)
        assert result == ""
