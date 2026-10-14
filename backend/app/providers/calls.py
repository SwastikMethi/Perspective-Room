"""The one provider-call policy (TRD §Cancellation and failures, G17).

Every call: Stop check → attempt ceiling → a committed `provider_calls` row BEFORE the request →
per-purpose timeout → classification. Only 429/503/529 and connection-before-send are retried,
once. Timeouts and 500/502/504 have uncertain outcomes: recorded as unknown usage, never resent.
SDK/client retries are disabled so retries never multiply.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import update

from app.persistence.models import ProviderCall, Run
from app.providers.base import (
    Incomplete,
    ProviderFailure,
    Refused,
    ResearchRaw,
    Structured,
    Usage,
)
from app.services.common import utcnow
from app.workers.context import DeadlineExceeded, RunCancelled, RunContext

T = TypeVar("T")

TIMEOUT_FOR = {
    "intake": "generation",
    "draft": "generation",
    "repair": "generation",
    "summary": "generation",
    "memory": "generation",
    "research_normalize": "generation",
    "research_search": "research",
    "route": "jev",
    "assess": "jev",
}


MAX_RETRY_WAIT = 10.0  # a longer provider hint ends the attempt instead of stalling the turn


class AttemptsExhausted(Exception):
    """The run used its provider-attempt ceiling."""


def classify_http(
    status: int, body: str = "", *, retry_after: str | None = None, request_id: str | None = None
) -> ProviderFailure:
    """Map an HTTP status to the retry policy. Body text is never surfaced to users."""

    def wait() -> float | None:
        try:
            return float(retry_after) if retry_after is not None else None
        except ValueError:
            return None

    if status in (429, 503, 529):
        return ProviderFailure(
            "transient",
            f"Provider busy ({status}).",
            retryable=True,
            retry_after=wait(),
            status=status,
            request_id=request_id,
        )
    if status in (401, 403):
        return ProviderFailure(
            "provider_not_ready",
            "The provider rejected the configured API key.",
            status=status,
            request_id=request_id,
        )
    if status == 404 and "model" in body:
        return ProviderFailure(
            "model_unavailable",
            "The configured model is not available to this account.",
            status=status,
            request_id=request_id,
        )
    if status in (400, 404, 409, 413, 422):
        return ProviderFailure(
            "invalid_request",
            f"The provider rejected the request ({status}).",
            status=status,
            request_id=request_id,
        )
    return ProviderFailure(
        "provider_error",
        f"Provider error ({status}); outcome unknown.",
        usage_unknown=True,
        status=status,
        request_id=request_id,
    )


def _count(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def usage_of(result: Any) -> Usage:
    if isinstance(result, Structured | Refused | Incomplete | ResearchRaw):
        return result.usage
    if isinstance(result, dict) and isinstance(result.get("usage"), dict):  # Jev envelope
        u = result["usage"]  # untrusted: only non-negative integers are kept
        return Usage(_count(u.get("input_tokens")), _count(u.get("output_tokens")))
    return Usage()


def _status_of(result: Any) -> str:
    if isinstance(result, Refused):
        return "refused"
    if isinstance(result, Incomplete):
        return "incomplete"
    return "ok"


async def _reserve_attempt(ctx: RunContext) -> int:
    limit = int(ctx.snapshot["limits"]["provider_attempts_per_turn"])
    async with ctx.sessionmaker() as s, s.begin():
        used = await s.scalar(
            update(Run)
            .where(Run.id == ctx.run_id, Run.attempts < limit)
            .values(attempts=Run.attempts + 1)
            .returning(Run.attempts)
        )
    if used is None:
        raise AttemptsExhausted
    return int(used)


async def _start_row(ctx: RunContext, **fields: Any) -> UUID:
    async with ctx.sessionmaker() as s, s.begin():
        row = ProviderCall(
            run_id=ctx.run_id,
            session_id=ctx.session_id,
            status="started",
            started_at=utcnow(),
            **fields,
        )
        s.add(row)
        await s.flush()
        return row.id


async def _finish_row(
    ctx: RunContext,
    call_id: UUID,
    started: float,
    status: str,
    *,
    provider: str,
    usage: Usage | None = None,
    unknown: bool = False,
    model: str | None = None,
    response_id: str | None = None,
    request_id: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> None:
    u = usage or Usage()
    values: dict[str, Any] = {
        "status": status,
        "finished_at": utcnow(),
        "usage_unknown": unknown,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "reasoning_tokens": u.reasoning_tokens,
        "cached_tokens": u.cached_tokens,
        "response_id": response_id,
        "request_id": request_id,
        "diagnostics": diagnostics or {},
    }
    if model:
        values["model"] = model
    async with ctx.sessionmaker() as s, s.begin():
        await s.execute(update(ProviderCall).where(ProviderCall.id == call_id).values(**values))
        run = await s.get(Run, ctx.run_id, with_for_update=True)
        if run is not None:
            totals = dict(run.usage or {})
            for key, add in (("input_tokens", u.input_tokens), ("output_tokens", u.output_tokens)):
                if add is not None:
                    totals[key] = (totals.get(key) or 0) + add
            missing = (
                provider != "demo"
                and status in ("ok", "refused", "incomplete")
                and u.input_tokens is None
            )
            totals["usage_incomplete"] = bool(totals.get("usage_incomplete")) or unknown or missing
            totals.setdefault("estimated_cost_usd", None)  # G21: no rate card → unknown
            run.usage = totals


async def call_provider[T](
    ctx: RunContext,
    *,
    purpose: str,
    provider: str,
    model: str,
    fn: Callable[[], Awaitable[T]],
    template_hash: str | None = None,
    profile_hash: str | None = None,
) -> T:
    retries_left = int(ctx.snapshot["limits"]["provider_retries"])
    timeout = float(ctx.snapshot["timeouts"][TIMEOUT_FOR.get(purpose, "generation")])
    attempt = 0
    while True:
        await ctx.check_db()
        await _reserve_attempt(ctx)
        attempt += 1
        call_id = await _start_row(
            ctx,
            purpose=purpose,
            attempt=attempt,
            provider=provider,
            model=model,
            template_hash=template_hash,
            profile_hash=profile_hash,
        )
        started = time.monotonic()
        try:
            result = await ctx.call(asyncio.wait_for(fn(), timeout))
        except TimeoutError:
            await _finish_row(
                ctx,
                call_id,
                started,
                "timeout",
                provider=provider,
                unknown=True,
                diagnostics={"code": "timeout", "seconds": timeout},
            )
            raise ProviderFailure(
                "timeout",
                "The provider did not answer in time; outcome unknown, not resent.",
                usage_unknown=True,
            ) from None
        except asyncio.CancelledError:  # the run task itself is being torn down
            await asyncio.shield(
                _finish_row(
                    ctx,
                    call_id,
                    started,
                    "cancelled",
                    provider=provider,
                    unknown=True,
                    diagnostics={"code": "cancelled"},
                )
            )
            raise
        except (RunCancelled, DeadlineExceeded):
            await _finish_row(
                ctx,
                call_id,
                started,
                "cancelled",
                provider=provider,
                unknown=True,
                diagnostics={"code": "cancelled"},
            )
            raise
        except ProviderFailure as f:
            await _finish_row(
                ctx,
                call_id,
                started,
                "error",
                provider=provider,
                unknown=f.usage_unknown,
                request_id=f.request_id,
                diagnostics={"code": f.code, "status": f.status},
            )
            wait = f.retry_after if f.retry_after is not None else 1.0
            if f.retryable and retries_left > 0 and wait <= MAX_RETRY_WAIT:
                retries_left -= 1
                await asyncio.sleep(wait)
                continue
            raise
        except Exception as e:  # adapter bug or unexpected SDK error: unknown outcome
            await _finish_row(
                ctx,
                call_id,
                started,
                "error",
                provider=provider,
                unknown=True,
                diagnostics={"code": "unexpected", "type": type(e).__name__},
            )
            raise ProviderFailure(
                "provider_error", "Unexpected provider error.", usage_unknown=True
            ) from e
        await _finish_row(
            ctx,
            call_id,
            started,
            _status_of(result),
            provider=provider,
            usage=usage_of(result),
            model=getattr(result, "model", None)
            or (result.get("model") if isinstance(result, dict) else None),
            response_id=getattr(result, "response_id", None),
        )
        return result
