"""Context edits (brief revisions, T16), saved ideas, feedback and sources API."""

from datetime import UTC, datetime
from uuid import uuid4

from conftest import idem, turn_body
from sqlalchemy import select, update
from test_orchestrator import ScriptedJev, recording, use, wait_done

from app.persistence.models import IdeaRevision, Message, ResearchPack, Run, Source
from app.persistence.models import Session as SessionRow

CONTRIB = {
    "headline": "Start small",
    "blocks": [{"kind": "suggestion", "text": "Try one.", "source_ids": []}],
    "referenced_message_ids": [],
    "new_angle": "x",
    "next_question": None,
}


async def persona_message(db, session_id, seq=1):
    async with db() as s:
        m = Message(
            session_id=session_id,
            sequence=seq,
            role="persona",
            persona_id="mentor",
            contribution=CONTRIB,
            search_text="Start small",
        )
        s.add(m)
        await s.execute(
            update(SessionRow).where(SessionRow.id == session_id).values(last_sequence=seq)
        )
        await s.commit()
        return m


async def patch(client, sid, **body):
    return await client.patch(f"/api/v1/sessions/{sid}", json=body)


async def test_brief_edit_creates_an_immutable_revision(client, db, new_session):
    s = await new_session()
    r = await patch(
        client,
        s["id"],
        expected_version=1,
        brief={
            "idea": "Tool sharing",
            "goal": "Pilot in one building",
            "constraints": ["No smartphones required", "  "],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 2 and body["brief"]["revision"] == 2
    assert body["brief"]["constraints"] == ["No smartphones required"]
    async with db() as sess:
        revs = (
            await sess.scalars(
                select(IdeaRevision)
                .where(IdeaRevision.session_id == s["id"])
                .order_by(IdeaRevision.revision)
            )
        ).all()
    assert [(r.revision, r.idea) for r in revs] == [(1, s["brief"]["idea"]), (2, "Tool sharing")]


async def test_next_run_uses_the_new_brief_and_flags_older_memory(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    s = await new_session()
    first = await client.post(
        f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem()
    )
    await wait_done(db, first.json()["id"])
    version = (await client.get(f"/api/v1/sessions/{s['id']}")).json()["version"]
    r = await patch(
        client,
        s["id"],
        expected_version=version,
        brief={"idea": "Revised idea", "goal": None, "constraints": ["Budget 0"]},
    )
    assert r.status_code == 200
    rec = recording(running_app)
    run = await client.post(
        f"/api/v1/sessions/{s['id']}/turns", json=turn_body(r.json()["version"]), headers=idem()
    )
    await wait_done(db, run.json()["id"])
    async with db() as sess:
        snap = (await sess.get(Run, run.json()["id"])).snapshot
    assert snap["brief"]["revision"] == 2 and snap["brief"]["constraints"] == ["Budget 0"]
    draft = next(p for purpose, p in rec.payloads if purpose == "draft")
    assert draft["brief"]["constraints"] == ["Budget 0"]
    assert draft["memory"]["superseded_by_brief_revision"] is True


async def test_settings_and_selection_edits(client, new_session):
    s = await new_session()
    r = await patch(
        client,
        s["id"],
        expected_version=1,
        selected_persona_ids=["engineer", "health"],
        settings={"research_policy": "off", "auto_contributions": 2},
    )
    assert r.status_code == 200
    assert r.json()["selected_persona_ids"] == ["engineer", "health"]
    assert r.json()["settings"] == {"research_policy": "off", "auto_contributions": 2}


async def test_invalid_patches_are_rejected(client, db, new_session):
    s = await new_session()
    sid = s["id"]
    assert (await patch(client, sid, expected_version=1)).status_code == 422  # nothing to change
    assert (await patch(client, sid, expected_version=1, settings=None)).status_code == 422
    dup = await patch(client, sid, expected_version=1, selected_persona_ids=["mentor", "mentor"])
    assert dup.status_code == 422
    stale = await patch(client, sid, expected_version=9, selected_persona_ids=["mentor"])
    assert stale.status_code == 409 and stale.json()["details"]["current_version"] == 1
    blank = await patch(
        client, sid, expected_version=1, brief={"idea": "  ", "goal": None, "constraints": []}
    )
    assert blank.status_code == 422


async def test_context_edits_are_blocked_during_a_run_and_while_archived(client, db, new_session):
    s = await new_session()
    await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    r = await patch(client, s["id"], expected_version=2, selected_persona_ids=["mentor"])
    assert r.status_code == 409 and r.json()["code"] == "run_active"
    other = await new_session()
    async with db() as sess:
        await sess.execute(
            update(SessionRow).where(SessionRow.id == other["id"]).values(is_archived=True)
        )
        await sess.commit()
    r = await patch(client, other["id"], expected_version=1, selected_persona_ids=["mentor"])
    assert r.status_code == 409 and r.json()["code"] == "session_archived"


async def test_saved_ideas_lifecycle(client, db, new_session):
    s = await new_session()
    m = await persona_message(db, s["id"])
    url = f"/api/v1/sessions/{s['id']}/idea-cards"
    h = idem()
    body = {
        "message_id": str(m.id),
        "title": "  Safe first step ",
        "note": "",
        "status": "exploring",
    }
    a = await client.post(url, json=body, headers=h)
    b = await client.post(url, json=body, headers=h)
    assert a.status_code == 201 and a.json() == b.json()
    card = a.json()
    assert card["title"] == "Safe first step" and card["version"] == 1
    second = (await client.post(url, json={**body, "title": "Second"}, headers=idem())).json()
    listed = (await client.get(url)).json()
    assert [c["id"] for c in listed["items"]] == [card["id"], second["id"]]
    p = await client.patch(
        f"/api/v1/idea-cards/{card['id']}",
        json={"expected_version": 1, "note": "Try with 5 people", "status": "selected"},
    )
    assert p.status_code == 200 and p.json()["version"] == 2 and p.json()["status"] == "selected"
    stale = await client.patch(
        f"/api/v1/idea-cards/{card['id']}", json={"expected_version": 1, "note": "x"}
    )
    assert stale.status_code == 409
    assert (await client.delete(f"/api/v1/idea-cards/{card['id']}")).status_code == 204
    assert (
        await client.patch(f"/api/v1/idea-cards/{card['id']}", json={"expected_version": 2})
    ).status_code == 404


async def test_saved_idea_must_come_from_a_reply_in_the_same_chat(client, db, new_session):
    s = await new_session()
    other = await new_session()
    foreign = await persona_message(db, other["id"])
    r = await client.post(
        f"/api/v1/sessions/{s['id']}/idea-cards",
        json={"message_id": str(foreign.id), "title": "x", "note": "", "status": "exploring"},
        headers=idem(),
    )
    assert r.status_code == 422


async def test_ideas_and_feedback_during_a_run_do_not_touch_the_context(client, db, new_session):
    s = await new_session()
    m = await persona_message(db, s["id"])
    run = (
        await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    ).json()
    before = (await client.get(f"/api/v1/sessions/{s['id']}")).json()["version"]
    card = await client.post(
        f"/api/v1/sessions/{s['id']}/idea-cards",
        json={"message_id": str(m.id), "title": "Idea", "note": "", "status": "exploring"},
        headers=idem(),
    )
    fb = await client.post(
        f"/api/v1/messages/{m.id}/feedback", json={"labels": ["useful"], "note": ""}
    )
    assert card.status_code == 201 and fb.status_code == 200
    assert (await client.get(f"/api/v1/sessions/{s['id']}")).json()["version"] == before
    async with db() as sess:
        assert (await sess.get(Run, run["id"])).snapshot["idea_cards"] == []


async def test_feedback_replaces_the_previous_answer(client, db, new_session):
    s = await new_session()
    m = await persona_message(db, s["id"])
    url = f"/api/v1/messages/{m.id}/feedback"
    a = (await client.post(url, json={"labels": ["useful"], "note": "good"})).json()
    b = (
        await client.post(url, json={"labels": ["repetitive", "off_character"], "note": ""})
    ).json()
    assert a["id"] == b["id"] and b["labels"] == ["repetitive", "off_character"]
    dup = await client.post(url, json={"labels": ["useful", "useful"], "note": ""})
    assert dup.status_code == 422
    assert (
        await client.post(f"/api/v1/messages/{uuid4()}/feedback", json={"labels": [], "note": ""})
    ).status_code == 404


async def test_sources_list_and_get(client, db, new_session):
    s = await new_session()
    async with db() as sess:
        pack = ResearchPack(session_id=s["id"], query="q", status="available")
        sess.add(pack)
        await sess.flush()
        for i in range(3):
            sess.add(
                Source(
                    session_id=s["id"],
                    research_pack_id=pack.id,
                    url=f"https://e.org/{i}",
                    title=f"T{i}",
                    domain="e.org",
                    retrieved_at=datetime(2026, 10, 15, 0, 0, i, tzinfo=UTC),
                    provider_response_id="r",
                    research_excerpt="x",
                )
            )
        await sess.commit()
    page = (await client.get(f"/api/v1/sessions/{s['id']}/sources", params={"limit": 2})).json()
    assert [x["title"] for x in page["items"]] == ["T0", "T1"] and page["next_cursor"]
    rest = (
        await client.get(
            f"/api/v1/sessions/{s['id']}/sources", params={"cursor": page["next_cursor"]}
        )
    ).json()
    assert [x["title"] for x in rest["items"]] == ["T2"] and rest["next_cursor"] is None
    one = (await client.get(f"/api/v1/sources/{page['items'][0]['id']}")).json()
    assert one["url"] == "https://e.org/0" and one["is_fixture"] is False
    assert (await client.get(f"/api/v1/sources/{uuid4()}")).status_code == 404


async def test_lab_chats_refuse_saved_ideas_and_feedback(client, db, new_session):
    from app.persistence.models import EvaluationBatch

    s = await new_session()
    m = await persona_message(db, s["id"])
    async with db() as sess:
        batch = EvaluationBatch(
            status="running", config={}, snapshot={}, seed=1, provider_mode="demo", planned=1
        )
        sess.add(batch)
        await sess.flush()
        await sess.execute(
            update(SessionRow).where(SessionRow.id == s["id"]).values(evaluation_batch_id=batch.id)
        )
        await sess.commit()
    card = await client.post(
        f"/api/v1/sessions/{s['id']}/idea-cards",
        json={"message_id": str(m.id), "title": "x", "note": "", "status": "exploring"},
        headers=idem(),
    )
    fb = await client.post(f"/api/v1/messages/{m.id}/feedback", json={"labels": [], "note": ""})
    assert card.status_code == 409 and card.json()["code"] == "evaluation_managed"
    assert fb.status_code == 409 and fb.json()["code"] == "evaluation_managed"


async def test_feedback_is_for_replies_not_your_own_messages(client, db, new_session):
    s = await new_session()
    async with db() as sess:
        mine = Message(session_id=s["id"], sequence=1, role="user", text="Mine", search_text="Mine")
        sess.add(mine)
        await sess.commit()
    r = await client.post(f"/api/v1/messages/{mine.id}/feedback", json={"labels": [], "note": ""})
    assert r.status_code == 422
