"""Fork, edit-and-branch, regenerate (T17, T32, T33) and retry missing work."""

import asyncio
from uuid import uuid4

from conftest import idem, turn_body
from sqlalchemy import func, select, update
from test_orchestrator import ScriptedJev, use, wait_done

from app.persistence.models import IdeaCard, Message, ResearchPack, Run, Source
from app.persistence.models import Session as SessionRow
from app.providers.base import ProviderFailure


async def turn(client, db, sid, message="Help me explore it.", **control):
    version = (await client.get(f"/api/v1/sessions/{sid}")).json()["version"]
    r = await client.post(
        f"/api/v1/sessions/{sid}/turns", json=turn_body(version, message, **control), headers=idem()
    )
    assert r.status_code == 202, r.text
    return await wait_done(db, r.json()["id"])


async def messages(db, sid):
    async with db() as s:
        return (
            await s.scalars(
                select(Message).where(Message.session_id == sid).order_by(Message.sequence)
            )
        ).all()


async def fork(client, sid, key=None, **body):
    version = (await client.get(f"/api/v1/sessions/{sid}")).json()["version"]
    payload = {"expected_version": version, "through_message_id": None, "title": None, **body}
    return await client.post(f"/api/v1/sessions/{sid}/forks", json=payload, headers=key or idem())


async def two_rounds(running_app, client, db, new_session, **kw):
    use(running_app, ScriptedJev())
    s = await new_session(**kw)
    await turn(client, db, s["id"], "First round")
    await turn(client, db, s["id"], "Second round")
    return s


async def test_prefix_fork_copies_only_the_chosen_history(running_app, client, db, new_session):
    s = await two_rounds(running_app, client, db, new_session)
    src_msgs = await messages(db, s["id"])
    cut = src_msgs[3]  # end of round one (user + 3 replies)
    r = await fork(client, s["id"], through_message_id=str(cut.id))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["turn_template"] is None
    new = body["session"]
    assert new["origin_session_id"] == s["id"] and new["title"].endswith("(fork)")
    copied = await messages(db, new["id"])
    assert [m.sequence for m in copied] == [1, 2, 3, 4]
    assert [m.origin_message_id for m in copied] == [m.id for m in src_msgs[:4]]
    assert all(m.id not in {o.id for o in src_msgs} for m in copied)
    assert len(await messages(db, s["id"])) == len(src_msgs)  # the source is untouched
    async with db() as sess:
        row = await sess.get(SessionRow, new["id"])
    # memory never carries conclusions from after the cutoff
    later = {str(m.id) for m in src_msgs[4:]}
    for item in (row.memory or {}).get("ideas", []):
        assert not set(item["source_message_ids"]) & later
        assert set(item["source_message_ids"]) <= {str(m.id) for m in copied}


async def test_full_fork_remaps_message_and_source_references(running_app, client, db, new_session):
    use(running_app, ScriptedJev(lambda qid, o, s: "needed" if qid == "research_needed" else o[0]))
    s = await new_session()
    await turn(client, db, s["id"], "What existing research shows about mock interviews?")
    r = await fork(client, s["id"], title="Copy of research chat")
    new = r.json()["session"]
    assert new["title"] == "Copy of research chat" and new["folder_id"] == s["folder_id"]
    copied = await messages(db, new["id"])
    async with db() as sess:
        new_sources = {
            str(x.id)
            for x in (
                await sess.scalars(select(Source).where(Source.session_id == new["id"]))
            ).all()
        }
        packs = (
            await sess.scalars(select(ResearchPack).where(ResearchPack.session_id == new["id"]))
        ).all()
    cited = {
        sid
        for m in copied
        if m.contribution
        for b in m.contribution["blocks"]
        for sid in b["source_ids"]
    }
    assert cited and cited <= new_sources and packs and all(p.origin_pack_id for p in packs)
    ids = {str(m.id) for m in copied}
    for m in copied:
        if m.contribution:
            assert set(m.contribution["referenced_message_ids"]) <= ids


async def test_edit_first_message_branches_before_it_with_the_pre_turn_brief(
    running_app, client, db, new_session
):
    s = await two_rounds(running_app, client, db, new_session)
    version = (await client.get(f"/api/v1/sessions/{s['id']}")).json()["version"]
    await client.patch(
        f"/api/v1/sessions/{s['id']}",
        json={
            "expected_version": version,
            "brief": {"idea": "Later brief", "goal": None, "constraints": ["later"]},
        },
    )
    first_user = (await messages(db, s["id"]))[0]
    r = await fork(client, s["id"], before_message_id=str(first_user.id), purpose="edit")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["session"]["brief"]["revision"] == 1
    assert body["session"]["brief"]["constraints"] == []
    tpl = body["turn_template"]
    assert tpl["message"] == "First round" and tpl["expected_version"] == body["session"]["version"]
    assert tpl["control"]["audience"] == "auto"
    assert await messages(db, body["session"]["id"]) == []
    sent = await client.post(
        f"/api/v1/sessions/{body['session']['id']}/turns",
        json={**tpl, "message": "First round, edited"},
        headers=idem(),
    )
    assert sent.status_code == 202


async def test_regenerate_needs_a_completed_round_and_mode_overrides_are_refused(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    s = await new_session()
    await turn(client, db, s["id"], "[[demo:fail=skeptic]] partial round", audience="panel")
    user = (await messages(db, s["id"]))[0]
    r = await fork(client, s["id"], before_message_id=str(user.id), purpose="regenerate")
    assert r.status_code == 409 and r.json()["code"] == "regenerate_requires_completed"
    r = await fork(client, s["id"], before_message_id=str(user.id), purpose="edit", mode="standard")
    assert r.status_code == 422


async def test_regenerate_a_completed_round(running_app, client, db, new_session):
    s = await two_rounds(running_app, client, db, new_session)
    second_user = [m for m in await messages(db, s["id"]) if m.role == "user"][1]
    r = await fork(client, s["id"], before_message_id=str(second_user.id), purpose="regenerate")
    assert r.status_code == 201
    body = r.json()
    assert body["turn_template"]["message"] == "Second round"
    assert len(await messages(db, body["session"]["id"])) == 4


async def test_edit_inside_a_fork_and_source_deletion_keeps_copies(
    running_app, client, db, new_session
):
    s = await two_rounds(running_app, client, db, new_session)
    child = (await fork(client, s["id"])).json()["session"]
    child_users = [m for m in await messages(db, child["id"]) if m.role == "user"]
    grand = await fork(
        client, child["id"], before_message_id=str(child_users[1].id), purpose="edit"
    )
    assert grand.status_code == 201 and grand.json()["turn_template"]["message"] == "Second round"
    assert (await client.delete(f"/api/v1/sessions/{s['id']}")).status_code == 204
    kept = await messages(db, child["id"])
    assert kept and all(m.origin_message_id is None for m in kept)
    assert (await client.get(f"/api/v1/sessions/{child['id']}")).json()["origin_session_id"] is None


async def test_fork_is_idempotent_and_needs_an_idle_unarchived_source(
    running_app, client, db, new_session
):
    s = await two_rounds(running_app, client, db, new_session)
    key = idem()
    a = await fork(client, s["id"], key=key)
    b = await fork(client, s["id"], key=key)
    assert a.json() == b.json()
    async with db() as sess:
        n = await sess.scalar(
            select(func.count())
            .select_from(SessionRow)
            .where(SessionRow.origin_session_id == s["id"])
        )
        await sess.execute(
            update(SessionRow).where(SessionRow.id == s["id"]).values(is_archived=True)
        )
        await sess.commit()
    assert n == 1
    assert (await fork(client, s["id"])).status_code == 409


async def test_saved_ideas_on_copied_messages_come_along(running_app, client, db, new_session):
    s = await two_rounds(running_app, client, db, new_session)
    reply = (await messages(db, s["id"]))[1]
    await client.post(
        f"/api/v1/sessions/{s['id']}/idea-cards",
        json={"message_id": str(reply.id), "title": "Keep me", "note": "", "status": "selected"},
        headers=idem(),
    )
    child = (await fork(client, s["id"])).json()["session"]
    async with db() as sess:
        [card] = (
            await sess.scalars(select(IdeaCard).where(IdeaCard.session_id == child["id"]))
        ).all()
        copied_reply = await sess.get(Message, card.message_id)
    assert card.title == "Keep me" and str(copied_reply.session_id) == child["id"]


class FlakyOnce:
    """Fails the first draft for one persona, then behaves."""

    def __init__(self, inner, persona):
        self.inner, self.persona, self.failed = inner, persona, False
        self.name = inner.name

    async def structured(self, **kw):
        import json as _json

        payload = _json.loads(kw["input_items"][-1]["content"][-1]["text"])
        who = (payload.get("profile") or {}).get("id")
        if kw["purpose"] == "draft" and who == self.persona and not self.failed:
            self.failed = True
            raise ProviderFailure("provider_error", "transient outage", usage_unknown=True)
        return await self.inner.structured(**kw)

    async def web_research(self, **kw):
        return await self.inner.web_research(**kw)


async def retry(client, run_id, sid, key=None):
    version = (await client.get(f"/api/v1/sessions/{sid}")).json()["version"]
    return await client.post(
        f"/api/v1/runs/{run_id}/retry", json={"expected_version": version}, headers=key or idem()
    )


async def test_retry_fills_only_the_missing_replies(running_app, client, db, new_session):
    use(running_app, ScriptedJev())
    running_app.state.deps.generation = FlakyOnce(running_app.state.deps.generation, "skeptic")
    s = await new_session()
    first = await turn(client, db, s["id"], "Panel please", audience="panel")
    assert first.status == "partial" and first.missing == ["skeptic"]
    r = await retry(client, first.id, s["id"])
    assert r.status_code == 202 and r.json()["requested_count"] == 1
    second = await wait_done(db, r.json()["id"])
    assert second.status == "completed" and second.retry_of_run_id == first.id
    msgs = await messages(db, s["id"])
    assert [m.role for m in msgs].count("user") == 1
    assert sorted(m.persona_id for m in msgs if m.persona_id) == ["explorer", "mentor", "skeptic"]
    user = msgs[0]
    assert user.round_status == "completed"
    assert user.run_id == second.id  # the round's message points at its latest run (UI retry)


async def test_retry_is_refused_for_completed_or_superseded_rounds(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    s = await new_session()
    done = await turn(client, db, s["id"])
    r = await retry(client, done.id, s["id"])
    assert r.status_code == 409 and r.json()["code"] == "retry_not_allowed"
    partial = await turn(client, db, s["id"], "[[demo:fail=skeptic]] x", audience="panel")
    await turn(client, db, s["id"], "a later turn")
    r = await retry(client, partial.id, s["id"])
    assert r.status_code == 409 and r.json()["code"] == "retry_not_allowed"
    assert (await retry(client, uuid4(), s["id"])).status_code == 404


async def test_retry_with_the_same_key_creates_one_run(running_app, client, db, new_session):
    use(running_app, ScriptedJev())
    s = await new_session()
    partial = await turn(client, db, s["id"], "[[demo:fail=skeptic]] x", audience="panel")
    key = idem()
    a = await retry(client, partial.id, s["id"], key=key)
    b = await client.post(
        f"/api/v1/runs/{partial.id}/retry",
        json={
            "expected_version": (await client.get(f"/api/v1/sessions/{s['id']}")).json()["version"]
            - 1
        },
        headers=key,
    )
    assert a.status_code == 202 and (b.status_code == 409 or b.json()["id"] == a.json()["id"])
    async with db() as sess:
        n = await sess.scalar(
            select(func.count()).select_from(Run).where(Run.retry_of_run_id == partial.id)
        )
    assert n == 1


# ---------- Checkpoint 4 review regressions ----------

QUESTION = "What existing research shows about peer mock interviews?"


class Gate:
    """Records structured calls; can fail drafts; tags memory overviews with what it heard."""

    def __init__(self, inner, fail_persona=None):
        self.inner, self.name = inner, inner.name
        self.fail_all = False
        self.fail_persona, self.failed_once = fail_persona, False
        self.calls = []
        self.research_calls = 0

    async def structured(self, **kw):
        import json as _json

        from app.providers.base import Structured

        payload = _json.loads(kw["input_items"][-1]["content"][-1]["text"])
        self.calls.append((kw["purpose"], payload))
        who = (payload.get("profile") or {}).get("id")
        if kw["purpose"] == "draft":
            if self.fail_all:
                raise ProviderFailure("provider_error", "down", usage_unknown=True)
            if who == self.fail_persona and not self.failed_once:
                self.failed_once = True
                raise ProviderFailure("provider_error", "down", usage_unknown=True)
        res = await self.inner.structured(**kw)
        if kw.get("schema_name") == "memory" and isinstance(res, Structured):
            ids = [m["id"] for m in payload.get("recent_messages", []) if m.get("role") != "user"]
            res.data["overview"] = "HEARD:" + ",".join(ids)
        return res

    async def web_research(self, **kw):
        self.research_calls += 1
        return await self.inner.web_research(**kw)


def research_jev(app):
    return use(app, ScriptedJev(lambda qid, o, s: "needed" if qid == "research_needed" else o[0]))


async def test_mid_round_fork_memory_never_covers_cut_replies(running_app, client, db, new_session):
    use(running_app, ScriptedJev())
    running_app.state.deps.generation = Gate(running_app.state.deps.generation)
    s = await new_session()
    for t in ("Round one", "Round two", "Round three"):
        await turn(client, db, s["id"], t)
    src = await messages(db, s["id"])
    cut = src[5]  # the first reply of round two
    r = await fork(client, s["id"], through_message_id=str(cut.id))
    async with db() as sess:
        row = await sess.get(SessionRow, r.json()["session"]["id"])
    after_cut = [str(m.id) for m in src[6:]]
    memory = row.memory or {}
    assert not any(i in memory.get("overview", "") for i in after_cut)
    assert memory.get("through_sequence", 0) <= cut.sequence


async def test_copied_research_packs_point_at_the_forks_own_sources(
    running_app, client, db, new_session
):
    research_jev(running_app)
    s = await new_session()
    await turn(client, db, s["id"], QUESTION)
    new_id = (await fork(client, s["id"])).json()["session"]["id"]
    async with db() as sess:
        packs = (
            await sess.scalars(select(ResearchPack).where(ResearchPack.session_id == new_id))
        ).all()
        own = {
            str(x.id)
            for x in (await sess.scalars(select(Source).where(Source.session_id == new_id))).all()
        }
    findings = {
        sid
        for p in packs
        for f in (p.normalized or {}).get("findings", [])
        for sid in f["source_ids"]
    }
    assert findings and findings <= own


async def test_fixed_panel_cycle_advances_after_a_failed_round_is_retried(
    running_app, client, db, new_session
):
    gate = Gate(running_app.state.deps.generation)
    running_app.state.deps.generation = gate
    sel = ["mentor", "skeptic", "explorer", "strategist", "engineer"]
    s = await new_session(mode="fixed_panel", selected_persona_ids=sel)
    gate.fail_all = True
    first = await turn(client, db, s["id"], "Round zero")
    assert first.status == "failed"
    gate.fail_all = False
    done = await wait_done(db, (await retry(client, first.id, s["id"])).json()["id"])
    assert done.status == "completed"
    second = await turn(client, db, s["id"], "Round one")
    msgs = await messages(db, s["id"])
    assert [m.persona_id for m in msgs if m.run_id == second.id and m.persona_id] == [
        "strategist",
        "engineer",
        "mentor",
    ]


async def test_copied_controls_keep_resolvable_references_and_still_refuse_edits(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    s = await new_session()
    await turn(client, db, s["id"], "Round one")
    src = await messages(db, s["id"])
    r1, r2 = src[1], src[2]
    card = (
        await client.post(
            f"/api/v1/sessions/{s['id']}/idea-cards",
            json={"message_id": str(r1.id), "title": "A", "note": "", "status": "selected"},
            headers=idem(),
        )
    ).json()
    await turn(
        client,
        db,
        s["id"],
        "Build on that",
        reply_to_message_id=str(r2.id),
        idea_card_ids=[card["id"]],
    )
    assert (await client.delete(f"/api/v1/idea-cards/{card['id']}")).status_code == 204
    users = [m for m in await messages(db, s["id"]) if m.role == "user"]
    in_source = await fork(client, s["id"], before_message_id=str(users[1].id), purpose="edit")
    assert in_source.status_code == 409
    child = (await fork(client, s["id"])).json()["session"]
    copied = await messages(db, child["id"])
    child_users = [m for m in copied if m.role == "user"]
    copied_r2 = next(m for m in copied if m.origin_message_id == r2.id)
    assert child_users[1].turn_control["reply_to_message_id"] == str(copied_r2.id)
    in_fork = await fork(
        client, child["id"], before_message_id=str(child_users[1].id), purpose="edit"
    )
    assert in_fork.status_code == 409 and in_fork.json()["code"] == "unresolvable_reference"


async def test_retry_reuses_the_rounds_intake_and_evidence_and_sees_its_replies(
    running_app, client, db, new_session
):
    research_jev(running_app)
    gate = Gate(running_app.state.deps.generation, fail_persona="skeptic")
    running_app.state.deps.generation = gate
    s = await new_session()
    first = await turn(client, db, s["id"], QUESTION)
    assert first.status == "partial"
    published = [
        str(m.id) for m in await messages(db, s["id"]) if m.run_id == first.id and m.persona_id
    ]
    n_calls, searches = len(gate.calls), gate.research_calls
    done = await wait_done(db, (await retry(client, first.id, s["id"])).json()["id"])
    assert done.status == "completed"
    purposes = [p for p, _ in gate.calls[n_calls:]]
    assert "intake" not in purposes and "research_normalize" not in purposes
    assert gate.research_calls == searches
    draft = next(payload for p, payload in gate.calls[n_calls:] if p == "draft")
    assert {m["id"] for m in draft["recent_messages"]} >= set(published)
    assert draft["evidence"], "the retried speaker keeps the round's evidence"
    async with db() as sess:
        packs = await sess.scalar(
            select(func.count()).select_from(ResearchPack).where(ResearchPack.session_id == s["id"])
        )
    assert packs == 1


async def test_regenerate_refuses_a_changed_research_model(running_app, client, db, new_session):
    from conftest import make_test_env

    s = await two_rounds(running_app, client, db, new_session)
    users = [m for m in await messages(db, s["id"]) if m.role == "user"]
    running_app.state.env = make_test_env(OPENAI_RESEARCH_MODEL="another-model")
    r = await fork(client, s["id"], before_message_id=str(users[1].id), purpose="regenerate")
    assert r.status_code == 409 and r.json()["code"] == "model_unavailable"


class SlowMemory:
    """Demo generation whose memory call is slow, so Stop can land after every reply published."""

    def __init__(self, inner):
        self.inner, self.name = inner, inner.name

    async def structured(self, **kw):
        if kw["purpose"] == "memory":
            await asyncio.sleep(2)
        return await self.inner.structured(**kw)

    async def web_research(self, **kw):
        return await self.inner.web_research(**kw)


async def test_stop_during_memory_after_every_reply_leaves_nothing_to_retry(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    running_app.state.deps.generation = SlowMemory(running_app.state.deps.generation)
    s = await new_session()
    version = (await client.get(f"/api/v1/sessions/{s['id']}")).json()["version"]
    run = (
        await client.post(
            f"/api/v1/sessions/{s['id']}/turns", json=turn_body(version, "Go"), headers=idem()
        )
    ).json()
    async with asyncio.timeout(15):
        while True:
            async with db() as sess:
                if (await sess.get(Run, run["id"])).stage == "memory":
                    break
            await asyncio.sleep(0.05)
    await client.post(f"/api/v1/runs/{run['id']}/cancel")
    final = await wait_done(db, run["id"])
    assert final.status == "cancelled" and final.published_count == final.requested_count == 3
    r = await retry(client, final.id, s["id"])
    assert r.status_code == 409 and r.json()["code"] == "retry_not_allowed"
