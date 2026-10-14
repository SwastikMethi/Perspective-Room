"""Idempotency-Key handling for every create/paid-work endpoint (TRD §Submission).

The record is inserted in the same transaction as the work: identical retries return the stored
response, a reused key with a different body is 409, and a failed request stores nothing.
"""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.catalog import canonical_hash
from app.persistence.models import IdempotencyRecord

Handler = Callable[[AsyncSession], Awaitable[tuple[int, BaseModel | dict[str, Any]]]]


async def idempotent(
    db: AsyncSession, route: str, key: UUID, body: dict[str, Any], handler: Handler
) -> tuple[int, dict[str, Any]]:
    request_hash = canonical_hash(body)
    async with db.begin():
        record_id = await db.scalar(
            insert(IdempotencyRecord)
            .values(route=route, key=key, request_hash=request_hash, status_code=0, response={})
            .on_conflict_do_nothing(index_elements=["route", "key"])
            .returning(IdempotencyRecord.id)
        )
        if record_id is None:  # a committed earlier request owns this key
            existing = await db.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.route == route, IdempotencyRecord.key == key
                )
            )
            assert existing is not None
            if existing.request_hash != request_hash:
                raise ApiError(
                    409,
                    "idempotency_conflict",
                    "This Idempotency-Key was already used with a different request.",
                )
            return existing.status_code, existing.response
        status, result = await handler(db)
        payload = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        await db.execute(
            update(IdempotencyRecord)
            .where(IdempotencyRecord.id == record_id)
            .values(status_code=status, response=payload)
        )
        return status, payload
