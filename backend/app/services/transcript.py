"""Message projection and cursor paging (doc 08 §Workspace endpoints). Never calls a model."""

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.domain import api
from app.persistence.models import Message
from app.persistence.models import Session as SessionRow
from app.services.common import decode_cursor, encode_cursor


def message_out(m: Message) -> api.Message:
    return api.Message(
        id=m.id,
        session_id=m.session_id,
        run_id=m.run_id,
        sequence=m.sequence,
        role=m.role,  # type: ignore[arg-type]
        persona_id=m.persona_id,  # type: ignore[arg-type]
        text=m.text,
        contribution=api.Contribution(**m.contribution) if m.contribution else None,
        summary=api.Summary(**m.summary) if m.summary else None,
        created_at=m.created_at,
        warning_codes=list(m.warning_codes),
    )


async def list_messages(
    db: AsyncSession,
    session_id: UUID,
    limit: int,
    cursor: str | None,
    around: UUID | None,
) -> api.MessageList:
    if cursor and around:
        raise ApiError(400, "bad_request", "Use either cursor or around_message_id, not both.")
    if await db.get(SessionRow, session_id) is None:
        raise ApiError(404, "not_found", "Chat not found.")
    base = select(Message).where(Message.session_id == session_id)
    rows: list[Message]
    if around is not None:
        anchor = await db.scalar(base.where(Message.id == around))
        if anchor is None:
            raise ApiError(404, "not_found", "That message is not in this chat.")
        before = (
            await db.scalars(
                base.where(Message.sequence < anchor.sequence)
                .order_by(Message.sequence.desc())
                .limit(limit)
            )
        ).all()
        after = (
            await db.scalars(
                base.where(Message.sequence > anchor.sequence)
                .order_by(Message.sequence)
                .limit(limit)
            )
        ).all()
        n_before = min(len(before), (limit - 1) // 2)
        n_after = min(len(after), limit - 1 - n_before)
        n_before = min(len(before), limit - 1 - n_after)
        rows = [*reversed(before[:n_before]), anchor, *after[:n_after]]
    elif cursor:
        c = decode_cursor(cursor, scope=str(session_id))
        if c.get("d") not in ("before", "after") or not isinstance(c.get("s"), int):
            raise ApiError(400, "bad_request", "That cursor is not valid.")
        if c.get("d") == "after":
            rows = list(
                (
                    await db.scalars(
                        base.where(Message.sequence > c["s"])
                        .order_by(Message.sequence)
                        .limit(limit)
                    )
                ).all()
            )
        else:
            rows = list(
                reversed(
                    (
                        await db.scalars(
                            base.where(Message.sequence < c["s"])
                            .order_by(Message.sequence.desc())
                            .limit(limit)
                        )
                    ).all()
                )
            )
    else:
        rows = list(
            reversed((await db.scalars(base.order_by(Message.sequence.desc()).limit(limit))).all())
        )

    async def more(cond) -> bool:
        return bool(await db.scalar(select(exists().where(Message.session_id == session_id, cond))))

    prev_c = next_c = None
    if rows:
        first, last = rows[0].sequence, rows[-1].sequence
        if await more(Message.sequence < first):
            prev_c = encode_cursor({"d": "before", "s": first}, scope=str(session_id))
        if await more(Message.sequence > last):
            next_c = encode_cursor({"d": "after", "s": last}, scope=str(session_id))
    return api.MessageList(
        items=[message_out(m) for m in rows], next_cursor=next_c, previous_cursor=prev_c
    )
