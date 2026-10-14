"""Handoff fixtures validate against the contract and round-trip through the generated models."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from contract_support import SPEC_PATH, component

from app.domain import api
from app.domain.internal import MODES, PERSONA_IDS

FIXTURES = Path(__file__).resolve().parents[3] / "handoff" / "fixtures"

FIXTURE_COMPONENTS = {
    "api.session.example.json": "Session",
    "api.session-list.example.json": "SessionList",
    "api.message.example.json": "Message",
    "api.run-event.example.json": "RunEvent",
    "api.turn.request.json": "TurnCreate",
    "api.fork.request.json": "ForkCreate",
    "api.fork-result.example.json": "ForkResult",
    "api.folder.example.json": "Folder",
    "api.organization.request.json": "SessionOrganizationPatch",
    "intake.example.json": "Intake",
    "contribution.example.json": "Contribution",
    "research.example.json": "Research",
    "memory.example.json": "Memory",
    "summary.example.json": "Summary",
}


@pytest.mark.parametrize("fixture,name", sorted(FIXTURE_COMPONENTS.items()))
def test_fixture_matches_contract_and_round_trips(fixture, name):
    data = json.loads((FIXTURES / fixture).read_text())
    errors = list(component(name).iter_errors(data))
    assert not errors, errors[0].message
    model = getattr(api, name).model_validate(data)
    assert model.model_dump(mode="json", exclude_unset=True) == data


def test_internal_literals_match_contract_enums():
    schemas = yaml.safe_load(SPEC_PATH.read_text())["components"]["schemas"]
    assert list(PERSONA_IDS) == schemas["PersonaId"]["enum"]
    assert list(MODES) == schemas["Mode"]["enum"]


def test_rating_amendment_is_in_the_generated_models():
    fields = api.RatingCreate.model_fields
    assert {"labels", "distinct_directions"} <= set(fields)


def test_uri_fields_are_plain_strings():
    assert api.Source.model_fields["url"].annotation is str


def test_required_nullable_fields_stay_required():
    ctl = api.TurnControl.model_fields
    assert all(ctl[f].is_required() for f in ("target_persona_id", "move_override"))
    assert api.ForkCreate.model_fields["through_message_id"].is_required()


def test_handoff_package_validator_passes():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-B", str(root / "handoff/validation/validate_handoff.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
