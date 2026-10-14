"""Turn submission: user message + immutable run snapshot + queued event, in one transaction."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.catalog import Catalog
from app.domain import api
from app.persistence.models import IdeaCard, Message, Run
from app.persistence.models import Session as SessionRow
from app.services.common import active_run_id, invalid, lock_session, trimmed, unique, utcnow
from app.services.context import build_snapshot, required_context_tokens
from app.services.runs import EMPTY_USAGE, append_event, run_out
from app.services.sessions import require_provider
from app.settings import AppEnv


def plan_slots(
    session: SessionRow, control: api.TurnControl, catalog: Catalog
) -> tuple[list[str], int]:
    """Requested work: (slots, requested_count). Auto speakers are routed later, so slots = []."""
    selected = list(session.selected_persona_ids)
    if control.audience == "summary":
        return ["summary"], 1
    if session.mode == "standard":
        return ["assistant"], 1
    if control.audience == "person":
        return [str(control.target_persona_id)], 1
    if control.audience == "panel":
        return [p for p in catalog.order if p in selected], len(selected)
    return [], min(int(session.settings.get("auto_contributions", 3)), len(selected))


async def validate_control(
    db: AsyncSession, session: SessionRow, control: api.TurnControl
) -> tuple[list[IdeaCard], str]:
    """Doc 08 cross-field rules. Returns the referenced idea cards and the reply target text."""
    aud = control.audience
    if session.mode == "standard" and aud in ("person", "panel"):
        raise invalid("Standard mode uses one neutral assistant; ask it directly instead.")
    if aud == "person":
        if control.target_persona_id is None:
            raise invalid("Choose who should respond.", field="target_persona_id")
        if control.target_persona_id not in session.selected_persona_ids:
            raise ApiError(
                422,
                "target_not_selected",
                "Add that perspective to the room before asking it directly.",
                details={"target_persona_id": control.target_persona_id},
            )
    elif control.target_persona_id is not None:
        raise invalid("A target personality is only used when asking one person.")
    if aud == "summary" and (control.move_override or control.research_override == "force"):
        raise invalid("A summary uses existing evidence and cannot take a move or force research.")
    reply_text = ""
    if control.reply_to_message_id is not None:
        reply = await db.scalar(
            select(Message).where(
                Message.id == control.reply_to_message_id, Message.session_id == session.id
            )
        )
        if reply is None:
            raise invalid("The message you replied to is not in this chat.")
        reply_text = reply.text or reply.search_text
    unique([str(i) for i in control.idea_card_ids], "idea_card_ids")
    cards: list[IdeaCard] = []
    if control.idea_card_ids:
        found = (
            await db.scalars(
                select(IdeaCard).where(
                    IdeaCard.id.in_(control.idea_card_ids), IdeaCard.session_id == session.id
                )
            )
        ).all()
        if len(found) != len(control.idea_card_ids):
            raise invalid("Some referenced saved ideas are not in this chat.")
        cards = list(found)
    if control.move_override == "combine" and not (
        len(cards) >= 2 or (control.reply_to_message_id and len(cards) >= 1)
    ):
        raise invalid("Combine needs two saved ideas, or a reply target plus one saved idea.")
    return cards, reply_text


async def submit_turn(
    db: AsyncSession,
    env: AppEnv,
    catalog: Catalog,
    session_id: UUID,
    body: api.TurnCreate,
    *,
    lab: bool = False,
) -> api.Run:
    require_provider(env)
    session = await lock_session(db, session_id)
    if session.evaluation_batch_id is not None and not lab:
        raise ApiError(409, "evaluation_managed", "Experiment Lab chats are driven by the Lab.")
    if session.is_archived:
        raise ApiError(409, "session_archived", "Restore this chat before sending.")
    if body.expected_version != session.version:
        raise ApiError(
            409,
            "version_conflict",
            "This chat changed; refresh and try again.",
            details={"current_version": session.version},
        )
    if (active := await active_run_id(db, session_id)) is not None:
        raise ApiError(
            409,
            "run_active",
            "A reply is still running in this chat.",
            details={"active_run_id": str(active)},
        )
    text = trimmed(body.message, "message", catalog.defaults.limits.user_message_chars)
    cards, reply_text = await validate_control(db, session, body.control)
    slots, requested = plan_slots(session, body.control, catalog)

    run_id, message_id = uuid4(), uuid4()
    control = body.control.model_dump(mode="json")
    all_cards = (await db.scalars(select(IdeaCard).where(IdeaCard.session_id == session_id))).all()
    snapshot = build_snapshot(
        env=env,
        catalog=catalog,
        session=session,
        control=control,
        message_id=str(message_id),
        message_text=text,
        cards=list(all_cards),
    )
    limits = catalog.defaults.limits
    max_out = (
        limits.summary_output_tokens
        if slots == ["summary"]
        else (limits.contribution_output_tokens)
    )
    if required_context_tokens(snapshot, reply_text, cards, max_out) > limits.llm_input_tokens:
        raise ApiError(
            422,
            "context_too_large",
            "This request needs more context than the configured limit. "
            "Narrow it (shorter message, fewer references) and try again.",
        )

    now = utcnow()
    session.version += 1
    session.last_sequence += 1
    session.last_activity_at = session.updated_at = now
    run = Run(
        id=run_id,
        session_id=session_id,
        user_message_id=message_id,
        status="queued",
        stage="queued",
        mode=session.mode,
        audience=body.control.audience,
        control=control,
        snapshot=snapshot,
        slots=slots,
        requested_count=requested,
        usage=dict(EMPTY_USAGE),
        session_version=session.version,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    await db.flush()  # the run first: messages.run_id is checked immediately
    db.add(
        Message(
            id=message_id,
            session_id=session_id,
            run_id=run_id,
            sequence=session.last_sequence,
            role="user",
            text=text,
            search_text=text,
            turn_control=control,
            turn_snapshot=snapshot,
            created_at=now,
        )
    )
    await db.flush()
    await append_event(db, run, "run.queued", queued_data(run))
    return run_out(run)


def queued_data(run: Run) -> dict[str, Any]:
    return {
        "status": run.status,
        "stage": run.stage,
        "session_version": run.session_version,
        "audience": run.audience,
        "slots": list(run.slots),
    }
