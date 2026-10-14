"""Small helpers shared by services: validation shortcuts and row locking."""

import base64
import binascii
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.persistence.models import ACTIVE_RUN_STATUSES, Run, Session


def utcnow() -> datetime:
    return datetime.now(UTC)


def invalid(message: str, **details: object) -> ApiError:
    return ApiError(422, "validation_error", message, details=dict(details))


def reject_explicit_nulls(model: BaseModel, fields: Iterable[str]) -> None:
    """Optional-but-not-nullable contract fields may be omitted, never sent as null."""
    for name in fields:
        if name in model.model_fields_set and getattr(model, name) is None:
            raise invalid(f"{name} cannot be null", field=name)


def trimmed(value: str, field: str, max_len: int) -> str:
    text = value.strip()
    if not text:
        raise invalid(f"{field} cannot be blank", field=field)
    if len(text) > max_len:
        raise invalid(f"{field} is longer than {max_len} characters", field=field)
    return text


def unique(values: list[str], field: str) -> list[str]:
    if len(set(values)) != len(values):
        raise invalid(f"{field} contains duplicates", field=field)
    return values


async def lock_session(db: AsyncSession, session_id: UUID) -> Session:
    row = await db.scalar(select(Session).where(Session.id == session_id).with_for_update())
    if row is None:
        raise ApiError(404, "not_found", "Chat not found.")
    return row


async def active_run_id(db: AsyncSession, session_id: UUID) -> UUID | None:
    return await db.scalar(
        select(Run.id).where(Run.session_id == session_id, Run.status.in_(ACTIVE_RUN_STATUSES))
    )


def encode_cursor(data: dict[str, object], scope: str) -> str:
    """Opaque cursor bound to its scope (session, or query + filters)."""
    raw = json.dumps({**data, "scope": scope}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, scope: str) -> dict[str, Any]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, binascii.Error) as e:
        raise ApiError(400, "bad_request", "That cursor is not valid.") from e
    if not isinstance(data, dict) or data.get("scope") != scope:
        raise ApiError(400, "bad_request", "That cursor belongs to a different list.")
    return data
