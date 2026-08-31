"""One-shot timed consultation against local :8002. Not a product module."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8002/task/submit"
MSG = (
    "analisa TD.TO e me da uma dica operacional em portugues. "
    "Nao execute ordem."
)
TIMEOUT_S = 240.0

envelope = {
    "version": "a2a/1.0",
    "from": "operator",
    "to": "generic_agent",
    "type": "TASK.SUBMIT",
    "payload": {
        "message": MSG,
        "session_id": "speed-consult-20260829",
    },
}

req = urllib.request.Request(
    URL,
    data=json.dumps(envelope).encode("utf-8"),
    headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
    method="POST",
)

t0 = time.perf_counter()
first_byte_s = None
first_chunk_s = None
stream_end_s = None
events: dict[str, int] = {}
chunks: list[str] = []
steps: list[str] = []
last_types: list[str] = []
http_status = None

try:
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        http_status = resp.status
        buf = ""
        while True:
            raw = resp.read(256)
            if not raw:
                break
            now = time.perf_counter()
            if first_byte_s is None:
                first_byte_s = now - t0
            buf += raw.decode("utf-8", errors="replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    events["PARSE_ERR"] = events.get("PARSE_ERR", 0) + 1
                    continue
                et = str(ev.get("type") or "?")
                events[et] = events.get(et, 0) + 1
                last_types.append(et)
                if et == "CHUNK":
                    if first_chunk_s is None:
                        first_chunk_s = now - t0
                    chunks.append(str(ev.get("content") or ""))
                if et == "PIPELINE_STEP":
                    steps.append(f"{ev.get('step')}:{ev.get('status')}")
                if et == "STREAM_END":
                    stream_end_s = now - t0
except urllib.error.HTTPError as exc:
    http_status = exc.code
    err_body = exc.read().decode("utf-8", errors="replace")
    print(f"HTTP_ERROR {exc.code}")
    print(err_body[:800])
    sys.exit(2)
except Exception as exc:  # noqa: BLE001 — probe operacional: qualquer falha vira saida cronometrada
    elapsed = time.perf_counter() - t0
    print(f"STREAM_FAIL after {elapsed:.2f}s: {type(exc).__name__}: {exc}")
    print(f"http_status={http_status}")
    print(f"first_byte_s={first_byte_s}")
    print(f"first_chunk_s={first_chunk_s}")
    print(f"events={json.dumps(events, ensure_ascii=False)}")
    sys.exit(3)

elapsed = time.perf_counter() - t0
text = "".join(chunks)
print("=== TIMING ===")
print(f"http_status={http_status}")
print(f"wall_s={elapsed:.2f}")
print(f"ttfb_s={first_byte_s:.2f}" if first_byte_s is not None else "ttfb_s=None")
print(
    f"first_chunk_s={first_chunk_s:.2f}" if first_chunk_s is not None else "first_chunk_s=None"
)
print(f"stream_end_s={stream_end_s:.2f}" if stream_end_s is not None else "stream_end_s=None")
print(f"chunk_chars={len(text)}")
print(f"events={json.dumps(events, ensure_ascii=False)}")
print("=== STEPS ===")
for s in steps:
    print(s)
print("=== ANSWER_HEAD ===")
print(text[:900] if text else "(empty)")
print("=== ANSWER_TAIL ===")
print(text[-400:] if text else "(empty)")
