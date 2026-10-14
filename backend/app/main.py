"""Application factory: `uvicorn --factory app.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.api import conversation, events, sessions, system
from app.api.errors import RequestIdMiddleware, install_error_handlers
from app.api.spa import mount_spa
from app.catalog import Catalog, load_catalog
from app.persistence.db import make_engine, make_sessionmaker, ping
from app.providers.base import ProviderFailure
from app.providers.demo import DemoCoordinator, DemoGeneration
from app.services import orchestrator
from app.settings import AppEnv, get_env
from app.workers.context import RunContext, RunResult
from app.workers.notifier import Notifier
from app.workers.runner import Runner


def providers_for(env: AppEnv, catalog: Catalog) -> dict[str, Any]:
    """Demo only when explicitly chosen; live adapters land in Tasks 13-14."""
    if env.APP_PROVIDER_MODE == "demo":
        return {
            "generation": DemoGeneration(catalog.fixture_packs),
            "coordinator": DemoCoordinator(),
        }
    return {"generation": NotWired(), "coordinator": NotWired()}  # Tasks 13-14


class NotWired:
    """Live mode never falls back to demo output: it fails honestly instead."""

    name = "unavailable"

    async def structured(self, **_: Any) -> Any:
        raise ProviderFailure("provider_not_ready", "The live OpenAI adapter is not available.")

    async def web_research(self, **_: Any) -> Any:
        raise ProviderFailure("provider_not_ready", "The live OpenAI adapter is not available.")

    async def ask(self, state: Any, questions: Any) -> Any:
        raise ProviderFailure("provider_not_ready", "The live Jev adapter is not available.")


def create_app(env: AppEnv | None = None, catalog: Catalog | None = None) -> FastAPI:
    env = env or get_env()
    catalog = catalog or load_catalog(env.HANDOFF_DIR)
    engine = make_engine(env.DATABASE_URL)  # lazy: no connection until first use

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await app.state.runner.start()
        try:
            yield
        finally:
            await app.state.runner.stop()
            await engine.dispose()

    app = FastAPI(
        title="Perspective Room API",
        version="1.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
        separate_input_output_schemas=False,
        lifespan=lifespan,
    )
    app.state.env = env
    app.state.catalog = catalog
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.notifier = Notifier()

    async def db_ping() -> bool:
        return await ping(engine)

    app.state.db_ping = db_ping
    deps = orchestrator.Deps(env=env, catalog=catalog, **providers_for(env, catalog))
    app.state.deps = deps

    async def run_pipeline(ctx: RunContext) -> RunResult:
        return await orchestrator.execute(ctx, app.state.deps)

    app.state.execute = run_pipeline

    async def execute(ctx: RunContext) -> RunResult:
        return await app.state.execute(ctx)

    runner = Runner(app.state.sessionmaker, app.state.notifier, catalog, execute)
    app.state.runner = runner
    app.state.worker_alive = runner.alive
    install_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(system.router)
    app.include_router(sessions.router)
    app.include_router(conversation.router)
    app.include_router(events.router)
    mount_spa(app, env.STATIC_DIR)  # last: its catch-all must not shadow API routes
    return app
