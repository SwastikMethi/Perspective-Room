"""Worker claiming, Stop (T09), deadline (T06), restart recovery (T11), concurrency cap."""

import asyncio
import dataclasses
from uuid import uuid4

import pytest
from conftest import idem, make_test_env, turn_body
from sqlalchemy import func, select, update

from app.persistence.models import (
    EvaluationBatch,
    EvaluationTrial,
    Message,
    ProviderCall,
    Run,
    RunEvent,
    Session,
)
from app.services.publish import publish_contribution
from app.workers.context import RunContext, RunResult
from app.workers.runner import Runner, recover

CONTRIBUTION = {
    "headline": "A safe first step",
    "blocks": [{"kind": "suggestion", "text": "Try one private answer first.", "source_ids": []}],
    "referenced_message_ids": [],
    "new_angle": "Lower the stakes of the first attempt.",
    "next_question": None,
}


class FakePipeline:
    """Stands in for the orchestrator: N provider calls, each followed by a publication."""

    def __init__(self, steps=3, delay=0.0):
        self.steps, self.delay = steps, delay
        self.calls: list[str] = []
        self.running = 0
        self.max_running = 0

    async def __call__(self, ctx: RunContext) -> RunResult:
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            for i in range(self.steps):
                await ctx.check_db()
                await ctx.call(self._provider(ctx, i))
                await publish_contribution(
                    ctx,
                    role="persona",
                    persona_id="mentor",
                    contribution=CONTRIBUTION,
                    contribution_index=i,
                )
            return RunResult(status="completed")
        finally:
            self.running -= 1

    async def _provider(self, ctx, i):
        await asyncio.sleep(self.delay)
        self.calls.append(f"{ctx.run_id}:{i}")


async def start_runner(app, pipeline, catalog=None):
    runner = Runner(
        app.state.sessionmaker,
        app.state.notifier,
        catalog or app.state.catalog,
        execute=pipeline,
        worker_id="test-worker",
    )
    app.state.runner = runner
    app.state.worker_alive = runner.alive
    await runner.start()
    return runner


async def submit(client, session_id, version=1):
    r = await client.post(
        f"/api/v1/sessions/{session_id}/turns", json=turn_body(version), headers=idem()
    )
    assert r.status_code == 202, r.text
    return r.json()


async def wait_for(predicate, timeout=5.0):
    async with asyncio.timeout(timeout):
        while not await predicate():
            await asyncio.sleep(0.02)


async def run_status(db, run_id):
    async with db() as s:
        return (await s.get(Run, run_id)).status


async def count(db, model, *where):
    async with db() as s:
        return await s.scalar(select(func.count()).select_from(model).where(*where))


async def test_worker_claims_and_completes_a_run(app, client, db, new_session):
    pipeline = FakePipeline(steps=2)
    runner = await start_runner(app, pipeline)
    try:
        s = await new_session()
        run = await submit(client, s["id"])
        await wait_for(lambda: _is(db, run["id"], "completed"))
        async with db() as sess:
            types = (
                await sess.scalars(
                    select(RunEvent.type).where(RunEvent.run_id == run["id"]).order_by(RunEvent.id)
                )
            ).all()
            user = await sess.scalar(select(Message).where(Message.role == "user"))
        assert types == [
            "run.queued",
            "run.started",
            "message.completed",
            "message.completed",
            "run.completed",
        ]
        assert user.round_status == "completed"
        got = (await client.get(f"/api/v1/runs/{run['id']}")).json()
        assert got["published_count"] == 2 and got["status"] == "completed"
        health = (await client.get("/api/v1/health")).json()
        assert health["worker"] == "ok"
    finally:
        await runner.stop()


async def _is(db, run_id, status):
    return await run_status(db, run_id) == status


async def test_stop_during_generation_prevents_later_calls_and_messages(
    app, client, db, new_session
):
    pipeline = FakePipeline(steps=5, delay=0.3)
    runner = await start_runner(app, pipeline)
    try:
        s = await new_session()
        run = await submit(client, s["id"])
        await wait_for(lambda: _count_is(db, Message, 2))  # user message + first contribution
        r = await client.post(f"/api/v1/runs/{run['id']}/cancel")
        assert r.status_code == 200 and r.json()["status"] in ("cancelling", "cancelled")
        await wait_for(lambda: _is(db, run["id"], "cancelled"))
        calls_at_stop = len(pipeline.calls)
        await asyncio.sleep(0.8)
        assert len(pipeline.calls) == calls_at_stop <= 2
        assert await count(db, Message) == 2  # the published reply survives; nothing late
        again = await client.post(f"/api/v1/runs/{run['id']}/cancel")
        assert again.status_code == 200 and again.json()["status"] == "cancelled"
        async with db() as sess:
            last = await sess.scalar(
                select(RunEvent)
                .where(RunEvent.run_id == run["id"])
                .order_by(RunEvent.id.desc())
                .limit(1)
            )
        assert last.type == "run.cancelled" and last.data["run"]["status"] == "cancelled"
    finally:
        await runner.stop()


async def _count_is(db, model, n):
    return await count(db, model) == n


async def test_cancelling_a_queued_run_never_executes_it(client, db, new_session):
    s = await new_session()
    run = await submit(client, s["id"])
    r = await client.post(f"/api/v1/runs/{run['id']}/cancel")
    assert r.json()["status"] == "cancelled"
    session = (await client.get(f"/api/v1/sessions/{s['id']}")).json()
    assert session["active_run_id"] is None


async def test_turn_deadline_ends_a_stuck_run_and_keeps_published_output(
    app, client, db, new_session
):
    cat = app.state.catalog
    short = cat.defaults.model_copy(
        update={
            "timeouts_seconds": cat.defaults.timeouts_seconds.model_copy(
                update={"turn_deadline": 0.9}
            )
        }
    )
    app.state.catalog = dataclasses.replace(cat, defaults=short)
    pipeline = FakePipeline(steps=6, delay=0.35)
    runner = await start_runner(app, pipeline)
    try:
        s = await new_session()
        run = await submit(client, s["id"])
        await wait_for(lambda: _is(db, run["id"], "partial"), timeout=6)
        got = (await client.get(f"/api/v1/runs/{run['id']}")).json()
        assert "deadline_exceeded" in got["warning_codes"]
        assert got["error"]["code"] == "deadline_exceeded" and got["published_count"] >= 1
    finally:
        await runner.stop()


async def test_restart_recovery_interrupts_orphans_without_repeating_paid_work(
    app, client, db, new_session
):
    s = await new_session()
    run = await submit(client, s["id"])
    async with db() as sess:  # a worker claimed it, made a call, then the process died
        await sess.execute(update(Run).where(Run.id == run["id"]).values(status="running"))
        sess.add(
            ProviderCall(
                run_id=run["id"],
                session_id=s["id"],
                purpose="draft",
                attempt=1,
                provider="openai",
                model="gpt-6.1-sol",
                status="started",
            )
        )
        await sess.commit()
    await recover(app.state.sessionmaker)
    assert await run_status(db, run["id"]) == "interrupted"
    async with db() as sess:
        call = await sess.scalar(select(ProviderCall))
        assert call.usage_unknown is True and call.status != "started"
        user = await sess.scalar(select(Message).where(Message.role == "user"))
        assert user.round_status == "interrupted"
    pipeline = FakePipeline()
    runner = await start_runner(app, pipeline)
    try:
        await asyncio.sleep(0.5)
        assert pipeline.calls == []  # an uncertain run is never retried automatically
        assert await count(db, Message) == 1
    finally:
        await runner.stop()


async def test_queued_ordinary_runs_survive_restart_but_lab_runs_are_cancelled(
    app, client, db, new_session
):
    s = await new_session()
    lab = await new_session()
    run = await submit(client, s["id"])
    async with db() as sess:
        batch = EvaluationBatch(
            status="running", config={}, snapshot={}, seed=1, provider_mode="demo", planned=1
        )
        sess.add(batch)
        await sess.flush()
        await sess.execute(
            update(Session).where(Session.id == lab["id"]).values(evaluation_batch_id=batch.id)
        )
        sess.add(
            EvaluationTrial(
                batch_id=batch.id,
                case_id="case_01",
                replicate=1,
                mode="standard",
                session_id=lab["id"],
                blind_label="Output 1",
                status="running",
            )
        )
        await sess.commit()
        batch_id = batch.id
    from app.domain import api
    from app.services.turns import submit_turn

    async with db() as sess, sess.begin():
        lab_run = await submit_turn(
            sess,
            make_test_env(),
            app.state.catalog,
            lab["id"],
            api.TurnCreate(**turn_body(1)),
            lab=True,
        )
    await recover(app.state.sessionmaker)
    assert await run_status(db, run["id"]) == "queued"
    assert await run_status(db, lab_run.id) == "cancelled"
    async with db() as sess:
        assert (await sess.get(EvaluationBatch, batch_id)).status == "interrupted"
        trial = await sess.scalar(select(EvaluationTrial))
        assert trial.status == "interrupted"


async def test_at_most_two_runs_execute_concurrently(app, client, db, new_session):
    pipeline = FakePipeline(steps=1, delay=0.4)
    runner = await start_runner(app, pipeline)
    try:
        runs = []
        for _ in range(3):
            s = await new_session()
            runs.append(await submit(client, s["id"]))
        await wait_for(lambda: _all_done(db, [r["id"] for r in runs]), timeout=8)
        assert pipeline.max_running == 2
    finally:
        await runner.stop()


async def _all_done(db, ids):
    return all([await run_status(db, i) == "completed" for i in ids])


@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_cancel_on_a_finished_run_is_a_no_op(client, db, new_session, status):
    s = await new_session()
    run = await submit(client, s["id"])
    async with db() as sess:
        await sess.execute(update(Run).where(Run.id == run["id"]).values(status=status))
        await sess.commit()
    r = await client.post(f"/api/v1/runs/{run['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == status
    assert (await client.post(f"/api/v1/runs/{uuid4()}/cancel")).status_code == 404


async def test_finalize_retries_until_the_database_answers(
    app, client, db, new_session, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    import app.workers.runner as runner_mod

    real = runner_mod.finalize_run
    attempts = {"n": 0}

    async def flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OperationalError("UPDATE runs", {}, Exception("database blip"))
        return await real(*args, **kwargs)

    monkeypatch.setattr(runner_mod, "finalize_run", flaky)
    monkeypatch.setattr(runner_mod, "FINALIZE_BACKOFF", (0.05, 0.1))
    runner = await start_runner(app, FakePipeline(steps=1))
    try:
        s = await new_session()
        run = await submit(client, s["id"])
        await wait_for(lambda: _is(db, run["id"], "completed"))
        assert attempts["n"] >= 2
    finally:
        await runner.stop()
