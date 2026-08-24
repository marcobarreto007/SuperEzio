"""Deterministic chart-for-Bob tests — PNG from real candles, fail-closed, gateway vision."""

from __future__ import annotations

import asyncio

from core.model_serving.gateway import ModelGateway, _has_image_content, _openai_messages
from core.model_serving.providers import GatewayConfig, ModelProvider
from core.pipeline.chart_image import (
    MIN_CANDLES,
    build_chart_visual_message,
    chart_facts,
    extract_ohlcv,
    render_ohlcv_png,
)


def _candles(n: int = 40, start: float = 100.0) -> list[dict]:
    rows = []
    price = start
    for i in range(n):
        price += 0.4 if i % 3 else -0.2
        rows.append(
            {
                "open": price - 0.3,
                "high": price + 0.8,
                "low": price - 0.9,
                "close": price,
                "volume": 1_000_000 + i * 1000,
            }
        )
    return rows


def test_extract_ohlcv_from_pipeline_data():
    ticker, candles = extract_ohlcv({"ticker": "TD.TO", "data": {"ohlcv": _candles(25)}})
    assert ticker == "TD.TO"
    assert len(candles) == 25


def test_extract_ohlcv_missing_is_empty():
    ticker, candles = extract_ohlcv({"ticker": "AAPL", "data": {}})
    assert ticker == "AAPL"
    assert candles == []


def test_render_png_is_real_png_and_facts_match_series():
    candles = _candles(40, start=160.0)
    png = render_ohlcv_png("TD.TO", candles)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 800
    facts = chart_facts("TD.TO", candles)
    assert facts["ticker"] == "TD.TO"
    assert facts["candles"] == 40
    assert facts["last_close"] == round(candles[-1]["close"], 4)
    assert facts["sma20"] is not None
    assert "SMA20" in facts["trend"].upper()


def test_build_message_attaches_image_when_candles_exist():
    msg = build_chart_visual_message({"ticker": "TD.TO", "data": {"ohlcv": _candles(30)}})
    assert msg is not None
    assert msg["role"] == "user"
    assert isinstance(msg["content"], list)
    kinds = [p["type"] for p in msg["content"]]
    assert "text" in kinds
    assert "image_url" in kinds
    text = next(p["text"] for p in msg["content"] if p["type"] == "text")
    assert "CONTRATO DE EVIDENCIA" in text
    assert "TD.TO" in text
    url = next(p["image_url"]["url"] for p in msg["content"] if p["type"] == "image_url")
    assert url.startswith("data:image/png;base64,")


def test_build_message_fail_closed_without_enough_candles():
    msg = build_chart_visual_message(
        {"ticker": "GRTS", "data": {"ohlcv": _candles(MIN_CANDLES - 1)}}
    )
    assert msg is not None
    assert isinstance(msg["content"], str)
    assert "WAIT" in msg["content"]
    assert "COMPRA" in msg["content"]


def test_build_message_skips_casual_turns_without_ticker():
    assert build_chart_visual_message({"message": "oi", "data": {}}) is None


def test_has_image_content_and_openai_strip_internal_keys():
    raw = [
        {"role": "system", "content": "sys"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "see"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}},
            ],
            "_chart_facts": {"ticker": "TD.TO"},
        },
    ]
    assert _has_image_content(raw) is True
    cleaned = _openai_messages(raw)
    assert cleaned[1]["role"] == "user"
    assert "_chart_facts" not in cleaned[1]
    assert _has_image_content([{"role": "user", "content": "texto"}]) is False


def test_chat_completion_forwards_image_messages_without_flattening():
    captured: dict = {}

    async def fake_api(
        self,
        provider,
        prompt="",
        system_prompt="",
        max_tokens=None,
        temperature=None,
        json_mode=False,
        assistant_prefix="",
        messages=None,
    ):
        captured["messages"] = messages
        captured["json_mode"] = json_mode
        captured["prompt"] = prompt
        return "vi o grafico"

    provider = ModelProvider(
        name="agent",
        base_url="http://127.0.0.1:8080/v1",
        priority=0,
        api_key="local-served",
        backend="openai_compatible",
    )
    gw = ModelGateway(
        providers=[provider], config=GatewayConfig(retry_attempts=1, retry_delay_s=0)
    )

    original = ModelGateway.generate_api
    ModelGateway.generate_api = fake_api  # type: ignore[method-assign]
    try:
        msgs = [
            {"role": "system", "content": "Bob"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "analisa"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            },
        ]
        out = asyncio.run(
            gw.chat_completion(messages=msgs, preferred_provider="agent", json_mode=True)
        )
    finally:
        ModelGateway.generate_api = original  # type: ignore[method-assign]

    assert out == "vi o grafico"
    assert captured["messages"] == msgs
    assert captured["json_mode"] is False
    assert captured["prompt"] == ""
    assert _has_image_content(captured["messages"]) is True
