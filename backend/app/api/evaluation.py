"""Experiment Lab API (doc 09). Reveal-bearing reads are never cached."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, IdempotencyKey, route_key
from app.api.errors import ERROR_RESPONSES
from app.domain import api
from app.services import evaluation as svc
from app.services import runs as run_svc
from app.services.idempotency import idempotent

router = APIRouter(prefix="/api/v1", tags=["evaluations"], responses=ERROR_RESPONSES)
Limit = Annotated[int, Query(ge=1, le=100)]
NO_STORE = {"Cache-Control": "no-store"}


@router.get(
    "/evaluation-cases", operation_id="listEvaluationCases", response_model=api.EvaluationCaseList
)
async def list_cases(request: Request) -> api.EvaluationCaseList:
    return svc.list_cases(request.app.state.catalog)


@router.post(
    "/evaluations", operation_id="createEvaluation", status_code=202, response_model=api.Evaluation
)
async def create_evaluation(
    request: Request, body: api.EvaluationCreate, key: IdempotencyKey, db: DB
) -> JSONResponse:
    state = request.app.state

    async def handler(s: AsyncSession) -> tuple[int, api.Evaluation]:
        return 202, await svc.create_batch(s, state.env, state.catalog, body)

    status, payload = await idempotent(
        db, route_key(request), key, body.model_dump(mode="json"), handler
    )
    state.lab.wake()
    return JSONResponse(payload, status_code=status)


@router.get("/evaluations", operation_id="listEvaluations", response_model=api.EvaluationList)
async def list_evaluations(
    db: DB, cursor: str | None = None, limit: Limit = 30
) -> api.EvaluationList:
    return await svc.list_batches(db, limit, cursor)


@router.get(
    "/evaluations/{evaluation_id}", operation_id="getEvaluation", response_model=api.Evaluation
)
async def get_evaluation(evaluation_id: UUID, db: DB) -> api.Evaluation:
    return svc.batch_out(await svc.get_batch(db, evaluation_id))


@router.post(
    "/evaluations/{evaluation_id}/cancel",
    operation_id="cancelEvaluation",
    response_model=api.Evaluation,
)
async def cancel_evaluation(request: Request, evaluation_id: UUID, db: DB) -> api.Evaluation:
    state = request.app.state
    async with db.begin():
        out, active = await svc.cancel_batch(db, evaluation_id)
    for run_id in active:  # stop the child that is running now; no new turns start
        await run_svc.cancel_run(db, run_id)
        await state.notifier.notify_run(run_id)
        state.runner.cancel_signal(run_id)
    state.lab.wake()
    return out


@router.get(
    "/evaluations/{evaluation_id}/trials", operation_id="listTrials", response_model=api.TrialList
)
async def list_trials(
    evaluation_id: UUID,
    db: DB,
    response: Response,
    cursor: str | None = None,
    limit: Limit = 30,
    reveal: bool = False,
) -> api.TrialList:
    response.headers["Cache-Control"] = "no-store"
    async with db.begin():
        return await svc.list_trials(db, evaluation_id, reveal=reveal, limit=limit, cursor=cursor)


@router.post(
    "/evaluations/{evaluation_id}/ratings",
    operation_id="createRating",
    status_code=201,
    response_model=api.Rating,
)
async def create_rating(
    request: Request, evaluation_id: UUID, body: api.RatingCreate, key: IdempotencyKey, db: DB
) -> JSONResponse:
    async def handler(s: AsyncSession) -> tuple[int, api.Rating]:
        return 201, await svc.create_rating(s, evaluation_id, body)

    status, payload = await idempotent(
        db, route_key(request), key, body.model_dump(mode="json"), handler
    )
    return JSONResponse(payload, status_code=status)


@router.get(
    "/evaluations/{evaluation_id}/results",
    operation_id="getEvaluationResults",
    response_model=api.EvaluationResults,
)
async def get_results(
    evaluation_id: UUID, db: DB, response: Response, reveal: bool = False
) -> api.EvaluationResults:
    response.headers["Cache-Control"] = "no-store"
    async with db.begin():
        return await svc.results(db, evaluation_id, reveal=reveal)


@router.get(
    "/evaluations/{evaluation_id}/export",
    operation_id="exportEvaluation",
    response_class=Response,
    responses={
        200: {
            "content": {
                "text/csv": {"schema": {"type": "string"}},
                "application/json": {"schema": {"type": "object", "additionalProperties": True}},
            }
        }
    },
)
async def export_evaluation(
    request: Request,
    evaluation_id: UUID,
    fmt: Annotated[Literal["json", "csv"], Query(alias="format")],
    db: DB,
) -> Response:
    async with db.begin():
        body, media = await svc.export_batch(db, request.app.state.catalog, evaluation_id, fmt)
    name = f"perspective-room-evaluation-{str(evaluation_id)[:8]}.{fmt}"
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}"', **NO_STORE},
    )
