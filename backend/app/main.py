"""Application factory: `uvicorn --factory app.main:create_app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import system
from app.api.errors import RequestIdMiddleware, install_error_handlers
from app.api.spa import mount_spa
from app.catalog import Catalog, load_catalog
from app.persistence.db import make_engine, make_sessionmaker, ping
from app.settings import AppEnv, get_env


def create_app(env: AppEnv | None = None, catalog: Catalog | None = None) -> FastAPI:
    env = env or get_env()
    catalog = catalog or load_catalog(env.HANDOFF_DIR)
    engine = make_engine(env.DATABASE_URL)  # lazy: no connection until first use

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
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

    async def db_ping() -> bool:
        return await ping(engine)

    app.state.db_ping = db_ping
    app.state.worker_alive = lambda: False
    install_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(system.router)
    mount_spa(app, env.STATIC_DIR)  # last: its catch-all must not shadow API routes
    return app
