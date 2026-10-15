"""smoke-live never reports a demo or half-configured app as a live success."""

import json

from app import smoke
from app.settings import AppEnv


def test_demo_mode_is_not_a_live_pass(tmp_path, monkeypatch):
    def fake(self, method, path, body=None):
        if path == "/api/v1/provider-checks":
            return {
                "openai": {"status": "demo", "message": "x"},
                "jev": {"status": "demo", "message": "x"},
            }
        if path == "/api/v1/settings":
            return {
                "provider_mode": "demo",
                "openai_model": "m",
                "research_model": "m",
                "jev_model": "j",
            }
        raise AssertionError(f"no work may start: {method} {path}")

    monkeypatch.setattr(smoke.Api, "call", fake)
    code, out = smoke.run_smoke(AppEnv(_env_file=None), "http://127.0.0.1:1", tmp_path, probe=True)
    report = json.loads(out.read_text())
    assert code == 1 and report["steps"] == [] and report["provider_mode"] == "demo"


def test_cli_asks_before_any_paid_call(monkeypatch, capsys):
    from app.cli import main

    monkeypatch.setattr("builtins.input", lambda prompt="": "no")
    monkeypatch.setattr(
        smoke, "run_smoke", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran"))
    )
    assert main(["smoke-live"]) == 1
    assert "Not started" in capsys.readouterr().err
