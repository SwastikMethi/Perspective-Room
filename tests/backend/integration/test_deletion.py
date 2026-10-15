"""Local deletion (T25, doc 12): deleting a chat removes every record it owns — transcript, runs
and their events, provider-call and decision logs, research packs, sources, saved ideas, feedback,
brief revisions — and leaves other chats and their forks' copies intact."""

from conftest import idem
from sqlalchemy import func, select
from test_fork import fork, messages, research_jev, turn

from app.persistence.models import (
    DecisionEvent,
    Feedback,
    IdeaCard,
    IdeaRevision,
    Message,
    ProviderCall,
    ResearchPack,
    Run,
    RunEvent,
    Source,
)

QUESTION = "What existing research shows about peer mock interviews?"


async def owned(db, sid):
    async with db() as s:
        run_ids = select(Run.id).where(Run.session_id == sid)
        counts = {
            "messages": select(func.count()).select_from(Message).where(Message.session_id == sid),
            "runs": select(func.count()).select_from(Run).where(Run.session_id == sid),
            "events": select(func.count())
            .select_from(RunEvent)
            .where(RunEvent.run_id.in_(run_ids)),
            "calls": select(func.count())
            .select_from(ProviderCall)
            .where(ProviderCall.run_id.in_(run_ids)),
            "decisions": select(func.count())
            .select_from(DecisionEvent)
            .where(DecisionEvent.run_id.in_(run_ids)),
            "packs": select(func.count())
            .select_from(ResearchPack)
            .where(ResearchPack.session_id == sid),
            "sources": select(func.count()).select_from(Source).where(Source.session_id == sid),
            "cards": select(func.count()).select_from(IdeaCard).where(IdeaCard.session_id == sid),
            "revisions": select(func.count())
            .select_from(IdeaRevision)
            .where(IdeaRevision.session_id == sid),
            "feedback": select(func.count())
            .select_from(Feedback)
            .join(Message, Message.id == Feedback.message_id)
            .where(Message.session_id == sid),
        }
        return {k: await s.scalar(q) for k, q in counts.items()}


async def test_deleting_a_chat_removes_everything_it_owns(running_app, client, db, new_session):
    research_jev(running_app)
    s = await new_session()
    other = await new_session()
    await turn(client, db, s["id"], QUESTION)
    reply = next(m for m in await messages(db, s["id"]) if m.persona_id)
    await client.post(
        f"/api/v1/sessions/{s['id']}/idea-cards",
        json={"message_id": str(reply.id), "title": "Keep", "note": "", "status": "selected"},
        headers=idem(),
    )
    await client.post(
        f"/api/v1/messages/{reply.id}/feedback", json={"labels": ["useful"], "note": ""}
    )
    child = (await fork(client, s["id"])).json()["session"]
    before = await owned(db, s["id"])
    assert all(
        before[k] > 0
        for k in (
            "messages",
            "runs",
            "events",
            "calls",
            "decisions",
            "packs",
            "sources",
            "cards",
            "feedback",
            "revisions",
        )
    )
    child_before = await owned(db, child["id"])

    assert (await client.delete(f"/api/v1/sessions/{s['id']}")).status_code == 204
    assert set((await owned(db, s["id"])).values()) == {0}
    assert (await client.get(f"/api/v1/sessions/{s['id']}")).status_code == 404
    # A fork keeps its own copies; another chat is untouched.
    assert await owned(db, child["id"]) == child_before
    assert (await client.get(f"/api/v1/sessions/{other['id']}")).status_code == 200
