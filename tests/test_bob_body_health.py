from __future__ import annotations

from core.bob_consciousness.body import BobsBody, Organ, OrganCategory, PainLevel


def test_repeated_health_poll_does_not_duplicate_unchanged_pain(tmp_path, monkeypatch):
    pain_log = tmp_path / "bob_pain.jsonl"
    monkeypatch.setenv("SUPEREZIO_BOB_PAIN_LOG", str(pain_log))

    diagnosis = {"error": "broker offline"}

    def unhealthy_check():
        return False, diagnosis["error"]

    body = BobsBody()
    body.organs = {
        "broker": Organ(
            name="Broker",
            category=OrganCategory.MUSCLES,
            check_fn=unhealthy_check,
            pain_level=PainLevel.SEVERE,
        )
    }

    body.full_body_scan()
    body.full_body_scan()

    assert len(body.pain_history) == 1
    assert len(pain_log.read_text(encoding="utf-8").splitlines()) == 1

    diagnosis["error"] = "broker timeout"
    body.full_body_scan()

    assert len(body.pain_history) == 2
    assert len(pain_log.read_text(encoding="utf-8").splitlines()) == 2
