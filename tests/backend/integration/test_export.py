"""Session export (doc 08 §Fork and export semantics, doc 07 §Display and export; T23 part):
a source survives retrieval → contribution → summary → Markdown/JSON export and the CLI."""

import asyncio
import json

from conftest import TEST_DB_URL, idem, make_test_env
from contract_support import contract_client
from sqlalchemy import update
from test_fork import messages, turn
from test_orchestrator import ScriptedJev, use

from app.cli import main as cli_main
from app.persistence.models import EvaluationBatch
from app.persistence.models import Session as SessionRow
from app.prompts.loader import template
from app.settings import get_env

FAKE_OPENAI = "sk-test-NEVER-EXPORTED-0123456789abcdef"
FAKE_JEV = "ts-test-NEVER-EXPORTED-fedcba9876543210"
QUESTION = "What existing research shows about peer mock interviews?"


async def research_then_summary(app, client, db, sid):
    use(app, ScriptedJev(lambda qid, o, s: "needed" if qid == "research_needed" else o[0]))
    await turn(client, db, sid, QUESTION)
    await turn(client, db, sid, "Summarize where we are.", audience="summary")


async def researched_and_summarized(app, client, db, new_session):
    s = await new_session()
    await research_then_summary(app, client, db, s["id"])
    return s


async def export(client, sid, fmt):
    return await client.get(f"/api/v1/sessions/{sid}/export", params={"format": fmt})


def cited_in(data):
    contrib = {
        sid
        for m in data["messages"]
        if m["contribution"]
        for b in m["contribution"]["blocks"]
        for sid in b["source_ids"]
    }
    summary = {
        sid
        for m in data["messages"]
        if m["summary"]
        for sec in m["summary"]["sections"]
        for i in sec["items"]
        for sid in i["source_ids"]
    }
    return contrib, summary


async def test_json_export_keeps_the_source_chain_and_public_metadata(
    running_app, client, db, new_session
):
    s = await researched_and_summarized(running_app, client, db, new_session)
    r = await export(client, s["id"], "json")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment;") and disposition.endswith('.json"')
    data = r.json()
    assert data["schema"] == "perspective-room/session-export" and data["schema_version"] == 1
    assert data["session"]["id"] == s["id"] and data["labels"]["demo"] is True
    sources = {x["id"]: x for x in data["sources"]}
    contrib, summary = cited_in(data)
    assert contrib and summary and (contrib | summary) <= set(sources)
    assert all(sources[i]["is_fixture"] for i in contrib)
    assert [r["revision"] for r in data["brief_revisions"]] == [1]
    assert {"status", "warning_codes", "usage", "missing_persona_ids"} <= set(data["runs"][0])
    flat = json.dumps(data)
    assert "snapshot" not in flat and "turn_control" not in flat and "raw_answer" not in flat


async def test_markdown_export_is_attributed_and_cites_by_number(
    running_app, client, db, new_session
):
    s = await researched_and_summarized(running_app, client, db, new_session)
    reply = next(m for m in await messages(db, s["id"]) if m.persona_id)
    await client.post(
        f"/api/v1/sessions/{s['id']}/idea-cards",
        json={"message_id": str(reply.id), "title": "Keep me", "note": "", "status": "selected"},
        headers=idem(),
    )
    data = (await export(client, s["id"], "json")).json()
    assert [c["title"] for c in data["idea_cards"]] == ["Keep me"]
    r = await export(client, s["id"], "markdown")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["content-disposition"].endswith('.md"')
    md = r.text
    assert md.startswith(f"# {data['session']['title']}\n")
    assert "Mode: Jev-guided" in md and "Demo mode" in md and data["session"]["brief"]["idea"] in md
    assert QUESTION in md and "## Saved ideas" in md and "## Sources" in md
    name = running_app.state.catalog.personas[reply.persona_id].display_name
    assert f"- **Keep me** (selected, from {name})" in md
    names = {p.display_name for p in running_app.state.catalog.personas.values()}
    assert any(f"### {n}" in md for n in names)
    contrib, summary = cited_in(data)
    order = list(dict.fromkeys(i for i in [*contrib, *summary]))
    by_id = {x["id"]: x for x in data["sources"]}
    for sid in order:
        assert by_id[sid]["url"] in md
    sources_part = md.split("## Sources", 1)[1]
    assert "[1]" in md.split("## Sources", 1)[0] and sources_part.lstrip().startswith("1. ")
    assert "(fixture)" in sources_part
    summary_part = md.split("### Moderator — Summary", 1)[1].split("## Saved ideas", 1)[0]
    assert "#### Directions" in summary_part and "[1]" in summary_part


async def test_exports_never_contain_keys_or_prompts(db, new_session):
    from app.main import create_app

    app = create_app(env=make_test_env(OPENAI_API_KEY=FAKE_OPENAI, TYPESAFE_API_KEY=FAKE_JEV))
    await app.state.runner.start()
    try:
        async with contract_client(app) as client:
            r = await client.post(
                "/api/v1/sessions",
                json={"idea": "A tool library for my building."},
                headers=idem(),
            )
            s = r.json()
            await research_then_summary(app, client, db, s["id"])
            bodies = [(await export(client, s["id"], f)).text for f in ("markdown", "json")]
    finally:
        await app.state.runner.stop()
        await app.state.engine.dispose()
    persona_rules = template("persona").text.strip().splitlines()[0]
    for body in bodies:
        assert FAKE_OPENAI not in body and FAKE_JEV not in body
        assert persona_rules not in body


async def test_archived_chats_export_and_lab_chats_and_bad_requests_do_not(client, db, new_session):
    s = await new_session()
    async with db() as sess:
        await sess.execute(
            update(SessionRow).where(SessionRow.id == s["id"]).values(is_archived=True)
        )
        await sess.commit()
    assert (await export(client, s["id"], "markdown")).status_code == 200
    assert (await export(client, s["id"], "pdf")).status_code == 422
    other = await new_session()
    from uuid import uuid4

    assert (await export(client, str(uuid4()), "json")).status_code == 404
    async with db() as sess:
        batch = EvaluationBatch(
            status="running", config={}, snapshot={}, seed=1, provider_mode="demo", planned=1
        )
        sess.add(batch)
        await sess.flush()
        await sess.execute(
            update(SessionRow)
            .where(SessionRow.id == other["id"])
            .values(evaluation_batch_id=batch.id)
        )
        await sess.commit()
    r = await export(client, other["id"], "json")
    assert r.status_code == 409 and r.json()["code"] == "evaluation_managed"


async def test_export_session_cli_writes_the_same_document(
    running_app, client, db, new_session, tmp_path, monkeypatch
):
    s = await researched_and_summarized(running_app, client, db, new_session)
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    get_env.cache_clear()
    try:
        out = tmp_path / "chat.json"
        code = await asyncio.to_thread(
            cli_main, ["export-session", s["id"], "--format", "json", "--out", str(out)]
        )
        assert code == 0
        again = await asyncio.to_thread(
            cli_main, ["export-session", s["id"], "--format", "json", "--out", str(out)]
        )
        assert again == 1  # never overwrites an existing file
        md = tmp_path / "chat.md"
        assert (
            await asyncio.to_thread(
                cli_main, ["export-session", s["id"], "--format", "markdown", "--out", str(md)]
            )
            == 0
        )
    finally:
        get_env.cache_clear()
    api_doc = (await export(client, s["id"], "json")).json()
    cli_doc = json.loads(out.read_text())
    assert {k: v for k, v in cli_doc.items() if k != "exported_at"} == {
        k: v for k, v in api_doc.items() if k != "exported_at"
    }
    assert md.read_text().startswith(f"# {api_doc['session']['title']}\n")


async def test_fork_exports_keep_demo_and_research_disclosures(
    running_app, client, db, new_session
):
    use(running_app, ScriptedJev(lambda qid, o, s: "needed" if qid == "research_needed" else o[0]))
    s = await new_session()
    await turn(client, db, s["id"], QUESTION + " [[demo:research=fail]]")
    version = (await client.get(f"/api/v1/sessions/{s['id']}")).json()["version"]
    child = await client.post(
        f"/api/v1/sessions/{s['id']}/forks",
        json={"expected_version": version, "through_message_id": None, "title": None},
        headers=idem(),
    )
    new_id = child.json()["session"]["id"]
    md = (await export(client, new_id, "markdown")).text
    assert "Demo mode" in md and "Current facts were not checked" in md
    data = (await export(client, new_id, "json")).json()
    assert data["labels"]["demo"] is True
    [round_] = data["rounds"]
    assert "research_unavailable" in round_["warning_codes"]


async def test_export_after_a_successful_retry_reports_nothing_missing(
    running_app, client, db, new_session
):
    from test_fork import Gate, retry
    from test_orchestrator import wait_done

    use(running_app, ScriptedJev())
    running_app.state.deps.generation = Gate(running_app.state.deps.generation, "skeptic")
    s = await new_session()
    first = await turn(client, db, s["id"], "Panel please", audience="panel")
    assert first.status == "partial"
    done = await wait_done(db, (await retry(client, first.id, s["id"])).json()["id"])
    assert done.status == "completed"
    md = (await export(client, s["id"], "markdown")).text
    assert "Missing replies" not in md
