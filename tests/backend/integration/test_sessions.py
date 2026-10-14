"""Session create/read/delete, idempotency, readiness and database-unavailable behavior."""

import asyncio
from uuid import uuid4

from conftest import make_test_env
from contract_support import contract_client
from sqlalchemy import func, select

from app.main import create_app
from app.persistence.models import IdeaRevision, Message, Run, Session
from app.services.sessions import auto_title

IDEA = "I want to build an interview-practice app for college students."


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


async def count(db, model) -> int:
    async with db() as s:
        return await s.scalar(select(func.count()).select_from(model))


async def test_create_applies_configured_defaults(client, db):
    r = await client.post("/api/v1/sessions", json={"idea": IDEA}, headers=key())
    assert r.status_code == 201
    s = r.json()
    assert s["mode"] == "jev_guided"
    assert s["selected_persona_ids"] == ["mentor", "skeptic", "explorer"]
    assert s["settings"] == {"research_policy": "auto", "auto_contributions": 3}
    assert s["brief"] == {"idea": IDEA, "goal": None, "constraints": [], "revision": 1}
    assert (s["version"], s["organization_version"]) == (1, 1)
    assert s["active_run_id"] is None and s["folder_id"] is None and s["is_pinned"] is False
    assert s["title"] == auto_title(IDEA)
    assert await count(db, IdeaRevision) == 1


async def test_same_key_and_body_returns_the_same_session_once(client, db):
    h = key()
    a = await client.post("/api/v1/sessions", json={"idea": IDEA}, headers=h)
    b = await client.post("/api/v1/sessions", json={"idea": IDEA}, headers=h)
    assert a.status_code == b.status_code == 201 and a.json() == b.json()
    assert await count(db, Session) == 1


async def test_same_key_with_a_different_body_conflicts(client):
    h = key()
    await client.post("/api/v1/sessions", json={"idea": IDEA}, headers=h)
    r = await client.post("/api/v1/sessions", json={"idea": "another idea"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "idempotency_conflict"


async def test_concurrent_identical_creates_make_one_session(client, db):
    h = key()
    a, b = await asyncio.gather(
        client.post("/api/v1/sessions", json={"idea": IDEA}, headers=h),
        client.post("/api/v1/sessions", json={"idea": IDEA}, headers=h),
    )
    assert a.status_code == b.status_code == 201 and a.json()["id"] == b.json()["id"]
    assert await count(db, Session) == 1


async def test_invalid_bodies_are_rejected(client, db):
    bad = [
        {"idea": "   "},
        {"idea": IDEA, "selected_persona_ids": ["mentor", "mentor"]},
        {"idea": IDEA, "mode": None},
        {"idea": IDEA, "title": "x" * 121},
        {"idea": IDEA, "selected_persona_ids": []},
    ]
    for body in bad:
        r = await client.post("/api/v1/sessions", json=body, headers=key())
        assert r.status_code == 422, body
    assert (await client.post("/api/v1/sessions", json={"idea": IDEA})).status_code == 422
    assert await count(db, Session) == 0


async def test_custom_title_and_mode_are_kept(client):
    body = {"idea": IDEA, "title": "  Interview practice  ", "mode": "standard"}
    s = (await client.post("/api/v1/sessions", json=body, headers=key())).json()
    assert s["title"] == "Interview practice" and s["mode"] == "standard"


async def test_missing_folder_fails_visibly(client, db):
    body = {"idea": IDEA, "folder_id": str(uuid4())}
    r = await client.post("/api/v1/sessions", json=body, headers=key())
    assert r.status_code == 409 and r.json()["code"] == "folder_missing"
    assert await count(db, Session) == 0


async def test_live_mode_without_openai_key_refuses_to_create(db):
    app = create_app(env=make_test_env(APP_PROVIDER_MODE="live"))
    async with contract_client(app) as c:
        r = await c.post("/api/v1/sessions", json={"idea": IDEA}, headers=key())
    await app.state.engine.dispose()
    assert r.status_code == 503 and r.json()["code"] == "provider_not_ready"
    assert await count(db, Session) == 0


async def test_get_and_missing(client):
    s = (await client.post("/api/v1/sessions", json={"idea": IDEA}, headers=key())).json()
    assert (await client.get(f"/api/v1/sessions/{s['id']}")).json() == s
    r = await client.get(f"/api/v1/sessions/{uuid4()}")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


async def test_delete_removes_owned_records(client, db):
    s = (await client.post("/api/v1/sessions", json={"idea": IDEA}, headers=key())).json()
    async with db() as sess:
        sess.add(Message(session_id=s["id"], sequence=1, role="user", text=IDEA))
        await sess.commit()
    assert (await client.delete(f"/api/v1/sessions/{s['id']}")).status_code == 204
    assert await count(db, Message) == 0 and await count(db, IdeaRevision) == 0
    assert (await client.delete(f"/api/v1/sessions/{s['id']}")).status_code == 404


async def test_delete_refuses_active_session(client, db):
    s = (await client.post("/api/v1/sessions", json={"idea": IDEA}, headers=key())).json()
    async with db() as sess:
        sess.add(
            Run(
                session_id=s["id"],
                status="running",
                mode="jev_guided",
                audience="auto",
                control={},
                snapshot={},
                slots=[],
                requested_count=1,
                session_version=1,
            )
        )
        await sess.commit()
    r = await client.delete(f"/api/v1/sessions/{s['id']}")
    assert r.status_code == 409 and r.json()["code"] == "run_active"
    got = (await client.get(f"/api/v1/sessions/{s['id']}")).json()
    assert got["active_run_id"] is not None


async def test_database_down_returns_503_with_error_body():
    app = create_app(env=make_test_env(DATABASE_URL="postgresql+asyncpg://x:y@127.0.0.1:1/none"))
    async with contract_client(app) as c:
        r = await c.post("/api/v1/sessions", json={"idea": IDEA}, headers=key())
    await app.state.engine.dispose()
    assert r.status_code == 503 and r.json()["code"] == "database_unavailable"
    assert r.json()["retryable"] is True


def test_auto_title_uses_first_line_at_a_word_boundary():
    assert auto_title("Short idea\nmore detail") == "Short idea"
    long = "A neighborhood tool-sharing service that lets residents borrow drills and ladders"
    t = auto_title(long)
    assert len(t) <= 61 and t.endswith("…") and not t[:-1].endswith(" ")
    assert long.startswith(t[:-1])
