"""The response-validation hook must actually catch contract drift."""

import pytest
from contract_support import ContractViolation, check_response


def test_hook_accepts_a_valid_health_body():
    body = {"status": "ok", "database": "ok", "worker": "ok", "version": "1.1.0"}
    check_response("GET", "/api/v1/health", 200, "application/json", body)


def test_hook_rejects_wrong_shape_extra_field_and_undeclared_status():
    with pytest.raises(ContractViolation, match="required property"):
        check_response("GET", "/api/v1/health", 200, "application/json", {"status": "fine"})
    with pytest.raises(ContractViolation):
        good = {"status": "ok", "database": "ok", "worker": "ok", "version": "1", "extra": 1}
        check_response("GET", "/api/v1/health", 200, "application/json", good)
    with pytest.raises(ContractViolation, match="not declared"):
        check_response("GET", "/api/v1/health", 418, "application/json", {})


def test_hook_requires_error_envelope_on_unknown_routes():
    with pytest.raises(ContractViolation):
        check_response("GET", "/api/v1/zzz", 404, "application/json", {"detail": "Not Found"})


def test_path_templates_match_concrete_ids():
    check_response(
        "GET",
        "/api/v1/sessions/00000000-0000-4000-8000-000000000001/sources",
        404,
        "application/json",
        {"code": "not_found", "message": "x", "retryable": False, "request_id": "r", "details": {}},
    )
