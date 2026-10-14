# Setup and local operations

This document specifies commands the implemented repository must provide. They are not commands that make this documentation-only package run as an application.

## Prerequisites

Use Docker Engine/Desktop with Compose for the supported local path. Native development uses Node 24, Python 3.12, and PostgreSQL 16. Supply an OpenAI API key with access to the configured generation/research model and a TypeSafe API key with access to Jev. Credentials remain in a local ignored `.env` or injected environment variables.

The researched default generation/research identifier is `gpt-6.1-sol`; Jev is `jev-1.13.0`. These are configuration choices checked against public documentation on 14 October 2026, not proof of this user's account access. Run the explicit small connection check. If the selected model is unavailable, display a useful configuration error; never silently replace only one personality or experiment condition.

## Required startup experience

The implemented README should support:

```bash
cp .env.example .env
# Edit .env locally and set provider credentials, or explicitly choose demo mode.
docker compose up --build
```

Open `http://localhost:8000`. The app service waits for database readiness, runs `alembic upgrade head`, verifies profile configuration, then starts one Uvicorn process. Publish the app port on 127.0.0.1 only. Never publish PostgreSQL by default.

The application image should use a multi-stage frontend build and a non-root backend runtime. Keep dependency caches in build layers and exclude `.env`, local data exports, and secrets from the image context. The local database volume persists across ordinary restarts. Do not suggest a volume-deleting reset as a routine troubleshooting step.

## Configuration ownership

`config/app.defaults.json` describes application defaults. Environment variables override provider selection, credentials, DB connection, host/origin settings, and optional dollar cap. The Settings screen is read-only for secrets/models and explains how to change the environment and restart. Session preferences such as selected personalities and research policy are stored per session.

Default provider mode is live. If keys are absent, show setup guidance and an explicit demo-mode option, never an automatic mock substitution. Demo mode displays a persistent label, uses deterministic fixtures, and reports zero external calls. A connection check occurs only through an explicit user action or documented CLI command, not on every page render.

## Required maintenance commands

Provide documented script entry points for:

- Migration and profile/config validation.
- Mock tests and a small live smoke test.
- Running a selected evaluation subset with a dry-run count.
- Exporting a session or evaluation.
- Backing up/restoring the local database.
- Deleting a selected evaluation and its generated sessions, with a concrete target summary and interactive confirmation for the local operator.

The CLI may use `python -m app.cli <command>`; finalize exact flags in the implementation README and test them. No administrative deletion runs automatically on startup.

## Usage and limits

The historical $200 budget is removed. There is no default dollar cap. Per-turn limits, concurrency, input/output ceilings, retry bounds, and deadlines still protect usability and prevent accidental loops. Record all billable attempts, including discarded drafts, research, normalization, intake, memory, and repairs. Unknown timeout usage remains unknown.

If a dollar cap is configured, require a complete versioned rate card, reserve estimated maximum usage before calls, reconcile actual usage, and account for concurrent reservations. Explain that provider billing can differ and ambiguous in-flight calls cannot be known instantly. If rates are missing, do not claim a hard dollar guarantee. The default UI shows tokens/calls and optional estimates separately.

## Recovery and troubleshooting

| Symptom | Action |
| --- | --- |
| No key configured | Set the server variable and restart, or deliberately choose demo mode. |
| Model unavailable | Verify the configured model and account access; update configuration consistently. |
| Jev failure | Inspect sanitized error; fixed coordination should continue with a visible fallback label. |
| Search produces no usable sources | Continue with assumptions or request evidence; do not invent citations. |
| Browser disconnect | Reconnect SSE and retrieve snapshots; do not resubmit the turn. |
| App restarts mid-turn | Mark orphaned work interrupted and retry only unfinished work after explicit user action. |
| Database unavailable | Health becomes degraded; fail writes clearly and preserve the user's unsent draft. |
| A benchmark was interrupted | Preserve all original trials; start a separate batch for selected unfinished cases. |

## Logs, deletion, and exports

Operational logs contain IDs, stages, durations, status codes, and usage. Detailed prompt/decision snapshots are local application records with no secrets; expose them only in diagnostics/export options intended for the local owner. Do not log authorization headers. Local deletion removes local content and references but does not establish provider-side erasure. Application-owned history with `store=false` is not a promise of zero provider retention.

Backups and exports may contain the user's ideas. Save only when requested through explicit local actions. Keep exported files out of git by default. The app does not need remote deployment, cloud storage, telemetry vendors, or a public account system to satisfy this release.

## Workspace and appearance state (revision 1.1)

Chat/folder membership, pin/archive state and organization versions live in PostgreSQL and are included in database backups. Browser local storage holds theme, sidebar state and per-chat unsent drafts; those drafts are not part of a server backup or export. Warn before clearing local workspace state. Do not clear drafts as a side effect of changing theme, reconnecting or running a migration.

Migrations add folders, organization fields, normalized public search text, and PostgreSQL pg_trgm indexes. The supplied PostgreSQL container must support `CREATE EXTENSION IF NOT EXISTS pg_trgm`; migration credentials need that permission. A missing extension is a clear migration error, not a silent broken search field. Apply migrations before accepting writes. Static approved portrait/reference assets are bundled locally and require no network or image-generation key at runtime.
