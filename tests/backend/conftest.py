import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.persistence.db import make_engine, make_sessionmaker
from app.persistence.models import Base

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "handoff"
BACKEND = ROOT / "backend"
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://perspective:local_development_only@127.0.0.1:55432/perspective_test",
)


@pytest.fixture(scope="session")
def handoff_dir() -> Path:
    return HANDOFF


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


def _plain_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session")
async def migrated_db() -> str:
    """A freshly created and migrated test database (real PostgreSQL, never SQLite)."""
    base, name = TEST_DB_URL.rsplit("/", 1)
    admin = await asyncpg.connect(_plain_dsn(base + "/perspective"))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    await asyncio.to_thread(command.upgrade, alembic_config(TEST_DB_URL), "head")
    return TEST_DB_URL


@pytest.fixture(scope="session")
async def engine(migrated_db):
    eng = make_engine(migrated_db)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine):
    """Empty tables before each test; yields a session factory."""
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    return make_sessionmaker(engine)


def make_test_env(**overrides):
    from app.settings import AppEnv

    base = dict(
        DATABASE_URL=TEST_DB_URL, APP_PROVIDER_MODE="demo", OPENAI_API_KEY="", TYPESAFE_API_KEY=""
    )
    base.update(overrides)
    return AppEnv(_env_file=None, **base)


@pytest.fixture
async def app(db):
    from app.main import create_app

    application = create_app(env=make_test_env())
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app):
    from contract_support import contract_client

    async with contract_client(app) as c:
        yield c
