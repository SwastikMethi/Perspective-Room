"""Request security (T24, plan G1): trusted Host, exact allowed origins, cross-site mutation
rejection, JSON-only mutation bodies. Security-layer responses are not contract operations, so this
uses a plain client instead of the contract-validating one."""

import httpx
import pytest
from conftest import IDEA, idem, make_test_env

from app.main import create_app


@pytest.fixture
async def raw(db):
    app = create_app(env=make_test_env())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as c:
        yield c
    await app.state.engine.dispose()


def assert_error(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert body["code"] == code and body["request_id"] == r.headers["x-request-id"]


async def test_cross_site_mutations_are_rejected(raw):
    url, body = "/api/v1/sessions", {"idea": IDEA}
    foreign = await raw.post(url, json=body, headers={**idem(), "Origin": "https://evil.example"})
    assert_error(foreign, 403, "cross_site_rejected")
    fetch_meta = await raw.post(url, json=body, headers={**idem(), "Sec-Fetch-Site": "cross-site"})
    assert_error(fetch_meta, 403, "cross_site_rejected")
    null_origin = await raw.post(url, json=body, headers={**idem(), "Origin": "null"})
    assert_error(null_origin, 403, "cross_site_rejected")
    ok = await raw.post(url, json=body, headers={**idem(), "Origin": "http://127.0.0.1:8000"})
    assert ok.status_code == 201
    no_origin = await raw.post(url, json=body, headers=idem())  # CLI and scripts
    assert no_origin.status_code == 201


async def test_reads_are_not_blocked_by_origin(raw):
    r = await raw.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers  # no CORS: a foreign page cannot read it


async def test_mutation_bodies_must_be_json(raw):
    r = await raw.post(
        "/api/v1/sessions",
        content=b"idea=hello",
        headers={**idem(), "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_error(r, 415, "json_required")
    r = await raw.post(
        "/api/v1/sessions",
        content=b'{"idea":"x"}',
        headers={**idem(), "Content-Type": "text/plain"},
    )
    assert_error(r, 415, "json_required")
    charset = await raw.post(
        "/api/v1/sessions",
        content=b'{"idea": "charset ok"}',
        headers={**idem(), "Content-Type": "application/json; charset=utf-8"},
    )
    assert charset.status_code == 201
    bodyless = await raw.post("/api/v1/provider-checks")  # Stop/check style POSTs carry no body
    assert bodyless.status_code == 200


async def test_untrusted_host_headers_are_refused(raw):
    r = await raw.get("/api/v1/health", headers={"Host": "evil.example"})
    assert_error(r, 400, "bad_request")
    for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000"):
        assert (await raw.get("/api/v1/health", headers={"Host": host})).status_code == 200
