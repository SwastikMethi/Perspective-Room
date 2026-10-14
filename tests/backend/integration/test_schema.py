"""Migration and database guarantees (real PostgreSQL)."""

import asyncio
from uuid import uuid4

import pytest
from alembic import command
from conftest import alembic_config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.persistence.models import Message, Run, Session


async def test_upgrade_head_is_repeatable_and_models_match_migration(migrated_db):
    cfg = alembic_config(migrated_db)
    await asyncio.to_thread(command.upgrade, cfg, "head")  # second run is a no-op
    await asyncio.to_thread(command.check, cfg)  # raises if models and migration disagree


async def test_pg_trgm_and_cyclic_fk_exist(db, engine):
    async with engine.connect() as c:
        ext = await c.scalar(text("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm'"))
        fk = await c.scalar(
            text("SELECT count(*) FROM pg_constraint WHERE conname = 'fk_messages_run_id'")
        )
    assert ext == 1 and fk == 1


def _session(**kw) -> Session:
    base = dict(
        id=uuid4(),
        title="t",
        mode="jev_guided",
        selected_persona_ids=["mentor"],
        settings={"research_policy": "auto", "auto_contributions": 3},
        brief={"idea": "x", "goal": None, "constraints": [], "revision": 1},
    )
    base.update(kw)
    return Session(**base)


def _run(session_id, status="queued") -> Run:
    return Run(
        id=uuid4(),
        session_id=session_id,
        status=status,
        mode="jev_guided",
        audience="auto",
        control={},
        snapshot={},
        slots=[],
        requested_count=1,
        session_version=1,
    )


async def test_one_active_run_per_session_is_enforced(db):
    async with db() as s:
        sess = _session()
        s.add(sess)
        await s.flush()
        s.add_all([_run(sess.id), _run(sess.id, status="completed")])
        await s.commit()
    async with db() as s:
        s.add(_run(sess.id, status="running"))
        with pytest.raises(IntegrityError, match="uq_runs_one_active_per_session"):
            await s.commit()


async def test_message_content_variant_is_enforced(db):
    async with db() as s:
        sess = _session()
        s.add(sess)
        await s.flush()
        s.add(
            Message(
                id=uuid4(),
                session_id=sess.id,
                sequence=1,
                role="persona",
                persona_id="skeptic",
                text="plain text, no contribution",
            )
        )
        with pytest.raises(IntegrityError, match="message_content_variant"):
            await s.commit()


async def test_message_sequence_is_unique_per_session(db):
    async with db() as s:
        sess = _session()
        s.add(sess)
        await s.flush()
        s.add_all(
            [
                Message(id=uuid4(), session_id=sess.id, sequence=1, role="user", text="a"),
                Message(id=uuid4(), session_id=sess.id, sequence=1, role="user", text="b"),
            ]
        )
        with pytest.raises(IntegrityError):
            await s.commit()
