"""Live smoke (doc 10): only with real keys and RUN_LIVE=1, against the running app.

    RUN_LIVE=1 docker compose exec app python -m app.cli smoke-live --yes --probe

is the documented way; this wrapper exists so `pytest tests/live` documents the same check."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1", reason="live smoke runs only with RUN_LIVE=1 and real keys"
)


def test_live_smoke_set_passes(tmp_path):
    from app.settings import get_env
    from app.smoke import run_smoke

    env = get_env()
    assert env.openai_configured and env.jev_configured, "set OPENAI_API_KEY and TYPESAFE_API_KEY"
    code, out = run_smoke(
        env, os.environ.get("APP_URL", "http://127.0.0.1:8000"), tmp_path, probe=False
    )
    assert code == 0, out.read_text()[:2000]
