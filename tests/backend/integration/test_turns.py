"""Turn submission (T07, T08), cross-field control rules, context ceiling, run reads."""

import asyncio
import dataclasses
from uuid import uuid4

from conftest import idem, make_test_env, turn_body
from contract_support import contract_client
from sqlalchemy import func, select, update

from app.catalog import load_catalog
from app.main import create_app
from app.persistence.models import IdeaCard, Message, ProviderCall, Run, RunEvent, Session


async def count(db, model, *where) -> int:
    async with db() as s:
        return await s.scalar(select(func.count()).select_from(model).where(*where))


async def test_submit_persists_message_run_and_queued_event(client, db, new_session):
    s = await new_session()
    r = await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    assert r.status_code == 202
    run = r.json()
    assert (run["status"], run["stage"], run["published_count"]) == ("queued", "queued", 0)
    assert run["requested_count"] == 3 and run["session_version"] == 2
    session = (await client.get(f"/api/v1/sessions/{s['id']}")).json()
    assert session["version"] == 2 and session["active_run_id"] == run["id"]
    async with db() as sess:
        msg = await sess.scalar(select(Message).where(Message.session_id == s["id"]))
        ev = await sess.scalar(select(RunEvent).where(RunEvent.run_id == run["id"]))
        row = await sess.get(Run, run["id"])
    assert (msg.role, msg.sequence, msg.text, msg.run_id) == (
        "user",
        1,
        "Help me explore it.",
        row.id,
    )
    assert msg.turn_control["audience"] == "auto" and msg.turn_snapshot["mode"] == "jev_guided"
    assert ev.type == "run.queued" and ev.data["audience"] == "auto"
    assert row.snapshot["selected"] == ["mentor", "skeptic", "explorer"]
    assert set(row.snapshot["profiles"]) == {"mentor", "skeptic", "explorer"}
    assert row.snapshot["brief"]["revision"] == 1 and row.snapshot["templates"]["persona"]


async def test_duplicate_submission_creates_one_run_and_one_message(client, db, new_session):
    s = await new_session()
    h = idem()
    a = await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=h)
    b = await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=h)
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert await count(db, Run) == 1 and await count(db, Message) == 1
    c = await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1, "x"), headers=h)
    assert c.status_code == 409 and c.json()["code"] == "idempotency_conflict"


async def test_two_concurrent_turns_accept_exactly_one(client, db, new_session):
    s = await new_session()
    url = f"/api/v1/sessions/{s['id']}/turns"
    a, b = await asyncio.gather(
        client.post(url, json=turn_body(1, "first"), headers=idem()),
        client.post(url, json=turn_body(1, "second"), headers=idem()),
    )
    assert sorted([a.status_code, b.status_code]) == [202, 409]
    assert await count(db, Run) == 1 and await count(db, Message) == 1


async def test_active_run_blocks_a_new_turn_even_with_fresh_version(client, new_session):
    s = await new_session()
    url = f"/api/v1/sessions/{s['id']}/turns"
    await client.post(url, json=turn_body(1), headers=idem())
    r = await client.post(url, json=turn_body(2), headers=idem())
    assert r.status_code == 409 and r.json()["code"] == "run_active"


async def test_stale_version_returns_current_version(client, new_session):
    s = await new_session()
    r = await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(7), headers=idem())
    assert r.status_code == 409 and r.json()["code"] == "version_conflict"
    assert r.json()["details"]["current_version"] == 1


async def test_archived_and_lab_sessions_refuse_turns(client, db, new_session):
    s = await new_session()
    async with db() as sess:
        await sess.execute(update(Session).where(Session.id == s["id"]).values(is_archived=True))
        await sess.commit()
    r = await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    assert r.status_code == 409 and r.json()["code"] == "session_archived"


async def test_control_cross_field_rules(client, db, new_session):
    s = await new_session()
    std = await new_session(mode="standard")
    other = await new_session()
    async with db() as sess:
        m = Message(session_id=other["id"], sequence=1, role="user", text="elsewhere")
        sess.add(m)
        await sess.flush()
        foreign_card = IdeaCard(
            session_id=other["id"], message_id=m.id, title="t", note="", status="exploring"
        )
        sess.add(foreign_card)
        await sess.commit()
    url = f"/api/v1/sessions/{s['id']}/turns"
    cases = [
        (s, turn_body(1, audience="person"), "validation_error"),
        (s, turn_body(1, audience="person", target_persona_id="engineer"), "target_not_selected"),
        (s, turn_body(1, target_persona_id="mentor"), "validation_error"),
        (s, turn_body(1, audience="summary", research_override="force"), "validation_error"),
        (s, turn_body(1, audience="summary", move_override="explore"), "validation_error"),
        (s, turn_body(1, move_override="combine"), "validation_error"),
        (s, turn_body(1, reply_to_message_id=str(m.id)), "validation_error"),
        (s, turn_body(1, idea_card_ids=[str(foreign_card.id)]), "validation_error"),
        (s, turn_body(1, message="   "), "validation_error"),
        (std, turn_body(1, audience="panel"), "validation_error"),
        (std, turn_body(1, audience="person", target_persona_id="mentor"), "validation_error"),
    ]
    for session, body, code in cases:
        url = f"/api/v1/sessions/{session['id']}/turns"
        r = await client.post(url, json=body, headers=idem())
        assert r.status_code == 422 and r.json()["code"] == code, (body["control"], r.json())
    assert await count(db, Run) == 0


async def test_panel_and_person_and_standard_request_counts(client, new_session):
    panel = await new_session(selected_persona_ids=["health", "mentor", "engineer"])
    r = await client.post(
        f"/api/v1/sessions/{panel['id']}/turns", json=turn_body(1, audience="panel"), headers=idem()
    )
    assert r.json()["requested_count"] == 3
    two = await new_session(selected_persona_ids=["mentor", "skeptic"])
    r = await client.post(f"/api/v1/sessions/{two['id']}/turns", json=turn_body(1), headers=idem())
    assert r.json()["requested_count"] == 2  # auto never exceeds the number selected (G6)
    std = await new_session(mode="standard")
    r = await client.post(f"/api/v1/sessions/{std['id']}/turns", json=turn_body(1), headers=idem())
    assert r.json()["requested_count"] == 1


async def test_required_context_over_the_ceiling_is_refused_at_submit(db):
    cat = load_catalog(make_test_env().HANDOFF_DIR)
    tiny = cat.defaults.model_copy(
        update={"limits": cat.defaults.limits.model_copy(update={"llm_input_tokens": 200})}
    )
    app = create_app(env=make_test_env(), catalog=dataclasses.replace(cat, defaults=tiny))
    async with contract_client(app) as c:
        s = (await c.post("/api/v1/sessions", json={"idea": "x"}, headers=idem())).json()
        r = await c.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    await app.state.engine.dispose()
    assert r.status_code == 422 and r.json()["code"] == "context_too_large"
    assert await count(db, Run) == 0


async def test_get_run_and_missing_run(client, new_session):
    s = await new_session()
    run = (
        await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    ).json()
    assert (await client.get(f"/api/v1/runs/{run['id']}")).json() == run
    assert (await client.get(f"/api/v1/runs/{uuid4()}")).status_code == 404


async def test_submission_makes_no_provider_calls(client, db, new_session):
    s = await new_session()
    await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    assert await count(db, ProviderCall) == 0
