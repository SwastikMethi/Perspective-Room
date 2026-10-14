"""Saved ideas (idea cards) and message feedback."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, IdempotencyKey, route_key
from app.api.errors import ERROR_RESPONSES
from app.domain import api
from app.services import ideas as svc
from app.services.idempotency import idempotent

router = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get(
    "/sessions/{session_id}/idea-cards",
    operation_id="listIdeaCards",
    tags=["sessions"],
    response_model=api.IdeaCardList,
)
async def list_idea_cards(
    session_id: UUID, db: DB, cursor: str | None = None, limit: Limit = 30
) -> api.IdeaCardList:
    return await svc.list_cards(db, session_id, limit, cursor)


@router.post(
    "/sessions/{session_id}/idea-cards",
    operation_id="createIdeaCard",
    tags=["sessions"],
    status_code=201,
    response_model=api.IdeaCard,
)
async def create_idea_card(
    request: Request, session_id: UUID, body: api.IdeaCardCreate, key: IdempotencyKey, db: DB
) -> JSONResponse:
    async def handler(s: AsyncSession) -> tuple[int, api.IdeaCard]:
        return 201, await svc.create_card(s, session_id, body)

    status, payload = await idempotent(
        db, route_key(request), key, body.model_dump(mode="json"), handler
    )
    return JSONResponse(payload, status_code=status)


@router.patch(
    "/idea-cards/{card_id}",
    operation_id="updateIdeaCard",
    tags=["idea-cards"],
    response_model=api.IdeaCard,
)
async def update_idea_card(card_id: UUID, body: api.IdeaCardPatch, db: DB) -> api.IdeaCard:
    return await svc.update_card(db, card_id, body)


@router.delete(
    "/idea-cards/{card_id}", operation_id="deleteIdeaCard", tags=["idea-cards"], status_code=204
)
async def delete_idea_card(card_id: UUID, db: DB) -> Response:
    await svc.delete_card(db, card_id)
    return Response(status_code=204)


@router.post(
    "/messages/{message_id}/feedback",
    operation_id="setFeedback",
    tags=["messages"],
    response_model=api.Feedback,
)
async def set_feedback(message_id: UUID, body: api.FeedbackCreate, db: DB) -> api.Feedback:
    return await svc.set_feedback(db, message_id, body)
