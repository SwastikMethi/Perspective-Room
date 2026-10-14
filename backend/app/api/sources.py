"""Research sources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DB
from app.api.errors import ERROR_RESPONSES
from app.domain import api
from app.services import ideas as svc

router = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get(
    "/sessions/{session_id}/sources",
    operation_id="listSources",
    tags=["sessions"],
    response_model=api.SourceList,
)
async def list_sources(
    session_id: UUID, db: DB, cursor: str | None = None, limit: Limit = 30
) -> api.SourceList:
    return await svc.list_sources(db, session_id, limit, cursor)


@router.get(
    "/sources/{source_id}", operation_id="getSource", tags=["sources"], response_model=api.Source
)
async def get_source(source_id: UUID, db: DB) -> api.Source:
    return await svc.get_source(db, source_id)
