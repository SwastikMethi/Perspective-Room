"""Maintenance commands: `python -m app.cli <command>` (documented in the README)."""

import argparse
import sys

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-config", help="Validate personas, defaults, cases and templates")
    args = parser.parse_args(argv)
    if args.command == "validate-config":
        return validate_config()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
