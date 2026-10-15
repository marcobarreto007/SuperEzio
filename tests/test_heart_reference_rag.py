"""Heart archive rows are a dynamic reference, not an order."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from core.heart.event_book import MarketEvent
from core.heart.reference_rag import HeartReferenceIndex


def _archive(tmp_path):
    heart = tmp_path / "heart"
    ohlcv = heart / "ohlcv"
    ohlcv.mkdir(parents=True)
    (ohlcv / "ZZTEST.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2024-06-03,1,1.1,0.9,1.0,1000\n"
        "2024-06-04,1,1.6,0.95,1.5,2000\n",
        encoding="utf-8",
    )
    event = MarketEvent(
        identity="newsfile:zztest:1",
        source="newsfile",
        event_type="press_release",
        occurred_at=datetime(2024, 6, 4, 14, 0, tzinfo=ZoneInfo("America/New_York")),
        timestamp_precision="minute",
        symbol="ZZTEST",
        mic_code="XNAS",
    )
    (heart / "events.jsonl").write_text(
        json.dumps(event.to_row()) + "\n",
        encoding="utf-8",
    )
    return heart, ohlcv


def test_search_returns_archive_row(tmp_path):
    heart, ohlcv = _archive(tmp_path)
    index = HeartReferenceIndex(heart, ohlcv)

    hits = index.search("o que o ZZTEST fez")
    block = index.format_for_query("ZZTEST")

    assert hits
    assert "symbol=ZZTEST" in hits[0]["text"]
    assert "session=2024-06-04" in hits[0]["text"]
    assert "source=newsfile" in hits[0]["text"]
    assert "event=newsfile:zztest:1" in hits[0]["text"]
    assert "HEART_REFERENCE" in block
    assert "nao ordem" in block


def test_index_refits_when_price_file_changes(tmp_path):
    heart, ohlcv = _archive(tmp_path)
    index = HeartReferenceIndex(heart, ohlcv)
    first = index.search("ZZTEST")[0]["text"]

    (ohlcv / "ZZTEST.csv").write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2024-06-03,1,1.1,0.9,1.0,1000\n"
        "2024-06-04,1,2.2,0.95,3.0,2000\n",
        encoding="utf-8",
    )
    second = index.search("ZZTEST")[0]["text"]

    assert first != second
    assert "gross_ret=1.0986" in second


def test_unrelated_name_does_not_scan_as_a_hit(tmp_path):
    heart, ohlcv = _archive(tmp_path)
    index = HeartReferenceIndex(heart, ohlcv)

    assert index.search("analisa AAPL") == []
    assert index.format_for_query("bob , me explica sua arquitetura") == ""


def test_prompt_cites_heart_reference_for_archived_symbol(monkeypatch):
    from core.pipeline.prompts.builder import build_agent_prompt

    monkeypatch.setattr(
        "core.heart.reference_rag.heart_reference.format_for_query",
        lambda query, top_k=5: "HEART_REFERENCE:\n- score=0.90 symbol=ZZTEST session=2024-06-04",
    )
    prompt = build_agent_prompt(
        {
            "message": "o que aconteceu com ZZTEST",
            "intent": "bob_decides",
            "route": "agent",
            "ticker": "ZZTEST",
            "data_context": "price=1.5",
        }
    )

    assert "HEART_REFERENCE" in prompt
    assert "symbol=ZZTEST" in prompt


def test_architecture_prompt_skips_heart_reference():
    from core.pipeline.prompts.builder import build_agent_prompt

    prompt = build_agent_prompt(
        {
            "message": "bob , me explica sua arquitetura",
            "intent": "bob_decides",
            "route": "agent",
            "ticker": "",
        }
    )

    assert "HEART_REFERENCE" not in prompt


def test_observation_includes_heart_and_skips_architecture(monkeypatch):
    from core.pipeline.nodes.observation_builder import _inject_heart_reference

    monkeypatch.setattr(
        "core.heart.reference_rag.heart_reference.format_for_query",
        lambda query, top_k=5: "HEART_REFERENCE:\n- symbol=ZZTEST session=2024-06-04",
    )

    cited: list[str] = []
    _inject_heart_reference({"message": "ZZTEST subiu", "ticker": "ZZTEST"}, cited)
    skipped: list[str] = []
    _inject_heart_reference({"message": "bob , me explica sua arquitetura", "ticker": ""}, skipped)

    assert "symbol=ZZTEST" in "\n".join(cited)
    assert skipped == []
