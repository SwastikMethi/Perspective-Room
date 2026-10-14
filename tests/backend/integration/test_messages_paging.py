"""Transcript paging: latest window, older/newer cursors, anchored windows. Never runs a model."""

from uuid import uuid4

from app.persistence.models import Message


async def seed(db, session_id, n):
    ids = []
    async with db() as s:
        for i in range(1, n + 1):
            m = Message(session_id=session_id, sequence=i, role="user", text=f"message {i}")
            s.add(m)
            await s.flush()
            ids.append(str(m.id))
        await s.commit()
    return ids


def seqs(body):
    return [m["sequence"] for m in body["items"]]


async def test_latest_window_and_older_pages(client, db, new_session):
    s = await new_session()
    await seed(db, s["id"], 7)
    url = f"/api/v1/sessions/{s['id']}/messages"
    first = (await client.get(url, params={"limit": 3})).json()
    assert seqs(first) == [5, 6, 7] and first["next_cursor"] is None
    older = (await client.get(url, params={"limit": 3, "cursor": first["previous_cursor"]})).json()
    assert seqs(older) == [2, 3, 4]
    oldest = (await client.get(url, params={"limit": 3, "cursor": older["previous_cursor"]})).json()
    assert seqs(oldest) == [1] and oldest["previous_cursor"] is None
    newer = (await client.get(url, params={"limit": 3, "cursor": oldest["next_cursor"]})).json()
    assert seqs(newer) == [2, 3, 4]


async def test_anchor_windows_fill_from_the_other_side_at_edges(client, db, new_session):
    s = await new_session()
    ids = await seed(db, s["id"], 7)
    url = f"/api/v1/sessions/{s['id']}/messages"
    mid = (await client.get(url, params={"limit": 3, "around_message_id": ids[3]})).json()
    assert seqs(mid) == [3, 4, 5]
    start = (await client.get(url, params={"limit": 3, "around_message_id": ids[0]})).json()
    assert seqs(start) == [1, 2, 3] and start["previous_cursor"] is None
    end = (await client.get(url, params={"limit": 4, "around_message_id": ids[6]})).json()
    assert seqs(end) == [4, 5, 6, 7] and end["next_cursor"] is None


async def test_invalid_paging_requests(client, db, new_session):
    s = await new_session()
    other = await new_session()
    ids = await seed(db, other["id"], 2)
    url = f"/api/v1/sessions/{s['id']}/messages"
    both = await client.get(url, params={"cursor": "x", "around_message_id": ids[0]})
    assert both.status_code == 400 and both.json()["code"] == "bad_request"
    assert (await client.get(url, params={"cursor": "not-a-cursor"})).status_code == 400
    foreign = await client.get(url, params={"around_message_id": ids[0]})
    assert foreign.status_code == 404
    assert (await client.get(f"/api/v1/sessions/{uuid4()}/messages")).status_code == 404
    empty = (await client.get(url)).json()
    assert empty == {"items": [], "next_cursor": None, "previous_cursor": None}


async def test_well_scoped_but_malformed_cursor_is_400(client, new_session):
    import base64
    import json

    s = await new_session()
    raw = json.dumps({"scope": s["id"], "d": "sideways"}).encode()
    bad = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    r = await client.get(f"/api/v1/sessions/{s['id']}/messages", params={"cursor": bad})
    assert r.status_code == 400 and r.json()["code"] == "bad_request"
