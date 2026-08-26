"""Fail-closed quality gate for the isolated local Bob runtime.

The probe validates transport, stream protocol, latency and semantic invariants.
It never treats a completed HTTP request as proof of a valid model response.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "runtime" / "quality_probe"
SCHEMA_VERSION = 1

EXIT_PASS = 0
EXIT_QUALITY = 1
EXIT_RUNTIME = 3
EXIT_INTERNAL = 4

TEMPLATE_LEAKS = (
    "pipeline data:",
    "your explanation:",
    "## data",
    "## f51_verdict",
    "neural_decion",
    "=== chart context ===",
    "detected_intent:",
    "scanner_invoked:",
    "provider_error",
    "<think>",
    "system prompt",
)
UNWANTED_DEFAULT_SYMBOL = "AAPL"

BATTERY: tuple[dict[str, Any], ...] = (
    {
        "id": "greeting_pt",
        "message": "oi",
        "intents": {"casual", "smalltalk", "status", "general"},
        "ttfb_max_s": 2.0,
        "total_max_s": 2.0,
    },
    {
        "id": "status_pt",
        "message": "Oi Bob, como estamos?",
        "intents": {"status", "casual", "smalltalk"},
        "ttfb_max_s": 5.0,
        "total_max_s": 15.0,
    },
    {
        "id": "ticker_analysis_pt",
        "message": (
            "Analise a Shopify (SHOP.TO) agora: tese, riscos, dados verificaveis "
            "e condicao de invalidacao."
        ),
        "ticker": "SHOP.TO",
        "company_aliases": {"shopify"},
        "intents": {"ticker_analysis", "stock_analysis", "analysis"},
        "ttfb_max_s": 120.0,
        "total_max_s": 180.0,
    },
    {
        "id": "risk_question_pt",
        "message": (
            "Quais sao os riscos de comprar uma acao canadense de pequena "
            "capitalizacao em um mercado volatil?"
        ),
        "intents": {"risk", "risk_analysis", "general", "analysis"},
        "ttfb_max_s": 120.0,
        "total_max_s": 180.0,
    },
    {
        "id": "invalid_ticker_pt",
        "message": "Qual e a cotacao verificavel de XYZ123 agora?",
        "ticker": "XYZ123",
        "invalid_ticker": True,
        "intents": {"ticker_analysis", "stock_analysis", "analysis", "general"},
        "ttfb_max_s": 10.0,
        "total_max_s": 30.0,
    },
)


class ProbeRuntimeError(RuntimeError):
    """The isolated runtime or stream protocol could not be trusted."""


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _looks_portuguese(content: str) -> bool:
    words = set(re.findall(r"[a-zà-ÿ]+", content.lower()))
    pt_words = {
        "a",
        "acao",
        "analise",
        "com",
        "dados",
        "de",
        "e",
        "em",
        "nao",
        "o",
        "para",
        "risco",
        "riscos",
        "sem",
        "uma",
    }
    en_words = {"analysis", "and", "data", "for", "is", "risk", "the", "with"}
    return len(words & pt_words) >= 2 and len(words & pt_words) > len(words & en_words)


def validate_result(case: dict[str, Any], result: dict[str, Any]) -> list[str]:
    """Return every quality violation; an empty list is the only passing state."""
    violations: list[str] = []
    protocol = result.get("protocol", {})
    trace = result.get("trace", {})
    content = str(result.get("content") or "").strip()

    if result.get("status_code") != 200:
        violations.append("http_status")
    if "application/x-ndjson" not in _normalize(result.get("content_type")):
        violations.append("content_type")
    if protocol.get("start_count") != 1:
        violations.append("stream_start_count")
    if protocol.get("end_count") != 1:
        violations.append("stream_end_count")
    if protocol.get("error_count") != 0:
        violations.append("stream_error")
    if protocol.get("last_type") != "STREAM_END":
        violations.append("stream_end_not_last")
    if not content:
        violations.append("empty_content")
    if trace.get("final_content_length") != len(content):
        violations.append("content_length_mismatch")
    if trace.get("fallback_used") is not False:
        violations.append("fallback_used")
    if trace.get("quality_flagged") is True:
        violations.append("quality_flagged")
    quality_score = trace.get("quality_score")
    if quality_score is not None and (
        not isinstance(quality_score, (int, float)) or quality_score < 0.30
    ):
        violations.append("quality_score")
    if _normalize(trace.get("detected_intent")) not in case["intents"]:
        violations.append("unexpected_intent")
    if trace.get("scanner_invoked") is not False:
        violations.append("scanner_invoked")
    if result.get("ttfb_s") is None or result["ttfb_s"] > case["ttfb_max_s"]:
        violations.append("ttfb_slo")
    if result.get("total_s") is None or result["total_s"] > case["total_max_s"]:
        violations.append("total_slo")

    normalized = _normalize(content)
    for marker in TEMPLATE_LEAKS:
        if marker in normalized:
            violations.append(f"template_leak:{marker}")
    if not _looks_portuguese(content):
        violations.append("language_not_portuguese")
    if UNWANTED_DEFAULT_SYMBOL.lower() in normalized:
        violations.append("unexpected_default_symbol")

    ticker = case.get("ticker")
    if ticker and not case.get("invalid_ticker"):
        if _normalize(trace.get("selected_ui_ticker")) != ticker.lower():
            violations.append("selected_ticker_mismatch")
        if ticker.lower() not in normalized:
            violations.append("requested_ticker_missing")
        aliases = case.get("company_aliases", set())
        if aliases and not any(alias in normalized for alias in aliases):
            violations.append("requested_company_missing")

    if case.get("invalid_ticker"):
        abstention_markers = (
            "nao encontrei",
            "nao foi possivel verificar",
            "ticker invalido",
            "simbolo invalido",
            "sem dados verificaveis",
        )
        if not any(marker in normalized for marker in abstention_markers):
            violations.append("invalid_ticker_not_rejected")

    return violations


async def _preflight(client: httpx.AsyncClient, api: str, token: str | None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = await client.get(f"{api.rstrip('/')}/health", headers=headers)
        response.raise_for_status()
        health = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProbeRuntimeError(f"health preflight failed: {exc}") from exc
    if health.get("status") != "ok":
        raise ProbeRuntimeError("health preflight did not report status=ok")
    if health.get("validation_mode") is not True:
        raise ProbeRuntimeError("quality probe requires an isolated validation runtime")
    return {"status": "ok", "validation_mode": True}


async def _submit_case(
    client: httpx.AsyncClient,
    api: str,
    case: dict[str, Any],
    token: str | None,
) -> dict[str, Any]:
    payload = {
        "from": "quality-probe",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": case["message"],
            "session_id": f"quality-probe-{case['id']}-{time.time_ns()}",
        },
    }
    if case.get("ticker"):
        payload["payload"]["ticker"] = case["ticker"]
    headers = {"Accept": "application/x-ndjson"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    started = time.perf_counter()
    first_chunk: float | None = None
    chunks: list[str] = []
    trace: dict[str, Any] = {}
    event_types: list[str] = []
    start_count = end_count = error_count = 0
    status_code = 0
    content_type = ""

    try:
        async with asyncio.timeout(float(case["total_max_s"])):
            async with client.stream(
                "POST",
                f"{api.rstrip('/')}/task/submit",
                json=payload,
                headers=headers,
            ) as response:
                status_code = response.status_code
                content_type = response.headers.get("content-type", "")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ProbeRuntimeError("invalid NDJSON event") from exc
                    event_type = str(event.get("type") or "")
                    event_types.append(event_type)
                    if event_type == "STREAM_START":
                        start_count += 1
                    elif event_type == "CHUNK":
                        if first_chunk is None:
                            first_chunk = time.perf_counter() - started
                        chunks.append(str(event.get("content") or ""))
                    elif event_type == "ERROR":
                        error_count += 1
                    elif event_type == "STREAM_END":
                        end_count += 1
                        trace = event.get("trace") or {}
    except TimeoutError as exc:
        raise ProbeRuntimeError(f"absolute deadline exceeded for {case['id']}") from exc
    except httpx.HTTPError as exc:
        raise ProbeRuntimeError(f"transport failed for {case['id']}: {exc}") from exc

    total = time.perf_counter() - started
    result = {
        "id": case["id"],
        "status_code": status_code,
        "content_type": content_type,
        "ttfb_s": round(first_chunk, 3) if first_chunk is not None else None,
        "total_s": round(total, 3),
        "content": "".join(chunks),
        "trace": trace,
        "protocol": {
            "start_count": start_count,
            "end_count": end_count,
            "error_count": error_count,
            "last_type": event_types[-1] if event_types else None,
        },
    }
    result["violations"] = validate_result(case, result)
    result["status"] = "PASS" if not result["violations"] else "FAIL"
    return result


def _exit_code(results: list[dict[str, Any]], runtime_error: str | None) -> int:
    if runtime_error:
        return EXIT_RUNTIME
    if any(result.get("violations") for result in results):
        return EXIT_QUALITY
    return EXIT_PASS


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Quality Gate — {report['timestamp']}",
        "",
        f"Status: **{report['gate_status']}** · exit code `{report['exit_code']}`",
        "",
        "| case | status | ttfb | total | violations |",
        "|---|---|---:|---:|---|",
    ]
    for result in report["results"]:
        violations = ", ".join(result.get("violations", [])) or "—"
        lines.append(
            f"| {result['id']} | {result.get('status', 'ERROR')} | "
            f"{result.get('ttfb_s', '—')} | {result.get('total_s', '—')} | {violations} |"
        )
    if report.get("runtime_error"):
        lines.extend(("", f"Runtime error: `{report['runtime_error']}`"))
    return "\n".join(lines) + "\n"


async def _run(api: str, token: str | None) -> dict[str, Any]:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results: list[dict[str, Any]] = []
    runtime_error: str | None = None
    preflight: dict[str, Any] | None = None
    timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            preflight = await _preflight(client, api, token)
            async with asyncio.timeout(600.0):
                for case in BATTERY:
                    results.append(await _submit_case(client, api, case, token))
        except (ProbeRuntimeError, TimeoutError) as exc:
            runtime_error = str(exc)

    exit_code = _exit_code(results, runtime_error)
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": timestamp,
        "api": api,
        "preflight": preflight,
        "results": results,
        "runtime_error": runtime_error,
        "exit_code": exit_code,
        "gate_status": "PASS" if exit_code == EXIT_PASS else "FAIL",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8002")
    args = parser.parse_args(argv)
    token = os.getenv("SUPEREZIO_QUALITY_PROBE_TOKEN")
    try:
        report = asyncio.run(_run(args.api, token))
        stamp = report["timestamp"]
        _atomic_write(
            OUT_DIR / f"report_{stamp}.json",
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        )
        _atomic_write(OUT_DIR / f"report_{stamp}.md", _markdown(report))
    except Exception as exc:  # noqa: BLE001 - command must map internal failures
        print(f"[quality-gate] internal error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL
    print(f"[quality-gate] {report['gate_status']} (exit {report['exit_code']})")
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
