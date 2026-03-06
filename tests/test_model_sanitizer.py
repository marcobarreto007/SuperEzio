from core.model_serving.sanitizer import (
    PrivateChannelFilter,
    strip_private_model_channels,
)


def test_strip_think_block():
    text = "<think>private reasoning</think>Final answer."
    assert strip_private_model_channels(text) == "Final answer."


def test_stream_think_block_suppressed():
    f = PrivateChannelFilter()
    assert f.feed("<think>private ") == ""
    out = f.feed("reasoning</think>" + ("Final " * 20))
    tail = f.flush()
    combined = out + tail
    assert "private" not in combined
    assert "reasoning" not in combined
    assert "Final" in combined
