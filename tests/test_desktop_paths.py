from pathlib import Path


def test_desktop_paths_and_secret_search_stay_in_customer_workspace(monkeypatch, tmp_path):
    from core.config.secrets import _find_project_root
    from core.paths import find_project_root

    customer = tmp_path / "Cliente com espaços"
    monkeypatch.setenv("SUPEREZIO_DESKTOP_DATA_DIR", str(customer))
    assert find_project_root(Path(__file__)) == customer.resolve()
    assert _find_project_root() == customer.resolve()
