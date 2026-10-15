"""Chat workspace: folders, organization edits, history listing and literal search
(doc 08 §Workspace endpoints, doc 14). Organization metadata is never model context and never
changes the content `version` or `last_activity_at`. No call here executes a model."""

import hashlib
import json
import re
from uuid import UUID

from sqlalchemy import exists, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.domain import api
from app.persistence.models import ACTIVE_RUN_STATUSES, Folder, Message, Run
from app.persistence.models import Session as SessionRow
from app.services.common import (
    active_run_id,
    decode_cursor,
    encode_cursor,
    invalid,
    keyset_page,
    lock_session,
    reject_explicit_nulls,
    trimmed,
    utcnow,
)
from app.services.sessions import require_folder, session_out

FOLDER_NAME_MAX = 80
TITLE_MAX = 120
SNIPPET_MAX = 240
SNIPPET_LEAD = 80


def _normalized(name: str) -> str:
    return name.casefold()


def _taken() -> ApiError:
    return ApiError(409, "folder_name_taken", "A folder with that name already exists.")


async def _counts(db: AsyncSession, folder_ids: list[UUID]) -> dict[UUID, tuple[int, int]]:
    rows = await db.execute(
        select(SessionRow.folder_id, SessionRow.is_archived, func.count())
        .where(SessionRow.folder_id.in_(folder_ids), SessionRow.evaluation_batch_id.is_(None))
        .group_by(SessionRow.folder_id, SessionRow.is_archived)
    )
    out: dict[UUID, list[int]] = {fid: [0, 0] for fid in folder_ids}
    for fid, archived, n in rows.all():
        if fid is not None:
            out[fid][1 if archived else 0] = n
    return {fid: (a, b) for fid, (a, b) in out.items()}


def _folder_out(f: Folder, counts: tuple[int, int]) -> api.Folder:
    return api.Folder(
        id=f.id,
        name=f.name,
        version=f.version,
        chat_count=counts[0],
        archived_chat_count=counts[1],
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


async def _folder(db: AsyncSession, folder_id: UUID, *, lock: bool = False) -> Folder:
    q = select(Folder).where(Folder.id == folder_id)
    row = await db.scalar(q.with_for_update() if lock else q)
    if row is None:
        raise ApiError(404, "not_found", "Folder not found.")
    return row


async def folder_out(db: AsyncSession, f: Folder) -> api.Folder:
    return _folder_out(f, (await _counts(db, [f.id]))[f.id])


async def create_folder(db: AsyncSession, body: api.FolderCreate) -> api.Folder:
    name = trimmed(body.name, "name", FOLDER_NAME_MAX)
    now = utcnow()
    new_id = await db.scalar(
        pg_insert(Folder)
        .values(name=name, name_normalized=_normalized(name), created_at=now, updated_at=now)
        .on_conflict_do_nothing(index_elements=["name_normalized"])
        .returning(Folder.id)
    )
    if new_id is None:
        raise _taken()
    return await folder_out(db, await _folder(db, new_id))


async def get_folder(db: AsyncSession, folder_id: UUID) -> api.Folder:
    return await folder_out(db, await _folder(db, folder_id))


async def list_folders(db: AsyncSession, limit: int, cursor: str | None) -> api.FolderList:
    q = select(Folder)
    if cursor:
        c = decode_cursor(cursor, "folders")
        try:
            key = (str(c["n"]), UUID(c["i"]))
        except (KeyError, ValueError, TypeError) as e:
            raise ApiError(400, "bad_request", "That cursor is not valid.") from e
        q = q.where(tuple_(Folder.name_normalized, Folder.id) > key)
    rows = list(
        (await db.scalars(q.order_by(Folder.name_normalized, Folder.id).limit(limit + 1))).all()
    )
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        nxt = encode_cursor({"n": rows[-1].name_normalized, "i": str(rows[-1].id)}, "folders")
    counts = await _counts(db, [f.id for f in rows])
    return api.FolderList(items=[_folder_out(f, counts[f.id]) for f in rows], next_cursor=nxt)


def _check_version(row: Folder, expected: int) -> None:
    if row.version != expected:
        raise ApiError(
            409,
            "version_conflict",
            "This folder changed; refresh and try again.",
            details={"current_version": row.version},
        )


async def rename_folder(db: AsyncSession, folder_id: UUID, body: api.FolderPatch) -> api.Folder:
    name = trimmed(body.name, "name", FOLDER_NAME_MAX)
    row = await _folder(db, folder_id, lock=True)
    _check_version(row, body.expected_version)
    clash = await db.scalar(
        select(Folder.id).where(Folder.name_normalized == _normalized(name), Folder.id != row.id)
    )
    if clash is not None:
        raise _taken()
    row.name, row.name_normalized = name, _normalized(name)
    row.version += 1
    row.updated_at = utcnow()
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as e:  # a concurrent create took the name between check and write
        raise _taken() from e
    return await folder_out(db, row)


async def delete_folder(db: AsyncSession, folder_id: UUID, expected_version: int) -> None:
    """Unfile every member (active and archived) and remove the folder in one transaction. The
    row lock conflicts with the FOR SHARE lock membership writes take, so a concurrent move
    either lands first (and is unfiled here) or fails with folder_missing."""
    row = await _folder(db, folder_id, lock=True)
    _check_version(row, expected_version)
    await db.execute(
        update(SessionRow)
        .where(SessionRow.folder_id == row.id)
        .values(
            folder_id=None,
            organization_version=SessionRow.organization_version + 1,
            updated_at=utcnow(),
        )
    )
    await db.delete(row)


# ---------- organization ----------


async def organize_session(
    db: AsyncSession, session_id: UUID, body: api.SessionOrganizationPatch
) -> api.Session:
    reject_explicit_nulls(body, ("title", "is_pinned", "is_archived"))
    changes = body.model_fields_set - {"expected_organization_version"}
    if not changes:
        raise invalid("Nothing to change.")
    if "folder_id" in changes and body.folder_id is not None:
        # Lock order folder → chat, the same as delete_folder, so the two can never deadlock.
        await require_folder(db, body.folder_id)
    row = await lock_session(db, session_id)
    if row.evaluation_batch_id is not None:
        raise ApiError(409, "evaluation_managed", "Experiment Lab chats are organized by the Lab.")
    if body.expected_organization_version != row.organization_version:
        raise ApiError(
            409,
            "version_conflict",
            "This chat changed; refresh and try again.",
            details={"current_organization_version": row.organization_version},
        )
    restoring = "is_archived" in changes and body.is_archived is False
    if restoring and changes - {"is_archived"}:
        raise invalid("Restore the chat first, then make the other change.")
    if row.is_archived and not restoring and changes - {"title", "is_archived"}:
        raise ApiError(409, "session_archived", "Restore this chat before changing it.")
    title = trimmed(body.title, "title", TITLE_MAX) if "title" in changes and body.title else None
    if body.is_archived and not row.is_archived:
        if (active := await active_run_id(db, session_id)) is not None:
            raise ApiError(
                409,
                "run_active",
                "Stop the running reply before archiving this chat.",
                details={"active_run_id": str(active)},
            )
    if title is not None:
        row.title, row.title_is_custom = title, True
    if "folder_id" in changes:
        row.folder_id = body.folder_id
    if body.is_pinned is not None:
        row.is_pinned = body.is_pinned
    if body.is_archived is not None:
        row.is_archived = body.is_archived
    row.organization_version += 1
    row.updated_at = utcnow()
    await db.flush()
    return session_out(row, await active_run_id(db, session_id))


# ---------- listing and search ----------


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def snippet(text: str, q: str) -> str:
    """A ≤240-char plain substring of `text` around the first match."""
    found = re.search(re.escape(q), text, re.IGNORECASE)
    start = max(0, found.start() - SNIPPET_LEAD) if found else 0
    if found and found.end() - start > SNIPPET_MAX:
        start = found.start()
    return text[start : start + SNIPPET_MAX].strip() or text[:SNIPPET_MAX]


async def list_sessions(
    db: AsyncSession,
    *,
    limit: int,
    cursor: str | None,
    q: str | None,
    folder_id: UUID | None,
    unfiled: bool,
    pinned: bool | None,
    archive: str,
) -> api.SessionList:
    if folder_id is not None and unfiled:
        raise ApiError(400, "bad_request", "Use either a folder or unfiled, not both.")
    term = (q or "").strip() or None
    if folder_id is not None:
        await _folder(db, folder_id)
    query = select(SessionRow).where(SessionRow.evaluation_batch_id.is_(None))
    if archive != "all":
        query = query.where(SessionRow.is_archived.is_(archive == "archived"))
    if folder_id is not None:
        query = query.where(SessionRow.folder_id == folder_id)
    if unfiled:
        query = query.where(SessionRow.folder_id.is_(None))
    if pinned is not None:
        query = query.where(SessionRow.is_pinned.is_(pinned))
    pattern = _like(term) if term else None
    if pattern is not None:
        message_hit = exists().where(
            Message.session_id == SessionRow.id, Message.search_text.ilike(pattern, escape="\\")
        )
        query = query.where(or_(SessionRow.title.ilike(pattern, escape="\\"), message_hit))
    filters = {"q": term, "f": str(folder_id) if folder_id else None, "u": unfiled}
    filters |= {"p": pinned, "a": archive}
    scope = "sessions:" + hashlib.sha256(json.dumps(filters).encode()).hexdigest()[:16]
    rows, nxt = await keyset_page(
        db,
        query,
        SessionRow.last_activity_at,
        SessionRow.id,
        limit=limit,
        cursor=cursor,
        scope=scope,
        descending=True,
    )
    ids = [r.id for r in rows]
    active = dict(
        (
            await db.execute(
                select(Run.session_id, Run.id).where(
                    Run.session_id.in_(ids), Run.status.in_(ACTIVE_RUN_STATUSES)
                )
            )
        ).all()
    )
    matches: dict[UUID, api.SearchMatch] = {}
    if term is not None and pattern is not None:
        lowered = term.casefold()
        need = [r.id for r in rows if lowered not in r.title.casefold()]
        for r in rows:
            if r.id not in need:
                matches[r.id] = api.SearchMatch(
                    kind="title",
                    snippet=snippet(r.title, term),
                    message_id=None,
                    message_sequence=None,
                )
        if need:
            hits = await db.execute(
                select(Message.session_id, Message.id, Message.sequence, Message.search_text)
                .where(
                    Message.session_id.in_(need),
                    Message.search_text.ilike(pattern, escape="\\"),
                )
                .order_by(Message.session_id, Message.sequence)
                .ext(distinct_on(Message.session_id))
            )
            for sid, mid, seq, text in hits.all():
                matches[sid] = api.SearchMatch(
                    kind="message",
                    snippet=snippet(text, term),
                    message_id=mid,
                    message_sequence=seq,
                )
    if term is not None:
        for r in rows:  # ILIKE matched the title where Python case folding disagreed
            matches.setdefault(
                r.id,
                api.SearchMatch(
                    kind="title",
                    snippet=r.title[:SNIPPET_MAX],
                    message_id=None,
                    message_sequence=None,
                ),
            )
    items = [
        api.SessionSummary(
            id=r.id,
            title=r.title,
            mode=r.mode,  # type: ignore[arg-type]
            selected_persona_ids=r.selected_persona_ids,
            organization_version=r.organization_version,
            folder_id=r.folder_id,
            is_pinned=r.is_pinned,
            is_archived=r.is_archived,
            last_activity_at=r.last_activity_at,
            active_run_id=active.get(r.id),
            created_at=r.created_at,
            updated_at=r.updated_at,
            match=matches.get(r.id),
        )
        for r in rows
    ]
    return api.SessionList(items=items, next_cursor=nxt)
