"""Collect evidence for a single analysis run."""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = PROJECT_ROOT / "runs" / "evidence"
_RUN_ID_SAFE = re.compile(r"[^A-Z0-9_.-]+")


def _safe_run_suffix(ticker: str) -> str:
    suffix = _RUN_ID_SAFE.sub("", ticker.upper())[:16]
    return suffix.strip("._-")


class EvidenceRun:
    """One analysis run's worth of evidence."""

    def __init__(self, prompt: str, ticker: str = "") -> None:
        self.run_id = (
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}"
        )
        suffix = _safe_run_suffix(ticker)
        if suffix:
            self.run_id += f"_{suffix}"
        self.run_dir = EVIDENCE_DIR / self.run_id
        self.created_at = datetime.now(timezone.utc).isoformat()

        self.prompt: str = prompt
        self.ticker: str = ticker
        self.timeline: list[dict[str, Any]] = []
        self.sources: dict[str, Any] = {}
        self.candidates: list[dict[str, Any]] = []
        self.experts: dict[str, Any] = {}
        self.risk: dict[str, Any] = {}
        self.verdict: dict[str, Any] = {}
        self.response: str = ""
        self.errors: list[dict[str, Any]] = []
        self.price_at_analysis: dict[str, Any] = {}

        self._mark("evidence_run_created")

    def _mark(self, event: str, data: dict[str, Any] | None = None) -> None:
        self.timeline.append(
            {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "elapsed_ms": int((time.monotonic() - self._start) * 1000)
                if hasattr(self, "_start")
                else 0,
                "data": data or {},
            }
        )

    def start(self) -> None:
        self._start = time.monotonic()
        self._mark("pipeline_started")

    def record_scan(
        self,
        candidates: list[dict[str, Any]],
        rejected: int,
        sources_used: list[str],
    ) -> None:
        self.candidates = candidates
        self._mark(
            "scan_complete",
            {
                "candidates_found": len(candidates),
                "rejected": rejected,
                "sources": sources_used,
            },
        )

    def record_source(
        self,
        provider: str,
        capability: str,
        status: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        key = f"{provider}:{capability}"
        self.sources[key] = {
            "provider": provider,
            "capability": capability,
            "status": status,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._mark(
            "source_collected",
            {
                "provider": provider,
                "capability": capability,
                "status": status,
            },
        )

    def record_price(self, ticker: str, price: float, source: str) -> None:
        self.price_at_analysis = {
            "ticker": ticker,
            "price": price,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._mark("price_recorded", {"ticker": ticker, "price": price, "source": source})

    def record_expert(
        self,
        expert_name: str,
        verdict: str,
        confidence: float,
        provider: str,
        bob_readable: str,
    ) -> None:
        self.experts[expert_name] = {
            "verdict": verdict,
            "confidence": confidence,
            "provider": provider,
            "bob_readable": bob_readable,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._mark("expert_complete", {"expert": expert_name, "verdict": verdict})

    def record_risk(self, sdca_result: dict[str, Any]) -> None:
        self.risk = sdca_result
        self._mark(
            "risk_assessment_complete",
            {
                "blocked": sdca_result.get("blocked", False),
                "ghost_tokens": sdca_result.get("ghost_tokens", []),
            },
        )

    def record_verdict(self, verdict_data: dict[str, Any]) -> None:
        self.verdict = verdict_data
        self._mark("verdict_complete")

    def record_response(self, response_text: str, tokens: int = 0) -> None:
        self.response = response_text
        self._mark("response_complete", {"tokens": tokens, "length": len(response_text)})

    def record_error(
        self,
        phase: str,
        error: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.errors.append(
            {
                "phase": phase,
                "error": str(error),
                "detail": detail or {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._mark("error", {"phase": phase, "error": str(error)})

    def finish(self) -> None:
        elapsed = int((time.monotonic() - self._start) * 1000) if hasattr(self, "_start") else 0
        self._mark("evidence_run_complete", {"total_elapsed_ms": elapsed})

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "prompt": self.prompt,
            "ticker": self.ticker,
            "timeline": self.timeline,
            "sources": self.sources,
            "candidates": self.candidates,
            "experts": self.experts,
            "risk": self.risk,
            "verdict": self.verdict,
            "response": self.response,
            "errors": self.errors,
            "price_at_analysis": self.price_at_analysis,
        }
