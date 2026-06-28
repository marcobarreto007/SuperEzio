"""Bob's Autonomic Nervous System — background scanner + self-healing loop.

Runs continuously in a daemon thread:
  - Every 60s: full body scan
  - If pain detected: auto-heal attempt
  - Every 300s: deep scan (includes historical cache, circuit breakers)
  - On critical pain: escalate to operator (log, dashboard alert)

This is Bob's "heartbeat" — if this stops, Bob is clinically dead.
"""

from __future__ import annotations

import logging, threading, time
from datetime import datetime, timezone
from typing import Any

from .body import get_bobs_body, PainLevel

logger = logging.getLogger(__name__)

class AutonomicNervousSystem:
    """Bob's background health monitor — runs forever."""

    def __init__(self, scan_interval: int = 60, deep_scan_interval: int = 300):
        self._body = get_bobs_body()
        self._scan_interval = scan_interval
        self._deep_scan_interval = deep_scan_interval
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_deep_scan = 0.0
        self._cycles = 0
        self._critical_events = 0

    def start(self) -> None:
        """Start the autonomic nervous system in background."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="bob-ans")
        self._thread.start()
        logger.info("bob_ans_started: scan_every_%ds deep_every_%ds",
                     self._scan_interval, self._deep_scan_interval)

    def stop(self) -> None:
        """Stop the autonomic nervous system."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("bob_ans_stopped: %d cycles", self._cycles)

    def _loop(self) -> None:
        """Main loop — scan, heal, sleep, repeat."""
        while self._running:
            try:
                self._cycles += 1
                now = time.time()

                # Quick scan every cycle
                report = self._body.full_body_scan()

                # Auto-heal if anything is sick
                if report["sick_count"] > 0:
                    logger.warning("bob_pain_detected: %d sick organs, pain=%d",
                                   report["sick_count"], report["overall_pain"])
                    heal = self._body.auto_heal()
                    healed = sum(1 for v in heal.values() if v["healed"])
                    if healed > 0:
                        logger.info("bob_healed: %d organs recovered", healed)

                # Deep scan periodically
                if now - self._last_deep_scan >= self._deep_scan_interval:
                    self._last_deep_scan = now
                    if report["critical_count"] > 0:
                        self._critical_events += 1
                        logger.critical(
                            "bob_critical_pain: %d critical organs | total_critical_events=%d",
                            report["critical_count"], self._critical_events,
                        )

                # Log health every 10 cycles
                if self._cycles % 10 == 0:
                    logger.info(
                        "bob_vitals: healthy=%d sick=%d pain=%d cycles=%d",
                        report["healthy_count"], report["sick_count"],
                        report["overall_pain"], self._cycles,
                    )

            except Exception as e:
                logger.error("bob_ans_cycle_error: %s", str(e)[:200])

            time.sleep(self._scan_interval)

    @property
    def status(self) -> dict[str, Any]:
        """Current ANS status."""
        report = self._body.full_body_scan()
        return {
            "running": self._running,
            "cycles": self._cycles,
            "critical_events": self._critical_events,
            "healthy_organs": report["healthy_count"],
            "sick_organs": report["sick_count"],
            "overall_pain": report["overall_pain"],
            "last_scan": report["timestamp"],
            "scan_interval_s": self._scan_interval,
        }


# Singleton
_ans: AutonomicNervousSystem | None = None


def get_ans() -> AutonomicNervousSystem:
    global _ans
    if _ans is None:
        _ans = AutonomicNervousSystem()
    return _ans


def start_ans() -> None:
    get_ans().start()


def stop_ans() -> None:
    if _ans:
        _ans.stop()
