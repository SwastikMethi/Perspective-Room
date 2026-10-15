"""Workspace: chat history listing/search, organization edits and folders."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, IdempotencyKey, route_key
from app.api.errors import ERROR_RESPONSES
from app.domain import api
from app.services import workspace as svc
from app.services.idempotency import idempotent

router = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get(
    "/sessions", operation_id="listSessions", tags=["sessions"], response_model=api.SessionList
)
async def list_sessions(
    db: DB,
    cursor: str | None = None,
    limit: Limit = 30,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    folder_id: UUID | None = None,
    unfiled: bool = False,
    pinned: bool | None = None,
    archive: Literal["active", "archived", "all"] = "active",
) -> api.SessionList:
    return await svc.list_sessions(
        db,
        limit=limit,
        cursor=cursor,
        q=q,
        folder_id=folder_id,
        unfiled=unfiled,
        pinned=pinned,
        archive=archive,
    )


@router.patch(
    "/sessions/{session_id}/organization",
    operation_id="updateSessionOrganization",
    tags=["sessions"],
    response_model=api.Session,
)
async def update_session_organization(
    session_id: UUID, body: api.SessionOrganizationPatch, db: DB
) -> api.Session:
    async with db.begin():
        return await svc.organize_session(db, session_id, body)


@router.get("/folders", operation_id="listFolders", tags=["folders"], response_model=api.FolderList)
async def list_folders(db: DB, cursor: str | None = None, limit: Limit = 30) -> api.FolderList:
    return await svc.list_folders(db, limit, cursor)


@router.post(
    "/folders",
    operation_id="createFolder",
    tags=["folders"],
    status_code=201,
    response_model=api.Folder,
)
async def create_folder(
    request: Request, body: api.FolderCreate, key: IdempotencyKey, db: DB
) -> JSONResponse:
    async def handler(s: AsyncSession) -> tuple[int, api.Folder]:
        return 201, await svc.create_folder(s, body)

    status, payload = await idempotent(
        db, route_key(request), key, body.model_dump(mode="json"), handler
    )
    return JSONResponse(payload, status_code=status)


@router.get(
    "/folders/{folder_id}", operation_id="getFolder", tags=["folders"], response_model=api.Folder
)
async def get_folder(folder_id: UUID, db: DB) -> api.Folder:
    return await svc.get_folder(db, folder_id)


@router.patch(
    "/folders/{folder_id}", operation_id="updateFolder", tags=["folders"], response_model=api.Folder
)
async def update_folder(folder_id: UUID, body: api.FolderPatch, db: DB) -> api.Folder:
    async with db.begin():
        return await svc.rename_folder(db, folder_id, body)


@router.delete(
    "/folders/{folder_id}", operation_id="deleteFolder", tags=["folders"], status_code=204
)
async def delete_folder(
    folder_id: UUID, db: DB, expected_version: Annotated[int, Query(ge=1)]
) -> Response:
    async with db.begin():
        await svc.delete_folder(db, folder_id, expected_version)
    return Response(status_code=204)
