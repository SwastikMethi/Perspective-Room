"""Maintenance commands: `python -m app.cli <command>` (documented in the README)."""

import argparse
import asyncio
import sys
from pathlib import Path
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


async def _export_session(session_id: UUID, fmt: str, out: Path) -> int:
    from app.api.errors import ApiError
    from app.persistence.db import make_engine, make_sessionmaker
    from app.services.export import export_session

    env = get_env()
    engine = make_engine(env.DATABASE_URL)
    try:
        async with make_sessionmaker(engine)() as db:
            exported = await export_session(db, load_catalog(env.HANDOFF_DIR), session_id, fmt)
    except ApiError as e:
        print(f"export failed: {e.message}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    try:
        with out.open("x", encoding="utf-8") as f:  # never overwrite an earlier export
            f.write(exported.body)
    except FileExistsError:
        print(f"{out} already exists; choose another path", file=sys.stderr)
        return 1
    print(f"wrote {out} ({len(exported.body.encode())} bytes)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-config", help="Validate personas, defaults, cases and templates")
    exp = sub.add_parser("export-session", help="Write one chat as Markdown or JSON")
    exp.add_argument("session_id", type=UUID)
    exp.add_argument("--format", choices=["markdown", "json"], required=True)
    exp.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "validate-config":
        return validate_config()
    if args.command == "export-session":
        return asyncio.run(_export_session(args.session_id, args.format, args.out))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
