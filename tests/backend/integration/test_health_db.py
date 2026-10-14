"""Health reflects the real database connection."""

from conftest import make_test_env
from contract_support import contract_client

from app.main import create_app


async def test_health_sees_live_database(client):
    body = (await client.get("/api/v1/health")).json()
    assert body["database"] == "ok"


async def test_health_degrades_when_database_is_unreachable():
    app = create_app(env=make_test_env(DATABASE_URL="postgresql+asyncpg://x:y@127.0.0.1:1/none"))
    async with contract_client(app) as c:
        r = await c.get("/api/v1/health")
    await app.state.engine.dispose()
    assert r.status_code == 200
    assert r.json()["database"] == "failed" and r.json()["status"] == "degraded"
