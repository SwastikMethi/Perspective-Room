"""Run event stream (T10): replay after a cursor, tail, heartbeat, terminal close, bad cursors."""

import asyncio
import dataclasses
import json
import time

from conftest import idem, turn_body
from sqlalchemy import func, select

from app.persistence.models import ProviderCall, Run, RunEvent
from app.services.runs import append_event, mark_terminal


def parse_sse(text: str) -> list[dict]:
    frames = []
    for block in text.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if line.startswith(":"):
                fields.setdefault("comments", []).append(line)
            elif ": " in line:
                k, v = line.split(": ", 1)
                fields[k] = v
        if fields:
            frames.append(fields)
    return frames


def events(text: str) -> list[dict]:
    return [f for f in parse_sse(text) if "event" in f]


async def make_run(client, new_session):
    s = await new_session()
    r = await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    return r.json()


async def add_events(db, run_id, *types, terminal=None):
    async with db() as s, s.begin():
        run = await s.scalar(select(Run).where(Run.id == run_id).with_for_update())
        for t in types:
            await append_event(
                s, run, t, {"stage": "drafting", "persona_id": None, "status_key": "x"}
            )
        if terminal:
            run.status = "running"
            await mark_terminal(s, run, terminal)


async def test_replay_streams_each_event_once_then_closes_after_terminal(client, db, new_session):
    run = await make_run(client, new_session)
    await add_events(db, run["id"], "run.stage", "run.stage", terminal="completed")
    r = await client.get(f"/api/v1/runs/{run['id']}/events")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-store"
    got = events(r.text)
    assert [e["event"] for e in got] == ["run.queued", "run.stage", "run.stage", "run.completed"]
    ids = [int(e["id"]) for e in got]
    assert ids == sorted(ids) and len(set(ids)) == 4
    envelope = json.loads(got[-1]["data"])
    assert envelope["id"] == got[-1]["id"] and envelope["type"] == "run.completed"
    assert envelope["data"]["run"]["status"] == "completed"


async def test_cursor_resumes_after_the_last_seen_event_and_header_wins(client, db, new_session):
    run = await make_run(client, new_session)
    await add_events(db, run["id"], "run.stage", terminal="completed")
    first = events((await client.get(f"/api/v1/runs/{run['id']}/events")).text)
    after_first = events(
        (
            await client.get(f"/api/v1/runs/{run['id']}/events", params={"after": first[0]["id"]})
        ).text
    )
    assert [e["id"] for e in after_first] == [e["id"] for e in first[1:]]
    by_header = await client.get(
        f"/api/v1/runs/{run['id']}/events",
        params={"after": first[0]["id"]},
        headers={"Last-Event-ID": first[1]["id"]},
    )
    assert [e["id"] for e in events(by_header.text)] == [e["id"] for e in first[2:]]


async def test_reconnect_after_terminal_closes_immediately(client, db, new_session):
    run = await make_run(client, new_session)
    await add_events(db, run["id"], terminal="cancelled")
    all_events = events((await client.get(f"/api/v1/runs/{run['id']}/events")).text)
    r = await client.get(
        f"/api/v1/runs/{run['id']}/events", headers={"Last-Event-ID": all_events[-1]["id"]}
    )
    assert r.status_code == 200 and events(r.text) == []


async def test_invalid_or_foreign_cursor_is_409_before_streaming(client, db, new_session):
    run = await make_run(client, new_session)
    other = await make_run(client, new_session)
    async with db() as s:
        foreign = await s.scalar(select(RunEvent.id).where(RunEvent.run_id == other["id"]))
    for cursor in ("abc", "-1", str(foreign), "999999"):
        r = await client.get(f"/api/v1/runs/{run['id']}/events", params={"after": cursor})
        assert r.status_code == 409 and r.json()["code"] == "invalid_cursor", cursor
    missing = await client.get("/api/v1/runs/00000000-0000-4000-8000-000000000999/events")
    assert missing.status_code == 404


async def test_live_tail_delivers_new_events_without_waiting_for_a_heartbeat(
    app, client, db, new_session
):
    run = await make_run(client, new_session)
    stream = asyncio.create_task(client.get(f"/api/v1/runs/{run['id']}/events"))
    await asyncio.sleep(0.2)
    started = time.monotonic()
    await add_events(db, run["id"], "run.stage")
    await app.state.notifier.notify_run(run["id"])
    await add_events(db, run["id"], terminal="completed")
    await app.state.notifier.notify_run(run["id"])
    r = await asyncio.wait_for(stream, 5)
    assert time.monotonic() - started < 3  # heartbeat is 15 s; the notifier woke the tail
    assert [e["event"] for e in events(r.text)] == ["run.queued", "run.stage", "run.completed"]


async def test_idle_stream_sends_heartbeat_comments(app, client, db, new_session):
    cat = app.state.catalog
    fast = cat.defaults.model_copy(
        update={
            "timeouts_seconds": cat.defaults.timeouts_seconds.model_copy(
                update={"sse_heartbeat": 0.1}
            )
        }
    )
    app.state.catalog = dataclasses.replace(cat, defaults=fast)
    run = await make_run(client, new_session)
    stream = asyncio.create_task(client.get(f"/api/v1/runs/{run['id']}/events"))
    await asyncio.sleep(0.45)
    await add_events(db, run["id"], terminal="completed")
    await app.state.notifier.notify_run(run["id"])
    r = await asyncio.wait_for(stream, 5)
    comments = [c for f in parse_sse(r.text) for c in f.get("comments", [])]
    assert len(comments) >= 2 and all(c == ": heartbeat" for c in comments)


async def test_replay_and_reconnect_never_create_provider_work(client, db, new_session):
    run = await make_run(client, new_session)
    await add_events(db, run["id"], terminal="completed")
    for _ in range(3):
        await client.get(f"/api/v1/runs/{run['id']}/events")
    async with db() as s:
        assert await s.scalar(select(func.count()).select_from(ProviderCall)) == 0
