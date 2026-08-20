from __future__ import annotations

from agent_server.auth import AuthDB
from scripts import first_run, seed_admin


def test_seed_admin_writes_runtime_auth_schema_without_printing_password(
    tmp_path, monkeypatch, capsys
) -> None:
    db_path = tmp_path / "auth.db"
    password = "UniqueReleaseP@ssword1"
    monkeypatch.setenv("SUPEREZIO_ADMIN_PASSWORD", password)

    seed_admin.main(
        [
            "--username",
            "operator_seed",
            "--email",
            "operator-seed@example.test",
            "--db-path",
            str(db_path),
        ]
    )

    runtime_user = AuthDB(db_path=db_path).get_user_by_username("operator_seed")
    assert runtime_user is not None
    assert runtime_user["email"] == "operator-seed@example.test"
    assert runtime_user["password_hash"] != password
    assert password not in capsys.readouterr().out


def test_first_run_and_runtime_share_the_same_auth_database(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(first_run, "_resolve_auth_db", lambda: db_path)

    created = first_run._create_admin_user(
        "operator_wizard", "operator-wizard@example.test", "WizardP@ssword1"
    )

    runtime_user = AuthDB(db_path=db_path).get_user_by_username("operator_wizard")
    assert runtime_user is not None
    assert runtime_user["id"] == created["id"]


def test_first_run_health_accepts_runtime_schema_without_fake_admin_role(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "auth.db"
    AuthDB(db_path=db_path).create_user(
        username="operator_health",
        email="operator-health@example.test",
        password="HealthP@ssword1",
    )
    monkeypatch.setattr(first_run, "_resolve_auth_db", lambda: db_path)

    result = first_run._check_auth_db()

    assert result == {
        "status": "ok",
        "detail": "1 operator account(s)",
        "user_count": 1,
    }
