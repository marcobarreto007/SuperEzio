"""Test L — Regression coverage for the ``collect_experts`` compatibility shim.

Background
----------
A regression was observed where the runtime tried to import
``core.pipeline.nodes.collect_experts`` and failed with
``No module named 'core.pipeline.nodes.collect_experts'`` because the expert
collection logic had been moved to ``experts.py``.

To keep older callers (and tool_executor's import chain) working, a thin
shim module ``collect_experts.py`` re-exports ``node_collect_experts`` from
``experts.py``.

This test locks that contract in place so the broken-import failure mode
cannot silently reappear.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect

import pytest

# Literal top-of-file import to match the exact failure mode from the runtime
# logs ("No module named 'core.pipeline.nodes.collect_experts'"). If the shim
# regresses, this fails at collection time — louder than a runtime ImportError
# buried inside a single test.
import core.pipeline.nodes.collect_experts as _collect_experts_shim  # noqa: F401


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


def test_collect_experts_module_importable_via_legacy_path() -> None:
    """The legacy dotted path must import cleanly."""
    module = importlib.import_module("core.pipeline.nodes.collect_experts")
    assert module is not None
    # Same object as the top-of-file literal import.
    assert module is _collect_experts_shim


def test_collect_experts_exports_node_collect_experts() -> None:
    """The shim must expose ``node_collect_experts`` as a public symbol."""
    module = importlib.import_module("core.pipeline.nodes.collect_experts")
    assert hasattr(module, "node_collect_experts"), (
        "Shim is missing node_collect_experts; tool_executor will break."
    )
    assert "node_collect_experts" in getattr(module, "__all__", []), (
        "node_collect_experts must be in __all__ so the shim contract is explicit."
    )


# ---------------------------------------------------------------------------
# Identity with canonical implementation
# ---------------------------------------------------------------------------


def test_shim_reexports_canonical_implementation() -> None:
    """The shim and the canonical experts module must yield the same object."""
    shim = importlib.import_module("core.pipeline.nodes.collect_experts")
    canonical = importlib.import_module("core.pipeline.nodes.experts")

    assert shim.node_collect_experts is canonical.node_collect_experts, (
        "Shim must re-export the same callable, not a copy or a wrapper."
    )


def test_node_collect_experts_is_async_callable() -> None:
    """The re-exported node must remain an async callable."""
    from core.pipeline.nodes.collect_experts import node_collect_experts

    assert callable(node_collect_experts)
    assert inspect.iscoroutinefunction(node_collect_experts), (
        "node_collect_experts must stay async; the pipeline awaits it."
    )


# ---------------------------------------------------------------------------
# Runtime smoke — empty/missing state must not crash
# ---------------------------------------------------------------------------


def test_node_collect_experts_handles_missing_expert_results() -> None:
    """A minimal state with no expert_results must not raise.

    The pipeline can reach the collect step before any experts have written
    results (e.g. when the router skips the fan-out). The node must degrade
    gracefully rather than raise an ImportError or KeyError.
    """
    from unittest.mock import patch

    from core.pipeline.nodes.collect_experts import node_collect_experts

    state: dict = {"message": "test", "expert_results": []}

    with patch(
        "core.pipeline.nodes.experts.get_stream_writer",
        return_value=lambda msg: None,
    ):
        try:
            result = asyncio.run(node_collect_experts(state))
        except Exception as exc:  # pragma: no cover - failure path documents intent
            pytest.fail(
                "node_collect_experts must accept empty expert_results without "
                f"raising; got {type(exc).__name__}: {exc}"
            )

    assert isinstance(result, dict), "node_collect_experts must return a dict-shaped state update."
