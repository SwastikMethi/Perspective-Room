"""Delivery guards: no secrets in the image; enums and generated models match the contract."""

import os
import subprocess
from pathlib import Path

from contract_support import spec

from app.persistence import models
from app.settings import REPO_ROOT, AppEnv

ROOT = Path(__file__).resolve().parents[3]


def test_dockerignore_excludes_env_files_at_any_depth():
    lines = (ROOT / ".dockerignore").read_text().split()
    assert {"**/.env", "**/.env.*", "!.env.example"} <= set(lines)


def test_env_file_has_one_location_at_repo_root():
    assert AppEnv.model_config["env_file"] == REPO_ROOT / ".env"


def test_persistence_enums_match_contract():
    schemas = spec()["components"]["schemas"]
    assert list(models.RUN_STATUSES) == schemas["Run"]["properties"]["status"]["enum"]
    assert list(models.EVENT_TYPES) == schemas["RunEvent"]["properties"]["type"]["enum"]
    assert list(models.MODES) == schemas["Mode"]["enum"]
    assert list(models.BATCH_STATUSES) == schemas["Evaluation"]["properties"]["status"]["enum"]


def test_generated_models_are_current():
    # Inside backend/: the generator's formatter reads the nearest pyproject.toml.
    out = ROOT / "backend/app/domain/_api_regen_check.py"
    env = {**os.environ, "API_OUT": str(out), "API_ONLY": "1"}
    try:
        subprocess.run(
            ["bash", str(ROOT / "scripts/gen_contracts.sh")],
            check=True,
            env=env,
            capture_output=True,
        )
        fresh = out.read_text()
    finally:
        out.unlink(missing_ok=True)
    assert fresh == (ROOT / "backend/app/domain/api.py").read_text(), (
        "app/domain/api.py is stale: run scripts/gen_contracts.sh"
    )


def test_compose_publishes_only_loopback_and_never_the_database():
    import yaml

    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
    assert services["app"]["ports"] == ["127.0.0.1:${APP_PORT:-8000}:8000"]
    assert "ports" not in services["db"]
    for name, svc in services.items():
        for port in svc.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), (name, port)


def test_built_frontend_contains_no_key_material():
    import re

    import pytest

    dist = ROOT / "frontend/dist"
    if not dist.exists():
        pytest.skip("frontend/dist not built (npm run build)")
    pattern = re.compile(
        rb"sk-[A-Za-z0-9_-]{16,}|OPENAI_API_KEY=|TYPESAFE_API_KEY=|Bearer [A-Za-z0-9]"
    )
    env = AppEnv()  # the real .env too, once the user has added keys
    secrets = [env.OPENAI_API_KEY, env.TYPESAFE_API_KEY]
    env_values = [
        s.get_secret_value().encode() for s in secrets if s and len(s.get_secret_value()) >= 8
    ]
    for f in dist.rglob("*"):
        if f.is_file() and f.suffix in (".js", ".html", ".css", ".map", ".json"):
            data = f.read_bytes()
            assert not pattern.search(data), f
            assert not any(v in data for v in env_values), f


def test_warning_texts_match_between_backend_and_frontend():
    import re

    from app.domain.internal import WARNING_TEXT

    copy = (ROOT / "frontend/src/features/rooms/copy.ts").read_text()
    start = copy.index("export const WARNING_TEXT")
    block = copy[start : copy.index("\n}", start)]
    frontend = dict(re.findall(r"^\s+(\w+): '([^']*)',", block, re.M))
    assert frontend == WARNING_TEXT


def _fake_docker(tmp_path: Path, exec_script: str) -> dict[str, str]:
    """A stand-in `docker` on PATH: logs every call; `compose exec` runs exec_script."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{tmp_path}/calls.log"\n'
        'case "$*" in\n'
        '  *"ps -q"*) echo abc123 ;;\n'
        f"  *exec*) cat > /dev/null; {exec_script} ;;\n"
        "esac\n"
    )
    fake.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}


def _copy_script(tmp_path: Path, name: str) -> Path:
    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts" / name
    script.write_text((REPO_ROOT / "scripts" / name).read_text())
    script.chmod(0o755)
    return script


def test_a_backup_that_fails_midway_leaves_no_dump_behind(tmp_path):
    script = _copy_script(tmp_path, "db_backup.sh")
    env = _fake_docker(tmp_path, "printf 'PGDMP partial'; exit 1")
    r = subprocess.run(
        [str(script)], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    assert r.returncode != 0
    assert list((tmp_path / "backups").iterdir()) == []


def test_a_failed_restore_starts_the_app_again_and_says_so(tmp_path):
    script = _copy_script(tmp_path, "db_restore.sh")
    dump = tmp_path / "x.dump"
    dump.write_text("PGDMP")
    env = _fake_docker(tmp_path, "exit 1")
    r = subprocess.run(
        [str(script), str(dump)], env=env, input="restore\n", capture_output=True, text=True
    )
    assert r.returncode != 0
    calls = (tmp_path / "calls.log").read_text()
    assert "compose stop app" in calls and "compose start app" in calls
    assert "restore failed" in r.stderr


def test_a_finished_backup_is_kept_under_its_final_name(tmp_path):
    script = _copy_script(tmp_path, "db_backup.sh")
    env = _fake_docker(tmp_path, "printf 'PGDMP complete'")
    r = subprocess.run([str(script)], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    (dump,) = (tmp_path / "backups").iterdir()
    assert dump.suffix == ".dump" and dump.read_text() == "PGDMP complete"
