"""Built SPA is served on the API origin; API paths never fall back to HTML. Config CLI works."""

from conftest import make_test_env
from contract_support import contract_client

from app.cli import main as cli_main
from app.main import create_app


def build_static(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Perspective Room</title>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    return tmp_path


async def test_spa_routes_serve_index_and_assets(tmp_path):
    app = create_app(env=make_test_env(STATIC_DIR=build_static(tmp_path)))
    async with contract_client(app) as c:
        room = await c.get("/rooms/00000000-0000-4000-8000-000000000001")
        root = await c.get("/")
        asset = await c.get("/assets/app-abc123.js")
        missing_asset = await c.get("/assets/nope.js")
        api_missing = await c.get("/api/v1/does-not-exist")
    await app.state.engine.dispose()
    assert room.status_code == 200 and "Perspective Room" in room.text
    assert root.status_code == 200 and "text/html" in root.headers["content-type"]
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert missing_asset.status_code == 404
    assert api_missing.status_code == 404 and api_missing.json()["code"] == "not_found"


async def test_index_is_not_cached(tmp_path):
    app = create_app(env=make_test_env(STATIC_DIR=build_static(tmp_path)))
    async with contract_client(app) as c:
        r = await c.get("/chats")
    await app.state.engine.dispose()
    assert r.headers["cache-control"] == "no-cache"


def test_validate_config_cli_reports_counts(capsys):
    assert cli_main(["validate-config"]) == 0
    out = capsys.readouterr().out
    assert "personas: 8" in out and "cases: 30" in out and "templates:" in out
