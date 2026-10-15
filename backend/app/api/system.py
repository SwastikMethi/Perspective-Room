"""Health, persona catalog and read-only settings."""

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from app.api.errors import ERROR_RESPONSES
from app.catalog import Catalog
from app.domain.api import Health, Jev, Openai, PersonaList, ProviderCheck, Settings
from app.providers.base import ProviderFailure
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
        # G21: no rate card, so a configured cap is shown but never claimed as enforced.
        limits={
            **cat.defaults.limits.model_dump(),
            "max_session_usd": env.MAX_SESSION_USD,
            "cost_cap_enforced": False,
        },
        local_only=True,
    )


CHECK_TIMEOUT_S = 15.0


async def _check(configured: bool, key_name: str, fn: Any) -> tuple[str, str]:
    if not configured:
        return "missing", f"{key_name} is not set. Add it to .env and restart the app."
    try:
        await asyncio.wait_for(fn(), CHECK_TIMEOUT_S)
    except ProviderFailure as f:  # adapter messages are fixed, sanitized strings
        return "failed", f.message
    except TimeoutError:
        return "failed", f"No answer within {CHECK_TIMEOUT_S:.0f} seconds."
    return "ok", "Connected; the configured model is available."


@router.post(
    "/provider-checks",
    operation_id="checkProviders",
    tags=["provider-checks"],
    response_model=ProviderCheck,
)
async def check_providers(request: Request) -> ProviderCheck:
    """Explicit, user-triggered connection check: lists/retrieves models, never generates."""
    env: AppEnv = request.app.state.env
    deps = request.app.state.deps
    if env.APP_PROVIDER_MODE == "demo":
        msg = "Demo mode: no external calls are made."
        return ProviderCheck(
            openai=Openai(status="demo", message=msg), jev=Jev(status="demo", message=msg)
        )
    openai_status, openai_msg = await _check(
        env.OPENAI_API_KEY is not None,
        "OPENAI_API_KEY",
        lambda: deps.generation.check(env.OPENAI_MODEL),
    )
    jev_status, jev_msg = await _check(
        env.TYPESAFE_API_KEY is not None, "TYPESAFE_API_KEY", lambda: deps.coordinator.check()
    )
    return ProviderCheck(
        openai=Openai(status=openai_status, message=openai_msg),  # type: ignore[arg-type]
        jev=Jev(status=jev_status, message=jev_msg),  # type: ignore[arg-type]
    )
