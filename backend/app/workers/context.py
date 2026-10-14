"""Per-run execution context: cancellation, deadline and tracked provider calls.

Stop and the turn deadline cancel only the in-flight provider call (a tracked child task); they
never interrupt a database transaction. The pipeline sees `RunCancelled` / `DeadlineExceeded` at
its next check or from the cancelled call.
"""

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.persistence.models import Run
from app.workers.notifier import Notifier

T = TypeVar("T")


class RunCancelled(Exception):
    """The user pressed Stop."""


class DeadlineExceeded(Exception):
    """The turn deadline passed."""


@dataclass
class RunResult:
    status: str  # completed | partial | failed
    warnings: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None
    degraded: bool = False


class RunContext:
    def __init__(
        self,
        run_id: UUID,
        session_id: UUID,
        snapshot: dict[str, Any],
        sessionmaker: async_sessionmaker[AsyncSession],
        notifier: Notifier,
    ) -> None:
        self.run_id, self.session_id, self.snapshot = run_id, session_id, snapshot
        self.sessionmaker, self.notifier = sessionmaker, notifier
        self.cancelled = False
        self.expired = False
        self.warnings: list[str] = []
        self._children: set[asyncio.Task[Any]] = set()

    def check(self) -> None:
        if self.cancelled:
            raise RunCancelled
        if self.expired:
            raise DeadlineExceeded

    async def check_db(self) -> None:
        """Plain read of the persisted Stop flag (no lock held), then the in-memory checks."""
        async with self.sessionmaker() as s:
            if await s.scalar(select(Run.cancel_requested).where(Run.id == self.run_id)):
                self.cancelled = True
        self.check()

    def cancel_inflight(self) -> None:
        for task in list(self._children):
            task.cancel()

    def stop(self) -> None:
        self.cancelled = True
        self.cancel_inflight()

    def expire(self) -> None:
        self.expired = True
        self.cancel_inflight()

    async def call(self, coro: Coroutine[Any, Any, T]) -> T:
        """Run one provider call as a cancellable child of this run."""
        try:
            self.check()
        except BaseException:
            coro.close()
            raise
        task: asyncio.Task[T] = asyncio.ensure_future(coro)
        self._children.add(task)
        try:
            return await task
        except asyncio.CancelledError:
            outer = asyncio.current_task()
            if task.cancelled() and not (outer and outer.cancelling()):
                self.check()  # Stop or deadline: raise the domain exception instead
            raise
        finally:
            self._children.discard(task)

    def warn(self, code: str) -> None:
        if code not in self.warnings:
            self.warnings.append(code)
