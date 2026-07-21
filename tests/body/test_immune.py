"""
Tests for ImmuneSystem — Fase 5 (Imunidade) da arquitetura CORPO.
"""

from __future__ import annotations

from core.body import ImmuneSystem


class TestImmuneSystem:
    """Immune system kernel integrity, backup, and anti-bloat."""

    def test_initial_kernel_hashes_computed(self, tmp_path):
        # Create a minimal project structure
        src = tmp_path / "src" / "core" / "body"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("# test")
        (src / "dna.py").write_text("# dna")
        (src / "immune.py").write_text("# immune")

        kernel = [
            "src/core/body/__init__.py",
            "src/core/body/dna.py",
            "src/core/body/immune.py",
        ]
        immune = ImmuneSystem(project_root=tmp_path, kernel_files=kernel)
        changed = immune.verify_kernel_integrity()
        assert changed == []

    def test_verify_kernel_detects_change(self, tmp_path):
        src = tmp_path / "src" / "core" / "body"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("# original")
        (src / "dna.py").write_text("# dna")

        kernel = ["src/core/body/__init__.py", "src/core/body/dna.py"]
        immune = ImmuneSystem(project_root=tmp_path, kernel_files=kernel)

        # Modify a kernel file
        (src / "__init__.py").write_text("# modified")
        changed = immune.verify_kernel_integrity()
        assert "src/core/body/__init__.py" in changed

    def test_auto_backup_creates_file(self, tmp_path):
        src = tmp_path / "src" / "test.py"
        src.parent.mkdir(parents=True)
        src.write_text("x = 1")

        immune = ImmuneSystem(project_root=tmp_path, kernel_files=[])
        backup = immune.auto_backup("src/test.py")
        assert backup is not None
        assert backup.exists()
        assert backup.suffix == ".bak"

    def test_anti_bloat_check_under_limit(self, tmp_path):
        src = tmp_path / "small.py"
        src.write_text("\n".join(f"x{i} = {i}" for i in range(10)))

        immune = ImmuneSystem(project_root=tmp_path, kernel_files=[])
        ok, count = immune.anti_bloat_check("small.py")
        assert ok is True
        assert count == 10

    def test_anti_bloat_check_over_limit(self, tmp_path):
        src = tmp_path / "bloated.py"
        src.write_text("\n".join(f"x{i} = {i}" for i in range(600)))

        immune = ImmuneSystem(project_root=tmp_path, kernel_files=[])
        ok, count = immune.anti_bloat_check("bloated.py")
        assert ok is False
        assert count == 600

    def test_scan_bloat_returns_only_bloated(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "small.py").write_text("x = 1")
        (src / "big.py").write_text("\n".join(f"x{i} = {i}" for i in range(600)))

        kernel = ["src/small.py", "src/big.py"]
        immune = ImmuneSystem(project_root=tmp_path, kernel_files=kernel)
        bloated = immune.scan_bloat()
        assert "src/big.py" in bloated
        assert "src/small.py" not in bloated

    def test_rollback_restores_file(self, tmp_path):
        src = tmp_path / "target.py"
        src.write_text("original content")

        immune = ImmuneSystem(project_root=tmp_path, kernel_files=[])
        immune.auto_backup("target.py")
        src.write_text("corrupted content")
        immune.rollback("target.py")
        assert src.read_text() == "original content"

    def test_status_report(self, tmp_path):
        src = tmp_path / "src" / "core" / "body"
        src.mkdir(parents=True)
        (src / "__init__.py").write_text("# ok")

        immune = ImmuneSystem(
            project_root=tmp_path,
            kernel_files=["src/core/body/__init__.py"],
        )
        report = immune.status_report()
        assert "Immune System Status" in report
        assert "Kernel integrity" in report
