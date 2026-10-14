"""Validate live API responses against handoff/contracts/openapi.yaml (the one public contract)."""

import re
from functools import cache
from pathlib import Path
from typing import Any

import httpx
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

SPEC_PATH = Path(__file__).resolve().parents[2] / "handoff" / "contracts" / "openapi.yaml"


class ContractViolation(AssertionError):
    pass


@cache
def spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


@cache
def _registry() -> Registry:
    return Registry().with_resource("spec.yaml", DRAFT202012.create_resource(spec()))


def validator_for(schema: dict[str, Any]) -> Draft202012Validator:
    if "$ref" in schema:
        schema = {"$ref": "spec.yaml" + schema["$ref"]}
    return Draft202012Validator(schema, registry=_registry())


def component(name: str) -> Draft202012Validator:
    return validator_for({"$ref": f"#/components/schemas/{name}"})


@cache
def _routes() -> list[tuple[str, re.Pattern[str], dict[str, Any]]]:
    out = []
    for path, item in spec()["paths"].items():
        pattern = re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$")
        for method, op in item.items():
            out.append((method.upper(), pattern, op))
    return out


def operation_for(method: str, path: str) -> dict[str, Any] | None:
    for m, pattern, op in _routes():
        if m == method and pattern.match(path):
            return op
    return None


def check_response(method: str, path: str, status: int, content_type: str, body: Any) -> None:
    """Raise ContractViolation when a JSON response does not match its declared schema."""
    if "application/json" not in content_type:
        return
    op = operation_for(method, path)
    if op is None:
        if status >= 400:  # undeclared test routes still use the Error envelope
            _validate(component("Error"), body, f"{method} {path} {status}")
        return
    declared = op["responses"].get(str(status))
    if declared is None:
        raise ContractViolation(f"{method} {path}: status {status} not declared in contract")
    media = declared.get("content", {}).get("application/json")
    if media is None:
        raise ContractViolation(f"{method} {path}: {status} must not return JSON")
    _validate(validator_for(media["schema"]), body, f"{method} {path} {status}")


def _validate(v: Draft202012Validator, body: Any, where: str) -> None:
    errors = sorted(v.iter_errors(body), key=lambda e: list(e.path))
    if errors:
        e = errors[0]
        raise ContractViolation(f"{where}: {e.message} at {list(e.path)}")


async def _hook(response: httpx.Response) -> None:
    await response.aread()
    body = (
        response.json() if "application/json" in response.headers.get("content-type", "") else None
    )
    check_response(
        response.request.method,
        response.request.url.path,
        response.status_code,
        response.headers.get("content-type", ""),
        body,
    )


def contract_client(app: Any, **kw: Any) -> httpx.AsyncClient:
    """An httpx client for the ASGI app whose every JSON response is contract-validated."""
    transport = httpx.ASGITransport(
        app=app, raise_app_exceptions=kw.pop("raise_app_exceptions", True)
    )
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:8000",
        event_hooks={"response": [_hook]},
        **kw,
    )
