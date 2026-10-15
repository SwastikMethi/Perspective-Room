"""Maintenance commands: `python -m app.cli <command>` (documented in the README)."""

import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from app.catalog import ConfigError, load_catalog
from app.prompts.loader import TEMPLATE_DIR, template
from app.settings import get_env


def validate_config() -> int:
    env = get_env()
    try:
        cat = load_catalog(env.HANDOFF_DIR)
    except ConfigError as e:
        print(f"configuration invalid: {e}", file=sys.stderr)
        return 1
    names = sorted(p.stem for p in TEMPLATE_DIR.glob("*.md"))
    print(f"personas: {len(cat.personas)} (version {cat.personas_version})")
    for pid in cat.order:
        print(f"  {pid}: {cat.persona_hash(pid)[:12]}")
    print(f"cases: {len(cat.cases)} (version {cat.cases_version}, hash {cat.cases_hash[:12]})")
    print(f"fixture evidence packs: {len(cat.fixture_packs)}")
    print("templates: " + ", ".join(f"{n}@{template(n).version}" for n in names))
    print(f"provider mode: {env.APP_PROVIDER_MODE}")
    return 0


async def _with_db(fn: Callable[[Any, Any], Awaitable[Any]]) -> Any:
    """Run `fn(db, catalog)` in one committed transaction against the configured database."""
    from app.persistence.db import make_engine, make_sessionmaker

    env = get_env()
    engine = make_engine(env.DATABASE_URL)
    try:
        async with make_sessionmaker(engine)() as db, db.begin():
            return await fn(db, load_catalog(env.HANDOFF_DIR))
    finally:
        await engine.dispose()


def _write_new(out: Path, body: str) -> int:
    try:
        with out.open("x", encoding="utf-8") as f:  # never overwrite an earlier export
            f.write(body)
    except FileExistsError:
        print(f"{out} already exists; choose another path", file=sys.stderr)
        return 1
    print(f"wrote {out} ({len(body.encode())} bytes)")
    return 0


def export_session(session_id: UUID, fmt: str, out: Path) -> int:
    from app.api.errors import ApiError
    from app.services.export import export_session as build

    try:
        exported = asyncio.run(_with_db(lambda db, cat: build(db, cat, session_id, fmt)))
    except ApiError as e:
        print(f"export failed: {e.message}", file=sys.stderr)
        return 1
    return _write_new(out, exported.body)


def export_eval(batch_id: UUID, fmt: str, out: Path) -> int:
    from app.api.errors import ApiError
    from app.services.evaluation import export_batch

    try:
        body, _ = asyncio.run(_with_db(lambda db, cat: export_batch(db, cat, batch_id, fmt)))
    except ApiError as e:
        print(f"export failed: {e.message}", file=sys.stderr)
        return 1
    print("Note: exporting reveals which output came from which condition.")
    return _write_new(out, body)


def delete_eval(batch_id: UUID) -> int:
    """Shows what will be removed and asks for the batch ID to be typed back (no --yes)."""
    from app.api.errors import ApiError
    from app.services.evaluation import batch_out, delete_batch, get_batch

    try:
        b = asyncio.run(_with_db(lambda db, cat: get_batch(db, batch_id)))
    except ApiError as e:
        print(e.message, file=sys.stderr)
        return 1
    info = batch_out(b)
    print(
        f"Batch {info.id}: status {info.status}, {info.planned_trials} trials "
        f"(cases {', '.join(info.config.case_ids)}; modes {', '.join(info.config.modes)}), "
        f"created {info.created_at:%Y-%m-%d %H:%M}."
    )
    print("This permanently deletes its trials, Lab chats and ratings from this computer.")
    if input("Type the batch ID to confirm: ").strip() != str(batch_id):
        print("Not deleted: the ID did not match.", file=sys.stderr)
        return 1
    try:
        counts = asyncio.run(_with_db(lambda db, cat: delete_batch(db, batch_id)))
    except ApiError as e:
        print(f"Not deleted: {e.message}", file=sys.stderr)
        return 1
    print(
        f"Deleted: {counts['trials']} trials, {counts['sessions']} chats, "
        f"{counts['ratings']} ratings."
    )
    return 0


def eval_run(args: argparse.Namespace) -> int:
    """G19: work-creating commands go through the running app's API, never a second worker."""
    from pydantic import ValidationError

    from app.api.errors import ApiError
    from app.domain import api
    from app.services.evaluation import _validate

    try:
        body = api.EvaluationCreate(
            case_ids=[c.strip() for c in args.cases.split(",") if c.strip()],
            modes=[m.strip() for m in args.modes.split(",") if m.strip()],  # type: ignore[misc]
            repetitions=args.reps,
            evidence_policy=args.evidence,
            blind_rating=True,
            max_trials=90,
        )
        planned = _validate(body, load_catalog(get_env().HANDOFF_DIR))
    except (ValidationError, ApiError) as e:
        print(f"Not started: {getattr(e, 'message', e)}", file=sys.stderr)
        return 1
    print(
        f"{planned} trials planned ({len(body.case_ids)} cases × {len(body.modes)} modes "
        f"× {body.repetitions})."
    )
    if args.dry_run:
        return 0
    if (
        input("This can make paid provider calls in live mode. Type 'run' to start: ").strip()
        != "run"
    ):
        print("Not started.", file=sys.stderr)
        return 1
    req = urllib.request.Request(
        f"{args.url.rstrip('/')}/api/v1/evaluations",
        data=json.dumps(body.model_dump(mode="json")).encode(),
        headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            batch = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"Not started: {e.code} {e.read().decode(errors='replace')[:300]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Not started: the app at {args.url} is not reachable ({e.reason}).", file=sys.stderr)
        return 1
    print(f"Started batch {batch['id']} ({batch['planned_trials']} trials, {batch['status']}).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-config", help="Validate personas, defaults, cases and templates")
    exp = sub.add_parser("export-session", help="Write one chat as Markdown or JSON")
    exp.add_argument("session_id", type=UUID)
    exp.add_argument("--format", choices=["markdown", "json"], required=True)
    exp.add_argument("--out", type=Path, required=True)
    run = sub.add_parser("eval-run", help="Start an Experiment Lab batch via the running app")
    run.add_argument(
        "--cases", required=True, help="comma-separated case IDs, e.g. case_01,case_02"
    )
    run.add_argument("--modes", required=True, help="standard,fixed_panel,jev_guided (any subset)")
    run.add_argument("--reps", type=int, default=1)
    run.add_argument("--evidence", choices=["off", "fixture", "live"], default="off")
    run.add_argument("--url", default="http://127.0.0.1:8000")
    run.add_argument("--dry-run", action="store_true", help="count trials locally; start nothing")
    ex = sub.add_parser("export-eval", help="Write a batch as CSV or JSON (reveals conditions)")
    ex.add_argument("batch_id", type=UUID)
    ex.add_argument("--format", choices=["csv", "json"], required=True)
    ex.add_argument("--out", type=Path, required=True)
    rm = sub.add_parser("delete-eval", help="Delete a finished batch after typed confirmation")
    rm.add_argument("batch_id", type=UUID)
    args = parser.parse_args(argv)
    if args.command == "validate-config":
        return validate_config()
    if args.command == "export-session":
        return export_session(args.session_id, args.format, args.out)
    if args.command == "eval-run":
        return eval_run(args)
    if args.command == "export-eval":
        return export_eval(args.batch_id, args.format, args.out)
    if args.command == "delete-eval":
        return delete_eval(args.batch_id)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
