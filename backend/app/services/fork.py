"""Branches and retries (doc 08 §Fork and export semantics, doc 14 §Composer, G13–G16).

A fork copies a committed prefix with new IDs and remaps every message/source/card reference;
published history is never mutated. Edit/regenerate branch BEFORE a user message and return the
original turn as a template; nothing runs until the client submits it. Retry fills only the
missing replies of the latest incomplete round.
"""

from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.catalog import Catalog
from app.domain import api
from app.persistence.models import (
    TERMINAL_RUN_STATUSES,
    IdeaCard,
    IdeaRevision,
    Message,
    ResearchPack,
    Run,
    Source,
)
from app.persistence.models import Session as SessionRow
from app.services.common import active_run_id, invalid, lock_session, reject_explicit_nulls, utcnow
from app.services.runs import EMPTY_USAGE, append_event, run_out
from app.services.sessions import require_folder, session_out
from app.services.turns import queued_data
from app.settings import AppEnv

RETRYABLE = {"partial", "failed", "interrupted", "cancelled"}
TITLE_MAX = 120


def _remap_ids(ids: list[str], mapping: dict[str, str]) -> list[str]:
    return [mapping[i] for i in ids if i in mapping]


def _remap_contribution(c: dict[str, Any], msgs: dict[str, str], srcs: dict[str, str]) -> dict:
    out = deepcopy(c)
    out["referenced_message_ids"] = _remap_ids(c.get("referenced_message_ids", []), msgs)
    for b in out["blocks"]:
        b["source_ids"] = _remap_ids(b.get("source_ids", []), srcs)
    return out


def _remap_items(
    items: list[dict[str, Any]], msgs: dict[str, str], srcs: dict[str, str], *, drop_outside: bool
) -> list[dict[str, Any]]:
    out = []
    for item in items:
        mids = item.get("source_message_ids", [])
        if drop_outside and any(m not in msgs for m in mids):
            continue  # never carry a conclusion from after the cutoff (G14)
        out.append(
            {
                **item,
                "source_message_ids": _remap_ids(mids, msgs),
                "source_ids": _remap_ids(item.get("source_ids", []), srcs),
            }
        )
    return out


def _remap_control(
    control: dict[str, Any], msgs: dict[str, str], cards: dict[str, str]
) -> tuple[dict[str, Any], bool]:
    """Remap each reference on its own; anything unresolvable is dropped and the control keeps
    an internal marker, so a later edit/regenerate of it is refused instead of silently changed."""
    out = dict(control)
    unresolved = bool(out.pop("unresolved_references", False))
    reply = control.get("reply_to_message_id")
    if reply is not None:
        out["reply_to_message_id"] = msgs.get(reply)
        unresolved |= reply not in msgs
    refs = control.get("idea_card_ids") or []
    out["idea_card_ids"] = [cards[c] for c in refs if c in cards]
    unresolved |= len(out["idea_card_ids"]) != len(refs)
    if unresolved:
        out["unresolved_references"] = True
    return out, unresolved


def _remap_normalized(normalized: dict[str, Any] | None, srcs: dict[str, str]) -> Any:
    if not normalized:
        return normalized
    out = deepcopy(normalized)
    for finding in out.get("findings", []):
        finding["source_ids"] = _remap_ids(finding.get("source_ids", []), srcs)
    return out


def _remap_memory(
    memory: dict[str, Any] | None, msgs: dict[str, str], srcs: dict[str, str]
) -> dict[str, Any] | None:
    if not memory:
        return None
    out = dict(memory)
    for key in ("ideas", "open_questions", "assumptions"):
        out[key] = _remap_items(memory.get(key, []), msgs, srcs, drop_outside=True)
    return out


async def fork_session(
    db: AsyncSession, env: AppEnv, catalog: Catalog, source_id: UUID, body: api.ForkCreate
) -> api.ForkResult:
    reject_explicit_nulls(body, ("mode", "purpose"))
    src = await lock_session(db, source_id)
    if src.evaluation_batch_id is not None:
        raise ApiError(409, "evaluation_managed", "Use the Lab export for Experiment Lab chats.")
    if src.is_archived:
        raise ApiError(409, "session_archived", "Restore this chat before branching it.")
    if body.expected_version != src.version:
        raise ApiError(
            409,
            "version_conflict",
            "This chat changed; refresh and try again.",
            details={"current_version": src.version},
        )
    if await active_run_id(db, source_id) is not None:
        raise ApiError(409, "run_active", "Wait for the running reply or stop it first.")
    if body.through_message_id is not None and body.before_message_id is not None:
        raise invalid("Use either through_message_id or before_message_id, not both.")
    branching = body.purpose in ("edit", "regenerate")
    if branching and ("mode" in body.model_fields_set or body.before_message_id is None):
        raise invalid("Edit and regenerate branch before a user message and keep the mode.")

    all_msgs = list(
        (
            await db.scalars(
                select(Message).where(Message.session_id == source_id).order_by(Message.sequence)
            )
        ).all()
    )
    by_id = {str(m.id): m for m in all_msgs}
    cutoff_id = body.through_message_id or body.before_message_id
    if cutoff_id is not None and str(cutoff_id) not in by_id:
        raise ApiError(404, "not_found", "That message is not in this chat.")
    if body.through_message_id is not None:
        limit_seq = by_id[str(body.through_message_id)].sequence
    elif body.before_message_id is not None:
        limit_seq = by_id[str(body.before_message_id)].sequence - 1
    else:
        limit_seq = all_msgs[-1].sequence if all_msgs else 0
    prefix = [m for m in all_msgs if m.sequence <= limit_seq]
    next_user = next((m for m in all_msgs if m.sequence > limit_seq and m.role == "user"), None)

    target: Message | None = None
    if branching:
        target = by_id[str(body.before_message_id)]
        if target.role != "user" or not target.turn_snapshot:
            raise invalid("Edit and regenerate apply to one of your own messages.")
        if body.purpose == "regenerate" and target.round_status != "completed":
            raise ApiError(
                409,
                "regenerate_requires_completed",
                "Only a completed round can be regenerated; retry missing replies instead.",
            )
        models = target.turn_snapshot["models"]
        configured = {
            "openai_model": env.OPENAI_MODEL,
            "research_model": env.OPENAI_RESEARCH_MODEL,
            "jev_model": env.JEV_MODEL,
        }
        if any(models.get(k) != v for k, v in configured.items()):
            raise ApiError(
                409,
                "model_unavailable",
                "The model used for that turn is not the configured model.",
                details={"original": models, "configured": configured},
            )
        pre = target.turn_snapshot  # the immutable pre-turn context
        selected, settings, mode = list(pre["selected"]), dict(pre["settings"]), pre["mode"]
        brief_revision = int(pre["brief"]["revision"])
        memory_source = pre.get("memory")
    else:
        selected, settings = list(src.selected_persona_ids), dict(src.settings)
        mode = body.mode or src.mode
        # G15: the brief the next turn after the prefix used; else the current brief.
        brief_revision = (
            int(next_user.turn_snapshot["brief"]["revision"])
            if next_user is not None and next_user.turn_snapshot
            else int(src.brief["revision"])
        )
        memory_source = (
            next_user.turn_snapshot.get("memory")
            if next_user is not None and next_user.turn_snapshot
            else src.memory
        )

    if memory_source and int(memory_source.get("through_sequence", limit_seq + 1)) > limit_seq:
        # A mid-round cutoff: that memory already summarizes replies the branch leaves out, so
        # use the memory from before the round that the cutoff falls in.
        opener = next(
            (m for m in reversed(all_msgs) if m.sequence <= limit_seq and m.role == "user"), None
        )
        memory_source = (opener.turn_snapshot or {}).get("memory") if opener else None

    if "folder_id" in body.model_fields_set:
        folder_id = body.folder_id
    else:
        folder_id = src.folder_id
    if folder_id is not None:
        await require_folder(db, folder_id)

    revisions = list(
        (
            await db.scalars(
                select(IdeaRevision)
                .where(
                    IdeaRevision.session_id == source_id, IdeaRevision.revision <= brief_revision
                )
                .order_by(IdeaRevision.revision)
            )
        ).all()
    )
    brief_row = revisions[-1]
    now = utcnow()
    title = (body.title or "").strip()[
        :TITLE_MAX
    ] or f"{src.title[: TITLE_MAX - 9]} ({'branch' if branching else 'fork'})"
    new = SessionRow(
        title=title,
        title_is_custom=bool(body.title and body.title.strip()),
        folder_id=folder_id,
        mode=mode,
        selected_persona_ids=selected,
        settings=settings,
        brief={
            "idea": brief_row.idea,
            "goal": brief_row.goal,
            "constraints": list(brief_row.constraints),
            "revision": brief_row.revision,
        },
        origin_session_id=src.id,
        last_sequence=limit_seq,
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(new)
    await db.flush()
    for rev in revisions:
        db.add(
            IdeaRevision(
                session_id=new.id,
                revision=rev.revision,
                idea=rev.idea,
                goal=rev.goal,
                constraints=list(rev.constraints),
                author_type=rev.author_type,
                source_message_ids=list(rev.source_message_ids),  # remapped below
                created_at=rev.created_at,
            )
        )

    msg_map = {str(m.id): str(uuid4()) for m in prefix}
    cited: set[str] = set()
    for m in prefix:
        if m.contribution:
            cited |= {sid for b in m.contribution["blocks"] for sid in b.get("source_ids", [])}
        if m.summary:
            cited |= {
                sid
                for s in m.summary["sections"]
                for i in s["items"]
                for sid in i.get("source_ids", [])
            }
    src_map: dict[str, str] = {}
    pack_ids: set[UUID] = set()
    if cited:
        pack_ids |= set(
            (
                await db.scalars(
                    select(Source.research_pack_id).where(
                        Source.session_id == source_id, Source.id.in_([UUID(c) for c in cited])
                    )
                )
            ).all()
        )
    round_users = [m.id for m in prefix if m.role == "user"]
    if round_users:  # failed/empty packs of copied rounds keep their disclosure
        pack_ids |= set(
            (
                await db.scalars(
                    select(ResearchPack.id)
                    .join(Run, Run.id == ResearchPack.run_id)
                    .where(Run.user_message_id.in_(round_users))
                )
            ).all()
        )
    if pack_ids:
        for pack in (
            await db.scalars(select(ResearchPack).where(ResearchPack.id.in_(pack_ids)))
        ).all():
            new_pack = ResearchPack(
                session_id=new.id,
                run_id=None,
                query=pack.query,
                status=pack.status,
                raw_answer=pack.raw_answer,
                normalized=pack.normalized,
                unknowns=pack.unknowns,
                provider_response_id=pack.provider_response_id,
                is_fixture=pack.is_fixture,
                origin_pack_id=pack.id,
                created_at=pack.created_at,
            )
            db.add(new_pack)
            await db.flush()
            for s in (
                await db.scalars(select(Source).where(Source.research_pack_id == pack.id))
            ).all():
                copy = Source(
                    session_id=new.id,
                    research_pack_id=new_pack.id,
                    url=s.url,
                    title=s.title,
                    domain=s.domain,
                    retrieved_at=s.retrieved_at,
                    published_at=s.published_at,
                    provider_response_id=s.provider_response_id,
                    provider_citation=s.provider_citation,
                    research_excerpt=s.research_excerpt,
                    is_fixture=s.is_fixture,
                    origin_source_id=s.id,
                    created_at=s.created_at,
                )
                db.add(copy)
                await db.flush()
                src_map[str(s.id)] = str(copy.id)
            new_pack.normalized = _remap_normalized(pack.normalized, src_map)

    old_cards = (
        await db.scalars(
            select(IdeaCard).where(
                IdeaCard.session_id == source_id,
                IdeaCard.message_id.in_([m.id for m in prefix] or [uuid4()]),
            )
        )
    ).all()
    card_map = {str(c.id): str(uuid4()) for c in old_cards}

    for m in prefix:
        control = snapshot = None
        if m.turn_control is not None:
            control, _ = _remap_control(m.turn_control, msg_map, card_map)
        if m.turn_snapshot is not None:
            snapshot = deepcopy(m.turn_snapshot)
            snapshot["message_id"] = msg_map[str(m.id)]
            snapshot["control"] = control
            snapshot["memory"] = _remap_memory(snapshot.get("memory"), msg_map, src_map)
            snapshot["idea_cards"] = [
                {**c, "id": card_map[c["id"]], "message_id": msg_map[c["message_id"]]}
                for c in snapshot.get("idea_cards", [])
                if c["id"] in card_map and c["message_id"] in msg_map
            ]
        db.add(
            Message(
                id=UUID(msg_map[str(m.id)]),
                session_id=new.id,
                run_id=None,
                sequence=m.sequence,
                contribution_index=None,
                role=m.role,
                persona_id=m.persona_id,
                text=m.text,
                contribution=_remap_contribution(m.contribution, msg_map, src_map)
                if m.contribution
                else None,
                summary={
                    "sections": [
                        {
                            "kind": s["kind"],
                            "items": _remap_items(s["items"], msg_map, src_map, drop_outside=False),
                        }
                        for s in m.summary["sections"]
                    ]
                }
                if m.summary
                else None,
                warning_codes=list(m.warning_codes),
                search_text=m.search_text,
                origin_message_id=m.id,
                turn_control=control,
                turn_snapshot=snapshot,
                round_status=m.round_status,
                round_info=m.round_info,
                created_at=m.created_at,
            )
        )
    await db.flush()
    for c in old_cards:
        db.add(
            IdeaCard(
                id=UUID(card_map[str(c.id)]),
                session_id=new.id,
                message_id=UUID(msg_map[str(c.message_id)]),
                title=c.title,
                note=c.note,
                status=c.status,
                origin_card_id=c.id,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
        )
    new.memory = _remap_memory(memory_source, msg_map, src_map)
    for rev_row in (
        await db.scalars(select(IdeaRevision).where(IdeaRevision.session_id == new.id))
    ).all():
        rev_row.source_message_ids = _remap_ids(list(rev_row.source_message_ids), msg_map)
    await db.flush()

    template = None
    if target is not None:
        assert target.turn_control is not None
        control, unresolved = _remap_control(target.turn_control, msg_map, card_map)
        if unresolved:
            raise ApiError(
                409,
                "unresolvable_reference",
                "That turn referenced something this branch cannot include.",
            )
        template = api.TurnCreate(
            expected_version=new.version,
            message=target.text or "",
            control=api.TurnControl(**control),
        )
    await db.refresh(new)
    return api.ForkResult(session=session_out(new, None), turn_template=template)


async def retry_run(db: AsyncSession, env: AppEnv, run_id: UUID, body: api.RetryCreate) -> api.Run:
    original = await db.get(Run, run_id)
    if original is None:
        raise ApiError(404, "not_found", "Run not found.")
    session = await lock_session(db, original.session_id)
    if session.evaluation_batch_id is not None:
        raise ApiError(409, "evaluation_managed", "Experiment Lab chats are driven by the Lab.")
    if session.is_archived:
        raise ApiError(409, "session_archived", "Restore this chat before retrying.")
    if body.expected_version != session.version:
        raise ApiError(
            409,
            "version_conflict",
            "This chat changed; refresh and try again.",
            details={"current_version": session.version},
        )
    if await active_run_id(db, session.id) is not None:
        raise ApiError(409, "run_active", "A reply is still running in this chat.")
    if env.APP_PROVIDER_MODE != original.snapshot["provider_mode"]:
        raise ApiError(
            409,
            "retry_not_allowed",
            "This round ran in a different provider mode; send a new turn instead.",
        )
    user = await db.get(Message, original.user_message_id) if original.user_message_id else None
    latest_run = await db.scalar(
        select(Run)
        .where(Run.user_message_id == original.user_message_id)
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    later_turn = user is not None and await db.scalar(
        select(Message.id)
        .where(
            Message.session_id == session.id,
            Message.role == "user",
            Message.sequence > user.sequence,
        )
        .limit(1)
    )
    if (
        user is None
        or original.status not in RETRYABLE
        or later_turn
        or latest_run is None
        or latest_run.id != original.id
    ):
        raise ApiError(
            409,
            "retry_not_allowed",
            "Only the latest incomplete round can be retried; send a new turn instead.",
        )
    rounds = (await db.scalars(select(Run).where(Run.user_message_id == user.id))).all()
    published = {
        pid
        for (pid,) in (
            await db.execute(
                select(Message.persona_id).where(
                    Message.run_id.in_([r.id for r in rounds]), Message.role != "user"
                )
            )
        ).all()
    }
    root = min(rounds, key=lambda r: r.created_at)
    voiced = (
        await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.run_id.in_([r.id for r in rounds]), Message.role != "user")
        )
        or 0
    )
    if root.slots in (["assistant"], ["summary"]):
        slots, requested = (list(root.slots), 1) if not voiced else ([], 0)
    elif root.slots:
        slots = [s for s in root.slots if s not in published]
        requested = len(slots)
    else:  # auto: requested_count is an upper bound; fill what is left of it
        slots, requested = [], root.requested_count - int(voiced)
    if requested <= 0:
        raise ApiError(409, "retry_not_allowed", "Nothing is missing from that round.")
    now = utcnow()
    session.version += 1
    session.updated_at = now
    run = Run(
        session_id=session.id,
        user_message_id=user.id,
        status="queued",
        stage="queued",
        mode=original.mode,
        audience=original.audience,
        control=original.control,
        snapshot=original.snapshot,
        slots=slots,
        requested_count=requested,
        usage=dict(EMPTY_USAGE),
        session_version=session.version,
        retry_of_run_id=original.id,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    await db.flush()
    user.run_id = run.id  # the round's message points at its latest attempt (what a client retries)
    await append_event(db, run, "run.queued", queued_data(run))
    return run_out(run)


__all__ = ["TERMINAL_RUN_STATUSES", "fork_session", "retry_run"]
