"""Sanitizers for model-private channel tokens."""

from __future__ import annotations

import re
from typing import overload

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


@overload
def strip_private_model_channels(text: str) -> str: ...


@overload
def strip_private_model_channels(text: None) -> None: ...


def strip_private_model_channels(text: str | None) -> str | None:
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
