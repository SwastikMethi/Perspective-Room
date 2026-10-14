"""One provider-call policy (T06, G17): recorded before sending, bounded attempts, safe retries."""

import asyncio
import dataclasses

import pytest
from conftest import idem, turn_body
from sqlalchemy import select, update

from app.persistence.models import ProviderCall, Run
from app.providers.base import ProviderFailure, Structured, Usage
from app.providers.calls import AttemptsExhausted, call_provider, classify_http
from app.workers.context import RunCancelled, RunContext


async def make_ctx(app, client, new_session, **snapshot_overrides):
    s = await new_session()
    run = (
        await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    ).json()
    async with app.state.sessionmaker() as db:
        row = await db.get(Run, run["id"])
        snap = {**row.snapshot}
        if "timeouts" in snapshot_overrides:
            snap["timeouts"] = {**snap["timeouts"], **snapshot_overrides["timeouts"]}
        await db.execute(
            update(Run).where(Run.id == row.id).values(status="running", snapshot=snap)
        )
        await db.commit()
    return RunContext(row.id, row.session_id, snap, app.state.sessionmaker, app.state.notifier)


def ok(tokens=(10, 5)):
    return Structured({"x": 1}, "gpt-6.1-sol-2026", "resp_1", Usage(*tokens))


async def rows(db):
    async with db() as s:
        return (await s.scalars(select(ProviderCall).order_by(ProviderCall.attempt))).all()


async def test_success_is_recorded_with_usage(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)

    async def fn():
        return ok()

    result = await call_provider(
        ctx,
        purpose="draft",
        provider="openai",
        model="gpt-6.1-sol",
        fn=fn,
        template_hash="t" * 64,
        profile_hash="p" * 64,
    )
    assert result.data == {"x": 1}
    [row] = await rows(db)
    assert (row.status, row.attempt, row.purpose, row.provider) == ("ok", 1, "draft", "openai")
    assert (row.model, row.response_id) == ("gpt-6.1-sol-2026", "resp_1")
    assert (row.input_tokens, row.output_tokens, row.template_hash) == (10, 5, "t" * 64)
    async with db() as s:
        run = await s.get(Run, ctx.run_id)
    assert run.usage["input_tokens"] == 10 and run.usage["output_tokens"] == 5
    assert run.attempts == 1


async def test_call_row_is_committed_before_the_request(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)
    seen = []

    async def fn():
        seen.extend(r.status for r in await rows(db))
        return ok()

    await call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    assert seen == ["started"]


async def test_transient_failure_is_retried_exactly_once(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderFailure(
                "transient", "rate limited", retryable=True, retry_after=0.01, status=429
            )
        return ok()

    await call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    assert calls["n"] == 2
    assert [r.status for r in await rows(db)] == ["error", "ok"]


async def test_second_transient_failure_is_not_retried_again(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)

    async def fn():
        raise ProviderFailure("transient", "overloaded", retryable=True, retry_after=0.01)

    with pytest.raises(ProviderFailure):
        await call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    assert len(await rows(db)) == 2


async def test_invalid_key_is_one_call_and_no_retry(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)

    async def fn():
        raise ProviderFailure("provider_not_ready", "Incorrect API key", status=401)

    with pytest.raises(ProviderFailure) as err:
        await call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    assert err.value.code == "provider_not_ready"
    [row] = await rows(db)
    assert row.status == "error" and row.diagnostics["code"] == "provider_not_ready"
    assert "Incorrect API key" not in str(row.diagnostics)  # sanitized


async def test_timeout_is_unknown_usage_and_never_resubmitted(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session, timeouts={"generation": 0.05})
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        await asyncio.sleep(1)

    with pytest.raises(ProviderFailure) as err:
        await call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    assert err.value.code == "timeout" and calls["n"] == 1
    [row] = await rows(db)
    assert row.status == "timeout" and row.usage_unknown is True
    async with db() as s:
        assert (await s.get(Run, ctx.run_id)).usage["usage_incomplete"] is True


async def test_attempt_ceiling_refuses_the_next_call(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)
    async with db() as s:
        await s.execute(update(Run).where(Run.id == ctx.run_id).values(attempts=40))
        await s.commit()

    async def fn():
        raise AssertionError("must not be called")

    with pytest.raises(AttemptsExhausted):
        await call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    assert await rows(db) == []


async def test_stop_before_a_call_prevents_it(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)
    async with db() as s:
        await s.execute(update(Run).where(Run.id == ctx.run_id).values(cancel_requested=True))
        await s.commit()

    async def fn():
        raise AssertionError("must not be called")

    with pytest.raises(RunCancelled):
        await call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    assert await rows(db) == []


@pytest.mark.parametrize(
    "status,code,retryable,unknown",
    [
        (429, "transient", True, False),
        (503, "transient", True, False),
        (529, "transient", True, False),
        (500, "provider_error", False, True),
        (502, "provider_error", False, True),
        (504, "provider_error", False, True),
        (401, "provider_not_ready", False, False),
        (403, "provider_not_ready", False, False),
        (400, "invalid_request", False, False),
        (422, "invalid_request", False, False),
    ],
)
def test_http_status_classification(status, code, retryable, unknown):
    f = classify_http(status, "body text", retry_after="2", request_id="req_1")
    assert (f.code, f.retryable, f.usage_unknown) == (code, retryable, unknown)
    assert f.request_id == "req_1" and (f.retry_after == 2.0 if retryable else True)


def test_model_not_found_is_model_unavailable():
    f = classify_http(404, '{"error":{"code":"model_not_found"}}')
    assert f.code == "model_unavailable" and not f.retryable


def test_dataclass_ok():
    assert dataclasses.is_dataclass(Usage)


async def test_outer_cancellation_records_the_call_as_cancelled(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)
    started = asyncio.Event()

    async def fn():
        started.set()
        await asyncio.sleep(5)

    task = asyncio.create_task(
        call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    [row] = await rows(db)
    assert row.status == "cancelled" and row.usage_unknown is True


async def test_bad_key_does_not_mark_usage_incomplete(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)

    async def fn():
        raise ProviderFailure("provider_not_ready", "bad key", status=401)

    with pytest.raises(ProviderFailure):
        await call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    async with db() as s:
        assert (await s.get(Run, ctx.run_id)).usage.get("usage_incomplete") is False


async def test_long_retry_after_is_not_cut_short(app, client, db, new_session):
    ctx = await make_ctx(app, client, new_session)

    async def fn():
        raise ProviderFailure("transient", "slow down", retryable=True, retry_after=60)

    with pytest.raises(ProviderFailure):
        await call_provider(ctx, purpose="draft", provider="openai", model="m", fn=fn)
    assert len(await rows(db)) == 1  # waiting 60 s inside a turn is not a sane retry
