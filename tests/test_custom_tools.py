"""Tests for src/tools/custom_tools.py.

Covers:
  - register_custom_tools() -> calculate (safe AST-based expression eval)
  - create_code_executor_tool() -> execute_python (opt-in exec() sandbox)

The execute_python tool wraps exec() (custom_tools.py, ~line 315) behind:
  1. An opt-in env var (SUPEREZIO_ENABLE_PYTHON_EXEC) -- disabled by default.
  2. An AST pre-validator that blocks imports, dunder-attribute access, and
     a blocklist of dangerous builtins/methods (eval, exec, open, os, ...).
  3. A restricted __builtins__ dict passed to exec() (no __import__, no
     open, no getattr/setattr, etc).

These tests prove the mitigations actually hold against known Python
sandbox-escape patterns (subclass-walk via __class__/__bases__, __globals__
introspection on closures, forbidden builtins). They exist so future edits
to custom_tools.py cannot silently regress the sandbox.
"""

from __future__ import annotations

import importlib
import sys

import pytest

ROOT_SRC = None


@pytest.fixture(autouse=True)
def _src_on_path():
    import pathlib

    src = str(pathlib.Path(__file__).resolve().parent.parent / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    yield


class _FakeRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name, func, desc=None, schema=None):
        self.tools[name] = func


# ── calculate ──────────────────────────────────────────────────────────


def _get_calculate():
    from tools.custom_tools import register_custom_tools

    reg = _FakeRegistry()
    register_custom_tools(reg)
    return reg.tools["calculate"]


def test_calculate_basic_arithmetic():
    calculate = _get_calculate()
    assert calculate("2 + 2") == "Resultado: 4"


def test_calculate_finance_kelly():
    calculate = _get_calculate()
    result = calculate("kelly(0.6, 2.0)")
    assert result.startswith("Resultado:")


def test_calculate_rejects_import():
    calculate = _get_calculate()
    result = calculate("__import__('os').system('echo pwned')")
    assert result.startswith("Erro:")


def test_calculate_rejects_unknown_function():
    calculate = _get_calculate()
    result = calculate("os.system('echo pwned')")
    assert result.startswith("Erro:")


def test_calculate_rejects_attribute_access():
    calculate = _get_calculate()
    result = calculate("(1).__class__")
    assert result.startswith("Erro:")


def test_calculate_rejects_huge_exponent():
    calculate = _get_calculate()
    result = calculate("2 ** 999")
    assert result.startswith("Erro:")


# ── execute_python (disabled by default) ─────────────────────────────────


def test_execute_python_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_ENABLE_PYTHON_EXEC", raising=False)
    import tools.custom_tools as ct

    importlib.reload(ct)
    exec_fn = ct.create_code_executor_tool()
    result = exec_fn("print('hi')")
    assert "desabilitada" in result.lower()


# ── execute_python (opt-in, sandbox must hold) ───────────────────────────


@pytest.fixture()
def execute_python(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_ENABLE_PYTHON_EXEC", "true")
    import tools.custom_tools as ct

    importlib.reload(ct)
    fn = ct.create_code_executor_tool()
    yield fn
    importlib.reload(ct)  # restore disabled state for other tests


def test_execute_python_enabled_runs_simple_code(execute_python):
    result = execute_python("print(1 + 1)")
    assert result.strip() == "2"


@pytest.mark.parametrize(
    "payload",
    [
        "().__class__.__bases__[0].__subclasses__()",
        "print(().__class__)",
        "(1).__class__.__mro__",
        "import os",
        "from os import system",
        "eval('1+1')",
        "exec('print(1)')",
        "__import__('os')",
        "globals()",
        "locals()",
        "open('C:/Windows/win.ini')",
        "[x for x in ().__class__.__base__.__subclasses__()]",
        "getattr(1, '__class__')",
        "setattr(1, 'x', 2)",
        "x = 1\nx.__class__",
        "(lambda: 1).__globals__",
        "vars()",
        "dir()",
    ],
)
def test_execute_python_blocks_known_sandbox_escapes(execute_python, payload):
    result = execute_python(payload)
    assert result.startswith(("Error:", "Erro:"))
