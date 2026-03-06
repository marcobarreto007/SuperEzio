"""Project path helpers for the src-layout runtime."""

from __future__ import annotations

from pathlib import Path


def find_project_root(start: str | Path | None = None) -> Path:
    """Find the repository root from a file, package directory, or cwd."""
    current = Path(start or __file__).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        has_project_marker = (
            (candidate / "pyproject.toml").exists()
            or (candidate / "config.yml").exists()
            or (candidate / "config" / "runtime.yml").exists()
        )
        if has_project_marker:
            return candidate
        if candidate.name == "src" and (
            (candidate.parent / "pyproject.toml").exists()
            or (candidate.parent / "config.yml").exists()
            or (candidate.parent / "config" / "runtime.yml").exists()
        ):
            return candidate.parent

    return Path.cwd().resolve()


PROJECT_ROOT = find_project_root()


def project_path(*parts: str | Path) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def resolve_project_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return project_path(path)
