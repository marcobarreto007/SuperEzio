from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows release contract")
def test_release_builder_excludes_operator_state_and_verifies_manifest(tmp_path: Path) -> None:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "scripts" / "build_release.ps1"),
        "-OutputDirectory",
        str(tmp_path),
    ]
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=180, check=False
    )  # check=False: returncode é assertado na linha seguinte
    assert completed.returncode == 0, completed.stderr or completed.stdout

    zip_path = next(tmp_path.glob("SuperEzio-V1-*.zip"))
    checksum_path = Path(f"{zip_path}.sha256")
    manifest_path = tmp_path / "RELEASE_MANIFEST.json"
    assert checksum_path.exists()
    assert manifest_path.exists()
    expected_hash = checksum_path.read_text(encoding="utf-8").split()[0]
    assert hashlib.sha256(zip_path.read_bytes()).hexdigest() == expected_hash

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert "SuperEzio-V1/README.md" in names
        assert "SuperEzio-V1/.env.example" in names
        assert "SuperEzio-V1/requirements-lock.txt" in names
        assert "SuperEzio-V1/RELEASE_MANIFEST.json" in names
        forbidden = (
            "/.env.local",
            "/data/conversation_memory.jsonl",
            "/data/man_at_work/",
            "/journal/",
            "/runtime/",
            "/output/",
            "/.claude/settings.local.json",
            "/.f51/checkpoints/",
        )
        assert not any(marker in name for marker in forbidden for name in names)
        manifest = json.loads(archive.read("SuperEzio-V1/RELEASE_MANIFEST.json"))
        readme = archive.read("SuperEzio-V1/README.md")

    readme_record = next(item for item in manifest["files"] if item["path"] == "README.md")
    assert hashlib.sha256(readme).hexdigest() == readme_record["sha256"]
    assert manifest["file_count"] == len(manifest["files"])
    assert manifest["safety_boundary"].startswith("research-only")
