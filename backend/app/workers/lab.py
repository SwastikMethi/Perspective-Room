"""Experiment Lab scheduler (G19): one batch and one trial at a time, in-process FIFO. A trial is
its case's three scripted user turns submitted through the normal turn API path, so the worker
and orchestrator treat them like any chat; the Runner's claim cap keeps the Lab to one run slot.

Cancel stops new turns and cancels the active child run; finished trials are kept. A restart is
handled by Runner.recover (queued Lab runs cancelled, active batches/trials interrupted) before
this scheduler starts, so uncertain work is never continued automatically.
"""

import asyncio
import logging
import random
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.catalog import Catalog
from app.domain import api
from app.persistence.models import TERMINAL_RUN_STATUSES, EvaluationBatch, EvaluationTrial, Run
from app.persistence.models import Session as SessionRow
from app.services import runs as run_svc
from app.services.common import utcnow
from app.services.turns import submit_turn
from app.settings import AppEnv
from app.workers.notifier import Notifier

log = logging.getLogger("perspective.lab")
POLL_S = 0.1  # ponytail: DB polling for child runs; switch to notifier waits if it shows in load
MODE_RANK = {"standard": 0, "fixed_panel": 1, "jev_guided": 2}
CONTROL = api.TurnControl(
    audience="auto",
    target_persona_id=None,
    move_override=None,
    reply_to_message_id=None,
    idea_card_ids=[],
    research_override="auto",
)


class LabScheduler:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        env: Callable[[], AppEnv],
        catalog: Catalog,
        notifier: Notifier,
        cancel_signal: Callable[[UUID], None],
    ) -> None:
        self.sessionmaker, self.env, self.catalog = sessionmaker, env, catalog
        self.notifier, self.cancel_signal = notifier, cancel_signal
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def wake(self) -> None:
        self._wake.set()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="lab-scheduler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                worked = await self._step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("lab scheduler error")
                worked = False
            if not worked:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), 2.0)
                except TimeoutError:
                    pass

    async def _step(self) -> bool:
        async with self.sessionmaker() as s:
            batch_id = await s.scalar(
                select(EvaluationBatch.id)
                .where(EvaluationBatch.status.in_(("queued", "running")))
                .order_by(EvaluationBatch.created_at, EvaluationBatch.id)
                .limit(1)
            )
        if batch_id is None:
            return False
        await self._run_batch(batch_id)
        return True

    async def _cancel_requested(self, batch_id: UUID) -> bool:
        async with self.sessionmaker() as s:
            return bool(
                await s.scalar(
                    select(EvaluationBatch.cancel_requested).where(EvaluationBatch.id == batch_id)
                )
            )

    async def _run_batch(self, batch_id: UUID) -> None:
        async with self.sessionmaker() as s, s.begin():
            b = await s.get(EvaluationBatch, batch_id, with_for_update=True)
            if b is None or b.status not in ("queued", "running"):
                return
            b.status, b.updated_at = "running", utcnow()
            trials = (
                await s.scalars(
                    select(EvaluationTrial).where(
                        EvaluationTrial.batch_id == batch_id, EvaluationTrial.status == "queued"
                    )
                )
            ).all()
            seed = b.seed

            def rank(t: EvaluationTrial) -> tuple[str, int, int]:
                # Conditions run in a seeded shuffled order per case, so none always runs last
                # (provider drift/rate limits) and timing cannot hint at the condition.
                modes = sorted(MODE_RANK, key=MODE_RANK.__getitem__)
                random.Random(f"{seed}:order:{t.case_id}:{t.replicate}").shuffle(modes)
                return (t.case_id, t.replicate, modes.index(t.mode))

            trial_ids = [t.id for t in sorted(trials, key=rank)]
        for trial_id in trial_ids:
            if await self._cancel_requested(batch_id):
                break
            await self._run_trial(batch_id, trial_id)
        await self._finish_batch(batch_id)

    async def _finish_batch(self, batch_id: UUID) -> None:
        async with self.sessionmaker() as s, s.begin():
            b = await s.get(EvaluationBatch, batch_id, with_for_update=True)
            if b is None:
                return
            now = utcnow()
            if b.cancel_requested:
                await s.execute(
                    update(EvaluationTrial)
                    .where(EvaluationTrial.batch_id == batch_id, EvaluationTrial.status == "queued")
                    .values(status="cancelled", updated_at=now)
                )
            statuses = (
                await s.scalars(
                    select(EvaluationTrial.status).where(EvaluationTrial.batch_id == batch_id)
                )
            ).all()
            done = statuses.count("completed")
            produced = done + statuses.count("partial")  # partial trials have rateable output
            b.finished, b.failed = done, len(statuses) - done
            if b.cancel_requested:
                b.status = "cancelled"
            elif done == len(statuses):
                b.status = "completed"
            elif produced == 0:
                b.status = "failed"
            else:
                b.status = "partial"
            b.updated_at = b.finished_at = now

    async def _wait_terminal(self, batch_id: UUID, run_id: UUID) -> Run:
        cancelled = False
        while True:
            async with self.sessionmaker() as s:
                run = await s.get(Run, run_id)
            assert run is not None
            if run.status in TERMINAL_RUN_STATUSES:
                return run
            if not cancelled and await self._cancel_requested(batch_id):
                cancelled = True
                async with self.sessionmaker() as s:
                    await run_svc.cancel_run(s, run_id)
                await self.notifier.notify_run(run_id)
                self.cancel_signal(run_id)
            await asyncio.sleep(POLL_S)

    async def _run_trial(self, batch_id: UUID, trial_id: UUID) -> None:
        async with self.sessionmaker() as s, s.begin():
            trial = await s.get(EvaluationTrial, trial_id, with_for_update=True)
            assert trial is not None
            trial.status, trial.updated_at = "running", utcnow()
            case = self.catalog.cases[trial.case_id]
            session_id = trial.session_id
        status, degraded, ran_ms, ran_any = "completed", False, 0, False
        usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0, "usage_incomplete": False}
        try:
            for text in case.user_turns:
                if await self._cancel_requested(batch_id):
                    status = "cancelled"
                    break
                try:
                    async with self.sessionmaker() as s, s.begin():
                        session = await s.get(SessionRow, session_id)
                        assert session is not None
                        run = await submit_turn(
                            s,
                            self.env(),
                            self.catalog,
                            session.id,
                            api.TurnCreate(
                                expected_version=session.version, message=text, control=CONTROL
                            ),
                            lab=True,
                        )
                except ApiError as e:
                    log.warning("lab turn refused: %s", e.code)
                    status = "failed"
                    break
                self.notifier.wake_worker()
                final = await self._wait_terminal(batch_id, run.id)
                if final.started_at and final.finished_at:  # run time only, never queue waits
                    ran_ms += int((final.finished_at - final.started_at).total_seconds() * 1000)
                    ran_any = True
                degraded = degraded or final.degraded
                u = final.usage or {}
                for k in ("input_tokens", "output_tokens"):
                    if u.get(k) is None:
                        usage["usage_incomplete"] = True
                    else:
                        usage[k] += int(u[k])
                usage["usage_incomplete"] = usage["usage_incomplete"] or bool(
                    u.get("usage_incomplete")
                )
                if final.status == "partial":
                    status = "partial"  # some replies missing; the trial runs its next turn
                elif final.status != "completed":
                    status = "cancelled" if final.status == "cancelled" else "failed"
                    break
        except asyncio.CancelledError:
            raise  # shutdown: recovery marks the trial interrupted on the next start
        except Exception:
            log.exception("lab trial failed")
            status = "failed"
        if usage["usage_incomplete"]:  # a partial sum would look like a real total
            usage["input_tokens"] = usage["output_tokens"] = None
        async with self.sessionmaker() as s, s.begin():
            trial = await s.get(EvaluationTrial, trial_id, with_for_update=True)
            assert trial is not None
            trial.status, trial.degraded, trial.usage = status, degraded, usage
            trial.elapsed_ms = ran_ms if ran_any else None
            trial.updated_at = utcnow()
            b = await s.get(EvaluationBatch, batch_id, with_for_update=True)
            assert b is not None
            if status == "completed":
                b.finished += 1
            else:
                b.failed += 1
            b.updated_at = utcnow()
