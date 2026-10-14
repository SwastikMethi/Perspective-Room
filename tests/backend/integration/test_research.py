"""Research provenance (doc 07; T14, T09-research): sources only from citations, HTTP(S) only,
safe dedupe, honest failure, no invented sources, fixture labels kept."""

import asyncio

import pytest
from conftest import idem, turn_body
from sqlalchemy import select
from test_orchestrator import ScriptedJev, published, use, wait_done

from app.persistence.models import Message, ResearchPack, Run, Source
from app.providers.base import Citation, ResearchRaw, Structured
from app.services.research import normalize_url

QUESTION = "What existing research shows about peer mock interviews?"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("HTTPS://Example.ORG/a/b?x=1#frag", "https://example.org/a/b?x=1"),
        ("https://example.org/a?utm_source=x&id=7&fbclid=y", "https://example.org/a?id=7"),
        ("https://example.org", "https://example.org/"),
        ("javascript:alert(1)", None),
        ("ftp://example.org/file", None),
        ("/relative/path", None),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_distinct_query_values_are_kept():
    assert normalize_url("https://e.org/s?q=a") != normalize_url("https://e.org/s?q=b")


class StubResearch:
    """Generation provider whose web research returns a chosen raw answer; else delegates."""

    def __init__(self, inner, raw=None, normalized=None, delay=0.0):
        self.inner, self.raw, self.normalized, self.delay = inner, raw, normalized, delay
        self.name = inner.name

    async def structured(self, **kw):
        if kw["schema_name"] == "research" and self.normalized is not None:
            import json as _json

            payload = _json.loads(kw["input_items"][-1]["content"][-1]["text"])
            return Structured(self.normalized(payload), "demo", None)
        return await self.inner.structured(**kw)

    async def web_research(self, **kw):
        await asyncio.sleep(self.delay)
        return self.raw if self.raw is not None else await self.inner.web_research(**kw)


def research_jev(app):
    return use(app, ScriptedJev(lambda qid, o, s: "needed" if qid == "research_needed" else o[0]))


async def ask(client, sid, message=QUESTION, **control):
    r = await client.post(
        f"/api/v1/sessions/{sid}/turns", json=turn_body(1, message, **control), headers=idem()
    )
    assert r.status_code == 202, r.text
    return r.json()


async def rows(db, model, **where):
    async with db() as s:
        q = select(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return (await s.scalars(q)).all()


async def test_sources_come_from_citations_and_flow_into_cited_contributions(
    running_app, client, db, new_session
):
    research_jev(running_app)
    s = await new_session()
    run = await ask(client, s["id"])
    await wait_done(db, run["id"])
    [pack] = await rows(db, ResearchPack, session_id=s["id"])
    sources = await rows(db, Source, session_id=s["id"])
    assert pack.status == "available" and sources and all(src.is_fixture for src in sources)
    assert all(src.url.startswith("https://") and src.provider_citation for src in sources)
    cited = {
        sid
        for m in await published(db, s["id"])
        for b in m.contribution["blocks"]
        for sid in b["source_ids"]
    }
    assert cited and cited <= {str(src.id) for src in sources}


async def test_duplicate_urls_share_one_source_and_keep_every_citation(
    running_app, client, db, new_session
):
    text = "Mock interviews help. Peer practice also helps."
    raw = ResearchRaw(
        text,
        [
            Citation("https://example.edu/study?utm_campaign=x", "Study", 0, 20),
            Citation("https://EXAMPLE.edu/study#section-2", "Study", 21, len(text)),
            Citation("javascript:alert(1)", "Bad", 0, 5),
        ],
        [],
        "resp_r",
        "gpt-test",
    )
    running_app.state.deps.generation = StubResearch(running_app.state.deps.generation, raw=raw)
    research_jev(running_app)
    s = await new_session()
    run = await ask(client, s["id"])
    await wait_done(db, run["id"])
    [src] = await rows(db, Source, session_id=s["id"])
    assert len(src.provider_citation) == 2 and src.is_fixture is False
    assert src.domain == "example.edu"


async def test_normalizer_cannot_add_sources(running_app, client, db, new_session):
    def invent(payload):
        real = next(iter(payload["source_map"]))
        return {
            "query": payload["query"],
            "unknowns": [],
            "findings": [
                {"statement": "Supported claim.", "source_ids": [real], "qualification": None},
                {
                    "statement": "Invented claim.",
                    "source_ids": ["https://invented.example/x"],
                    "qualification": None,
                },
            ],
        }

    running_app.state.deps.generation = StubResearch(
        running_app.state.deps.generation, normalized=invent
    )
    research_jev(running_app)
    s = await new_session()
    run = await ask(client, s["id"])
    final = await wait_done(db, run["id"])
    [pack] = await rows(db, ResearchPack, session_id=s["id"])
    assert [f["statement"] for f in pack.normalized["findings"]] == ["Supported claim."]
    assert "research_findings_dropped" in final.warning_codes


async def test_failed_search_is_disclosed_and_brainstorming_continues(
    running_app, client, db, new_session
):
    research_jev(running_app)
    s = await new_session()
    run = await ask(client, s["id"], QUESTION + " [[demo:research=fail]]")
    final = await wait_done(db, run["id"])
    [pack] = await rows(db, ResearchPack, session_id=s["id"])
    assert pack.status == "failed" and await rows(db, Source, session_id=s["id"]) == []
    assert "research_unavailable" in final.warning_codes
    msgs = await published(db, s["id"])
    assert len(msgs) == 3
    assert all(b["kind"] != "fact" for m in msgs for b in m.contribution["blocks"])


async def test_empty_search_is_not_a_verification(running_app, client, db, new_session):
    research_jev(running_app)
    s = await new_session()
    run = await ask(client, s["id"], QUESTION + " [[demo:research=empty]]")
    final = await wait_done(db, run["id"])
    [pack] = await rows(db, ResearchPack, session_id=s["id"])
    assert pack.status == "empty" and "research_empty" in final.warning_codes


async def test_stop_during_research_prevents_any_later_reply(running_app, client, db, new_session):
    running_app.state.deps.generation = StubResearch(running_app.state.deps.generation, delay=1.5)
    research_jev(running_app)
    s = await new_session()
    run = await ask(client, s["id"])
    async with asyncio.timeout(5):
        while True:
            async with db() as sess:
                if (await sess.get(Run, run["id"])).stage == "researching":
                    break
            await asyncio.sleep(0.05)
    await client.post(f"/api/v1/runs/{run['id']}/cancel")
    final = await wait_done(db, run["id"])
    await asyncio.sleep(1.5)
    assert final.status == "cancelled"
    async with db() as sess:
        assert (
            await sess.scalars(
                select(Message).where(Message.session_id == s["id"], Message.role != "user")
            )
        ).all() == []


async def test_research_off_for_the_session_never_searches(running_app, client, db, new_session):
    research_jev(running_app)
    s = await new_session(settings={"research_policy": "off", "auto_contributions": 3})
    run = await ask(client, s["id"])
    await wait_done(db, run["id"])
    assert await rows(db, ResearchPack, session_id=s["id"]) == []
