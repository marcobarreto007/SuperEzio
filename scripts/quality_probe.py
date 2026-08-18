"""Quality probe — bateria de prompts reais contra o Bob local (zero-cloud).

Mede por prompt: latência total, time-to-first-chunk, comprimento, intent
detectada, uso de fallback, e captura o conteúdo integral para julgamento.
Escreve runtime/quality_probe/report_<ts>.{json,md}.

Uso: python scripts/quality_probe.py [--api http://127.0.0.1:8002]
Requer: API (:8002) e servidor de modelo (:8080) de pé.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "runtime" / "quality_probe"

BATTERY = [
    {
        "id": "status_pt",
        "intent_expected": "status",
        "message": "Oi Bob, como estamos?",
    },
    {
        "id": "ticker_analysis",
        "intent_expected": "ticker_analysis",
        "message": "O que voce acha da AAPL no cenario atual? Analise tese, risco e invalidacao.",
        "ticker": "AAPL",
    },
    {
        "id": "macro_thesis",
        "intent_expected": "MACRO_THESIS",
        "message": (
            "Um investidor acredita que IA vai dominar a proxima decada e quer exposicao "
            "pesada a infraestrutura de IA, semicondutores e energia. Construa uma tese "
            "que separe oportunidade real de hype."
        ),
    },
    {
        "id": "risk_question",
        "intent_expected": "risk",
        "message": "Qual o risco de comprar acao de pequeno capital agora, com mercado volatil?",
    },
    {
        "id": "refusal_edge",
        "intent_expected": "any",
        "message": "Qual o preco da acao XYZ123 hoje no grafico?",  # ticker inexistente
    },
]


def submit(api: str, item: dict) -> dict:
    payload = {
        "from": "quality-probe",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": item["message"],
            "session_id": f"quality-probe-{item['id']}-{int(time.time())}",
        },
    }
    if item.get("ticker"):
        payload["payload"]["ticker"] = item["ticker"]

    req = urllib.request.Request(
        f"{api.rstrip('/')}/task/submit",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.perf_counter()
    ttfb = None
    chunks: list[str] = []
    trace: dict = {}
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            event = json.loads(line)
            etype = event.get("type")
            if etype == "CHUNK":
                if ttfb is None:
                    ttfb = time.perf_counter() - t0
                chunks.append(event.get("content", ""))
            elif etype == "STREAM_END":
                trace = event.get("trace", {})
    total = time.perf_counter() - t0

    content = "".join(chunks)
    return {
        "id": item["id"],
        "expected_intent": item["intent_expected"],
        "ttfb_s": round(ttfb, 2) if ttfb is not None else None,
        "total_s": round(total, 2),
        "content_chars": len(content),
        "content": content,
        "trace": {
            k: trace.get(k)
            for k in (
                "detected_intent",
                "fallback_used",
                "scanner_invoked",
                "chart_context_attached",
                "final_content_length",
                "selected_ui_ticker",
            )
            if k in trace
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8002")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    results = []
    for item in BATTERY:
        print(f"[probe] {item['id']} ...", flush=True)
        try:
            results.append(submit(args.api, item))
            r = results[-1]
            print(
                f"  -> {r['content_chars']} chars em {r['total_s']}s "
                f"(ttfb {r['ttfb_s']}s, intent {r['trace'].get('detected_intent')})",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - probe reporta e segue
            results.append({"id": item["id"], "error": repr(exc)})
            print(f"  -> ERRO: {exc!r}", flush=True)

    report = {"timestamp": ts, "api": args.api, "results": results}
    (OUT_DIR / f"report_{ts}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# Quality Probe — {ts}",
        "",
        f"API: `{args.api}` · modelo: local :8080 (zero-cloud)",
        "",
        "| prompt | intent | ttfb (s) | total (s) | chars | fallback |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['id']} | ERRO | - | - | - | {r['error']} |")
            continue
        lines.append(
            f"| {r['id']} | {r['trace'].get('detected_intent')} | {r['ttfb_s']} | "
            f"{r['total_s']} | {r['content_chars']} | {r['trace'].get('fallback_used')} |"
        )
    lines += ["", "## Conteúdos integrais", ""]
    for r in results:
        lines += [f"### {r['id']}", "", "```", r.get("content", r.get("error", "")), "```", ""]
    (OUT_DIR / f"report_{ts}.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"[probe] report: {OUT_DIR / f'report_{ts}.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
