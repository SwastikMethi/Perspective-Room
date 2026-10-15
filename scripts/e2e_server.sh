#!/usr/bin/env bash
# Browser-test server: fresh perspective_e2e database on db-dev, demo providers, built SPA.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export DATABASE_URL="${E2E_DATABASE_URL:-postgresql+asyncpg://perspective:local_development_only@127.0.0.1:55432/perspective_e2e}"
cd "$root/backend"
uv run python - <<'PY'
import asyncio, os
import asyncpg

url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
base, name = url.rsplit("/", 1)

async def main() -> None:
    conn = await asyncpg.connect(base + "/perspective")
    await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    await conn.execute(f'CREATE DATABASE "{name}"')
    await conn.close()

asyncio.run(main())
PY
uv run alembic upgrade head
export APP_PROVIDER_MODE=demo OPENAI_API_KEY= TYPESAFE_API_KEY=
port="${E2E_PORT:-8010}"
export APP_ALLOWED_ORIGINS="http://127.0.0.1:$port" STATIC_DIR="$root/frontend/dist"
exec uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port "$port"
