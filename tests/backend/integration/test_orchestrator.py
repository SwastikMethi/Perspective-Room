"""Full pipeline: demo generator + scripted coordinator (T02, T03, T05, T06, T18, T20)."""

import asyncio
from collections.abc import Callable

from conftest import idem, turn_body
from sqlalchemy import select

from app.persistence.models import DecisionEvent, Message, ProviderCall, Run
from app.persistence.models import Session as SessionRow
from app.providers.base import ProviderFailure


class ScriptedJev:
    """Records each question batch; answers from a per-test chooser (valid typed answers)."""

    name = "jev"

    def __init__(
        self,
        choose: Callable[[str, list[str], dict], str] | None = None,
        score: float = 1.9,
        fail: bool = False,
    ):
        self.calls: list[dict] = []
        self.choose = choose or (lambda qid, options, state: options[0])
        self.score, self.fail = score, fail

    async def ask(self, state, questions, model=None):
        self.calls.append({"state": state, "questions": questions})
        if self.fail:
            raise ProviderFailure("provider_error", "Jev is down", usage_unknown=True)
        answers = {}
        for qid, q in questions.items():
            if q["type"] == "choice":
                options = list(q["criteria"])
                pick = self.choose(qid, options, state)
                n = len(options)
                probs = {o: (0.9 if o == pick else 0.1 / max(n - 1, 1)) for o in options}
                answers[qid] = {
                    "type": "choice",
                    "choice": pick,
                    "probabilities": probs,
                    "confidence": (0.9 - 1 / n) / (1 - 1 / n) if n > 1 else 1.0,
                }
            else:
                answers[qid] = {
                    "type": "score",
                    "score": self.score,
                    "legend": {"0": "a", "1": "b", "2": "c"},
                    "probabilities": {"0": 0.05, "1": 0.05, "2": 0.9},
                    "confidence": 0.9,
                }
        return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 50}}


async def wait_done(db, run_id, timeout=10.0):
    async with asyncio.timeout(timeout):
        while True:
            async with db() as s:
                run = await s.get(Run, run_id)
            if run.status in ("completed", "partial", "failed", "cancelled", "interrupted"):
                return run
            await asyncio.sleep(0.05)


async def turn(client, sid, message="Help me explore it.", version=1, **control):
    r = await client.post(
        f"/api/v1/sessions/{sid}/turns", json=turn_body(version, message, **control), headers=idem()
    )
    assert r.status_code == 202, r.text
    return r.json()


async def published(db, sid):
    async with db() as s:
        return (
            await s.scalars(
                select(Message)
                .where(Message.session_id == sid, Message.role != "user")
                .order_by(Message.sequence)
            )
        ).all()


async def jev_calls(db, run_id):
    async with db() as s:
        return (
            await s.scalars(
                select(ProviderCall).where(
                    ProviderCall.run_id == run_id, ProviderCall.purpose.in_(("route", "assess"))
                )
            )
        ).all()


def use(app, jev):
    app.state.deps.coordinator = jev
    return jev


async def test_explicit_target_speaks_even_if_jev_would_pick_another(
    running_app, client, db, new_session
):
    jev = use(
        running_app, ScriptedJev(lambda qid, o, s: "mentor" if qid == "next_speaker" else o[0])
    )
    s = await new_session()
    run = await turn(client, s["id"], audience="person", target_persona_id="skeptic")
    assert (await wait_done(db, run["id"])).status == "completed"
    assert [m.persona_id for m in await published(db, s["id"])] == ["skeptic"]
    route_batches = [c for c in jev.calls if "next_speaker" in c["questions"]]
    assert route_batches == []  # the user named the speaker: no automatic speaker question


async def test_auto_never_runs_unselected_or_already_heard_personas(
    running_app, client, db, new_session
):
    # Jev keeps naming an unselected persona: invalid → deterministic fallback every step.
    jev = use(
        running_app, ScriptedJev(lambda qid, o, s: "engineer" if qid == "next_speaker" else o[0])
    )
    s = await new_session()
    run = await turn(client, s["id"])
    final = await wait_done(db, run["id"])
    speakers = [m.persona_id for m in await published(db, s["id"])]
    assert speakers == ["mentor", "skeptic", "explorer"] and final.degraded
    assert "coordination_fallback" in final.warning_codes
    assert all(
        "engineer" not in c["questions"].get("next_speaker", {}).get("criteria", {})
        for c in jev.calls
    )
    later = [c for c in jev.calls if "next_speaker" in c["questions"]][1:]
    assert all("mentor" not in c["questions"]["next_speaker"]["criteria"] for c in later)


async def test_valid_jev_routing_is_followed_and_traced(running_app, client, db, new_session):
    order = iter(["explorer", "mentor", "skeptic"])
    use(
        running_app,
        ScriptedJev(
            lambda qid, o, s: (
                next(order)
                if qid == "next_speaker"
                else ("challenge" if "challenge" in o else o[0])
            )
        ),
    )
    s = await new_session()
    run = await turn(client, s["id"])
    final = await wait_done(db, run["id"])
    assert [m.persona_id for m in await published(db, s["id"])] == ["explorer", "mentor", "skeptic"]
    assert final.degraded is False and final.status == "completed"
    async with db() as sess:
        decisions = (
            await sess.scalars(
                select(DecisionEvent)
                .where(DecisionEvent.run_id == run["id"])
                .order_by(DecisionEvent.step)
            )
        ).all()
    routes = [d for d in decisions if d.kind == "route"]
    assert [d.selected["speaker"] for d in routes] == ["explorer", "mentor", "skeptic"]
    assert all(d.state_hash and d.eligible_options for d in routes)


async def test_return_user_after_one_reply_ends_the_round(running_app, client, db, new_session):
    steps = {"n": 0}

    def choose(qid, options, state):
        if qid == "next_speaker":
            steps["n"] += 1
            return "skeptic" if steps["n"] == 1 else "return_user"
        return options[0]

    use(running_app, ScriptedJev(choose))
    s = await new_session()
    run = await turn(client, s["id"])
    assert (await wait_done(db, run["id"])).status == "completed"
    assert [m.persona_id for m in await published(db, s["id"])] == ["skeptic"]


async def test_return_user_first_asks_the_intake_clarification(
    running_app, client, db, new_session
):
    use(
        running_app, ScriptedJev(lambda qid, o, s: "return_user" if qid == "next_speaker" else o[0])
    )
    s = await new_session()
    run = await turn(client, s["id"], "[[demo:clarify]] something vague")
    await wait_done(db, run["id"])
    [msg] = await published(db, s["id"])
    assert msg.role == "moderator" and msg.text and msg.persona_id is None


async def test_unavailable_jev_keeps_a_useful_labeled_generation_path(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev(fail=True))
    s = await new_session()
    run = await turn(client, s["id"])
    final = await wait_done(db, run["id"])
    assert len(await published(db, s["id"])) == 3 and final.status == "completed"
    assert final.degraded and "coordination_fallback" in final.warning_codes


async def test_no_jev_key_uses_the_fixed_order_fallback(running_app, client, db, new_session):
    from app.main import NotWired

    use(running_app, NotWired())
    s = await new_session()
    run = await turn(client, s["id"])
    final = await wait_done(db, run["id"])
    assert "coordination_unavailable" in final.warning_codes and final.degraded
    assert len(await published(db, s["id"])) == 3
    assert await jev_calls(db, run["id"]) == []


async def test_standard_and_fixed_panel_make_zero_jev_calls(running_app, client, db, new_session):
    jev = use(running_app, ScriptedJev())
    std = await new_session(mode="standard")
    fixed = await new_session(mode="fixed_panel")
    r1 = await turn(client, std["id"])
    r2 = await turn(client, fixed["id"])
    await wait_done(db, r1["id"])
    await wait_done(db, r2["id"])
    assert jev.calls == []
    [assistant] = await published(db, std["id"])
    assert assistant.role == "moderator" and assistant.persona_id is None
    assert assistant.contribution is not None
    assert [m.persona_id for m in await published(db, fixed["id"])] == [
        "mentor",
        "skeptic",
        "explorer",
    ]


async def test_fixed_panel_and_jev_snapshots_hold_the_same_conditions(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    b = await new_session(mode="fixed_panel")
    c = await new_session(mode="jev_guided")
    rb, rc = await turn(client, b["id"]), await turn(client, c["id"])
    async with db() as s:
        sb, sc = (await s.get(Run, rb["id"])).snapshot, (await s.get(Run, rc["id"])).snapshot
    for key in ("profiles", "profile_hashes", "models", "settings", "limits", "templates"):
        assert sb[key] == sc[key], key


async def test_auto_with_two_selected_publishes_two(running_app, client, db, new_session):
    use(running_app, ScriptedJev())
    s = await new_session(selected_persona_ids=["civic", "health"])
    run = await turn(client, s["id"])
    await wait_done(db, run["id"])
    assert sorted(m.persona_id for m in await published(db, s["id"])) == ["civic", "health"]


async def test_eight_person_panel_publishes_eight_in_roster_order(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    everyone = [
        "health",
        "civic",
        "customer",
        "engineer",
        "strategist",
        "explorer",
        "skeptic",
        "mentor",
    ]
    s = await new_session(selected_persona_ids=everyone)
    run = await turn(client, s["id"], audience="panel")
    final = await wait_done(db, run["id"], timeout=20)
    assert final.requested_count == 8 and final.published_count == 8
    assert [m.persona_id for m in await published(db, s["id"])] == [
        "mentor",
        "skeptic",
        "explorer",
        "strategist",
        "engineer",
        "customer",
        "civic",
        "health",
    ]


async def test_panel_partial_failure_keeps_the_rest_and_names_the_missing(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    s = await new_session()
    run = await turn(client, s["id"], "[[demo:fail=skeptic]] go", audience="panel")
    final = await wait_done(db, run["id"])
    assert final.status == "partial" and final.missing == ["skeptic"]
    assert [m.persona_id for m in await published(db, s["id"])] == ["mentor", "explorer"]


async def test_at_most_one_repair_per_turn_even_with_concurrent_slots(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    s = await new_session()
    run = await turn(client, s["id"], "[[demo:incomplete]] all broken", audience="panel")
    final = await wait_done(db, run["id"])
    async with db() as sess:
        repairs = (
            await sess.scalars(
                select(ProviderCall).where(
                    ProviderCall.run_id == run["id"], ProviderCall.purpose == "repair"
                )
            )
        ).all()
    assert len(repairs) == 1 and final.repairs_used == 1
    assert final.status == "failed" and await published(db, s["id"]) == []


async def test_weak_but_valid_reply_is_repaired_once_then_published(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev(score=0.2))  # every assessment says "contradicts the profile"
    s = await new_session()
    run = await turn(client, s["id"], audience="person", target_persona_id="mentor")
    final = await wait_done(db, run["id"])
    async with db() as sess:
        repairs = (
            await sess.scalars(
                select(ProviderCall).where(
                    ProviderCall.run_id == run["id"], ProviderCall.purpose == "repair"
                )
            )
        ).all()
    assert len(repairs) == 1 and final.status == "completed"
    assert "repair_used" in final.warning_codes


async def test_research_runs_at_most_once_and_is_shared(running_app, client, db, new_session):
    use(running_app, ScriptedJev(lambda qid, o, s: "needed" if qid == "research_needed" else o[0]))
    s = await new_session()
    run = await turn(client, s["id"], "What existing research shows about mock interviews?")
    await wait_done(db, run["id"])
    async with db() as sess:
        searches = (
            await sess.scalars(
                select(ProviderCall).where(
                    ProviderCall.run_id == run["id"], ProviderCall.purpose == "research_search"
                )
            )
        ).all()
    assert len(searches) == 1


async def test_summary_turn_uses_the_moderator_with_five_sections(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    s = await new_session()
    first = await turn(client, s["id"])
    await wait_done(db, first["id"])
    session = (await client.get(f"/api/v1/sessions/{s['id']}")).json()
    run = await turn(
        client,
        s["id"],
        "Summarize the conversation so far.",
        version=session["version"],
        audience="summary",
    )
    await wait_done(db, run["id"])
    summary = (await published(db, s["id"]))[-1]
    assert summary.role == "moderator" and summary.summary is not None
    assert [sec["kind"] for sec in summary.summary["sections"]] == [
        "directions",
        "disagreements",
        "assumptions",
        "questions",
        "experiments",
    ]


async def test_memory_and_title_are_updated_after_the_first_turn(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    s = await new_session()
    run = await turn(client, s["id"], "Neighborhood tool sharing for renters")
    await wait_done(db, run["id"])
    async with db() as sess:
        row = await sess.get(SessionRow, s["id"])
    msg_ids = {str(m.id) for m in await published(db, s["id"])}
    assert row.memory and row.memory["brief_revision"] == 1
    assert all(set(i["source_message_ids"]) <= msg_ids for i in row.memory["ideas"])
    assert row.title == "Neighborhood tool sharing for renters" and row.title_is_custom is False


async def test_custom_title_is_never_overwritten(running_app, client, db, new_session):
    use(running_app, ScriptedJev())
    s = await new_session(title="My own title")
    run = await turn(client, s["id"])
    await wait_done(db, run["id"])
    assert (await client.get(f"/api/v1/sessions/{s['id']}")).json()["title"] == "My own title"


async def test_stop_mid_panel_publishes_nothing_further(running_app, client, db, new_session):
    use(running_app, ScriptedJev())
    s = await new_session(selected_persona_ids=["mentor", "skeptic", "explorer", "engineer"])
    run = await turn(client, s["id"], "[[demo:delay=700]] slow panel", audience="panel")
    async with asyncio.timeout(8):
        while not await published(db, s["id"]):
            await asyncio.sleep(0.05)
    await client.post(f"/api/v1/runs/{run['id']}/cancel")
    final = await wait_done(db, run["id"])
    n = len(await published(db, s["id"]))
    await asyncio.sleep(1.5)
    assert final.status == "cancelled" and len(await published(db, s["id"])) == n < 4


# ---- checkpoint 3 review regressions ----


class Recording:
    """Delegates to the demo generator and records payloads; can fail chosen purposes."""

    def __init__(self, inner, fail_purposes=(), failure=None):
        self.inner, self.fail_purposes, self.failure = inner, set(fail_purposes), failure
        self.name = inner.name
        self.payloads: list[tuple[str, dict]] = []

    async def structured(self, **kw):
        import json as _json

        payload = _json.loads(kw["input_items"][-1]["content"][-1]["text"])
        self.payloads.append((kw["purpose"], payload))
        if kw["purpose"] in self.fail_purposes:
            raise self.failure
        return await self.inner.structured(**kw)

    async def web_research(self, **kw):
        return await self.inner.web_research(**kw)


def recording(app, **kw):
    rec = Recording(app.state.deps.generation, **kw)
    app.state.deps.generation = rec
    return rec


async def purposes(db, run_id):
    async with db() as s:
        return [
            (c.purpose, c.status)
            for c in (
                await s.scalars(
                    select(ProviderCall)
                    .where(ProviderCall.run_id == run_id)
                    .order_by(ProviderCall.started_at)
                )
            ).all()
        ]


async def test_nan_from_jev_falls_back_instead_of_crashing(running_app, client, db, new_session):
    class NaNJev(ScriptedJev):
        async def ask(self, state, questions, model=None):
            env = await super().ask(state, questions, model)
            for a in env["answers"].values():
                a["confidence"] = float("nan")
            env["usage"] = {"input_tokens": "lots"}
            return env

    use(running_app, NaNJev())
    s = await new_session()
    run = await turn(client, s["id"])
    final = await wait_done(db, run["id"])
    assert final.status == "completed" and len(await published(db, s["id"])) == 3
    assert final.degraded and "coordination_fallback" in final.warning_codes


async def test_failed_summary_call_is_never_resent(running_app, client, db, new_session):
    use(running_app, ScriptedJev())
    s = await new_session()
    first = await turn(client, s["id"])
    await wait_done(db, first["id"])
    recording(
        running_app,
        fail_purposes={"summary"},
        failure=ProviderFailure("provider_error", "504", usage_unknown=True),
    )
    version = (await client.get(f"/api/v1/sessions/{s['id']}")).json()["version"]
    run = await turn(client, s["id"], "Summarize.", version=version, audience="summary")
    final = await wait_done(db, run["id"])
    calls = await purposes(db, run["id"])
    assert [p for p, _ in calls] == ["summary"] and final.status == "failed"


async def test_a_failing_persona_does_not_starve_the_others(running_app, client, db, new_session):
    use(running_app, ScriptedJev(fail=True))
    s = await new_session()
    run = await turn(client, s["id"], "[[demo:fail=mentor]] try everyone")
    final = await wait_done(db, run["id"])
    assert sorted(m.persona_id for m in await published(db, s["id"])) == ["explorer", "skeptic"]
    assert final.status == "partial" and final.missing == ["mentor"]


async def test_invalid_move_answers_are_disclosed_as_degraded(running_app, client, db, new_session):
    use(
        running_app,
        ScriptedJev(lambda qid, o, s: "delete_everything" if qid.startswith("move_") else o[0]),
    )
    s = await new_session()
    run = await turn(client, s["id"], audience="panel")
    final = await wait_done(db, run["id"])
    assert final.status == "completed" and final.degraded
    assert "coordination_fallback" in final.warning_codes


async def test_invalid_assessment_counts_as_audit_unavailable(running_app, client, db, new_session):
    class BadScores(ScriptedJev):
        async def ask(self, state, questions, model=None):
            env = await super().ask(state, questions, model)
            for _qid, a in env["answers"].items():
                if a["type"] == "score":
                    a["score"] = 9.0
            return env

    use(running_app, BadScores())
    s = await new_session()
    run = await turn(client, s["id"], audience="person", target_persona_id="mentor")
    final = await wait_done(db, run["id"])
    [msg] = await published(db, s["id"])
    assert "audit_unavailable" in msg.warning_codes and final.degraded


async def test_each_panel_slot_keeps_its_own_assessment_trace(running_app, client, db, new_session):
    use(running_app, ScriptedJev(score=0.2))
    s = await new_session()
    run = await turn(client, s["id"], audience="panel")
    await wait_done(db, run["id"])
    async with db() as sess:
        rows = (
            await sess.scalars(
                select(DecisionEvent).where(
                    DecisionEvent.run_id == run["id"], DecisionEvent.kind == "assess"
                )
            )
        ).all()
    assert sorted(r.persona_id for r in rows) == ["explorer", "mentor", "skeptic"]
    assert all(r.state and r.answers for r in rows)
    assert sum(1 for r in rows if r.repair_outcome == "repaired") == 1


async def test_reply_target_is_passed_in_full(running_app, client, db, new_session):
    use(running_app, ScriptedJev())
    s = await new_session()
    first = await turn(client, s["id"], "[[demo:long]] a long first turn")
    await wait_done(db, first["id"])
    target = (await published(db, s["id"]))[0]
    rec = recording(running_app)
    version = (await client.get(f"/api/v1/sessions/{s['id']}")).json()["version"]
    run = await turn(
        client,
        s["id"],
        "Say more about this.",
        version=version,
        audience="person",
        target_persona_id=target.persona_id,
        reply_to_message_id=str(target.id),
        move_override="expand",
    )
    await wait_done(db, run["id"])
    drafts = [p for purpose, p in rec.payloads if purpose == "draft"]
    assert len(drafts[0]["reply_target"]["text"]) > 800


async def test_fatal_provider_error_stops_the_rest_of_the_turn(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev())
    recording(
        running_app,
        fail_purposes={"draft"},
        failure=ProviderFailure("provider_not_ready", "bad key", status=401),
    )
    s = await new_session()
    run = await turn(client, s["id"])
    final = await wait_done(db, run["id"])
    calls = [p for p, _ in await purposes(db, run["id"])]
    assert calls.count("draft") == 1 and "memory" not in calls and "repair" not in calls
    assert final.status == "failed" and final.error["code"] == "provider_not_ready"
