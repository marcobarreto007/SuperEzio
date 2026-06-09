#!/usr/bin/env python
"""Qwen Proxy — traduz Anthropic Messages API → OpenAI Chat Completions.

Faz o Claude Code funcionar com Qwen Cloud (dashscope-intl).
Roda em http://127.0.0.1:8787/v1/messages

Uso:
  python scripts/qwen_proxy.py
  set ANTHROPIC_BASE_URL=http://127.0.0.1:8787/v1
"""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError

QWEN_KEY = os.getenv("QWEN_API_KEY", "sk-ws-H.ILDXPI.doi4.MEQCIE2D1sAPg7dRKZUuobk-Qe4xPx8hT1ZlW8Xbgaisigl_AiA74bWE5IwnhreBj4MqZU_st56E4V2ds_e7_t28n7AbVg")
QWEN_BASE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3.7-plus")
PORT = int(os.getenv("QWEN_PROXY_PORT", "8787"))


class ProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len)) if content_len else {}

        # Translate Anthropic → OpenAI
        system_msg = ""
        messages = []
        for msg in body.get("messages", []):
            role = msg.get("role", "user")
            if role == "system":
                system_msg = msg.get("content", "")
            else:
                messages.append({"role": role, "content": msg.get("content", "")})

        if system_msg:
            messages.insert(0, {"role": "system", "content": system_msg})

        max_tokens = body.get("max_tokens", 4096)

        openai_body = {
            "model": QWEN_MODEL,
            "messages": messages,
            "max_tokens": min(max_tokens, 16000),  # Qwen safety cap
            "temperature": body.get("temperature", 0.7),
            "stream": body.get("stream", False),
        }

        try:
            req = Request(
                f"{QWEN_BASE}/chat/completions",
                data=json.dumps(openai_body).encode(),
                headers={
                    "Authorization": f"Bearer {QWEN_KEY}",
                    "Content-Type": "application/json",
                },
            )
            resp = urlopen(req, timeout=120)
            data = json.loads(resp.read())

            # Translate OpenAI → Anthropic
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            stop_reason = choice.get("finish_reason", "stop")
            usage = data.get("usage", {})

            anthropic_resp = {
                "id": f"msg_{data.get('id', '')}",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": content}],
                "model": data.get("model", QWEN_MODEL),
                "stop_reason": "end_turn" if stop_reason == "stop" else stop_reason,
                "usage": {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                },
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(anthropic_resp).encode())

        except HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok","provider":"qwen-cloud"}')


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), ProxyHandler)
    print(f"Qwen Proxy: http://127.0.0.1:{PORT}/v1/messages")
    print(f"Model: {QWEN_MODEL}")
    print(f"Set: ANTHROPIC_BASE_URL=http://127.0.0.1:{PORT}/v1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
        server.server_close()
