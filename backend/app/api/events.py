"""Run event stream (doc 08 §SSE): a read-only, reconnectable view of persisted events.

Replays events after the cursor, then tails new ones; closes after a terminal event. Reconnecting
never creates provider work.
"""

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.errors import ERROR_RESPONSES, ApiError
from app.persistence.models import TERMINAL_RUN_STATUSES, Run, RunEvent

router = APIRouter(prefix="/api/v1", tags=["runs"], responses=ERROR_RESPONSES)
TERMINAL_EVENTS = {f"run.{s}" for s in TERMINAL_RUN_STATUSES}
SSE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "SSE data is RunEvent JSON; event id is RunEvent.id",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
}


def frame(e: RunEvent) -> str:
    envelope = {
        "id": str(e.id),
        "run_id": str(e.run_id),
        "type": e.type,
        "created_at": e.created_at.isoformat().replace("+00:00", "Z"),
        "data": e.data,
    }
    return f"id: {e.id}\nevent: {e.type}\ndata: {json.dumps(envelope, separators=(',', ':'))}\n\n"


@router.get(
    "/runs/{run_id}/events",
    operation_id="streamRunEvents",
    response_class=StreamingResponse,
    responses=SSE_RESPONSE,
)
async def stream_run_events(
    request: Request,
    run_id: UUID,
    after: str | None = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    state = request.app.state
    raw = last_event_id if last_event_id is not None else after
    async with state.sessionmaker() as s:
        if await s.get(Run, run_id) is None:
            raise ApiError(404, "not_found", "Run not found.")
        cursor = 0
        if raw not in (None, "", "0"):
            try:
                cursor = int(raw)
            except ValueError:
                cursor = -1
            owner = await s.scalar(select(RunEvent.run_id).where(RunEvent.id == cursor))
            if cursor <= 0 or owner != run_id:
                raise ApiError(
                    409,
                    "invalid_cursor",
                    "That event cursor is not valid; reload the run and messages.",
                )

    async def body() -> AsyncIterator[str]:
        last = cursor
        while True:
            heartbeat = float(state.catalog.defaults.timeouts_seconds.sse_heartbeat)
            seen = state.notifier.seen(run_id)
            async with state.sessionmaker() as s:
                status = await s.scalar(select(Run.status).where(Run.id == run_id))
                batch = (
                    await s.scalars(
                        select(RunEvent)
                        .where(RunEvent.run_id == run_id, RunEvent.id > last)
                        .order_by(RunEvent.id)
                        .limit(500)
                    )
                ).all()
            for e in batch:
                yield frame(e)
                last = e.id
                if e.type in TERMINAL_EVENTS:
                    return
            if not batch and status in TERMINAL_RUN_STATUSES:
                return  # already finished and fully replayed
            if len(batch) == 500:
                continue
            if not await state.notifier.wait_change(run_id, seen, heartbeat):
                yield ": heartbeat\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
