from __future__ import annotations

import asyncio

import pytest

from core.pipeline.task_queue import TaskQueue


@pytest.mark.asyncio
async def test_cancel_stops_bound_execution_task():
    queue = TaskQueue()
    record = queue.submit("analyze AAPL", session_id="cancel-test")
    assert record is not None
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def worker() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    execution = asyncio.create_task(worker())
    record.bind_execution(execution)
    await started.wait()

    assert queue.cancel(record.run_id) is True
    with pytest.raises(asyncio.CancelledError):
        await execution

    assert cancelled.is_set()
    assert queue.active_count == 0
    assert queue.status(record.run_id)["status"] == "not_found"


@pytest.mark.asyncio
async def test_timeout_cancels_bound_execution_task(monkeypatch):
    queue = TaskQueue()
    record = queue.submit("analyze TD.TO", session_id="timeout-test")
    assert record is not None
    record.created_at -= 601
    started = asyncio.Event()

    async def worker() -> None:
        started.set()
        await asyncio.Event().wait()

    execution = asyncio.create_task(worker())
    record.bind_execution(execution)
    await started.wait()
    watchdog = asyncio.create_task(queue._watchdog_loop())

    try:
        await asyncio.wait_for(asyncio.shield(execution), timeout=6)
    except asyncio.CancelledError:
        pass
    finally:
        watchdog.cancel()
        with pytest.raises(asyncio.CancelledError):
            await watchdog

    assert execution.cancelled()
    assert queue.active_count == 0
