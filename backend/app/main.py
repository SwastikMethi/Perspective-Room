"""Application factory: `uvicorn --factory app.main:create_app`."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.api import conversation, evaluation, events, ideas, sessions, sources, system, workspace
from app.api.errors import RequestIdMiddleware, install_error_handlers
from app.api.security import SecurityMiddleware
from app.api.spa import mount_spa
from app.catalog import Catalog, load_catalog
from app.persistence.db import make_engine, make_sessionmaker, ping
from app.providers.base import ProviderFailure
from app.providers.demo import DemoCoordinator, DemoGeneration
from app.providers.jev_adapter import JevCoordinator
from app.providers.openai_adapter import OpenAIGeneration
from app.services import orchestrator
from app.settings import AppEnv, get_env
from app.workers.context import RunContext, RunResult
from app.workers.lab import LabScheduler
from app.workers.notifier import Notifier
from app.workers.runner import Runner


def providers_for(env: AppEnv, catalog: Catalog) -> dict[str, Any]:
    """Demo only when explicitly chosen (G3); live mode never falls back to demo output."""
    if env.APP_PROVIDER_MODE == "demo":
        return {
            "generation": DemoGeneration(catalog.fixture_packs),
            "coordinator": DemoCoordinator(),
        }
    generation: Any = (
        OpenAIGeneration(env.OPENAI_API_KEY.get_secret_value(), base_url=env.OPENAI_BASE_URL)
        if env.OPENAI_API_KEY
        else NotWired()
    )
    coordinator: Any = (
        JevCoordinator(env.TYPESAFE_API_KEY.get_secret_value(), env.JEV_MODEL)
        if env.TYPESAFE_API_KEY
        else NotWired()  # G5: Jev-guided turns use the labeled fixed-order fallback
    )
    return {"generation": generation, "coordinator": coordinator}


class NotWired:
    """Live mode never falls back to demo output: it fails honestly instead."""

    name = "unavailable"

    async def structured(self, **_: Any) -> Any:
        raise ProviderFailure("provider_not_ready", "The live OpenAI adapter is not available.")

    async def web_research(self, **_: Any) -> Any:
        raise ProviderFailure("provider_not_ready", "The live OpenAI adapter is not available.")

    async def ask(self, state: Any, questions: Any, model: str | None = None) -> Any:
        raise ProviderFailure("provider_not_ready", "The live Jev adapter is not available.")


def create_app(env: AppEnv | None = None, catalog: Catalog | None = None) -> FastAPI:
    env = env or get_env()
    catalog = catalog or load_catalog(env.HANDOFF_DIR)
    engine = make_engine(env.DATABASE_URL)  # lazy: no connection until first use

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await app.state.runner.start()  # recovery first: the Lab never resumes uncertain work
        await app.state.lab.start()
        try:
            yield
        finally:
            await app.state.lab.stop()
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
    deps = orchestrator.Deps(
        env=env,
        catalog=catalog,
        gen_slots=asyncio.Semaphore(catalog.defaults.limits.concurrent_generations),
        **providers_for(env, catalog),
    )
    app.state.deps = deps

    async def run_pipeline(ctx: RunContext) -> RunResult:
        return await orchestrator.execute(ctx, app.state.deps)

    app.state.execute = run_pipeline

    async def execute(ctx: RunContext) -> RunResult:
        return await app.state.execute(ctx)

    runner = Runner(app.state.sessionmaker, app.state.notifier, catalog, execute)
    app.state.runner = runner
    app.state.worker_alive = runner.alive
    app.state.lab = LabScheduler(
        app.state.sessionmaker,
        lambda: app.state.env,
        catalog,
        app.state.notifier,
        runner.cancel_signal,
    )
    install_error_handlers(app)
    app.add_middleware(SecurityMiddleware, env=env)
    app.add_middleware(RequestIdMiddleware)  # outermost: every response carries an ID
    app.include_router(system.router)
    app.include_router(sessions.router)
    app.include_router(conversation.router)
    app.include_router(events.router)
    app.include_router(ideas.router)
    app.include_router(sources.router)
    app.include_router(workspace.router)
    app.include_router(evaluation.router)
    mount_spa(app, env.STATIC_DIR)  # last: its catch-all must not shadow API routes
    return app
