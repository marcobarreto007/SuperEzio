"""Ask investment questions via A2A API and capture the full response stream."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
import urllib.request
from typing import Any

BASE_URL = os.getenv("SUPEREZIO_BROWSER_SMOKE_URL", "http://127.0.0.1:8002")

QUESTIONS = [
    "I have $25,000 to invest. I am 35 years old, moderate risk tolerance. "
    "How should I allocate this capital? Give me a specific allocation with percentages and tickers.",

    "I want to build a passive income portfolio with dividend stocks. "
    "What are 5 solid dividend stocks or ETFs for a Canadian investor? "
    "Consider tax efficiency and withholding taxes.",

    "With current interest rates and market volatility in May 2026, "
    "should I dollar-cost average into the market or wait for a correction? "
    "Give me a data-driven recommendation.",

    "I hold a concentrated position in AAPL (40% of my portfolio). "
    "Is this too risky? How should I diversify without triggering a huge tax bill?",

    "Compare VOO, VTI, and SCHD for a long-term buy-and-hold investor. "
    "Which one would you recommend and why? Consider fees, diversification, and historical performance.",
]


def ask_one(question: str, session_id: str, timeout_s: int = 180) -> dict[str, Any]:
    envelope = {
        "version": "a2a/1.0",
        "msg_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "from": "invest-qa-script",
        "to": "generic_agent",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": question,
            "session_id": session_id,
        },
    }

    req = urllib.request.Request(
        f"{BASE_URL}/task/submit",
        data=json.dumps(envelope).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        method="POST",
    )

    t0 = time.time()
    chunks: list[dict[str, Any]] = []
    final_text = ""

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            # Read NDJSON stream line by line
            buffer = b""
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line.strip():
                        try:
                            event = json.loads(line.decode("utf-8"))
                            chunks.append(event)
                            # Extract text content if present
                            if isinstance(event, dict):
                                kind = event.get("kind") or event.get("type") or ""
                                text = (
                                    event.get("final_content")
                                    or event.get("content")
                                    or ""
                                )
                                if isinstance(text, str) and len(text) > len(final_text):
                                    final_text = text
                        except json.JSONDecodeError:
                            pass
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "wall_seconds": round(time.time() - t0, 1),
            "chunks": len(chunks),
            "final_text": final_text,
        }

    elapsed = round(time.time() - t0, 1)
    return {
        "ok": True,
        "wall_seconds": elapsed,
        "chunk_count": len(chunks),
        "final_text": final_text[:5000],
        "text_length": len(final_text),
    }


def main():
    session_id = f"invest-qa-{int(time.time())}"
    results = []

    for i, q in enumerate(QUESTIONS, 1):
        label = q.split("?")[0].split(".")[0][:80].strip()
        print(f"\n{'─'*70}")
        print(f"Q{i}: {label}...")
        print(f"   Sending to Bob... ", end="", flush=True)

        result = ask_one(q, session_id, timeout_s=180)
        results.append({"question": label, "result": result})

        if result["ok"]:
            print(f"{result['wall_seconds']}s | {result['text_length']} chars | {result['chunk_count']} chunks")
            print(f"\n{'─'*50}")
            print(result["final_text"][:2000])
        else:
            print(f"FAILED: {result['error']}")

        # Small gap between questions
        if i < len(QUESTIONS):
            time.sleep(2)

    # Save report
    out_path = f"output/playwright/invest-api-qa-{time.strftime('%Y%m%d-%H%M%S')}.json"
    os.makedirs("output/playwright", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
