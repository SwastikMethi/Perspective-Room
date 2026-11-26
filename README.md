# Perspective Room

A local brainstorming app. Eight simulated personalities help you explore an idea; TypeSafe
**Jev** decides who speaks next and checks each reply; **OpenAI** writes the replies and does
sourced web research. It has a full chat workspace (history, folders, search, per-chat drafts),
dark and light cartoon themes, forks/branches and exports, and an **Experiment Lab** that compares
Standard, Fixed panel and Jev-guided conversations on matched cases with blind ratings.

Everything runs on your computer. The full specification is in [`handoff/`](handoff/START_HERE.md);
what was built and how it was verified is in [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md);
every design decision is in [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md).

![Room, dark theme](docs/screenshots/room-dark-rail.png)

## Quick start (Docker)

```bash
./start.sh
```

On Windows, run this from Git Bash or WSL. The script checks Docker, creates `.env` from
`.env.example` if needed, then builds and starts the containers. Edit `.env` and rerun
`./start.sh` after changing its settings:

- **Live mode** (default): set `OPENAI_API_KEY` and `TYPESAFE_API_KEY`. Keys stay on the server;
  they never reach the browser, logs or exports.
- **Demo mode**: set `APP_PROVIDER_MODE=demo` instead. Replies come from labeled deterministic
  fixtures and the app makes zero external calls. Demo output is never mixed with live output and
  never replaces a live failure.

Open <http://127.0.0.1:8000>. On start the app waits for PostgreSQL, runs `alembic upgrade head`,
validates the personality configuration and starts one Uvicorn worker. Only `127.0.0.1:8000` is
published; the database stays on the private Compose network.

Check it: `docker compose ps` and <http://127.0.0.1:8000/api/v1/health>. Settings → *Check
connection* verifies both keys without generating text.

To use another port: `APP_PORT=8001 docker compose up -d` (and open that port).

Stop with `docker compose down`. Your data stays in the `db-data` volume between restarts.

## Using it

- **New chat**: type an idea, choose who answers (Jev-guided by default) and which of the eight
  perspectives are in the room, press Enter. Shift+Enter adds a line; `@` addresses one persona.
- **Room**: replies arrive as cards; *Read full response* expands a turn; numbered citation chips
  open the source. Card actions: Copy, Reply, Ask more, Challenge, Feedback, save (bookmark), Fork
  here, Regenerate round. Your own messages can be edited into a new branch.
- **Composer**: *To* (Auto / Everyone selected / one perspective), *Research* (Auto / Off / Force),
  and the **+** menu (reference saved ideas, add a constraint, choose a move such as Combine).
- **Details drawer** (header): Brief (versioned), Saved ideas, Sources, Summary, Run details.
- **Workspace**: folders, pinned and archived chats, rename/move/duplicate/export/delete from any
  chat's menu, and Search (Ctrl/Cmd+K) over titles and messages.
- **Experiment Lab**: pick cases, conditions and repetitions, run a batch, rate outputs blind,
  then reveal and read the measured results. See [the evaluation plan](handoff/docs/09_EVALUATION.md).

## Command-line tools

Run inside the container (`docker compose exec app python -m app.cli …`) or natively from
`backend/` (`uv run python -m app.cli …`).

| Command | What it does |
| --- | --- |
| `validate-config` | Checks personalities, defaults, cases and prompt templates; prints counts and hashes |
| `export-session <chat-id> --format markdown\|json --out <file>` | Writes one chat (never overwrites a file) |
| `eval-run --cases case_01,case_02 --modes standard,fixed_panel,jev_guided [--reps N] [--evidence off\|fixture\|live] [--dry-run]` | Counts trials locally; without `--dry-run` asks for confirmation and starts the batch through the running app |
| `export-eval <batch-id> --format csv\|json --out <file>` | Exports a Lab batch (this reveals the conditions) |
| `delete-eval <batch-id>` | Deletes a finished batch after you type its ID back |
| `smoke-live [--probe]` | The small live check from doc 10 (a few paid calls, asks first); writes a JSON report to `exports/` |

## Backup and restore

```bash
scripts/db_backup.sh
```

writes `backups/<UTC time>.dump` (PostgreSQL custom format). To restore one:

```bash
scripts/db_restore.sh backups/20261015T023801Z.dump
```

Restoring replaces all chats, folders and Lab data, so it asks you to type `restore`; the app is
paused while it runs. Browser-only state (theme, sidebar, unsent drafts) is not part of a backup;
Settings → *Clear local workspace state* removes it. Backups and exports contain your ideas and
are git-ignored (`backups/`, `exports/`).

## Development

```bash
docker compose --profile dev up -d db-dev     # PostgreSQL 16 on 127.0.0.1:55432
export DATABASE_URL=postgresql+asyncpg://perspective:local_development_only@127.0.0.1:55432/perspective
export APP_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:8000
(cd backend && uv sync && uv run alembic upgrade head)
(cd backend && uv run uvicorn --factory app.main:create_app --port 8000 --reload)
(cd frontend && npm ci && npm run dev)        # second terminal: http://localhost:5173
```

Native runs read the one `.env` at the repository root. Requirements: Python 3.12 with
[uv](https://docs.astral.sh/uv/), Node 24, Docker. Contract types are generated from
`handoff/contracts/openapi.yaml`: `scripts/gen_contracts.sh` (backend models) and
`npm run gen:api` (frontend types); `npm run check:api` fails if they drift.

## Tests

```bash
docker compose --profile dev up -d db-dev
(cd backend && uv run pytest)                                   # real PostgreSQL, demo providers
(cd backend && uv run ruff check . ../tests && uv run mypy app)
(cd frontend && npm run typecheck && npm test && npm run check:api)
(cd frontend && npx playwright install chromium && npx playwright test)   # builds, serves demo mode on :8010
(cd frontend && npx playwright test --project screenshots)     # rewrites docs/screenshots/
docker compose exec app python -m app.cli smoke-live --probe   # live, with keys; asks first
(cd backend && RUN_LIVE=1 uv run pytest -c pyproject.toml ../tests/live)   # same check via pytest
```

Backend tests create and drop their own `perspective_test` database (override with
`TEST_DATABASE_URL`); browser tests use `perspective_e2e` (`E2E_DATABASE_URL`, `E2E_PORT`).

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Banner says a key is missing | Add it to `.env` and `docker compose up -d` again, or use `APP_PROVIDER_MODE=demo` |
| Settings → Check connection says *rejected* | The key is wrong or lacks access; replace it in `.env` |
| Check connection says *rejected* and the key is right | If OpenAI reports `incorrect_hostname`, your project uses a regional host: set `OPENAI_BASE_URL` (for example `https://us.api.openai.com/v1`) in `.env` |
| *model_unavailable* | The configured model (`OPENAI_MODEL`, `JEV_MODEL`) is not available to your key; the app never switches models on its own |
| Port 8000 is taken | `APP_PORT=8001 docker compose up -d` |
| Changes are refused with *cross_site_rejected* in development | Add your dev origin to `APP_ALLOWED_ORIGINS` |
| *The local database is unavailable* | `docker compose ps`; restart with `docker compose up -d`; your text stays in the composer |
| A reply was cut short (*incomplete*) | Set `OPENAI_REASONING_EFFORT=low` (reasoning tokens count toward output limits) and record it |

Do not delete the `db-data` volume to fix problems; it holds your chats.

## Layout

```
handoff/    the specification package as received (+ the documented contract amendment)
backend/    FastAPI app, worker, orchestrator, providers, migrations
frontend/   React + Vite app, unit tests, Playwright browser tests (frontend/e2e)
tests/      backend tests (unit, integration, contract) and the opt-in live check
scripts/    contract generation, container entrypoint, e2e server, backup/restore
docs/       real-app screenshots
```
