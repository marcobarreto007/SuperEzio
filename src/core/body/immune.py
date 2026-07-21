"""Immune System — Kernel integrity, auto-backup, import test, anti-bloat.

Protects the CORPO layer from accidental corruption by:
- Kernel hashing: critical files that MUST NEVER change without explicit review.
- Auto-backup: every mutation is preceded by a snapshot of the target file.
- Import test: after a mutation, the module is imported in an isolated subprocess.
- Anti-bloat: alerts when any monitored module exceeds 500 lines.
- Rollback: automatic restoration of the last backup on verification failure.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Default kernel — files that are NEVER allowed to be modified without review.
# Paths are relative to the project root.
_DEFAULT_KERNEL: list[str] = [
    "src/core/body/__init__.py",
    "src/core/body/dna.py",
    "src/core/body/memory_lattice.py",
    "src/core/body/immune.py",
    "src/core/body/emotion.py",
    "src/core/trading/outcome_learning.py",
    "src/core/config/settings.py",
    "src/core/ports/protocol.py",
    "docs/architecture/ARCHITECTURE_TEMPLATE.md",
]

_MAX_MODULE_LINES = 500


# ---------------------------------------------------------------------------
# Immune System
# ---------------------------------------------------------------------------


class ImmuneSystem:
    """Kernel integrity guard with auto-backup, import test, and rollback."""

    def __init__(
        self,
        project_root: str | Path | None = None,
        kernel_files: list[str] | None = None,
        backup_dir: str | Path | None = None,
    ) -> None:
        self._project_root = Path(project_root or _find_project_root())
        self._kernel_files = kernel_files or list(_DEFAULT_KERNEL)
        self._backup_dir = Path(backup_dir or self._project_root / "runtime" / "backups")
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._kernel_hashes: dict[str, str] = {}
        self._last_backups: dict[str, Path] = {}
        self._compute_kernel_hashes()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify_kernel_integrity(self) -> list[str]:
        """Check every kernel file against its recorded hash.

        Returns a list of files that have changed (empty = all intact).
        """
        changed: list[str] = []
        for rel_path, expected_hash in self._kernel_hashes.items():
            abs_path = self._project_root / rel_path
            if not abs_path.exists():
                changed.append(f"{rel_path} (MISSING)")
                continue
            current_hash = _file_hash(abs_path)
            if current_hash != expected_hash:
                changed.append(rel_path)
        return changed

    def auto_backup(self, rel_path: str) -> Path | None:
        """Snapshot a file before mutation. Returns the backup path."""
        abs_path = self._project_root / rel_path
        if not abs_path.exists():
            return None
        safe_name = rel_path.replace("/", "__").replace("\\", "__")
        backup_name = f"{safe_name}_{_now_stamp()}.bak"
        backup_path = self._backup_dir / backup_name
        with self._lock:
            shutil.copy2(str(abs_path), str(backup_path))
            self._last_backups[rel_path] = backup_path
        return backup_path

    def import_test(self, module_path: str, *, timeout: int = 30) -> tuple[bool, str]:
        """Attempt to import the given module in an isolated subprocess.

        Returns (success, message).
        """
        abs_path = self._project_root / module_path
        if not abs_path.exists():
            return False, f"File not found: {module_path}"

        # Derive an importable module name from the file path
        rel = abs_path.relative_to(self._project_root)
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        elif parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        module_name = ".".join(parts)

        code = (
            f"import sys; sys.path.insert(0, {str(self._project_root)!r}); "
            f"import {module_name}; "
            f"print('OK:{module_name}')"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "DISABLE_OTEL": "1"},
            )
            if result.returncode == 0:
                return True, f"Import OK: {module_name}"
            return False, f"Import FAILED: {result.stderr.strip() or result.stdout.strip()}"
        except subprocess.TimeoutExpired:
            return False, f"Import TIMEOUT (>={timeout}s): {module_name}"
        except Exception as exc:
            return False, f"Import ERROR: {exc}"

    def anti_bloat_check(self, module_path: str) -> tuple[bool, int]:
        """Check if a module exceeds the maximum allowed line count.

        Returns (is_ok, line_count).
        """
        abs_path = self._project_root / module_path
        if not abs_path.exists():
            return True, 0
        with open(abs_path, encoding="utf-8") as fh:
            count = sum(1 for _ in fh)
        return count <= _MAX_MODULE_LINES, count

    def safe_mutate(
        self,
        rel_path: str,
        mutator: Callable[[str], str],
    ) -> tuple[bool, str]:
        """Apply *mutator* to the file, run import test, rollback on failure.

        Returns (success, message).
        """
        abs_path = self._project_root / rel_path
        if not abs_path.exists():
            return False, f"File not found: {rel_path}"

        # 1. Back up
        backup = self.auto_backup(rel_path)
        if backup is None:
            return False, f"Backup failed for: {rel_path}"

        # 2. Anti-bloat pre-check
        ok, count = self.anti_bloat_check(rel_path)
        if not ok:
            return False, f"Anti-bloat FAIL: {rel_path} has {count} lines (max {_MAX_MODULE_LINES})"

        # 3. Apply mutation
        try:
            with open(abs_path, encoding="utf-8") as fh:
                original = fh.read()
            mutated = mutator(original)
            with open(abs_path, "w", encoding="utf-8") as fh:
                fh.write(mutated)
        except Exception as exc:
            self._rollback(rel_path, backup)
            return False, f"Mutation write FAILED: {exc}"

        # 4. Import test
        ok, msg = self.import_test(rel_path)
        if not ok:
            self._rollback(rel_path, backup)
            return False, f"Import test FAILED after mutation: {msg}"

        # 5. Update kernel hash
        self._kernel_hashes[rel_path] = _file_hash(abs_path)
        return True, f"Mutation OK: {rel_path}"

    def rollback(self, rel_path: str) -> bool:
        """Restore the last backup for a given file."""
        backup = self._last_backups.get(rel_path)
        if backup is None or not backup.exists():
            return False
        return self._rollback(rel_path, backup)

    def scan_bloat(self) -> dict[str, int]:
        """Scan all kernel files and return {rel_path: line_count} for bloated ones."""
        bloated: dict[str, int] = {}
        for rel_path in self._kernel_files:
            ok, count = self.anti_bloat_check(rel_path)
            if not ok:
                bloated[rel_path] = count
        return bloated

    def status_report(self) -> str:
        """Return a human-readable immune status string."""
        lines = ["[Immune System Status]", ""]
        integrity = self.verify_kernel_integrity()
        if integrity:
            lines.append(f"  Kernel integrity: FAIL — {len(integrity)} file(s) changed")
            for f in integrity:
                lines.append(f"    - {f}")
        else:
            lines.append("  Kernel integrity: OK")

        bloated = self.scan_bloat()
        if bloated:
            lines.append(f"  Anti-bloat: {len(bloated)} module(s) over {_MAX_MODULE_LINES} lines")
            for f, c in bloated.items():
                lines.append(f"    - {f}: {c} lines")
        else:
            lines.append("  Anti-bloat: OK")

        lines.append(f"  Kernel files tracked: {len(self._kernel_files)}")
        lines.append(f"  Backups stored: {len(list(self._backup_dir.glob('*.bak')))}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _compute_kernel_hashes(self) -> None:
        for rel_path in self._kernel_files:
            abs_path = self._project_root / rel_path
            if abs_path.exists():
                self._kernel_hashes[rel_path] = _file_hash(abs_path)

    def _rollback(self, rel_path: str, backup: Path) -> bool:
        abs_path = self._project_root / rel_path
        try:
            shutil.copy2(str(backup), str(abs_path))
            return True
        except OSError:
            return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _find_project_root() -> Path:
    """Walk up from cwd looking for a .git directory or CLAUDE.md."""
    cwd = Path.cwd().resolve()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists() or (parent / "CLAUDE.md").exists():
            return parent
    return cwd


__all__ = [
    "ImmuneSystem",
    "_DEFAULT_KERNEL",
    "_MAX_MODULE_LINES",
]
