#!/bin/sh
# Wait for PostgreSQL, apply migrations, validate configuration, then start ONE Uvicorn worker.
set -eu
cd /app/backend
python - <<'PY'
import asyncio, sys
import asyncpg
from app.settings import get_env

url = get_env().DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

async def wait() -> None:
    for _ in range(60):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            return
        except Exception as exc:
            print(f"waiting for database ({exc.__class__.__name__})", flush=True)
            await asyncio.sleep(1)
    sys.exit("database is not reachable")

asyncio.run(wait())
PY
alembic upgrade head
python -m app.cli validate-config
exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000 --workers 1 --no-server-header
