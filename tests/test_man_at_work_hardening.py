"""MAN_AT_WORK hardening: no false-positive freeze on a single failed CEO probe.

Regression tests for ticket B2. A single 5s HTTP timeout (e.g. llama.cpp
restarting on the local profile) must NOT engage MAN_AT_WORK mode and freeze
trading for minutes. The mode only engages after N consecutive failed probes
(the counter lives in body.py's ceo_brain Organ), and recovery is checked on
every diagnostic cycle, not every fifth.

All tests are deterministic and make no network calls: the decision function
is pure, the ANS loop runs against a fake body with sleeps neutralised, and
the Organ counter is exercised with an injected check_fn.
"""

import threading

from core.bob_consciousness.autonomic import (
    AutonomicNervousSystem,
    MAN_AT_WORK_FAILURE_THRESHOLD,
    _should_enter_man_at_work,
)
from core.bob_consciousness.body import (
    Organ,
    OrganCategory,
    PainLevel,
    SystemMode,
)


# ---------------------------------------------------------------
# Pure decision function: _should_enter_man_at_work(report[, counter])
# ---------------------------------------------------------------


def _ceo_report(healthy: bool = True, failures: int = 0) -> dict:
    """Synthetic full_body_scan report with only the ceo_brain slice filled."""
    return {
        "organs": {
            "ceo_brain": {
                "healthy": healthy,
                "error": "" if healthy else "fake CEO down",
                "consecutive_failures": failures,
            }
        }
    }


def test_single_failure_does_not_engage():
    engage, failures = _should_enter_man_at_work(_ceo_report(False, 1))
    assert engage is False
    assert failures == 1


def test_n_minus_1_failures_do_not_engage():
    engage, failures = _should_enter_man_at_work(
        _ceo_report(False, MAN_AT_WORK_FAILURE_THRESHOLD - 1)
    )
    assert engage is False
    assert failures == MAN_AT_WORK_FAILURE_THRESHOLD - 1


def test_n_failures_engage():
    engage, failures = _should_enter_man_at_work(_ceo_report(False, MAN_AT_WORK_FAILURE_THRESHOLD))
    assert engage is True
    assert failures == MAN_AT_WORK_FAILURE_THRESHOLD


def test_success_between_failures_resets_counter():
    """A healthy CEO report means zero effective failures — the counter the
    decision reads must be reset by any success (mirrors body.py Organ)."""
    engage, failures = _should_enter_man_at_work(_ceo_report(True, 3))
    assert engage is False
    assert failures == 0


def test_missing_ceo_entry_never_engages():
    engage, failures = _should_enter_man_at_work({})
    assert engage is False
    assert failures == 0


def test_explicit_counter_overrides_report():
    engage, failures = _should_enter_man_at_work(
        _ceo_report(False, 0), consecutive_failures=MAN_AT_WORK_FAILURE_THRESHOLD
    )
    assert engage is True
    assert failures == MAN_AT_WORK_FAILURE_THRESHOLD


# ---------------------------------------------------------------
# Counter pattern the threshold reuses: body.py Organ
# ---------------------------------------------------------------


def test_organ_consecutive_failures_reset_on_success():
    """The ceo_brain Organ counts consecutive failures and a success zeroes
    the counter (and closes the circuit) — the pattern the threshold relies
    on. Injected check_fn keeps this network-free."""
    organ = Organ(
        name="CEO Brain (Bob Core :8080)",
        category=OrganCategory.BRAIN,
        check_fn=lambda: (False, "boom"),
        pain_level=PainLevel.CRITICAL,
    )
    assert organ.check() is False
    assert organ.check() is False
    assert organ.consecutive_failures == 2

    organ.check_fn = lambda: (True, "")
    assert organ.check() is True
    assert organ.consecutive_failures == 0
    assert organ.circuit_open_until == 0


# ---------------------------------------------------------------
# ANS loop integration: real _loop, fake body, sleeps neutralised
# ---------------------------------------------------------------


class _FakeBody:
    """Minimal BobsBody stand-in: scripted CEO health, no network, no sleeps."""

    def __init__(self, ceo_healthy: bool = True, ceo_failures: int = 0, man_at_work: bool = False):
        self.system_mode = SystemMode.NORMAL
        self.organs: dict = {}
        self.ceo_healthy = ceo_healthy
        self.ceo_failures = ceo_failures
        self._man_at_work = man_at_work
        self.cycle = 0
        self.enter_calls = 0
        self.exit_calls = 0
        self.enter_cycle: int | None = None
        self.exit_cycle: int | None = None
        self.scan_event = threading.Event()
        self.entered = threading.Event()
        self.exited = threading.Event()

    def full_body_scan(self) -> dict:
        self.cycle += 1
        self.scan_event.set()
        healthy = self.ceo_healthy
        return {
            "organs": {
                "ceo_brain": {
                    "healthy": healthy,
                    "error": "" if healthy else "fake CEO down",
                    "consecutive_failures": 0 if healthy else self.ceo_failures,
                }
            },
            "overall_pain": 0 if healthy else 100,
            "healthy_count": 9 if healthy else 8,
            "sick_count": 0 if healthy else 1,
            "critical_count": 0 if healthy else 1,
            "timestamp": f"t{self.cycle}",
        }

    def is_man_at_work(self) -> bool:
        return self._man_at_work

    def enter_man_at_work_mode(self, reason: str) -> None:
        self.enter_calls += 1
        self.enter_cycle = self.cycle
        self._man_at_work = True
        self.entered.set()

    def exit_man_at_work_mode(self) -> None:
        self.exit_calls += 1
        self.exit_cycle = self.cycle
        self._man_at_work = False
        self.exited.set()


def _run_ans(ans: AutonomicNervousSystem, fake: _FakeBody, wait_for, timeout: float = 10.0) -> bool:
    """Run the real ANS _loop on a fake body; returns once wait_for succeeds.

    Sleeps are neutralised by the caller's monkeypatch, so cycles spin fast
    and the result is deterministic. The loop is stopped and joined in all
    cases.
    """
    ans._body = fake
    ans._running = True
    thread = threading.Thread(target=ans._loop, daemon=True)
    thread.start()
    try:
        return wait_for(timeout)
    finally:
        ans._running = False
        thread.join(timeout=5)


def _wait_n_scans(fake: _FakeBody, n: int):
    def wait(timeout: float) -> bool:
        for _ in range(n):
            if not fake.scan_event.wait(timeout):
                return False
            fake.scan_event.clear()
        return True

    return wait


def test_ans_single_failure_does_not_enter_mode(monkeypatch):
    """1 failed probe (CEO restarting) must NOT freeze trading."""
    monkeypatch.setattr("core.bob_consciousness.autonomic.time.sleep", lambda _: None)
    fake = _FakeBody(ceo_healthy=False, ceo_failures=1)
    ans = AutonomicNervousSystem(scan_interval=60)

    assert _run_ans(ans, fake, _wait_n_scans(fake, 3))
    assert fake.enter_calls == 0
    assert fake._man_at_work is False


def test_ans_enters_mode_after_n_failures(monkeypatch):
    """N consecutive failed probes do engage the mode (first cycle)."""
    monkeypatch.setattr("core.bob_consciousness.autonomic.time.sleep", lambda _: None)
    fake = _FakeBody(ceo_healthy=False, ceo_failures=MAN_AT_WORK_FAILURE_THRESHOLD)
    ans = AutonomicNervousSystem(scan_interval=60)

    assert _run_ans(ans, fake, lambda timeout: fake.entered.wait(timeout))
    assert fake.enter_calls == 1
    assert fake.enter_cycle == 1


def test_ans_recovery_checked_on_first_cycle(monkeypatch):
    """With MAN_AT_WORK active, the first diagnostic cycle attempts recovery —
    not the fifth. This is what bounds the false-positive freeze."""
    monkeypatch.setattr("core.bob_consciousness.autonomic.time.sleep", lambda _: None)
    fake = _FakeBody(ceo_healthy=True, ceo_failures=0, man_at_work=True)
    ans = AutonomicNervousSystem(scan_interval=60)

    assert _run_ans(ans, fake, lambda timeout: fake.exited.wait(timeout))
    assert fake.exit_calls == 1
    assert fake.exit_cycle == 1  # first cycle, not the fifth
