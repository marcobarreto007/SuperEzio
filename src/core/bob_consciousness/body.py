"""Bob's Body - System Health Monitor + Self-Healing.

Bob "feels" every component of his own body. When something breaks,
he feels pain, diagnoses the problem, and tries to heal himself.

Architecture (2026 self-healing pattern):
  Bob Consciousness
  |-- Body Scan (health check every component)
  |-- Pain System (loss signal -> urgency -> action)
  |-- Self-Diagnosis (what broke? why? can I fix it?)
  |-- Auto-Recovery (restart, retry, degrade, escalate)
  |-- Evolution Log (what did I learn from this pain?)

Design principles:
  - Bob's body IS the system. If a component dies, Bob feels it.
  - Pain is proportional to impact (CEO down = critical, Stooq down = mild).
  - Bob tries to fix before asking for help.
  - Every pain event is a learning opportunity.
"""

from __future__ import annotations

import json, logging, os, socket, sqlite3, subprocess, sys, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ===========================================================
# Pain Levels - How much it hurts when something breaks
# ===========================================================

class PainLevel(Enum):
    CRITICAL = 100   # Bob himself is dying (CEO down, no LLM)
    SEVERE = 75      # Can't trade (IBKR down, journal broken)
    HIGH = 50        # Can't scan (DataHub down, all providers dead)
    MODERATE = 25    # Degraded (one provider down, cache stale)
    MILD = 10        # Annoyance (Stooq 404, non-critical)
    NONE = 0         # Everything fine

class OrganCategory(Enum):
    BRAIN = "brain"       # CEO LLM, model serving
    SENSES = "senses"     # Data providers, scanner
    MUSCLES = "muscles"   # IBKR, broker, order execution
    MEMORY = "memory"     # Journal, dedup, dead letter
    DEFENSE = "defense"   # Trade gate, guardrails, circuit breaker
    HEART = "heart"       # API server, dashboard

class SystemMode(Enum):
    NORMAL = "normal"           # Tudo funcionando, trading ativo
    MAN_AT_WORK = "man_at_work" # CEO morto ou crítico, só diagnóstico, sem ordens
    EMERGENCY_SHUTDOWN = "emergency_shutdown"  # Falha catastrófica, tudo para

# ===========================================================
# Organ - A component Bob monitors and can heal
# ===========================================================

@dataclass
class Organ:
    name: str
    category: OrganCategory
    check_fn: Callable[[], tuple]
    pain_level: PainLevel
    auto_heal_fn: Callable[[], bool] | None = None
    last_health: bool = True
    last_check: str = ""
    last_error: str = ""
    heal_attempts: int = 0
    consecutive_failures: int = 0
    # Circuit breaker state
    circuit_open_until: float = 0  # unix timestamp when circuit closes
    failure_threshold: int = 5  # consecutive failures to open circuit

    def check(self) -> bool:
        # Circuit breaker: if open, skip check and return cached failure
        if self.circuit_open_until > time.time():
            return self.last_health  # Return last known state

        try:
            healthy, error = self.check_fn()
            self.last_health = healthy
            self.last_check = datetime.now(timezone.utc).isoformat()
            if not healthy:
                self.last_error = error
                self.consecutive_failures += 1
                # Open circuit if threshold reached
                if self.consecutive_failures >= self.failure_threshold:
                    self.circuit_open_until = time.time() + 300  # 5 min cooldown
                    logger.warning("bob_circuit_open: %s after %d failures", self.name, self.consecutive_failures)
            else:
                self.last_error = ""
                self.consecutive_failures = 0
                self.circuit_open_until = 0  # Close circuit on success
            return healthy
        except Exception as e:
            self.last_health = False
            self.last_error = str(e)[:200]
            self.consecutive_failures += 1
            # Open circuit on exception too
            if self.consecutive_failures >= self.failure_threshold:
                self.circuit_open_until = time.time() + 300
            return False

    def heal(self) -> bool:
        if not self.auto_heal_fn:
            return False
        try:
            self.heal_attempts += 1
            return self.auto_heal_fn()
        except Exception:
            return False

# ===========================================================
# Pain Event - Recorded when something hurts
# ===========================================================

@dataclass
class PainEvent:
    organ_name: str
    category: OrganCategory
    pain_level: PainLevel
    error: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    healed: bool = False
    healed_at: str = ""
    escalated: bool = False

# ===========================================================
# Body Scanner - Health check functions for every organ
# ===========================================================

def _check_ceo_health() -> tuple:
    """Check if Bob's brain (llama-server :8082) is alive."""
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8082/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "ok":
                return True, ""
            return False, f"CEO health status: {data.get('status', 'unknown')}"
    except Exception as e:
        return False, f"CEO unreachable: {str(e)[:100]}"

def _check_api_health() -> tuple:
    """Check if API server (:8002) is alive."""
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8002/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            if data.get("status") == "ok":
                return True, ""
            return False, f"API status: {data.get('status', 'unknown')}"
    except Exception as e:
        return False, f"API unreachable: {str(e)[:100]}"

def _check_datahub_health() -> tuple:
    """Check if at least one price provider works."""
    try:
        from data.data_hub import DataHub
        hub = DataHub()
        active = hub.list_active()
        if not active:
            return False, "No active data providers"
        result = hub.get_price("AAPL")
        if result and result.get("price"):
            return True, f"via {result.get('source', 'unknown')}"
        return False, "DataHub returned no price for AAPL"
    except Exception as e:
        return False, f"DataHub error: {str(e)[:100]}"

def _check_ibkr_health() -> tuple:
    """Check if IBKR TWS/Gateway is reachable."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(("127.0.0.1", 7497))
        s.close()
        return True, ""
    except Exception as e:
        return False, f"IBKR offline: {str(e)[:100]}"

def _check_journal_health() -> tuple:
    """Check if paper journal is writable."""
    try:
        from core.trading.paper_journal import DEFAULT_JOURNAL_PATH
        path = DEFAULT_JOURNAL_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"trade_id": f"hb-{int(time.time())}",
                "ticker": "__HEARTBEAT__", "direction": "none",
                "entry_date": datetime.now(timezone.utc).isoformat(),
                "entry_price": 0.0, "shares": 0,
                "outcome": "heartbeat",
                "created_at": datetime.now(timezone.utc).isoformat()}) + "\n")
            fh.flush()
        return True, ""
    except Exception as e:
        return False, f"Journal unwritable: {str(e)[:100]}"

def _check_openbb_scanner() -> tuple:
    """Check if OpenBB scanner works."""
    try:
        from src.core.scanner.openbb_scanner import OpenBBScanner
        scanner = OpenBBScanner()
        if scanner.available:
            results = scanner.scan_equities(limit=5)
            if results:
                return True, f"{len(results)} tickers"
            return False, "Scanner returned empty"
        return False, "OpenBB not available"
    except Exception as e:
        return False, f"Scanner error: {str(e)[:100]}"

def _check_settings_valid() -> tuple:
    """Check Pydantic Settings are valid."""
    try:
        from core.config.settings import get_settings
        s = get_settings()
        return True, f"freeze={s.f51_trading_execution_freeze}"
    except Exception as e:
        return False, f"Settings invalid: {str(e)[:100]}"

def _check_dead_letter_queue() -> tuple:
    """Check dead letter queue size."""
    try:
        from core.idempotency import count_dead_letters
        count = count_dead_letters()
        if count > 10:
            return False, f"Dead letter queue growing: {count} pending"
        return True, f"{count} pending"
    except Exception as e:
        return False, f"DLQ check error: {str(e)[:100]}"

def _check_historical_cache() -> tuple:
    """Check if historical cache has data."""
    try:
        db_path = Path("data/historical_cache.db")
        if not db_path.exists():
            return False, "Cache DB does not exist"
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT COUNT(DISTINCT ticker) FROM ohlcv_cache").fetchone()
        conn.close()
        count = row[0] if row else 0
        if count < 10:
            return False, f"Only {count} tickers cached (need >10)"
        return True, f"{count} tickers cached"
    except Exception as e:
        return False, f"Cache error: {str(e)[:100]}"

def _check_circuit_breakers() -> tuple:
    """Check circuit breaker states."""
    try:
        from core.resilience import get_all_circuits_health
        circuits = get_all_circuits_health()
        open_circuits = [c for c in circuits if c.get("state") == "open"]
        if open_circuits:
            return False, f"Open circuits: {[c['circuit'] for c in open_circuits]}"
        return True, f"{len(circuits)} circuits healthy"
    except Exception as e:
        return False, f"Circuit check error: {str(e)[:100]}"

# ===========================================================
# Auto-Healing Functions
# ===========================================================

def _heal_datahub() -> bool:
    """Try to heal DataHub by clearing provider cache."""
    try:
        from data.data_hub import DataHub
        hub = DataHub()
        hub.providers.clear()
        hub._register_default_routes()
        return True
    except Exception:
        return False

def _heal_journal() -> bool:
    """Try to heal journal by recreating directory."""
    try:
        from core.trading.paper_journal import DEFAULT_JOURNAL_PATH
        DEFAULT_JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False

# ===========================================================
# Bob's Body - The complete organism
# ===========================================================

class BobsBody:
    """Bob's physical body - all organs he monitors and heals."""

    def __init__(self):
        self.organs: dict[str, Organ] = {
            "ceo_brain": Organ(
                name="CEO Brain (Qwen 80B :8082)",
                category=OrganCategory.BRAIN,
                check_fn=_check_ceo_health,
                pain_level=PainLevel.CRITICAL,
            ),
            "api_heart": Organ(
                name="API Heart (:8002)",
                category=OrganCategory.HEART,
                check_fn=_check_api_health,
                pain_level=PainLevel.SEVERE,
            ),
            "datahub_senses": Organ(
                name="DataHub Senses (prices)",
                category=OrganCategory.SENSES,
                check_fn=_check_datahub_health,
                pain_level=PainLevel.HIGH,
                auto_heal_fn=_heal_datahub,
            ),
            "ibkr_muscles": Organ(
                name="IBKR Muscles (order execution)",
                category=OrganCategory.MUSCLES,
                check_fn=_check_ibkr_health,
                pain_level=PainLevel.SEVERE,
            ),
            "journal_memory": Organ(
                name="Journal Memory",
                category=OrganCategory.MEMORY,
                check_fn=_check_journal_health,
                pain_level=PainLevel.SEVERE,
                auto_heal_fn=_heal_journal,
            ),
            "scanner_eyes": Organ(
                name="Scanner Eyes (OpenBB)",
                category=OrganCategory.SENSES,
                check_fn=_check_openbb_scanner,
                pain_level=PainLevel.MODERATE,
            ),
            "settings_spine": Organ(
                name="Settings Spine (Pydantic)",
                category=OrganCategory.DEFENSE,
                check_fn=_check_settings_valid,
                pain_level=PainLevel.CRITICAL,
            ),
            "dead_letter_kidneys": Organ(
                name="Dead Letter Queue (kidneys)",
                category=OrganCategory.MEMORY,
                check_fn=_check_dead_letter_queue,
                pain_level=PainLevel.MODERATE,
            ),
            "cache_liver": Organ(
                name="Historical Cache (liver)",
                category=OrganCategory.MEMORY,
                check_fn=_check_historical_cache,
                pain_level=PainLevel.MODERATE,
            ),
            "circuit_breakers_immune": Organ(
                name="Circuit Breakers (immune system)",
                category=OrganCategory.DEFENSE,
                check_fn=_check_circuit_breakers,
                pain_level=PainLevel.HIGH,
            ),
        }
        self.pain_history: list[PainEvent] = []
        self.last_full_scan: str = ""
        self.total_scans: int = 0
        self.total_heals: int = 0
        self._pain_log_path = Path("data/bob_pain_log.jsonl")
        # System mode: NORMAL, MAN_AT_WORK, EMERGENCY_SHUTDOWN
        self.system_mode = SystemMode.NORMAL
        self._mode_entered_at: str = ""
        self._mode_reason: str = ""

    # ── System Mode (MAN_AT_WORK) ──

    def enter_man_at_work_mode(self, reason: str) -> None:
        """Enter MAN_AT_WORK mode - no trading, diagnosis only."""
        if self.system_mode == SystemMode.MAN_AT_WORK:
            return  # Already in mode

        self.system_mode = SystemMode.MAN_AT_WORK
        self._mode_entered_at = datetime.now(timezone.utc).isoformat()
        self._mode_reason = reason

        logger.critical("=== MAN_AT_WORK MODE ENTERED ===")
        logger.critical("Reason: %s", reason)
        logger.critical("Timestamp: %s", self._mode_entered_at)
        logger.critical("Actions: NO ORDERS, DIAGNOSIS ONLY, TECH NOTIFIED")

        # Save complete diagnostic snapshot
        self._save_diagnostic_snapshot(reason)

        # Notify technician
        self._notify_technician(reason)

    def is_man_at_work(self) -> bool:
        """Check if system is in MAN_AT_WORK mode."""
        return self.system_mode == SystemMode.MAN_AT_WORK

    def exit_man_at_work_mode(self) -> None:
        """Exit MAN_AT_WORK mode - return to normal operations."""
        if self.system_mode != SystemMode.MAN_AT_WORK:
            return

        duration = datetime.now(timezone.utc) - datetime.fromisoformat(self._mode_entered_at)
        logger.info("=== EXITING MAN_AT_WORK MODE ===")
        logger.info("Duration: %s", duration)
        logger.info("Original reason: %s", self._mode_reason)

        self.system_mode = SystemMode.NORMAL
        self._mode_entered_at = ""
        self._mode_reason = ""

    def _save_diagnostic_snapshot(self, trigger_reason: str) -> None:
        """Save complete system state for technician analysis."""
        try:
            snapshot = {
                "snapshot_id": f"man-at-work-{int(time.time())}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trigger_reason": trigger_reason,
                "system_mode": self.system_mode.value,
                "organs": {},
                "pain_history": [],
                "environment": {},
            }

            # Capture all organs state
            for name, organ in self.organs.items():
                snapshot["organs"][name] = {
                    "healthy": organ.last_health,
                    "last_check": organ.last_check,
                    "error": organ.last_error,
                    "pain_level": organ.pain_level.value,
                    "consecutive_failures": organ.consecutive_failures,
                    "circuit_open_until": organ.circuit_open_until,
                    "category": organ.category.value,
                }

            # Recent pain events
            snapshot["pain_history"] = [
                {
                    "organ": e.organ_name,
                    "pain": e.pain_level.value,
                    "error": e.error[:200],
                    "timestamp": e.timestamp,
                    "healed": e.healed,
                }
                for e in self.pain_history[-50:]  # Last 50 events
            ]

            # Environment info
            snapshot["environment"] = {
                "python_version": sys.version,
                "total_scans": self.total_scans,
                "total_heals": self.total_heals,
            }

            # Save to file
            diag_dir = Path("data/man_at_work")
            diag_dir.mkdir(parents=True, exist_ok=True)
            diag_path = diag_dir / f"diagnosis_{int(time.time())}.json"
            with open(diag_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)

            logger.info("man_at_work: diagnostic snapshot saved to %s", diag_path)

        except Exception as e:
            logger.error("man_at_work: failed to save snapshot: %s", str(e)[:200])

    def _notify_technician(self, reason: str) -> None:
        """Notify technician that system needs manual intervention."""
        try:
            # Log prominent alert
            alert_msg = f"""
═══════════════════════════════════════════════════════════
🚨 MAN_AT_WORK MODE - TECHNICIAN NEEDED 🚨
═══════════════════════════════════════════════════════════
Reason: {reason}
Time: {self._mode_entered_at}
Action: NO TRADING ORDERS UNTIL CLEARED
═══════════════════════════════════════════════════════════
"""
            logger.critical(alert_msg)

            # Try to notify via DeepSeek if CEO is down
            self._try_deepseek_notification(reason)

            # Save alert to dedicated file
            alert_path = Path("data/man_at_work/latest_alert.txt")
            alert_path.parent.mkdir(parents=True, exist_ok=True)
            with open(alert_path, "w", encoding="utf-8") as f:
                f.write(alert_msg.strip())

        except Exception as e:
            logger.error("man_at_work: failed to notify: %s", str(e)[:200])

    def _try_deepseek_notification(self, reason: str) -> None:
        """Try to notify technician via DeepSeek (backup CEO)."""
        try:
            import os

            api_key = os.getenv("SUPEREZIO_DEEPSEEK_API_KEY")
            if not api_key:
                logger.warning("man_at_work: no DEEPSEEK_API_KEY for notification")
                return

            # Simple notification using DeepSeek API
            import urllib.request

            prompt = f"""
SYSTEM ALERT: SuperEzio Financeiro entered MAN_AT_WORK mode.
Reason: {reason}
Time: {self._mode_entered_at}

You are the backup CEO. Analyze the situation and recommend recovery steps.
Keep response under 200 words. Focus on: 1) What broke, 2) How to fix, 3) Prevention.
"""

            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=json.dumps({
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                }).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                timeout=10,
            )

            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
                advice = result["choices"][0]["message"]["content"]

                logger.critical("=== DEEPSEEK BACKUP CEO ADVICE ===")
                logger.critical("%s", advice)

                # Save advice to file
                advice_path = Path("data/man_at_work/deepseek_advice.txt")
                with open(advice_path, "w", encoding="utf-8") as f:
                    f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")
                    f.write(f"Reason: {reason}\n\n")
                    f.write(advice)

        except Exception as e:
            logger.warning("man_at_work: DeepSeek notification failed: %s", str(e)[:100])

    def check_man_at_work_guard(self, operation: str = "trading") -> tuple[bool, str]:
        """
        Check if operation is allowed in current system mode.
        Returns (allowed, reason).

        Call this before any trading operation:
            allowed, reason = body.check_man_at_work_guard()
            if not allowed:
                raise RuntimeError(reason)
        """
        if self.system_mode == SystemMode.MAN_AT_WORK:
            return False, f"MAN_AT_WORK mode: {operation} blocked. System in diagnostic mode. Reason: {self._mode_reason}"

        if self.system_mode == SystemMode.EMERGENCY_SHUTDOWN:
            return False, f"EMERGENCY_SHUTDOWN: {operation} blocked. All operations suspended."

        return True, ""

    # ── Body Scan ──

    def full_body_scan(self) -> dict[str, Any]:
        """Bob checks every organ. Returns health report."""
        report = {
            "scan_id": f"scan-{int(time.time())}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "organs": {},
            "overall_pain": PainLevel.NONE.value,
            "healthy_count": 0,
            "sick_count": 0,
            "critical_count": 0,
        }

        for name, organ in self.organs.items():
            healthy = organ.check()
            report["organs"][name] = {
                "healthy": healthy,
                "error": organ.last_error,
                "pain": organ.pain_level.value,
                "category": organ.category.value,
                "consecutive_failures": organ.consecutive_failures,
            }
            if healthy:
                report["healthy_count"] += 1
            else:
                report["sick_count"] += 1
                if organ.pain_level == PainLevel.CRITICAL:
                    report["critical_count"] += 1
                report["overall_pain"] = max(report["overall_pain"], organ.pain_level.value)

                # Record pain event
                event = PainEvent(
                    organ_name=name,
                    category=organ.category,
                    pain_level=organ.pain_level,
                    error=organ.last_error,
                )
                self.pain_history.append(event)
                self._log_pain(event)

        self.total_scans += 1
        self.last_full_scan = report["timestamp"]
        return report

    # ── Pain Logging ──

    def _log_pain(self, event: PainEvent) -> None:
        """Record pain event to persistent log."""
        try:
            self._pain_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._pain_log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "organ": event.organ_name,
                    "category": event.category.value,
                    "pain": event.pain_level.value,
                    "error": event.error,
                    "timestamp": event.timestamp,
                    "healed": event.healed,
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ── Self-Healing ──

    def auto_heal(self) -> dict[str, Any]:
        """Bob tries to heal every sick organ that has an auto_heal function."""
        results = {}
        for name, organ in self.organs.items():
            if not organ.last_health and organ.auto_heal_fn:
                logger.warning("bob_healing: %s (attempt %d)", name, organ.heal_attempts + 1)
                success = organ.heal()
                results[name] = {"healed": success, "attempts": organ.heal_attempts}
                if success:
                    self.total_heals += 1
                    # Update last pain event as healed
                    for event in reversed(self.pain_history):
                        if event.organ_name == name and not event.healed:
                            event.healed = True
                            event.healed_at = datetime.now(timezone.utc).isoformat()
                            break
        return results

    def heal_and_rescan(self) -> dict[str, Any]:
        """Full cycle: scan -> heal -> rescan. Returns complete report."""
        initial = self.full_body_scan()
        if initial["sick_count"] > 0:
            heal_results = self.auto_heal()
            final = self.full_body_scan()
            return {
                "initial_scan": initial,
                "heal_attempts": heal_results,
                "final_scan": final,
                "organs_healed": sum(1 for v in heal_results.values() if v["healed"]),
                "still_sick": final["sick_count"],
            }
        return {"initial_scan": initial, "heal_attempts": {}, "organs_healed": 0, "still_sick": 0}

    # ── Pain Summary for Bob's Prompt ──

    def pain_summary(self) -> str:
        """Generate a text summary Bob can read in his system prompt."""
        report = self.full_body_scan()
        lines = [
            "=== BOB'S BODY STATUS ===",
            f"Scan: {report['healthy_count']}/{len(self.organs)} organs healthy",
            f"Pain Level: {report['overall_pain']}/100",
            f"Sick: {report['sick_count']} | Critical: {report['critical_count']}",
            "",
        ]
        for name, organ in self.organs.items():
            status = "OK" if report["organs"][name]["healthy"] else "SICK"
            icon = {100: "☠", 75: "🔴", 50: "🟠", 25: "🟡", 10: "⚪", 0: "🟢"}.get(
                report["organs"][name]["pain"], "?"
            )
            lines.append(f"  {icon} {self.organs[name].name}: {status}")
            if not report["organs"][name]["healthy"]:
                lines.append(f"     Error: {report['organs'][name]['error'][:100]}")

        recent_pain = [e for e in self.pain_history[-5:] if not e.healed]
        if recent_pain:
            lines.append("")
            lines.append("Recent Unhealed Pain:")
            for e in recent_pain:
                lines.append(f"  - {e.organ_name}: {e.error[:80]}")

        return "\n".join(lines)

    # ── History ──

    def get_pain_history(self, limit: int = 20) -> list[dict]:
        return [
            {
                "organ": e.organ_name,
                "pain": e.pain_level.value,
                "error": e.error[:100],
                "timestamp": e.timestamp,
                "healed": e.healed,
            }
            for e in self.pain_history[-limit:]
        ]


# ===========================================================
# Singleton
# ===========================================================

_bobs_body: BobsBody | None = None


def get_bobs_body() -> BobsBody:
    """Get Bob's body singleton."""
    global _bobs_body
    if _bobs_body is None:
        _bobs_body = BobsBody()
    return _bobs_body


def bob_body_scan() -> dict[str, Any]:
    """Quick health check - called by auto-scanner and dashboard."""
    return get_bobs_body().full_body_scan()


def bob_pain_summary() -> str:
    """Get pain summary for Bob's system prompt."""
    return get_bobs_body().pain_summary()
