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
