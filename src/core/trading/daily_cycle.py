"""Daily paper trading cycle orchestration."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from core.mission_context import mission_health_summary

from .approval_gate import approval_request_to_dict, get_approval_gate
from .kill_switch import get_kill_switch
from .paper_journal import PaperJournal
from .performance_metrics import PerformanceEngine


class DailyCycle:
    """Orchestrates explicit paper-trading daily routines."""

    def __init__(
        self,
        *,
        pipeline: Any | None = None,
        journal: PaperJournal | None = None,
        sentiment_pulse: Any | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.journal = journal or PaperJournal()
        self.sentiment_pulse = sentiment_pulse

    async def morning_routine(self) -> dict[str, Any]:
        """09:00 - check overnight sentiment, IBKR, approvals, and kill switch."""

        kill_state = get_kill_switch().check()
        gate = get_approval_gate()
        sentiment = []
        if self.sentiment_pulse is not None:
            sentiment = [
                item.to_dict() if hasattr(item, "to_dict") else item
                for item in self.sentiment_pulse.get_all_pulses()
            ]
        mission = mission_health_summary()
        return {
            "phase": "morning",
            "scheduled_local": "09:00",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "kill_switch": {
                "active": kill_state.is_active,
                "reason": kill_state.reason.value if kill_state.reason else "",
                "daily_pnl": kill_state.daily_pnl,
                "trade_count": kill_state.trade_count,
            },
            "approvals": {
                "pending_count": gate.pending_count,
                "pending": [approval_request_to_dict(req) for req in gate.get_pending()],
            },
            "ibkr": ((mission.get("broker") or {}).get("ibkr") or {}),
            "sentiment": {
                "count": len(sentiment),
                "pulses": sentiment,
            },
        }

    async def trading_session(self, message: str, **kwargs: Any) -> dict[str, Any]:
        """Marco asks; the configured pipeline runs the paper-trading flow."""

        if self.pipeline is None or not hasattr(self.pipeline, "stream_events"):
            return {
                "phase": "trading_session",
                "status": "skipped",
                "reason": "pipeline_not_configured",
                "message": message,
            }

        events = []
        stream: AsyncGenerator[dict[str, Any], None] = self.pipeline.stream_events(
            message,
            **kwargs,
        )
        async for event in stream:
            events.append(event)

        return {
            "phase": "trading_session",
            "status": "completed",
            "message": message,
            "event_count": len(events),
            "events": events,
            "paper_events": [
                event
                for event in events
                if str(event.get("type", "")).startswith("PAPER")
                or event.get("step") == "auto_execute_paper"
            ],
        }

    async def evening_routine(self) -> dict[str, Any]:
        """23:00 - generate paper post-mortem and lessons learned."""

        report = PerformanceEngine(self.journal).evaluate()
        return {
            "phase": "evening",
            "scheduled_local": "23:00",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "open_trades": self.journal.list_open(),
            "closed_trades": self.journal.list_closed(),
            "performance": report.to_dict(),
            "lessons": report.improvement_suggestions,
            "biases": report.detected_biases,
        }
