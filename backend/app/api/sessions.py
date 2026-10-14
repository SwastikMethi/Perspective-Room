"""Sessions API (chats)."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, IdempotencyKey, route_key
from app.api.errors import ERROR_RESPONSES
from app.domain import api
from app.services import export as export_svc
from app.services import fork as fork_svc
from app.services import sessions as svc
from app.services.idempotency import idempotent

router = APIRouter(prefix="/api/v1", tags=["sessions"], responses=ERROR_RESPONSES)


@router.post("/sessions", operation_id="createSession", status_code=201, response_model=api.Session)
async def create_session(
    request: Request, body: api.SessionCreate, key: IdempotencyKey, db: DB
) -> JSONResponse:
    state = request.app.state

    async def handler(s: AsyncSession) -> tuple[int, api.Session]:
        return 201, await svc.create_session(s, state.env, state.catalog, body)

    status, payload = await idempotent(
        db, route_key(request), key, body.model_dump(mode="json", exclude_unset=True), handler
    )
    return JSONResponse(payload, status_code=status)


@router.get("/sessions/{session_id}", operation_id="getSession", response_model=api.Session)
async def get_session(session_id: UUID, db: DB) -> api.Session:
    return await svc.get_session(db, session_id)


@router.delete("/sessions/{session_id}", operation_id="deleteSession", status_code=204)
async def delete_session(session_id: UUID, db: DB) -> Response:
    await svc.delete_session(db, session_id)
    return Response(status_code=204)


@router.patch("/sessions/{session_id}", operation_id="updateSession", response_model=api.Session)
async def update_session(
    request: Request, session_id: UUID, body: api.SessionPatch, db: DB
) -> api.Session:
    async with db.begin():
        return await svc.update_session(db, request.app.state.catalog, session_id, body)


@router.post(
    "/sessions/{session_id}/forks",
    operation_id="forkSession",
    status_code=201,
    response_model=api.ForkResult,
)
async def fork_session(
    request: Request, session_id: UUID, body: api.ForkCreate, key: IdempotencyKey, db: DB
) -> JSONResponse:
    state = request.app.state

    async def handler(s: AsyncSession) -> tuple[int, api.ForkResult]:
        return 201, await fork_svc.fork_session(s, state.env, state.catalog, session_id, body)

    status, payload = await idempotent(
        db, route_key(request), key, body.model_dump(mode="json", exclude_unset=True), handler
    )
    return JSONResponse(payload, status_code=status)


@router.get(
    "/sessions/{session_id}/export",
    operation_id="exportSession",
    response_class=Response,
    responses={
        200: {
            "content": {
                "text/markdown": {"schema": {"type": "string"}},
                "application/json": {"schema": {"type": "object", "additionalProperties": True}},
            }
        }
    },
)
async def export_session(
    request: Request,
    session_id: UUID,
    fmt: Annotated[Literal["markdown", "json"], Query(alias="format")],
    db: DB,
) -> Response:
    out = await export_svc.export_session(db, request.app.state.catalog, session_id, fmt)
    return Response(
        out.body,
        media_type=out.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{out.filename}"',
            "Cache-Control": "no-store",
        },
    )
