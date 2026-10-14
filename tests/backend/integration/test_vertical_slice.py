"""End-to-end slice with the demo provider: create → turn → worker → validated publish → events."""

import asyncio

from conftest import idem, turn_body
from sqlalchemy import select

from app.persistence.models import Message, Run, RunEvent


async def wait_status(db, run_id, statuses, timeout=8.0):
    async with asyncio.timeout(timeout):
        while True:
            async with db() as s:
                status = (await s.get(Run, run_id)).status
            if status in statuses:
                return status
            await asyncio.sleep(0.05)


async def submit(client, session_id, message="Help me explore it.", **control):
    r = await client.post(
        f"/api/v1/sessions/{session_id}/turns",
        json=turn_body(1, message, **control),
        headers=idem(),
    )
    assert r.status_code == 202, r.text
    return r.json()


async def persona_messages(db, session_id):
    async with db() as s:
        return (
            await s.scalars(
                select(Message)
                .where(Message.session_id == session_id, Message.role != "user")
                .order_by(Message.sequence)
            )
        ).all()


async def test_turn_produces_published_contributions_with_events(
    running_app, client, db, new_session
):
    s = await new_session()
    run = await submit(client, s["id"], audience="panel")
    assert await wait_status(db, run["id"], {"completed", "partial", "failed"}) == "completed"
    msgs = await persona_messages(db, s["id"])
    assert [m.persona_id for m in msgs] == ["mentor", "skeptic", "explorer"]  # roster order
    assert all(m.contribution["headline"] and m.search_text for m in msgs)
    async with db() as sess:
        published = (
            await sess.scalars(
                select(RunEvent).where(
                    RunEvent.run_id == run["id"], RunEvent.type == "message.completed"
                )
            )
        ).all()
    assert sorted(e.data["message"]["id"] for e in published) == sorted(str(m.id) for m in msgs)
    page = (await client.get(f"/api/v1/sessions/{s['id']}/messages")).json()
    assert [m["sequence"] for m in page["items"]] == [1, 2, 3, 4]


async def test_failed_slot_makes_the_run_partial_and_keeps_the_rest(
    running_app, client, db, new_session
):
    s = await new_session()
    run = await submit(client, s["id"], "[[demo:fail=skeptic]] explore", audience="panel")
    assert await wait_status(db, run["id"], {"completed", "partial", "failed"}) == "partial"
    assert [m.persona_id for m in await persona_messages(db, s["id"])] == ["mentor", "explorer"]
    async with db() as sess:
        row = await sess.get(Run, run["id"])
    assert row.missing == ["skeptic"] and "contribution_failed" in row.warning_codes


async def test_stop_a_delayed_demo_run(running_app, client, db, new_session):
    s = await new_session()
    run = await submit(client, s["id"], "[[demo:delay=600]] slowly", audience="panel")
    async with asyncio.timeout(5):
        while not await persona_messages(db, s["id"]):
            await asyncio.sleep(0.05)
    await client.post(f"/api/v1/runs/{run['id']}/cancel")
    assert await wait_status(db, run["id"], {"cancelled"}) == "cancelled"
    n = len(await persona_messages(db, s["id"]))
    await asyncio.sleep(1.5)
    assert len(await persona_messages(db, s["id"])) == n < 3


async def test_run_queued_under_another_provider_mode_never_calls_a_provider(
    app, client, db, new_session
):
    from sqlalchemy import update

    s = await new_session()
    run = await submit(client, s["id"])
    async with db() as sess:  # queued while the app was in live mode, then restarted in demo
        row = await sess.get(Run, run["id"])
        snap = {**row.snapshot, "provider_mode": "live"}
        await sess.execute(update(Run).where(Run.id == run["id"]).values(snapshot=snap))
        await sess.commit()
    await app.state.runner.start()
    try:
        assert await wait_status(db, run["id"], {"completed", "partial", "failed"}) == "failed"
    finally:
        await app.state.runner.stop()
    got = (await client.get(f"/api/v1/runs/{run['id']}")).json()
    assert got["error"]["code"] == "provider_mode_changed"
    assert await persona_messages(db, s["id"]) == []


async def test_demo_runs_are_labeled_and_report_missing_slots_on_stop(
    running_app, client, db, new_session
):
    s = await new_session()
    run = await submit(client, s["id"], "[[demo:delay=500]] label me", audience="panel")
    async with asyncio.timeout(5):
        while not await persona_messages(db, s["id"]):
            await asyncio.sleep(0.05)
    await client.post(f"/api/v1/runs/{run['id']}/cancel")
    await wait_status(db, run["id"], {"cancelled"})
    async with db() as sess:
        terminal = await sess.scalar(
            select(RunEvent)
            .where(RunEvent.run_id == run["id"])
            .order_by(RunEvent.id.desc())
            .limit(1)
        )
    assert "demo_mode" in terminal.data["run"]["warning_codes"]
    published = {m.persona_id for m in await persona_messages(db, s["id"])}
    assert (
        set(terminal.data["missing_persona_ids"]) == {"mentor", "skeptic", "explorer"} - published
    )
