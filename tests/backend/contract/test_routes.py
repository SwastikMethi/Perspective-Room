"""Every contract operation is routed with the same method, path, operationId, status, schemas."""

from functools import cache
from typing import Any

import pytest
from contract_support import spec

from app.main import create_app

# Operations not routed yet. Each router task removes its entries; Task 28 asserts this is empty.
PENDING: set[str] = set()


def _ops(doc: dict[str, Any]) -> dict[str, tuple[str, str, dict[str, Any]]]:
    return {
        op["operationId"]: (method, path, op)
        for path, item in doc["paths"].items()
        for method, op in item.items()
    }


@cache
def _app_doc() -> dict[str, Any]:
    return create_app().openapi()


def _success(op: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    code = min(c for c in op["responses"] if c.startswith("2"))
    return code, op["responses"][code]


def _ref(media: dict[str, Any] | None) -> str | None:
    if not media:
        return None
    schema = media.get("schema", {})
    return schema.get("$ref", "").rsplit("/", 1)[-1] or schema.get("type")


def _params(op: dict[str, Any]) -> set[tuple[str, str, bool]]:
    return {(p["name"], p["in"], bool(p.get("required"))) for p in op.get("parameters", [])}


CONTRACT = _ops(spec())


@pytest.mark.parametrize("operation_id", sorted(set(CONTRACT) - PENDING))
def test_operation_matches_contract(operation_id):
    method, path, want = CONTRACT[operation_id]
    got = _app_doc()["paths"].get(path, {}).get(method)
    assert got, f"{method.upper()} {path} is not routed"
    assert got["operationId"] == operation_id
    want_code, want_resp = _success(want)
    got_code, got_resp = _success(got)
    assert got_code == want_code
    assert _params(got) == _params(want)
    want_body = want.get("requestBody", {}).get("content", {}).get("application/json")
    got_body = got.get("requestBody", {}).get("content", {}).get("application/json")
    assert _ref(got_body) == _ref(want_body)
    assert set(got_resp.get("content", {})) == set(want_resp.get("content", {}))
    for ctype, media in want_resp.get("content", {}).items():
        if ctype == "application/json":
            assert _ref(got_resp["content"][ctype]) == _ref(media)


def test_pending_operations_are_really_unrouted():
    routed = {op["operationId"] for item in _app_doc()["paths"].values() for op in item.values()}
    assert not (PENDING & routed), f"remove from PENDING: {sorted(PENDING & routed)}"
    assert PENDING <= set(CONTRACT), sorted(PENDING - set(CONTRACT))


def test_every_contract_operation_is_routed():
    assert PENDING == set()  # Task 28: nothing in the contract is left unimplemented
