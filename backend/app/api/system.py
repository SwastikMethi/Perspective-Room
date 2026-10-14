"""Health, persona catalog and read-only settings."""

from fastapi import APIRouter, Request

from app.api.errors import ERROR_RESPONSES
from app.catalog import Catalog
from app.domain.api import Health, PersonaList, Settings
from app.settings import AppEnv

router = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)


@router.get("/health", operation_id="health", tags=["health"], response_model=Health)
async def health(request: Request) -> Health:
    state = request.app.state
    try:
        db_ok = bool(await state.db_ping())
    except Exception:
        db_ok = False
    worker_ok = bool(state.worker_alive())
    return Health(
        status="ok" if db_ok and worker_ok else "degraded",
        database="ok" if db_ok else "failed",
        worker="ok" if worker_ok else "failed",
        version=request.app.version,
    )


@router.get("/personas", operation_id="listPersonas", tags=["personas"], response_model=PersonaList)
async def list_personas(request: Request) -> PersonaList:
    cat: Catalog = request.app.state.catalog
    return PersonaList(
        items=[cat.personas[p] for p in cat.order], default_selection=cat.default_selection
    )


@router.get("/settings", operation_id="getSettings", tags=["settings"], response_model=Settings)
async def get_settings(request: Request) -> Settings:
    env: AppEnv = request.app.state.env
    cat: Catalog = request.app.state.catalog
    return Settings(
        provider_mode=env.APP_PROVIDER_MODE,
        openai_configured=env.openai_configured,
        jev_configured=env.jev_configured,
        openai_model=env.OPENAI_MODEL,
        research_model=env.OPENAI_RESEARCH_MODEL,
        jev_model=env.JEV_MODEL,
        limits=cat.defaults.limits.model_dump(),
        local_only=True,
    )
