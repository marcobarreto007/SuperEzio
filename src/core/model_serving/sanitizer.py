"""Sanitizers for model-private channel tokens."""

from __future__ import annotations

import re

_LOOKBACK = 96

_PRIVATE_CHANNEL_RE = re.compile(
    r"<\|channel\|?>\s*(?:thought|analysis)\s*\r?\n?",
    re.IGNORECASE,
)
_VISIBLE_CHANNEL_RE = re.compile(
    r"<\|channel\|?>\s*(?:final|assistant|commentary)\s*\r?\n?",
    re.IGNORECASE,
)
_CONTROL_TOKEN_RE = re.compile(
    r"<\|(?:channel|message|start|end|system)\|?>|<(?:channel|message|system)\|>",
    re.IGNORECASE,
)
_THINK_OPEN_RE = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)
_THINK_TOKEN_RE = re.compile(r"</?think\b[^>]*>", re.IGNORECASE)


def _strip_think_blocks(text: str) -> str:
    result = text
    while True:
        lower = result.lower()
        start = lower.find("<think>")
        if start == -1:
            break
        end = lower.find("</think>", start + len("<think>"))
        if end == -1:
            result = result[:start]
            break
        result = result[:start] + result[end + len("</think>") :]
    return result.replace("</think>", "")


def _clean_visible_tokens(text: str) -> str:
    return _CONTROL_TOKEN_RE.sub("", text)


def strip_private_model_channels(text: str) -> str:
    """Remove private thought/analysis channel spans from complete text."""
    if not text:
        return text

    source = _strip_think_blocks(text)
    output: list[str] = []
    pos = 0

    while True:
        private = _PRIVATE_CHANNEL_RE.search(source, pos)
        if not private:
            output.append(source[pos:])
            break

        output.append(source[pos : private.start()])
        visible = _VISIBLE_CHANNEL_RE.search(source, private.end())
        if not visible:
            break
        pos = visible.end()

    return _clean_visible_tokens("".join(output)).strip()


class PrivateChannelFilter:
    """Stateful filter for streaming model chunks."""

    def __init__(self) -> None:
        self._buffer = ""
        self._suppressing = False
        self._suppressing_think = False

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._buffer += text
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> str:
        output: list[str] = []

        while self._buffer:
            if self._suppressing_think:
                close = _THINK_CLOSE_RE.search(self._buffer)
                if not close:
                    if final:
                        self._buffer = ""
                    else:
                        self._buffer = self._buffer[-16:]
                    break
                self._buffer = self._buffer[close.end() :]
                self._suppressing_think = False
                continue

            if self._suppressing:
                visible = _VISIBLE_CHANNEL_RE.search(self._buffer)
                if not visible:
                    if final:
                        self._buffer = ""
                    else:
                        self._buffer = self._buffer[-_LOOKBACK:]
                    break
                self._buffer = self._buffer[visible.end() :]
                self._suppressing = False
                continue

            private = _PRIVATE_CHANNEL_RE.search(self._buffer)
            think = _THINK_OPEN_RE.search(self._buffer)
            markers = [m for m in (private, think) if m is not None]
            marker = min(markers, key=lambda m: m.start()) if markers else None
            if marker is None:
                if final:
                    output.append(_THINK_TOKEN_RE.sub("", _clean_visible_tokens(self._buffer)))
                    self._buffer = ""
                else:
                    emit_len = max(0, len(self._buffer) - _LOOKBACK)
                    if emit_len:
                        clean = _clean_visible_tokens(self._buffer[:emit_len])
                        output.append(_THINK_TOKEN_RE.sub("", clean))
                        self._buffer = self._buffer[emit_len:]
                break

            clean = _clean_visible_tokens(self._buffer[: marker.start()])
            output.append(_THINK_TOKEN_RE.sub("", clean))
            self._buffer = self._buffer[marker.end() :]
            if think is not None and marker.start() == think.start():
                self._suppressing_think = True
            else:
                self._suppressing = True

        return "".join(output)


# ── Legacy helpers (preserved for test compatibility) ──────────────────

_ANY_CHANNEL_RE = re.compile(
    r"<\|channel\|?>|<channel\|>",
    re.IGNORECASE,
)

_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)


def _strip_private_channels(text: str) -> str:
    """Strip private channel spans — legacy entrypoint for tests."""
    if not text:
        return text
    text = _THINK_BLOCK_RE.sub("", text)
    text = _THINK_TOKEN_RE.sub("", text)
    output: list[str] = []
    pos = 0
    while True:
        private = _PRIVATE_CHANNEL_RE.search(text, pos)
        if not private:
            output.append(text[pos:])
            break
        output.append(text[pos : private.start()])
        boundary = _ANY_CHANNEL_RE.search(text, private.end())
        if not boundary:
            break
        if _PRIVATE_CHANNEL_RE.match(text, boundary.start()):
            pos = boundary.start()
            continue
        pos = boundary.start()
    return _CONTROL_TOKEN_RE.sub("", "".join(output)).strip()


class _PrivateChannelFilter:
    """Stateful channel filter — legacy entrypoint for tests."""

    def __init__(self) -> None:
        self._buffer = ""
        self._suppressing = False
        self._suppressing_think = False

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._buffer += text
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> str:
        output: list[str] = []
        while self._buffer:
            if self._suppressing_think:
                close = _THINK_CLOSE_RE.search(self._buffer)
                if not close:
                    self._buffer = "" if final else self._buffer[-16:]
                    break
                self._buffer = self._buffer[close.end() :]
                self._suppressing_think = False
                continue
            if self._suppressing:
                boundary = _ANY_CHANNEL_RE.search(self._buffer)
                if not boundary:
                    self._buffer = "" if final else self._buffer[-96:]
                    break
                if _PRIVATE_CHANNEL_RE.match(self._buffer, boundary.start()):
                    self._buffer = self._buffer[boundary.end() :]
                    continue
                self._buffer = self._buffer[boundary.start() :]
                self._suppressing = False
                continue
            private = _PRIVATE_CHANNEL_RE.search(self._buffer)
            think = _THINK_OPEN_RE.search(self._buffer)
            markers = [m for m in (private, think) if m is not None]
            marker = min(markers, key=lambda m: m.start()) if markers else None
            if marker is None:
                if final:
                    clean = _CONTROL_TOKEN_RE.sub("", self._buffer)
                    output.append(_THINK_TOKEN_RE.sub("", clean))
                    self._buffer = ""
                else:
                    emit_len = max(0, len(self._buffer) - 96)
                    if emit_len:
                        clean = _CONTROL_TOKEN_RE.sub("", self._buffer[:emit_len])
                        output.append(_THINK_TOKEN_RE.sub("", clean))
                        self._buffer = self._buffer[emit_len:]
                break
            clean = _CONTROL_TOKEN_RE.sub("", self._buffer[: marker.start()])
            output.append(_THINK_TOKEN_RE.sub("", clean))
            self._buffer = self._buffer[marker.end() :]
            if think is not None and marker.start() == think.start():
                self._suppressing_think = True
            else:
                self._suppressing = True
        return "".join(output)


def _parse_model_tool_calls(content: str) -> tuple[str, list[dict]]:
    """Extract legacy tool calls: <|tool_call>call:name{args}<tool_call|>

    Returns (clean_content, tool_calls_list).
    """
    import json as _json
    import time as _time

    tool_calls = []
    clean_parts = []
    last_end = 0
    pattern = re.compile(r"<\|tool_call\|>call:(?:[\w]+:)?([^{]+)\{([^}]*)\}<tool_call\|>")
    for m in pattern.finditer(content):
        clean_parts.append(content[last_end : m.start()])
        name = m.group(1).strip()
        args_str = m.group(2).strip()
        arguments = {}
        for arg_match in re.finditer(r'(\w+):\s*"([^"]*)"', args_str):
            arguments[arg_match.group(1)] = arg_match.group(2)
        tool_calls.append(
            {
                "id": f"call_{len(tool_calls)}_{int(_time.time() * 1000)}",
                "type": "function",
                "function": {"name": name, "arguments": _json.dumps(arguments)},
            }
        )
        last_end = m.end()
    clean_parts.append(content[last_end:])
    clean = "".join(clean_parts).strip()
    # Strip private channels AFTER tool call extraction so calls survive suppression
    clean = _strip_private_channels(clean)
    return clean, tool_calls
