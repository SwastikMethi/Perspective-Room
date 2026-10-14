# Perspective Room

A local brainstorming app: eight simulated personalities help you explore an idea, coordinated by
TypeSafe **Jev**, with **OpenAI** generating conversation and sourced research. It includes a chat
workspace (history, folders, search, drafts), matching dark/light cartoon themes, forks and exports,
and a three-arm **Experiment Lab** (Standard · Fixed panel · Jev-guided).

The full specification lives in [`handoff/`](handoff/START_HERE.md).

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY and TYPESAFE_API_KEY, or set APP_PROVIDER_MODE=demo.
docker compose up --build
```

Open <http://localhost:8000>. The app waits for PostgreSQL, runs `alembic upgrade head`, validates
the personality configuration, then starts one Uvicorn worker. Only `127.0.0.1:8000` is published;
the database stays on the private Compose network.

- **Live mode** (default) needs both keys in `.env` (backend only; never in the browser).
- **Demo mode** (`APP_PROVIDER_MODE=demo`) uses clearly labeled deterministic fixtures and makes
  zero external calls. It never replaces a live failure.

## Development

```bash
docker compose --profile dev up -d db-dev     # PostgreSQL 16 on 127.0.0.1:55432
export DATABASE_URL=postgresql+asyncpg://perspective:local_development_only@127.0.0.1:55432/perspective
export APP_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:8000
(cd backend && uv sync && uv run alembic upgrade head)
(cd backend && uv run uvicorn --factory app.main:create_app --port 8000 --reload)
(cd frontend && npm ci && npm run dev)        # in a second terminal: http://localhost:5173
```

Native runs read one `.env` at the repository root (never `backend/.env`).

## Tests

```bash
(cd backend && uv run pytest)                 # needs db-dev running
(cd frontend && npm run typecheck && npm test && npm run check:api)
```
