"""Contract 2026-09-05: the cloud expert committee fans out in parallel.

The old concurrency=1 pinned a single local llama-server inference slot and
serialized the 6 DeepSeek expert calls (~1 inference round-trip each).
Experts now run on the cloud API and must not be serialized.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from core.pipeline.nodes.experts import expert_concurrency, run_experts_parallel

ROLES = [
    "macro_risk",
    "fundamental_value",
    "momentum_technical",
    "contrarian_opportunity",
    "sentiment",
    "social_forensics",
]


class TestExpertConcurrency:
    def test_default_is_all_roles_parallel(self, monkeypatch):
        # Hermetic: the operator dotenv may pin SUPEREZIO_EXPERT_CONCURRENCY
        # (hydrated into os.environ by load_local_env during the full suite).
        monkeypatch.delenv("SUPEREZIO_EXPERT_CONCURRENCY", raising=False)
        assert expert_concurrency(len(ROLES)) == 6

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SUPEREZIO_EXPERT_CONCURRENCY", "2")
        assert expert_concurrency(len(ROLES)) == 2

    def test_env_clamped_to_role_count(self, monkeypatch):
        monkeypatch.setenv("SUPEREZIO_EXPERT_CONCURRENCY", "99")
        assert expert_concurrency(len(ROLES)) == 6

    def test_invalid_env_falls_back_to_parallel(self, monkeypatch):
        monkeypatch.setenv("SUPEREZIO_EXPERT_CONCURRENCY", "banana")
        assert expert_concurrency(len(ROLES)) == 6

    def test_single_role_minimum(self, monkeypatch):
        monkeypatch.setenv("SUPEREZIO_EXPERT_CONCURRENCY", "0")
        assert expert_concurrency(1) == 1


class TestRunExpertsParallel:
    @pytest.mark.asyncio
    async def test_committee_runs_in_parallel_not_serial(self, monkeypatch):
        """6 experts with 150ms latency each must finish well under 900ms
        (serial) — the fan-out should be ~150-250ms total."""
        called: list[str] = []

        async def fake_node_expert(state: dict, *, gateway=None) -> dict[str, Any]:
            await asyncio.sleep(0.15)
            called.append(state.get("role", ""))
            return {"expert_results": [{"ok": True, "verdict": "HOLD", "role": state["role"]}]}

        monkeypatch.setattr("core.pipeline.nodes.experts.node_expert", fake_node_expert)

        t0 = time.perf_counter()
        results = await run_experts_parallel({}, ROLES)
        elapsed = time.perf_counter() - t0

        assert len(results) == 6
        assert sorted(called) == sorted(ROLES)
        assert elapsed < 0.9, f"experts ran serially: {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_one_failure_is_best_effort_not_abort(self, monkeypatch):
        async def fake_node_expert(state: dict, *, gateway=None) -> dict[str, Any]:
            if state.get("role") == "sentiment":
                raise RuntimeError("provider timeout")
            return {"expert_results": [{"ok": True, "verdict": "HOLD", "role": state["role"]}]}

        monkeypatch.setattr("core.pipeline.nodes.experts.node_expert", fake_node_expert)

        results = await run_experts_parallel({}, ROLES)

        assert len(results) == 6
        failed = [r for r in results if not r.get("ok")]
        assert len(failed) == 1
        assert failed[0]["role"] == "sentiment"
        assert "provider timeout" in failed[0]["error"]
        assert all(r.get("provider") for r in results)
