"""Sessions (= chats): creation, projection, deletion."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.catalog import Catalog
from app.domain import api
from app.persistence.models import Folder, IdeaRevision
from app.persistence.models import Session as SessionRow
from app.services.common import (
    active_run_id,
    lock_session,
    reject_explicit_nulls,
    trimmed,
    unique,
    utcnow,
)
from app.settings import AppEnv

TITLE_MAX = 120
AUTO_TITLE_CHARS = 60


def auto_title(idea: str) -> str:
    """First line of the idea, cut at a word boundary (G22). Replaced once by the intake title."""
    line = idea.strip().splitlines()[0].strip()
    if len(line) <= AUTO_TITLE_CHARS:
        return line
    cut = line[:AUTO_TITLE_CHARS].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return (cut or line[:AUTO_TITLE_CHARS]) + "…"


def require_provider(env: AppEnv) -> None:
    if env.APP_PROVIDER_MODE == "live" and not env.openai_configured:
        raise ApiError(
            503,
            "provider_not_ready",
            "OpenAI is not configured. Set OPENAI_API_KEY and restart, or use demo mode.",
            retryable=False,
        )


def session_out(row: SessionRow, active: UUID | None) -> api.Session:
    return api.Session(
        id=row.id,
        title=row.title,
        mode=row.mode,  # type: ignore[arg-type]
        selected_persona_ids=row.selected_persona_ids,
        version=row.version,
        brief=api.Brief(**row.brief),
        settings=api.SessionSettings(**row.settings),
        active_run_id=active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        organization_version=row.organization_version,
        folder_id=row.folder_id,
        is_pinned=row.is_pinned,
        is_archived=row.is_archived,
        last_activity_at=row.last_activity_at,
        origin_session_id=row.origin_session_id,
    )


async def require_folder(db: AsyncSession, folder_id: UUID) -> None:
    """Lock the folder row so a concurrent delete cannot leave a dangling membership."""
    found = await db.scalar(
        select(Folder.id).where(Folder.id == folder_id).with_for_update(read=True)
    )
    if found is None:
        raise ApiError(409, "folder_missing", "That folder no longer exists.")


async def create_session(
    db: AsyncSession, env: AppEnv, catalog: Catalog, body: api.SessionCreate
) -> api.Session:
    require_provider(env)
    reject_explicit_nulls(body, ("title", "mode", "selected_persona_ids", "settings"))
    idea = trimmed(body.idea, "idea", catalog.defaults.limits.user_message_chars)
    title = trimmed(body.title, "title", TITLE_MAX) if body.title is not None else auto_title(idea)
    selected = unique(
        list(body.selected_persona_ids or catalog.default_selection), "selected_persona_ids"
    )
    defaults = catalog.defaults
    settings = (
        body.settings.model_dump()
        if body.settings
        else {
            "research_policy": defaults.research_policy,
            "auto_contributions": defaults.limits.auto_contributions,
        }
    )
    if body.folder_id is not None:
        await require_folder(db, body.folder_id)
    now = utcnow()
    row = SessionRow(
        title=title,
        title_is_custom=body.title is not None,
        folder_id=body.folder_id,
        mode=body.mode or defaults.default_mode,
        selected_persona_ids=selected,
        settings=settings,
        brief={"idea": idea, "goal": None, "constraints": [], "revision": 1},
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    db.add(
        IdeaRevision(
            session_id=row.id, revision=1, idea=idea, goal=None, constraints=[], author_type="user"
        )
    )
    await db.flush()
    await db.refresh(row)
    return session_out(row, None)


async def get_session(db: AsyncSession, session_id: UUID) -> api.Session:
    row = await db.get(SessionRow, session_id)
    if row is None:
        raise ApiError(404, "not_found", "Chat not found.")
    return session_out(row, await active_run_id(db, session_id))


async def delete_session(db: AsyncSession, session_id: UUID) -> None:
    async with db.begin():
        row = await lock_session(db, session_id)
        if row.evaluation_batch_id is not None:
            raise ApiError(
                409,
                "evaluation_managed",
                "This chat belongs to an Experiment Lab batch; delete the batch instead.",
            )
        if (active := await active_run_id(db, session_id)) is not None:
            raise ApiError(
                409,
                "run_active",
                "Stop the running reply before deleting this chat.",
                details={"active_run_id": str(active)},
            )
        await db.delete(row)


async def update_session(
    db: AsyncSession, catalog: Catalog, session_id: UUID, body: api.SessionPatch
) -> api.Session:
    """Context edits (participants, settings, brief). Blocked during runs; brief changes create an
    immutable revision. Organization fields use their own endpoint and version."""
    reject_explicit_nulls(body, ("selected_persona_ids", "settings", "brief"))
    changes = body.model_fields_set - {"expected_version"}
    if not changes:
        raise ApiError(422, "validation_error", "Nothing to change.")
    row = await lock_session(db, session_id)
    if row.evaluation_batch_id is not None:
        raise ApiError(409, "evaluation_managed", "Experiment Lab chats are driven by the Lab.")
    if row.is_archived:
        raise ApiError(409, "session_archived", "Restore this chat before changing it.")
    if body.expected_version != row.version:
        raise ApiError(
            409,
            "version_conflict",
            "This chat changed; refresh and try again.",
            details={"current_version": row.version},
        )
    if (active := await active_run_id(db, session_id)) is not None:
        raise ApiError(
            409,
            "run_active",
            "Wait for the running reply or stop it first.",
            details={"active_run_id": str(active)},
        )
    if body.selected_persona_ids is not None:
        row.selected_persona_ids = unique(list(body.selected_persona_ids), "selected_persona_ids")
    if body.settings is not None:
        row.settings = body.settings.model_dump()
    if body.brief is not None:
        idea = trimmed(body.brief.idea, "idea", catalog.defaults.limits.user_message_chars)
        goal = body.brief.goal.strip() or None if body.brief.goal is not None else None
        constraints = [c.strip() for c in body.brief.constraints if c.strip()]
        current = row.brief
        if (idea, goal, constraints) != (
            current["idea"],
            current.get("goal"),
            current.get("constraints", []),
        ):
            revision = int(current["revision"]) + 1
            db.add(
                IdeaRevision(
                    session_id=row.id,
                    revision=revision,
                    idea=idea,
                    goal=goal,
                    constraints=constraints,
                    author_type="user",
                )
            )
            row.brief = {
                "idea": idea,
                "goal": goal,
                "constraints": constraints,
                "revision": revision,
            }
    row.version += 1
    row.updated_at = utcnow()
    await db.flush()
    return session_out(row, None)
