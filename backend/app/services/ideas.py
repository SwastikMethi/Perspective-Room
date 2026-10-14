"""Saved ideas, feedback and sources. None of these change a run's captured context or the
session content version (G22)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.domain import api
from app.persistence.models import Feedback, IdeaCard, Message, Source
from app.persistence.models import Session as SessionRow
from app.services.common import invalid, keyset_page, reject_explicit_nulls, trimmed, unique, utcnow

NOTE_MAX = 4000


async def _writable_session(db: AsyncSession, session_id: UUID) -> SessionRow:
    row = await db.get(SessionRow, session_id)
    if row is None:
        raise ApiError(404, "not_found", "Chat not found.")
    if row.evaluation_batch_id is not None:
        raise ApiError(409, "evaluation_managed", "Experiment Lab chats are rated in the Lab.")
    if row.is_archived:
        raise ApiError(409, "session_archived", "Restore this chat before changing it.")
    return row


def card_out(c: IdeaCard) -> api.IdeaCard:
    return api.IdeaCard(
        id=c.id,
        session_id=c.session_id,
        message_id=c.message_id,
        title=c.title,
        note=c.note,
        status=c.status,
        version=c.version,  # type: ignore[arg-type]
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def create_card(db: AsyncSession, session_id: UUID, body: api.IdeaCardCreate) -> api.IdeaCard:
    await _writable_session(db, session_id)
    message = await db.scalar(
        select(Message).where(Message.id == body.message_id, Message.session_id == session_id)
    )
    if message is None or message.role == "user":
        raise invalid("Save ideas from a reply in this chat.")
    now = utcnow()
    card = IdeaCard(
        session_id=session_id,
        message_id=body.message_id,
        title=trimmed(body.title, "title", 120),
        note=body.note[:NOTE_MAX],
        status=body.status,
        created_at=now,
        updated_at=now,
    )
    db.add(card)
    await db.flush()
    return card_out(card)


async def list_cards(
    db: AsyncSession, session_id: UUID, limit: int, cursor: str | None
) -> api.IdeaCardList:
    if await db.get(SessionRow, session_id) is None:
        raise ApiError(404, "not_found", "Chat not found.")
    rows, nxt = await keyset_page(
        db,
        select(IdeaCard).where(IdeaCard.session_id == session_id),
        IdeaCard.created_at,
        IdeaCard.id,
        limit=limit,
        cursor=cursor,
        scope=f"cards:{session_id}",
    )
    return api.IdeaCardList(items=[card_out(c) for c in rows], next_cursor=nxt)


async def update_card(db: AsyncSession, card_id: UUID, body: api.IdeaCardPatch) -> api.IdeaCard:
    reject_explicit_nulls(body, ("title", "note", "status"))
    async with db.begin():
        card = await db.scalar(select(IdeaCard).where(IdeaCard.id == card_id).with_for_update())
        if card is None:
            raise ApiError(404, "not_found", "Saved idea not found.")
        await _writable_session(db, card.session_id)
        if body.expected_version != card.version:
            raise ApiError(
                409,
                "version_conflict",
                "This saved idea changed; refresh it.",
                details={"current_version": card.version},
            )
        if body.title is not None:
            card.title = trimmed(body.title, "title", 120)
        if body.note is not None:
            card.note = body.note[:NOTE_MAX]
        if body.status is not None:
            card.status = body.status
        card.version += 1
        card.updated_at = utcnow()
        await db.flush()
        return card_out(card)


async def delete_card(db: AsyncSession, card_id: UUID) -> None:
    async with db.begin():
        card = await db.scalar(select(IdeaCard).where(IdeaCard.id == card_id).with_for_update())
        if card is None:
            raise ApiError(404, "not_found", "Saved idea not found.")
        await _writable_session(db, card.session_id)
        await db.delete(card)


async def set_feedback(
    db: AsyncSession, message_id: UUID, body: api.FeedbackCreate
) -> api.Feedback:
    labels = unique(list(body.labels), "labels")
    async with db.begin():
        message = await db.get(Message, message_id)
        if message is None:
            raise ApiError(404, "not_found", "Message not found.")
        if message.role == "user":
            raise invalid("Feedback is for replies, not your own messages.")
        await _writable_session(db, message.session_id)
        fb = await db.scalar(
            select(Feedback).where(Feedback.message_id == message_id).with_for_update()
        )
        if fb is None:
            fb = Feedback(message_id=message_id, labels=labels, note=body.note[:NOTE_MAX])
            db.add(fb)
        else:
            fb.labels, fb.note = labels, body.note[:NOTE_MAX]
        fb.updated_at = utcnow()
        await db.flush()
        return api.Feedback(
            id=fb.id,
            message_id=fb.message_id,
            labels=fb.labels,
            note=fb.note,
            updated_at=fb.updated_at,
        )


def source_out(s: Source) -> api.Source:
    return api.Source(
        id=s.id,
        session_id=s.session_id,
        research_pack_id=s.research_pack_id,
        url=s.url,
        title=s.title,
        domain=s.domain,
        retrieved_at=s.retrieved_at,
        published_at=s.published_at,
        research_excerpt=s.research_excerpt,
        provider_response_id=s.provider_response_id,
        is_fixture=s.is_fixture,
    )


async def list_sources(
    db: AsyncSession, session_id: UUID, limit: int, cursor: str | None
) -> api.SourceList:
    if await db.get(SessionRow, session_id) is None:
        raise ApiError(404, "not_found", "Chat not found.")
    rows, nxt = await keyset_page(
        db,
        select(Source).where(Source.session_id == session_id),
        Source.retrieved_at,
        Source.id,
        limit=limit,
        cursor=cursor,
        scope=f"sources:{session_id}",
    )
    return api.SourceList(items=[source_out(s) for s in rows], next_cursor=nxt)


async def get_source(db: AsyncSession, source_id: UUID) -> api.Source:
    src = await db.get(Source, source_id)
    if src is None:
        raise ApiError(404, "not_found", "Source not found.")
    return source_out(src)
