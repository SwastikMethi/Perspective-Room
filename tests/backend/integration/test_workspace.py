"""Workspace API (doc 08 §Workspace endpoints, doc 14; T27, T28, T29, T31, T35): folders,
organization edits, history listing and literal search. No LLM calls anywhere."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from conftest import idem, turn_body
from sqlalchemy import select, update

from app.persistence.models import EvaluationBatch, Message, Run
from app.persistence.models import Session as SessionRow


async def folder(client, name, key=None):
    return await client.post("/api/v1/folders", json={"name": name}, headers=key or idem())


async def organize(client, sid, **body):
    if "expected_organization_version" not in body:
        current = (await client.get(f"/api/v1/sessions/{sid}")).json()
        body["expected_organization_version"] = current["organization_version"]
    return await client.patch(f"/api/v1/sessions/{sid}/organization", json=body)


async def listing(client, **params):
    r = await client.get("/api/v1/sessions", params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def set_row(db, sid, **values):
    async with db() as s:
        await s.execute(update(SessionRow).where(SessionRow.id == sid).values(**values))
        await s.commit()


async def add_message(db, sid, seq, text, role="user"):
    async with db() as s:
        s.add(Message(session_id=sid, sequence=seq, role=role, text=text, search_text=text))
        await s.execute(update(SessionRow).where(SessionRow.id == sid).values(last_sequence=seq))
        await s.commit()


async def lab_session(db, sid):
    async with db() as s:
        batch = EvaluationBatch(
            status="running", config={}, snapshot={}, seed=1, provider_mode="demo", planned=1
        )
        s.add(batch)
        await s.flush()
        await s.execute(
            update(SessionRow).where(SessionRow.id == sid).values(evaluation_batch_id=batch.id)
        )
        await s.commit()


# ---------- folders ----------


async def test_folder_create_is_idempotent_and_names_are_unique_ignoring_case(client):
    key = idem()
    a = await folder(client, "  Work  ", key)
    b = await folder(client, "  Work  ", key)
    assert a.status_code == 201 and a.json() == b.json()
    assert a.json()["name"] == "Work" and a.json()["chat_count"] == 0
    dup = await folder(client, "work")
    assert dup.status_code == 409 and dup.json()["code"] == "folder_name_taken"
    assert (await folder(client, "   ")).status_code == 422
    assert (await folder(client, "x" * 81)).status_code == 422
    other = await folder(client, "Other", key)  # same key, different body
    assert other.status_code == 409 and other.json()["code"] == "idempotency_conflict"


async def test_folder_rename_checks_version_and_uniqueness(client):
    f = (await folder(client, "Ideas")).json()
    await folder(client, "Taken")
    url = f"/api/v1/folders/{f['id']}"
    r = await client.patch(url, json={"expected_version": 1, "name": "Side projects"})
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["id"] == f["id"]
    stale = await client.patch(url, json={"expected_version": 1, "name": "Again"})
    assert stale.status_code == 409 and stale.json()["details"]["current_version"] == 2
    taken = await client.patch(url, json={"expected_version": 2, "name": "TAKEN"})
    assert taken.status_code == 409 and taken.json()["code"] == "folder_name_taken"
    case = await client.patch(url, json={"expected_version": 2, "name": "SIDE projects"})
    assert case.status_code == 200 and case.json()["name"] == "SIDE projects"
    assert (await client.get(url)).json()["name"] == "SIDE projects"
    assert (await client.get(f"/api/v1/folders/{uuid4()}")).status_code == 404


async def test_deleting_a_folder_keeps_and_unfiles_active_and_archived_chats(
    client, db, new_session
):
    f = (await folder(client, "Garden")).json()
    a = await new_session(folder_id=f["id"])
    b = await new_session(folder_id=f["id"])
    assert (await organize(client, b["id"], is_archived=True)).status_code == 200
    got = (await client.get(f"/api/v1/folders/{f['id']}")).json()
    assert (got["chat_count"], got["archived_chat_count"]) == (1, 1)
    before = {s["id"]: s for s in [await _get(client, a["id"]), await _get(client, b["id"])]}
    stale = await client.delete(f"/api/v1/folders/{f['id']}", params={"expected_version": 9})
    assert stale.status_code == 409
    r = await client.delete(f"/api/v1/folders/{f['id']}", params={"expected_version": 1})
    assert r.status_code == 204
    for sid, old in before.items():
        now = await _get(client, sid)
        assert now["folder_id"] is None
        assert now["organization_version"] == old["organization_version"] + 1
        assert now["version"] == old["version"]
        assert now["last_activity_at"] == old["last_activity_at"]
    assert (await client.get(f"/api/v1/folders/{f['id']}")).status_code == 404


async def _get(client, sid):
    return (await client.get(f"/api/v1/sessions/{sid}")).json()


async def test_folder_counts_exclude_lab_chats_and_list_is_sorted_by_name(client, db, new_session):
    f = (await folder(client, "beta")).json()
    await folder(client, "Alpha")
    await folder(client, "gamma")
    lab = await new_session(folder_id=f["id"])
    await lab_session(db, lab["id"])
    await new_session(folder_id=f["id"])
    page = (await client.get("/api/v1/folders", params={"limit": 2})).json()
    assert [x["name"] for x in page["items"]] == ["Alpha", "beta"] and page["next_cursor"]
    assert page["items"][1]["chat_count"] == 1
    rest = (await client.get("/api/v1/folders", params={"cursor": page["next_cursor"]})).json()
    assert [x["name"] for x in rest["items"]] == ["gamma"] and rest["next_cursor"] is None


async def test_concurrent_folder_delete_and_move_never_orphan_a_chat(client, db, new_session):
    s = await new_session()
    for i in range(6):
        f = (await folder(client, f"Race {i}")).json()
        org = (await _get(client, s["id"]))["organization_version"]
        move, gone = await asyncio.gather(
            client.patch(
                f"/api/v1/sessions/{s['id']}/organization",
                json={"expected_organization_version": org, "folder_id": f["id"]},
            ),
            client.delete(f"/api/v1/folders/{f['id']}", params={"expected_version": 1}),
        )
        assert gone.status_code == 204 and move.status_code in (200, 409)
        assert (await _get(client, s["id"]))["folder_id"] is None


# ---------- organization ----------


async def test_organization_edits_during_a_run_leave_content_and_snapshot_alone(
    client, db, new_session
):
    s = await new_session()
    run = (
        await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    ).json()
    async with db() as sess:
        snapshot = (await sess.get(Run, run["id"])).snapshot
    before = await _get(client, s["id"])
    f = (await folder(client, "Busy")).json()
    for change in ({"title": "  Renamed  "}, {"is_pinned": True}, {"folder_id": f["id"]}):
        r = await organize(client, s["id"], **change)
        assert r.status_code == 200, r.text
    after = r.json()
    assert after["title"] == "Renamed" and after["is_pinned"] and after["folder_id"] == f["id"]
    assert after["version"] == before["version"]
    assert after["organization_version"] == before["organization_version"] + 3
    assert after["last_activity_at"] == before["last_activity_at"]
    archive = await organize(client, s["id"], is_archived=True)
    assert archive.status_code == 409 and archive.json()["code"] == "run_active"
    async with db() as sess:
        row = await sess.get(SessionRow, s["id"])
        assert (await sess.get(Run, run["id"])).snapshot == snapshot
    assert row.title_is_custom is True


async def test_archived_chats_allow_only_rename_and_restore(client, new_session):
    s = await new_session()
    assert (await organize(client, s["id"], is_archived=True)).status_code == 200
    for change in ({"is_pinned": True}, {"folder_id": None}):
        r = await organize(client, s["id"], **change)
        assert r.status_code == 409 and r.json()["code"] == "session_archived"
    mixed = await organize(client, s["id"], is_archived=False, title="Back")
    assert mixed.status_code == 422
    assert (await organize(client, s["id"], title="Still readable")).status_code == 200
    restored = await organize(client, s["id"], is_archived=False)
    assert restored.status_code == 200 and restored.json()["is_archived"] is False


async def test_organization_requires_a_change_a_current_version_and_a_user_chat(
    client, db, new_session
):
    s = await new_session()
    assert (await organize(client, s["id"])).status_code == 422
    assert (await organize(client, s["id"], title=None)).status_code == 422
    assert (await organize(client, s["id"], is_pinned=None)).status_code == 422
    assert (await organize(client, s["id"], title="   ")).status_code == 422
    stale = await organize(client, s["id"], expected_organization_version=7, is_pinned=True)
    assert stale.status_code == 409
    assert stale.json()["details"]["current_organization_version"] == 1
    gone = await organize(client, s["id"], folder_id=str(uuid4()))
    assert gone.status_code == 409 and gone.json()["code"] == "folder_missing"
    await lab_session(db, s["id"])
    lab = await organize(client, s["id"], is_pinned=True)
    assert lab.status_code == 409 and lab.json()["code"] == "evaluation_managed"
    assert (
        await organize(client, uuid4(), expected_organization_version=1, is_pinned=True)
    ).status_code == 404


# ---------- listing and search ----------


async def test_history_lists_filter_and_order_by_last_activity(client, db, new_session):
    f = (await folder(client, "Home")).json()
    base = datetime(2026, 10, 1, tzinfo=UTC)
    rows = {}
    for i, name in enumerate(["old", "mid", "new"]):
        rows[name] = await new_session(**({"folder_id": f["id"]} if name == "mid" else {}))
        await set_row(db, rows[name]["id"], last_activity_at=base + timedelta(days=i))
    lab = await new_session()
    await lab_session(db, lab["id"])
    await organize(client, rows["old"]["id"], is_pinned=True)
    archived = await new_session()
    await organize(client, archived["id"], is_archived=True)

    def ids(page):
        return [x["id"] for x in page["items"]]

    everything = await listing(client)
    assert ids(everything) == [rows["new"]["id"], rows["mid"]["id"], rows["old"]["id"]]
    assert all(x["match"] is None for x in everything["items"])
    assert ids(await listing(client, pinned="true")) == [rows["old"]["id"]]
    assert ids(await listing(client, pinned="false")) == [rows["new"]["id"], rows["mid"]["id"]]
    assert ids(await listing(client, folder_id=f["id"])) == [rows["mid"]["id"]]
    assert rows["mid"]["id"] not in ids(await listing(client, unfiled="true"))
    assert ids(await listing(client, archive="archived")) == [archived["id"]]
    assert len(ids(await listing(client, archive="all"))) == 4
    conflict = await client.get(
        "/api/v1/sessions", params={"folder_id": f["id"], "unfiled": "true"}
    )
    assert conflict.status_code == 400
    missing = await client.get("/api/v1/sessions", params={"folder_id": str(uuid4())})
    assert missing.status_code == 404


async def test_search_prefers_titles_then_the_earliest_matching_message(client, db, new_session):
    titled = await new_session(title="Budget planning for a garden")
    talky = await new_session(title="Something else")
    await add_message(db, talky["id"], 1, "Opening without the word")
    await add_message(db, talky["id"], 2, "We need a BUDGET under $40 for seeds.", role="moderator")
    await add_message(db, talky["id"], 3, "Another budget note later")
    nothing = await new_session(title="Unrelated")
    page = await listing(client, q="  budget ")
    by_id = {x["id"]: x["match"] for x in page["items"]}
    assert set(by_id) == {titled["id"], talky["id"]} and nothing["id"] not in by_id
    assert by_id[titled["id"]] == {
        "kind": "title",
        "snippet": "Budget planning for a garden",
        "message_id": None,
        "message_sequence": None,
    }
    hit = by_id[talky["id"]]
    assert hit["kind"] == "message" and hit["message_sequence"] == 2
    assert hit["snippet"] in "We need a BUDGET under $40 for seeds."
    assert (await listing(client, q="   "))["items"][0]["match"] is None  # empty = normal list


async def test_search_treats_wildcards_literally_and_bounds_snippets(client, db, new_session):
    s = await new_session(title="Literal")
    other = await new_session(title="Other")
    long_text = "x" * 500 + " 100%_done " + "y" * 500
    await add_message(db, s["id"], 1, long_text)
    await add_message(db, other["id"], 1, "100 percent done")
    page = await listing(client, q="%_d")
    assert [x["id"] for x in page["items"]] == [s["id"]]
    snippet = page["items"][0]["match"]["snippet"]
    assert len(snippet) <= 240 and "100%_done" in snippet and snippet in long_text
    assert (await listing(client, q="\\"))["items"] == []
    too_long = await client.get("/api/v1/sessions", params={"q": "q" * 201})
    assert too_long.status_code == 422


async def test_search_pages_are_stable_and_cursors_are_bound_to_the_query(client, db, new_session):
    made = []
    base = datetime(2026, 10, 1, tzinfo=UTC)
    for i in range(5):
        s = await new_session(title=f"Compost idea {i}")
        await set_row(db, s["id"], last_activity_at=base + timedelta(hours=i))
        made.append(s["id"])
    seen, cursor = [], None
    while True:
        params = {"q": "compost", "limit": 2, **({"cursor": cursor} if cursor else {})}
        page = await listing(client, **params)
        seen += [x["id"] for x in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
        bad = await client.get("/api/v1/sessions", params={"q": "other", "cursor": cursor})
        assert bad.status_code == 400
    assert seen == list(reversed(made))


async def test_active_run_is_reported_on_summaries(client, db, new_session):
    s = await new_session()
    run = (
        await client.post(f"/api/v1/sessions/{s['id']}/turns", json=turn_body(1), headers=idem())
    ).json()
    [row] = (await listing(client))["items"]
    assert row["active_run_id"] == run["id"]
    async with db() as sess:
        assert (await sess.scalar(select(Run.status).where(Run.id == run["id"]))) == "queued"


async def test_move_into_own_folder_racing_its_deletion_never_deadlocks(client, db, new_session):
    for i in range(12):
        f = (await folder(client, f"Own {i}")).json()
        s = await new_session(folder_id=f["id"])
        org = (await _get(client, s["id"]))["organization_version"]
        move, gone = await asyncio.gather(
            client.patch(
                f"/api/v1/sessions/{s['id']}/organization",
                json={"expected_organization_version": org, "folder_id": f["id"]},
            ),
            client.delete(f"/api/v1/folders/{f['id']}", params={"expected_version": 1}),
        )
        assert move.status_code in (200, 409), move.text
        assert gone.status_code == 204, gone.text
