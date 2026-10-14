"""Request dependencies."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


DB = Annotated[AsyncSession, Depends(get_db)]
IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


def route_key(request: Request) -> str:
    """Idempotency scope: method plus concrete path (keys are scoped per resource)."""
    return f"{request.method} {request.url.path}"
