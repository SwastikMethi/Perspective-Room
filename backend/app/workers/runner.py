"""Durable run worker (TRD §Run lifecycle): claims persisted runs with row locks and executes them
in-process. One Uvicorn worker; at most `concurrent_session_runs` runs at a time."""

import asyncio
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.catalog import Catalog
from app.persistence.models import (
    EvaluationBatch,
    EvaluationTrial,
    Message,
    ProviderCall,
    Run,
    Session,
)
from app.services.common import utcnow
from app.services.runs import append_event, error_dict, mark_terminal
from app.workers.context import DeadlineExceeded, RunCancelled, RunContext, RunResult
from app.workers.notifier import Notifier

log = logging.getLogger("perspective_room.worker")

Execute = Callable[[RunContext], Awaitable[RunResult]]

INTERRUPTED = error_dict(
    "interrupted",
    "The app stopped during this reply. Published replies were kept; retry to fill in the rest.",
    retryable=True,
)
DEADLINE = error_dict(
    "deadline_exceeded",
    "This turn ran past the configured deadline. Published replies were kept.",
    retryable=True,
)
INTERNAL = error_dict("internal_error", "Something went wrong while generating replies.")
LAB_CANCELLED = error_dict(
    "lab_interrupted",
    "The app restarted before this Lab turn started; its batch was marked interrupted.",
)
FINALIZE_BACKOFF = (0.5, 1.0, 2.0, 5.0, 10.0)  # retried until the database answers


async def missing_slots(s: AsyncSession, run: Run) -> list[str]:
    """Requested slots with no published reply (auto rounds have no fixed slots)."""
    rows = (
        await s.execute(
            select(Message.role, Message.persona_id).where(
                Message.run_id == run.id, Message.role != "user"
            )
        )
    ).all()
    published = {pid or "moderator" for _, pid in rows}
    missing = [
        slot
        for slot in run.slots
        if (slot if slot not in ("assistant", "summary") else "moderator") not in published
    ]
    return list(dict.fromkeys([*run.missing, *missing]))


async def finalize_run(
    sessionmaker: async_sessionmaker[AsyncSession],
    notifier: Notifier,
    run_id: UUID,
    kind: str,
    result: RunResult | None,
    warnings: list[str],
) -> None:
    """Idempotent: a run that is already terminal is left alone."""
    async with sessionmaker() as s, s.begin():
        run = await s.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if run is None or run.status not in ("running", "cancelling"):
            return
        published = run.published_count > 0
        error: dict[str, Any] | None = None
        degraded = None
        extra: list[str] = list(warnings)
        if run.cancel_requested or kind == "cancelled":
            status = "cancelled"
        elif kind == "result" and result is not None:
            status, error, degraded = result.status, result.error, result.degraded
            extra += result.warnings
        elif kind == "deadline":
            status, error = ("partial" if published else "failed"), DEADLINE
            extra.append("deadline_exceeded")
        elif kind == "interrupted":
            status, error = "interrupted", INTERRUPTED
        else:
            status, error = ("partial" if published else "failed"), INTERNAL
        run.missing = await missing_slots(s, run)
        await mark_terminal(s, run, status, warnings=extra, error=error, degraded=degraded)
    await notifier.notify_run(run_id, final=True)


async def recover(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Startup: orphaned work is interrupted, never silently retried (TRD §Run lifecycle)."""
    async with sessionmaker() as s, s.begin():
        now = utcnow()
        orphans = (
            await s.scalars(
                select(Run).where(Run.status.in_(("running", "cancelling"))).with_for_update()
            )
        ).all()
        for run in orphans:
            await mark_terminal(s, run, "interrupted", error=INTERRUPTED)
        await s.execute(
            update(ProviderCall)
            .where(ProviderCall.status == "started")
            .values(
                status="error",
                usage_unknown=True,
                finished_at=now,
                diagnostics={"note": "the app restarted before this call finished"},
            )
        )
        lab_queued = (
            await s.scalars(
                select(Run)
                .join(Session, Session.id == Run.session_id)
                .where(Run.status == "queued", Session.evaluation_batch_id.is_not(None))
                .with_for_update(of=Run)
            )
        ).all()
        for run in lab_queued:
            await mark_terminal(s, run, "cancelled", error=LAB_CANCELLED)
        await s.execute(
            update(EvaluationTrial)
            .where(EvaluationTrial.status.in_(("queued", "running")))
            .values(status="interrupted", updated_at=now)
        )
        await s.execute(
            update(EvaluationBatch)
            .where(EvaluationBatch.status.in_(("queued", "running")))
            .values(status="interrupted", updated_at=now, finished_at=now)
        )
    if orphans or lab_queued:
        log.warning(
            "recovery: %d interrupted, %d lab runs cancelled", len(orphans), len(lab_queued)
        )


class Runner:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        notifier: Notifier,
        catalog: Catalog,
        execute: Execute,
        worker_id: str | None = None,
    ) -> None:
        self.sessionmaker, self.notifier, self.catalog, self.execute = (
            sessionmaker,
            notifier,
            catalog,
            execute,
        )
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.contexts: dict[UUID, RunContext] = {}
        self.tasks: dict[UUID, asyncio.Task[None]] = {}
        self._loop_task: asyncio.Task[None] | None = None
        self._stopping = False

    @property
    def max_runs(self) -> int:
        return self.catalog.defaults.limits.concurrent_session_runs

    def alive(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    async def start(self) -> None:
        await recover(self.sessionmaker)
        self._loop_task = asyncio.create_task(self._loop(), name="run-worker")

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    def cancel_signal(self, run_id: UUID) -> None:
        if ctx := self.contexts.get(run_id):
            ctx.stop()

    async def _loop(self) -> None:
        while True:
            try:
                await self._fill()
            except Exception:
                log.exception("worker loop error")
            await self.notifier.wait_for_work(1.0)

    async def _fill(self) -> None:
        while len(self.tasks) < self.max_runs and not self._stopping:
            claimed = await self._claim()
            if claimed is None:
                return
            ctx = RunContext(
                claimed.id, claimed.session_id, claimed.snapshot, self.sessionmaker, self.notifier
            )
            self.contexts[claimed.id] = ctx
            self.tasks[claimed.id] = asyncio.create_task(self._execute(ctx))

    async def _claim(self) -> Run | None:
        async with self.sessionmaker() as s, s.begin():
            lab_running = await s.scalar(
                select(
                    exists().where(
                        Run.status.in_(("running", "cancelling")),
                        Run.session_id == Session.id,
                        Session.evaluation_batch_id.is_not(None),
                    )
                )
            )
            q = (
                select(Run)
                .join(Session, Session.id == Run.session_id)
                .where(Run.status == "queued")
            )
            if lab_running:  # G19: the Lab never holds more than one run slot
                q = q.where(Session.evaluation_batch_id.is_(None))
            run = await s.scalar(
                q.order_by(Run.created_at, Run.id)
                .with_for_update(skip_locked=True, of=Run)
                .limit(1)
            )
            if run is None:
                return None
            now = utcnow()
            deadline = float(run.snapshot["timeouts"]["turn_deadline"])
            run.status, run.stage, run.worker_id = "running", "preparing", self.worker_id
            run.started_at = run.heartbeat_at = run.updated_at = now
            run.deadline_at = now + timedelta(seconds=deadline)
            await s.flush()
            await append_event(
                s,
                run,
                "run.started",
                {
                    "status": run.status,
                    "stage": run.stage,
                    "session_version": run.session_version,
                    "audience": run.audience,
                    "slots": list(run.slots),
                },
            )
        await self.notifier.notify_run(run.id)
        return run

    async def _execute(self, ctx: RunContext) -> None:
        timer = asyncio.get_running_loop().call_later(
            float(ctx.snapshot["timeouts"]["turn_deadline"]), ctx.expire
        )
        kind, result, interrupted = "result", None, False
        try:
            result = await self.execute(ctx)
        except RunCancelled:
            kind = "cancelled"
        except DeadlineExceeded:
            kind = "deadline"
        except asyncio.CancelledError:
            kind, interrupted = "interrupted", True
        except Exception:
            log.exception("run %s failed", ctx.run_id)
            kind = "error"
        finally:
            timer.cancel()
        try:
            await asyncio.shield(self._finalize_reliably(ctx, kind, result))
        finally:
            self.tasks.pop(ctx.run_id, None)
            self.contexts.pop(ctx.run_id, None)
            self.notifier.wake_worker()
        if interrupted:
            raise asyncio.CancelledError

    async def _finalize_reliably(
        self, ctx: RunContext, kind: str, result: RunResult | None
    ) -> None:
        """A run must never stay active because its final write hit a database blip."""
        attempt = 0
        while True:
            try:
                await finalize_run(
                    self.sessionmaker, self.notifier, ctx.run_id, kind, result, ctx.warnings
                )
                return
            except Exception:
                delay = FINALIZE_BACKOFF[min(attempt, len(FINALIZE_BACKOFF) - 1)]
                log.warning("finalize of run %s failed; retrying in %ss", ctx.run_id, delay)
                attempt += 1
                await asyncio.sleep(delay)
