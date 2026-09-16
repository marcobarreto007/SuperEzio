"""Guards the environment the suite is allowed to run in.

The Python 3.12 migration surfaced four packages the code imports at runtime
but that no manifest ever declared, plus a lockfile pin (bcrypt 5) that broke
passlib. Every check below fails on one of those, so the class of bug cannot
come back silently.
"""

from __future__ import annotations

import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

# Distributions imported by src/ that were installed by hand and never declared.
_PREVIOUSLY_UNDECLARED = ("financedatabase", "akshare", "xlrd", "openpyxl")


def _manifest() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def _declared_requirements() -> dict[str, str]:
    project = _manifest()["project"]
    requirements = list(project["dependencies"])
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)

    declared: dict[str, str] = {}
    for requirement in requirements:
        name = re.match(r"[A-Za-z0-9._-]+", requirement)
        if name:
            declared[name.group(0).lower().replace("_", "-")] = requirement
    return declared


def _version_tuple(distribution: str) -> tuple[int, ...]:
    raw = metadata.version(distribution)
    return tuple(int(part) for part in re.findall(r"\d+", raw)[:3])


def test_declared_minimum_python_is_312():
    assert _manifest()["project"]["requires-python"] == ">=3.12"


def test_interpreter_running_the_suite_honours_the_declared_minimum():
    assert sys.version_info[:2] >= (3, 12), (
        f"suite is running on {sys.version.split()[0]}; use the project venv"
    )


@pytest.mark.parametrize("distribution", _PREVIOUSLY_UNDECLARED)
def test_runtime_import_is_declared_in_the_manifest(distribution):
    assert distribution in _declared_requirements()


@pytest.mark.parametrize("distribution", _PREVIOUSLY_UNDECLARED)
def test_runtime_import_is_actually_installed(distribution):
    assert _version_tuple(distribution) >= (1,)


def test_bcrypt_stays_below_the_release_that_breaks_passlib():
    # passlib 1.7.4 reads bcrypt.__about__, which bcrypt 4.1 removed.
    assert _version_tuple("bcrypt")[:2] < (4, 1)
    assert "bcrypt" in _declared_requirements()


def test_password_hashing_round_trip_works():
    from agent_server.auth import _pwd_ctx

    digest = _pwd_ctx.hash("correct horse battery staple")

    assert _pwd_ctx.verify("correct horse battery staple", digest)
    assert not _pwd_ctx.verify("wrong horse battery staple", digest)


def test_requirements_mirror_matches_the_manifest():
    mirror = [
        line.strip()
        for line in _PYPROJECT.with_name("requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    assert mirror == _manifest()["project"]["dependencies"], (
        "requirements.txt drifted from pyproject.toml; regenerate the mirror"
    )


def test_legacy_xls_workbooks_are_readable():
    # The Shiller reference workbook is a pre-2007 .xls; pandas needs xlrd.
    import pandas as pd

    with pytest.raises(FileNotFoundError):
        pd.read_excel(Path(__file__).with_name("does-not-exist.xls"))
