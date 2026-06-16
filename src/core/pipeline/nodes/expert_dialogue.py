"""Multi-turn expert dialogue support for the Trinity stage."""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any


def _parse_json_object(text: str) -> dict[str, Any]:
    clean = str(text or "").strip()
    if not clean:
        return {}
    if clean.startswith("```"):
        lines = clean.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines).strip()
    if clean.lower().startswith("json"):
        clean = clean[4:].strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(clean[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _heuristic_verdict(text: str) -> str:
    upper = str(text or "").upper()
    for verdict in (
        "BLOCK",
        "AVOID",
        "WAIT",
        "SUSPICIOUS",
        "MANIPULATED",
        "OVERVALUED",
        "UNDERVALUED",
        "BULLISH",
        "BEARISH",
        "NEUTRAL",
        "NO_DATA",
    ):
        if verdict in upper:
            return verdict
    return "UNKNOWN"


def extract_verdict_payload(text: str) -> dict[str, Any]:
    """Extract verdict/confidence from JSON when possible, with text fallback."""

    parsed = _parse_json_object(text)
    if parsed:
        confidence = parsed.get("confidence")
        try:
            confidence = float(confidence) if confidence not in (None, "") else None
        except (TypeError, ValueError):
            confidence = None
        return {
            "verdict": str(parsed.get("verdict") or _heuristic_verdict(text)).upper(),
            "confidence": confidence,
            "reasoning": parsed.get("bob_readable")
            or parsed.get("reasoning")
            or parsed.get("rationale")
            or parsed.get("summary")
            or "",
            "parsed": parsed,
        }

    confidence_match = re.search(r"\bconfidence\b[^0-9]*(\d+(?:\.\d+)?)", str(text), re.I)
    confidence = float(confidence_match.group(1)) if confidence_match else None
    return {
        "verdict": _heuristic_verdict(text),
        "confidence": confidence,
        "reasoning": str(text or "").strip()[:500],
        "parsed": {},
    }


class ExpertDialogue:
    """Stateful multi-turn dialogue between Bob and one external expert."""

    def __init__(self, gateway, max_rounds: int = 3):
        self.gateway = gateway
        self.max_rounds = max(1, int(max_rounds or 1))
        self.history: list[dict[str, Any]] = []
        self._system_prompts: dict[str, str] = {}
        self._timeout = int(os.getenv("SUPEREZIO_EXPERT_TIMEOUT", "240"))

    async def ask(
        self,
        role: str,
        provider: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        """First question, equivalent to the original fire-and-forget call."""

        self._system_prompts[role] = system_prompt
        return await self._call(
            role=role,
            provider=provider,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            question=user_prompt,
            phase="ask",
        )

    async def follow_up(self, role: str, provider: str, question: str) -> dict[str, Any]:
        """Ask a follow-up, including previous rounds in the prompt."""

        if len(self.history) >= self.max_rounds:
            skipped = {
                "round": len(self.history) + 1,
                "role": role,
                "provider": provider,
                "phase": "follow_up",
                "question": question,
                "ok": False,
                "skipped": True,
                "error": "max_rounds_reached",
            }
            self.history.append(skipped)
            return skipped

        system_prompt = self._system_prompts.get(
            role,
            f"You are SuperEzio's {role} expert. Refine your answer using the prior dialogue.",
        )
        history_text = self._format_history()
        user_prompt = (
            "Previous expert dialogue:\n"
            f"{history_text}\n\n"
            "Bob follow-up question:\n"
            f"{question}\n\n"
            "Refine your verdict. Output raw JSON when possible with verdict, confidence, "
            "reasoning, top_signals, top_risks, and bob_readable."
        )
        return await self._call(
            role=role,
            provider=provider,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            question=question,
            phase="follow_up",
        )

    def get_verdict(self) -> dict[str, Any]:
        """Return final verdict/confidence extracted from the latest non-skipped round."""

        rounds = [item for item in self.history if not item.get("skipped")]
        last = rounds[-1] if rounds else {}
        payload = extract_verdict_payload(str(last.get("response") or ""))
        return {
            "role": last.get("role", ""),
            "provider": last.get("provider", ""),
            "ok": bool(last.get("ok")),
            "verdict": payload["verdict"],
            "confidence": payload["confidence"],
            "reasoning": payload["reasoning"],
            "rounds": len(rounds),
            "history": list(self.history),
            "parsed": payload["parsed"],
        }

    async def _call(
        self,
        *,
        role: str,
        provider: str,
        system_prompt: str,
        user_prompt: str,
        question: str,
        phase: str,
    ) -> dict[str, Any]:
        round_no = len([item for item in self.history if not item.get("skipped")]) + 1
        if self.gateway is None:
            result = {
                "round": round_no,
                "role": role,
                "provider": provider,
                "phase": phase,
                "question": question,
                "ok": False,
                "error": "gateway_unavailable",
            }
            self.history.append(result)
            return result

        try:
            response = await asyncio.wait_for(
                self.gateway.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    preferred_provider=provider,
                    temperature=0.2,
                    max_tokens=int(os.getenv("SUPEREZIO_EXPERT_MAX_TOKENS", "2000")),
                ),
                timeout=self._timeout,
            )
            response_text = str(response)
            verdict = extract_verdict_payload(response_text)
            result = {
                "round": round_no,
                "role": role,
                "provider": provider,
                "phase": phase,
                "question": question,
                "ok": True,
                "response": response_text,
                "verdict": verdict["verdict"],
                "confidence": verdict["confidence"],
                "reasoning": verdict["reasoning"],
            }
            self.history.append(result)
            return result
        except Exception as exc:
            result = {
                "round": round_no,
                "role": role,
                "provider": provider,
                "phase": phase,
                "question": question,
                "ok": False,
                "error": str(exc)[:200],
            }
            self.history.append(result)
            return result

    def _format_history(self) -> str:
        if not self.history:
            return "(none)"
        lines: list[str] = []
        for item in self.history:
            if item.get("skipped"):
                continue
            lines.append(
                f"Round {item.get('round')}: Bob asked: {str(item.get('question') or '')[:500]}"
            )
            if item.get("ok"):
                lines.append(f"Round {item.get('round')}: Expert answered: {item.get('response')}")
            else:
                lines.append(
                    f"Round {item.get('round')}: Expert failed: {item.get('error', 'unknown')}"
                )
        return "\n".join(lines)


__all__ = ["ExpertDialogue", "extract_verdict_payload"]
