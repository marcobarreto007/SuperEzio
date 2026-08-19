"""Task Queue — Fila com TTL, watchdog, cancelamento.
Garante que /task/submit nao deixa probe preso consumindo Bob por 900s.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TASK_TTL_SECONDS = 600  # 10 minutos max por task
TASK_WATCHDOG_SECONDS = 5  # verifica a cada 5s


@dataclass
class Task:
    run_id: str
    session_id: str
    message: str
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | running | completed | cancelled | timeout
    result: Any = None
    error: str | None = None
    _cancel: asyncio.Event = field(default_factory=asyncio.Event)
    _execution_task: asyncio.Task[Any] | None = field(default=None, repr=False)

    @property
    def elapsed(self) -> float:
        return time.time() - self.created_at

    @property
    def expired(self) -> bool:
        return self.elapsed > TASK_TTL_SECONDS

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def bind_execution(self, execution_task: asyncio.Task[Any]) -> None:
        """Bind the actual coroutine so cancellation stops downstream work."""
        self._execution_task = execution_task

    def cancel(self) -> None:
        self._cancel.set()
        self.status = "cancelled"
        execution_task = self._execution_task
        if (
            execution_task is not None
            and not execution_task.done()
            and execution_task is not asyncio.current_task()
        ):
            execution_task.cancel()


class TaskQueue:
    """Fila de tasks com TTL, watchdog e cancelamento.

    - Max 1 task ativa por sessão
    - TTL de 10min — tasks que expiram são marcadas como timeout
    - Watchdog a cada 5s limpa tasks mortas
    - Suporte a cancelamento assíncrono
    """

    def __init__(self):
        self._active: dict[str, Task] = {}  # run_id → Task
        self._by_session: dict[str, str] = {}  # session_id → run_id
        self._watchdog_task: asyncio.Task | None = None
        self._history: list[Task] = []  # últimas 100 tasks (completed/cancelled/timeout)

    async def start(self) -> None:
        """Inicia o watchdog em background."""
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def stop(self) -> None:
        """Para o watchdog."""
        if self._watchdog_task:
            self._watchdog_task.cancel()

    async def _watchdog_loop(self) -> None:
        """Limpa tasks expiradas ou canceladas."""
        while True:
            try:
                for run_id, task in list(self._active.items()):
                    if task.expired:
                        task.cancel()
                        task.status = "timeout"
                        self._archive(task)
                        self._active.pop(run_id, None)
                        self._by_session.pop(task.session_id, None)
                        logger.warning(
                            "[task_queue] Task %s timed out after %.0fs", run_id, task.elapsed
                        )
            except Exception:
                pass
            await asyncio.sleep(TASK_WATCHDOG_SECONDS)

    def submit(self, message: str, session_id: str = "") -> Task | None:
        """Submete nova task. Se sessão já tem task ativa, rejeita."""
        if session_id and session_id in self._by_session:
            existing_run_id = self._by_session[session_id]
            existing = self._active.get(existing_run_id)
            if existing and existing.expired:
                existing.cancel()
                existing.status = "timeout"
                self._archive(existing)
                self._active.pop(existing_run_id, None)
                self._by_session.pop(session_id, None)
                logger.warning(
                    "[task_queue] Expired task %s removed before new submit",
                    existing_run_id,
                )
            elif existing:
                logger.warning(
                    "[task_queue] Session %s already has active task %s",
                    session_id,
                    existing_run_id,
                )
                return None

        task = Task(
            run_id=str(uuid.uuid4())[:12],
            session_id=session_id,
            message=message,
            status="running",
        )
        self._active[task.run_id] = task
        if session_id:
            self._by_session[session_id] = task.run_id
        logger.debug("[task_queue] Task %s submitted (session=%s)", task.run_id, session_id)
        return task

    def complete(self, run_id: str, result: Any = None) -> None:
        """Marca task como concluída."""
        task = self._active.pop(run_id, None)
        if task:
            task.status = "completed"
            task.result = result
            self._archive(task)
            self._by_session.pop(task.session_id, None)

    def cancel(self, run_id: str) -> bool:
        """Cancela uma task ativa."""
        task = self._active.get(run_id)
        if task:
            task.cancel()
            self._archive(task)
            self._active.pop(run_id, None)
            self._by_session.pop(task.session_id, None)
            return True
        return False

    def get(self, run_id: str) -> Task | None:
        return self._active.get(run_id)

    def active_for_session(self, session_id: str) -> Task | None:
        """Return the active task for a browser/session id, if it is still live."""
        if not session_id:
            return None
        run_id = self._by_session.get(session_id)
        if not run_id:
            return None
        task = self._active.get(run_id)
        if task and task.expired:
            task.cancel()
            task.status = "timeout"
            self._archive(task)
            self._active.pop(run_id, None)
            self._by_session.pop(session_id, None)
            return None
        return task

    def status(self, run_id: str) -> dict[str, Any]:
        task = self._active.get(run_id)
        if task:
            return {"run_id": run_id, "status": task.status, "elapsed": task.elapsed}
        return {"run_id": run_id, "status": "not_found"}

    def _archive(self, task: Task) -> None:
        self._history.append(task)
        if len(self._history) > 100:
            self._history = self._history[-100:]

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def active_tasks(self) -> list[dict[str, Any]]:
        return [
            {
                "run_id": t.run_id,
                "session_id": t.session_id,
                "elapsed": t.elapsed,
                "status": t.status,
            }
            for t in self._active.values()
        ]


# Singleton
_task_queue: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
