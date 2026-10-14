"""Run projection and the run event log."""

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.domain import api
from app.persistence.models import Message, Run, RunEvent
from app.services.common import utcnow

if TYPE_CHECKING:
    from app.workers.context import RunContext

EMPTY_USAGE: dict[str, Any] = {
    "input_tokens": None,
    "output_tokens": None,
    "estimated_cost_usd": None,
    "usage_incomplete": False,
}


def run_out(run: Run) -> api.Run:
    usage = {**EMPTY_USAGE, **(run.usage or {})}
    return api.Run(
        id=run.id,
        session_id=run.session_id,
        status=run.status,  # type: ignore[arg-type]
        stage=run.stage,
        published_count=run.published_count,
        requested_count=run.requested_count,
        degraded=run.degraded,
        warning_codes=list(run.warning_codes),
        error=api.Error(**run.error) if run.error else None,
        usage=api.Usage(**usage),
        session_version=run.session_version,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


async def append_event(db: AsyncSession, run: Run, type_: str, data: dict[str, Any]) -> RunEvent:
    """Append to the run's event log. Callers hold the run row lock (or created the run in this
    transaction), so one run's event IDs rise in commit order and SSE replay cannot skip one."""
    event = RunEvent(run_id=run.id, type=type_, data=data, created_at=utcnow())
    db.add(event)
    await db.flush()
    return event


async def get_run(db: AsyncSession, run_id: UUID) -> Run:
    run = await db.get(Run, run_id)
    if run is None:
        raise ApiError(404, "not_found", "Run not found.")
    return run


def error_dict(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "request_id": "",
        "details": {},
    }


async def mark_terminal(
    db: AsyncSession,
    run: Run,
    status: str,
    *,
    warnings: list[str] | None = None,
    error: dict[str, Any] | None = None,
    degraded: bool | None = None,
) -> None:
    """Move a locked run to a terminal status, record it on its round, and emit the event."""
    now = utcnow()
    run.status, run.stage = status, "finished"
    run.finished_at = run.updated_at = now
    run.warning_codes = list(dict.fromkeys([*run.warning_codes, *(warnings or [])]))
    if error is not None:
        run.error = error
    if degraded is not None:
        run.degraded = run.degraded or degraded
    if run.user_message_id is not None:
        await db.execute(
            update(Message).where(Message.id == run.user_message_id).values(round_status=status)
        )
    await db.flush()
    await append_event(
        db,
        run,
        f"run.{status}",
        {
            "run": run_out(run).model_dump(mode="json"),
            "missing_persona_ids": list(run.missing),
        },
    )


async def cancel_run(db: AsyncSession, run_id: UUID) -> Run:
    """Stop: queued runs end immediately; running runs flag cancellation for the worker."""
    async with db.begin():
        run = await db.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if run is None:
            raise ApiError(404, "not_found", "Run not found.")
        if run.status == "queued":
            await mark_terminal(db, run, "cancelled")
        elif run.status == "running":
            run.cancel_requested = True
            run.status, run.stage = "cancelling", "cancelling"
            run.updated_at = utcnow()
            await db.flush()
            await append_event(
                db,
                run,
                "run.stage",
                {"stage": "cancelling", "persona_id": None, "status_key": "stopping"},
            )
    return run


async def set_stage(
    ctx: "RunContext", stage: str, persona_id: str | None = None, status_key: str | None = None
) -> None:
    """Record real progress (never simulated typing) and refresh the heartbeat."""
    async with ctx.sessionmaker() as s, s.begin():
        run = await s.scalar(select(Run).where(Run.id == ctx.run_id).with_for_update())
        if run is None or run.status != "running":
            return
        run.stage = stage
        run.heartbeat_at = run.updated_at = utcnow()
        await s.flush()
        await append_event(
            s,
            run,
            "run.stage",
            {"stage": stage, "persona_id": persona_id, "status_key": status_key or stage},
        )
    await ctx.notifier.notify_run(ctx.run_id)


async def update_run(ctx: "RunContext", **values: Any) -> None:
    async with ctx.sessionmaker() as s, s.begin():
        await s.execute(
            update(Run).where(Run.id == ctx.run_id).values(updated_at=utcnow(), **values)
        )
