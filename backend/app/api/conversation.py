"""Conversation API: turns, transcript, runs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, IdempotencyKey, route_key
from app.api.errors import ERROR_RESPONSES
from app.domain import api
from app.services import fork as fork_svc
from app.services import runs as run_svc
from app.services import transcript
from app.services.idempotency import idempotent
from app.services.turns import submit_turn

router = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)
Limit = Annotated[int, Query(ge=1, le=100)]


@router.post(
    "/sessions/{session_id}/turns",
    operation_id="createTurn",
    tags=["sessions"],
    status_code=202,
    response_model=api.Run,
)
async def create_turn(
    request: Request, session_id: UUID, body: api.TurnCreate, key: IdempotencyKey, db: DB
) -> JSONResponse:
    state = request.app.state

    async def handler(s: AsyncSession) -> tuple[int, api.Run]:
        return 202, await submit_turn(s, state.env, state.catalog, session_id, body)

    status, payload = await idempotent(
        db, route_key(request), key, body.model_dump(mode="json"), handler
    )
    state.notifier.wake_worker()
    return JSONResponse(payload, status_code=status)


@router.get(
    "/sessions/{session_id}/messages",
    operation_id="listMessages",
    tags=["sessions"],
    response_model=api.MessageList,
)
async def list_messages(
    session_id: UUID,
    db: DB,
    cursor: str | None = None,
    limit: Limit = 30,
    around_message_id: UUID | None = None,
) -> api.MessageList:
    return await transcript.list_messages(db, session_id, limit, cursor, around_message_id)


@router.get("/runs/{run_id}", operation_id="getRun", tags=["runs"], response_model=api.Run)
async def get_run(run_id: UUID, db: DB) -> api.Run:
    return run_svc.run_out(await run_svc.get_run(db, run_id))


@router.post(
    "/runs/{run_id}/cancel", operation_id="cancelRun", tags=["runs"], response_model=api.Run
)
async def cancel_run(request: Request, run_id: UUID, db: DB) -> api.Run:
    run = await run_svc.cancel_run(db, run_id)
    state = request.app.state
    await state.notifier.notify_run(run_id)
    state.runner.cancel_signal(run_id)
    return run_svc.run_out(run)


@router.post(
    "/runs/{run_id}/retry",
    operation_id="retryRun",
    tags=["runs"],
    status_code=202,
    response_model=api.Run,
)
async def retry_run(
    request: Request, run_id: UUID, body: api.RetryCreate, key: IdempotencyKey, db: DB
) -> JSONResponse:
    state = request.app.state

    async def handler(s: AsyncSession) -> tuple[int, api.Run]:
        return 202, await fork_svc.retry_run(s, state.env, run_id, body)

    status, payload = await idempotent(
        db, route_key(request), key, body.model_dump(mode="json"), handler
    )
    state.notifier.wake_worker()
    return JSONResponse(payload, status_code=status)
