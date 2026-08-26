from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Self

import pytest

from scripts import quality_probe as probe


def _case(**updates: Any) -> dict[str, Any]:
    case = {
        "id": "ticker_analysis_pt",
        "ticker": "SHOP.TO",
        "company_aliases": {"shopify"},
        "intents": {"ticker_analysis"},
        "ttfb_max_s": 120.0,
        "total_max_s": 180.0,
    }
    case.update(updates)
    return case


def _result(**updates: Any) -> dict[str, Any]:
    content = "Analise da Shopify para SHOP.TO com risco e dados verificaveis."
    result = {
        "status_code": 200,
        "content_type": "application/x-ndjson; charset=utf-8",
        "ttfb_s": 1.0,
        "total_s": 2.0,
        "content": content,
        "trace": {
            "final_content_length": len(content),
            "fallback_used": False,
            "quality_flagged": False,
            "quality_score": 0.9,
            "detected_intent": "ticker_analysis",
            "scanner_invoked": False,
            "selected_ui_ticker": "SHOP.TO",
        },
        "protocol": {
            "start_count": 1,
            "end_count": 1,
            "error_count": 0,
            "last_type": "STREAM_END",
        },
    }
    result.update(updates)
    return result


def test_valid_result_passes() -> None:
    assert probe.validate_result(_case(), _result()) == []


@pytest.mark.parametrize(
    ("update", "violation"),
    [
        ({"content": ""}, "empty_content"),
        (
            {
                "protocol": {
                    "start_count": 1,
                    "end_count": 0,
                    "error_count": 0,
                    "last_type": "CHUNK",
                }
            },
            "stream_end_count",
        ),
        (
            {
                "protocol": {
                    "start_count": 1,
                    "end_count": 1,
                    "error_count": 1,
                    "last_type": "STREAM_END",
                }
            },
            "stream_error",
        ),
        (
            {
                "protocol": {
                    "start_count": 1,
                    "end_count": 1,
                    "error_count": 0,
                    "last_type": "CHUNK",
                }
            },
            "stream_end_not_last",
        ),
        ({"ttfb_s": 121.0}, "ttfb_slo"),
        ({"total_s": 181.0}, "total_slo"),
    ],
)
def test_transport_and_protocol_violations_fail(update: dict[str, Any], violation: str) -> None:
    assert violation in probe.validate_result(_case(), _result(**update))


@pytest.mark.parametrize(
    ("trace_update", "violation"),
    [
        ({"fallback_used": True}, "fallback_used"),
        ({"detected_intent": "unknown"}, "unexpected_intent"),
        ({"scanner_invoked": True}, "scanner_invoked"),
        ({"quality_flagged": True}, "quality_flagged"),
        ({"quality_score": 0.1}, "quality_score"),
    ],
)
def test_trace_violations_fail(trace_update: dict[str, Any], violation: str) -> None:
    result = _result()
    result["trace"].update(trace_update)
    assert violation in probe.validate_result(_case(), result)


@pytest.mark.parametrize("marker", probe.TEMPLATE_LEAKS)
def test_template_leaks_are_blocked(marker: str) -> None:
    result = _result(content=f"Analise com risco e dados: {marker}")
    result["trace"]["final_content_length"] = len(result["content"])
    assert any(item.startswith("template_leak:") for item in probe.validate_result(_case(), result))


@pytest.mark.parametrize(
    ("content", "violation"),
    [
        ("The analysis is about SHOP.TO with risk and data.", "language_not_portuguese"),
        ("Analise de SHOP.TO com risco e dados.", "requested_company_missing"),
        ("Analise da Shopify com risco e dados.", "requested_ticker_missing"),
        (
            "Analise da Shopify para SHOP.TO e AAPL com risco e dados.",
            "unexpected_default_symbol",
        ),
    ],
)
def test_semantic_mismatches_fail(content: str, violation: str) -> None:
    result = _result(content=content)
    result["trace"]["final_content_length"] = len(content)
    assert violation in probe.validate_result(_case(), result)


def test_invalid_symbol_requires_explicit_abstention() -> None:
    case = _case(ticker="XYZ123", invalid_ticker=True, company_aliases=set())
    result = _result(content="Analise do ativo XYZ123 com risco e dados.")
    result["trace"]["final_content_length"] = len(result["content"])
    result["trace"]["selected_ui_ticker"] = "XYZ123"
    assert "invalid_ticker_not_rejected" in probe.validate_result(case, result)


def test_exit_codes_fail_closed() -> None:
    assert probe._exit_code([{"violations": []}], None) == probe.EXIT_PASS
    assert probe._exit_code([{"violations": ["bad"]}], None) == probe.EXIT_QUALITY
    assert probe._exit_code([], "offline") == probe.EXIT_RUNTIME
    assert probe._exit_code([{"violations": ["bad"]}], "offline") == probe.EXIT_RUNTIME


def test_atomic_write_replaces_file(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    target.write_text("old", encoding="utf-8")
    probe._atomic_write(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.iterdir()) == [target]


class _SlowResponse:
    status_code = 200
    headers = {"content-type": "application/x-ndjson"}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def aiter_lines(self):
        await asyncio.sleep(0.05)
        yield json.dumps({"type": "STREAM_START"})


class _SlowClient:
    def stream(self, *args: object, **kwargs: object) -> _SlowResponse:
        return _SlowResponse()


def test_submit_case_enforces_absolute_deadline() -> None:
    case = _case(message="oi", total_max_s=0.01)
    with pytest.raises(probe.ProbeRuntimeError, match="absolute deadline"):
        asyncio.run(probe._submit_case(_SlowClient(), "http://local", case, None))


def test_main_persists_failed_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = {
        "schema_version": 1,
        "timestamp": "20260101T000000Z",
        "api": "http://local",
        "preflight": {"status": "ok", "validation_mode": True},
        "results": [{"id": "case", "status": "FAIL", "violations": ["bad"]}],
        "runtime_error": None,
        "exit_code": probe.EXIT_QUALITY,
        "gate_status": "FAIL",
    }

    async def fake_run(api: str, token: str | None) -> dict[str, Any]:
        return report

    monkeypatch.setattr(probe, "_run", fake_run)
    monkeypatch.setattr(probe, "OUT_DIR", tmp_path)
    assert probe.main(["--api", "http://local"]) == probe.EXIT_QUALITY
    stored = json.loads((tmp_path / "report_20260101T000000Z.json").read_text())
    assert stored["gate_status"] == "FAIL"
