"""Transactional publication: a contribution, its sequence number and its event commit together."""

from typing import Any

from sqlalchemy import select

from app.persistence.models import Message, Run
from app.services.common import lock_session, utcnow
from app.services.runs import append_event
from app.services.transcript import message_out
from app.workers.context import RunCancelled, RunContext


def search_text_for(
    text: str | None, contribution: dict[str, Any] | None, summary: dict[str, Any] | None
) -> str:
    """Public plain text indexed for chat search (never `new_angle` or private data)."""
    if text:
        return text
    if contribution:
        return "\n".join([contribution["headline"], *(b["text"] for b in contribution["blocks"])])
    if summary:
        return "\n".join(i["text"] for sec in summary["sections"] for i in sec["items"])
    return ""


async def publish_contribution(
    ctx: RunContext,
    *,
    role: str,
    persona_id: str | None = None,
    contribution: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    text: str | None = None,
    contribution_index: int,
    warning_codes: list[str] | None = None,
) -> Message:
    async with ctx.sessionmaker() as s, s.begin():
        run = await s.scalar(select(Run).where(Run.id == ctx.run_id).with_for_update())
        assert run is not None
        if run.cancel_requested or run.status != "running":
            ctx.cancelled = True
        ctx.check()  # never publish after Stop or the deadline
        session = await lock_session(s, run.session_id)  # lock order: run, then session
        now = utcnow()
        session.last_sequence += 1
        session.version += 1
        session.last_activity_at = session.updated_at = now
        msg = Message(
            session_id=session.id,
            run_id=run.id,
            sequence=session.last_sequence,
            contribution_index=contribution_index,
            role=role,
            persona_id=persona_id,
            text=text,
            contribution=contribution,
            summary=summary,
            warning_codes=warning_codes or [],
            search_text=search_text_for(text, contribution, summary),
            created_at=now,
        )
        s.add(msg)
        run.published_count += 1
        run.session_version = session.version
        run.heartbeat_at = run.updated_at = now
        await s.flush()
        await append_event(
            s,
            run,
            "message.completed",
            {
                "message": message_out(msg).model_dump(mode="json"),
                "session_version": session.version,
            },
        )
    await ctx.notifier.notify_run(ctx.run_id)
    return msg


__all__ = ["RunCancelled", "publish_contribution", "search_text_for"]
