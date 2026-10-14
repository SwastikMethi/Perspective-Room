"""Error envelope, env handling and system endpoints (health, personas, settings)."""

import httpx
import pytest
from contract_support import contract_client
from fastapi import APIRouter

from app.api.errors import ApiError
from app.main import create_app
from app.settings import AppEnv


def make_env(**kw) -> AppEnv:
    base = dict(OPENAI_API_KEY="", TYPESAFE_API_KEY="", APP_PROVIDER_MODE="live")
    base.update(kw)
    return AppEnv(_env_file=None, **base)


def client_for(app) -> httpx.AsyncClient:
    return contract_client(app)


def error_shape(body: dict) -> None:
    assert set(body) == {"code", "message", "retryable", "request_id", "details"}


def test_empty_env_values_become_none_and_keys_stay_secret():
    env = make_env(OPENAI_API_KEY="sk-test-123", OPENAI_REASONING_EFFORT="")
    assert env.OPENAI_REASONING_EFFORT is None
    assert make_env().OPENAI_API_KEY is None
    assert "sk-test-123" not in repr(env)


async def test_api_error_renders_error_envelope():
    app = create_app(env=make_env())
    router = APIRouter()

    @router.get("/api/v1/boom")
    async def boom():
        raise ApiError(409, "version_conflict", "Session changed.", details={"current_version": 3})

    app.include_router(router)
    async with client_for(app) as c:
        r = await c.get("/api/v1/boom")
    assert r.status_code == 409
    body = r.json()
    error_shape(body)
    assert body["code"] == "version_conflict" and body["details"] == {"current_version": 3}
    assert body["request_id"] and r.headers["x-request-id"] == body["request_id"]


async def test_validation_and_unknown_route_and_crash_use_error_envelope():
    app = create_app(env=make_env())
    router = APIRouter()

    @router.get("/api/v1/needs-int")
    async def needs_int(n: int):
        return {"n": n}

    @router.get("/api/v1/crash")
    async def crash():
        raise RuntimeError("secret internal detail")

    app.include_router(router)
    async with contract_client(app, raise_app_exceptions=False) as c:
        bad = await c.get("/api/v1/needs-int", params={"n": "x"})
        missing = await c.get("/api/v1/nope")
        crash_r = await c.get("/api/v1/crash")
    assert bad.status_code == 422 and bad.json()["code"] == "validation_error"
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"
    assert crash_r.status_code == 500 and crash_r.json()["code"] == "internal_error"
    assert "secret internal detail" not in crash_r.text
    assert crash_r.headers["x-request-id"] == crash_r.json()["request_id"]
    for r in (bad, missing, crash_r):
        error_shape(r.json())


async def test_personas_endpoint_lists_eight_with_default_trio():
    async with client_for(create_app(env=make_env())) as c:
        body = (await c.get("/api/v1/personas")).json()
    assert [p["id"] for p in body["items"]][:3] == ["mentor", "skeptic", "explorer"]
    assert len(body["items"]) == 8 and body["default_selection"] == [
        "mentor",
        "skeptic",
        "explorer",
    ]


@pytest.mark.parametrize("key,configured", [("", False), ("sk-live-abc", True)])
async def test_settings_reports_configuration_without_secrets(key, configured):
    app = create_app(env=make_env(OPENAI_API_KEY=key))
    async with client_for(app) as c:
        r = await c.get("/api/v1/settings")
    body = r.json()
    assert body["openai_configured"] is configured and body["jev_configured"] is False
    assert body["provider_mode"] == "live" and body["local_only"] is True
    assert body["openai_model"] == "gpt-6.1-sol" and body["limits"]["auto_contributions"] == 3
    assert "sk-live-abc" not in r.text


async def test_health_reports_database_and_worker_state():
    app = create_app(env=make_env())

    async def db_ok() -> bool:
        return True

    app.state.db_ping = db_ok
    app.state.worker_alive = lambda: True
    async with client_for(app) as c:
        ok = (await c.get("/api/v1/health")).json()

    async def db_down() -> bool:
        return False

    app.state.db_ping = db_down
    async with client_for(app) as c:
        r = await c.get("/api/v1/health")
    assert ok["status"] == "ok" and ok["database"] == "ok"
    assert (
        r.status_code == 200
        and r.json()["status"] == "degraded"
        and r.json()["database"] == "failed"
    )
