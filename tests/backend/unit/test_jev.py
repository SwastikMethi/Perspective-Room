"""Jev questions (T04), answer validation (T05) and the HTTPX adapter."""

import json
import math
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from app.catalog import load_catalog
from app.providers.base import ProviderFailure
from app.providers.jev_adapter import JevCoordinator
from app.services.jev_questions import (
    ChoiceAnswer,
    Invalid,
    ScoreAnswer,
    assessment_questions,
    bound_state,
    route_questions,
    validate_answers,
)

HANDOFF = Path(__file__).resolve().parents[3] / "handoff"
REQ = json.loads((HANDOFF / "fixtures/jev.route.request.json").read_text())
RESP = json.loads((HANDOFF / "fixtures/jev.route.response.json").read_text())


@pytest.fixture(scope="module")
def trio():
    cat = load_catalog(HANDOFF)
    return [cat.personas[p].model_dump() for p in ("mentor", "skeptic", "explorer")]


def test_route_batch_has_independent_questions_naming_each_persona(trio):
    qs = route_questions(trio, ask_speaker=True, ask_research=True, combinable=True)
    assert set(qs) == {
        "next_speaker",
        "move_mentor",
        "move_skeptic",
        "move_explorer",
        "research_needed",
    }
    assert set(qs["next_speaker"]["criteria"]) == {"mentor", "skeptic", "explorer", "return_user"}
    for p in trio:
        q = qs[f"move_{p['id']}"]
        assert q["type"] == "choice" and p["display_name"] in q["instructions"]
        assert set(q["criteria"]) == {"explore", "challenge", "expand", "combine", "clarify"}
    every_text = json.dumps(qs).lower()
    for other_id in qs:  # question IDs are not model-visible; no question may refer to another
        assert other_id.lower() not in every_text.replace(f'"{other_id.lower()}"', "")
    assert "answer" not in every_text


def test_combine_is_offered_only_when_something_can_be_combined(trio):
    qs = route_questions(trio[:1], ask_speaker=False, ask_research=False, combinable=False)
    assert set(qs) == {"move_mentor"} and "combine" not in qs["move_mentor"]["criteria"]


def test_assessment_uses_three_ordered_score_levels():
    qs = assessment_questions("Skeptical realist")
    assert set(qs) == {"profile_fit", "distinct_value", "constraint_fidelity"}
    for q in qs.values():
        assert q["type"] == "score" and len(q["criteria"]) == 3
        assert "Skeptical realist" in q["instructions"]


def test_handoff_fixture_answers_validate():
    out = validate_answers(REQ["questions"], RESP)
    assert all(isinstance(a, ChoiceAnswer) for a in out.values())
    assert out["next_speaker"].choice == "skeptic"


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda a: a["next_speaker"].update(choice="hacker"), "option"),
        (lambda a: a["next_speaker"]["probabilities"].update(mentor=math.nan), "finite"),
        (lambda a: a["next_speaker"].update(confidence=1.5), "confidence"),
        (lambda a: a.pop("next_speaker"), "missing"),
        (lambda a: a["next_speaker"]["probabilities"].pop("mentor"), "probabilities"),
        (lambda a: a["next_speaker"].update(type="score"), "type"),
        (lambda a: a["next_speaker"]["probabilities"].update(mentor=0.5), "sum"),
    ],
)
def test_malformed_answers_are_rejected(mutate, reason):
    resp = deepcopy(RESP)
    mutate(resp["answers"])
    result = validate_answers(REQ["questions"], resp)["next_speaker"]
    assert isinstance(result, Invalid) and reason in result.reason


def test_missing_envelope_rejects_every_question():
    out = validate_answers(REQ["questions"], {"error": "x"})
    assert all(isinstance(a, Invalid) for a in out.values())


def test_score_answers_validate_and_range_is_enforced():
    qs = assessment_questions("Engineer")
    good = {
        "type": "score",
        "score": 1.35,
        "legend": {"0": "a", "1": "b", "2": "c"},
        "probabilities": {"0": 0.1, "1": 0.45, "2": 0.45},
        "confidence": 0.62,
    }
    out = validate_answers(qs, {"answers": {k: dict(good) for k in qs}})
    assert all(isinstance(a, ScoreAnswer) and a.score == 1.35 for a in out.values())
    bad = {**good, "score": 2.4}
    out = validate_answers(qs, {"answers": {k: dict(bad) for k in qs}})
    assert all(isinstance(a, Invalid) for a in out.values())
    keys = {**good, "probabilities": {"low": 0.2, "mid": 0.4, "high": 0.4}}
    assert isinstance(
        validate_answers(qs, {"answers": {"profile_fit": keys}})["profile_fit"], Invalid
    )


def test_state_is_bounded_and_drops_oldest_messages_first():
    state = {
        "focus": "x",
        "recent_messages": [{"id": str(i), "text": "w " * 800} for i in range(40)],
    }
    bounded = bound_state(state, max_tokens=8000)
    assert len(json.dumps(bounded)) / 4 <= 8000
    kept = [m["id"] for m in bounded["recent_messages"]]
    assert kept and kept == [str(i) for i in range(40 - len(kept), 40)]


class Rec:
    def __init__(self, status=200, body=None, headers=None, exc=None):
        self.status, self.body, self.headers, self.exc = status, body, headers or {}, exc
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        if self.exc:
            raise self.exc(request)
        return httpx.Response(self.status, json=self.body, headers=self.headers)


def jev(rec):
    return JevCoordinator(
        "ts-test-key",
        "jev-1.13.0",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(rec), base_url="https://api.typesafe.ai"
        ),
    )


async def test_adapter_posts_the_envelope_with_bearer_auth():
    rec = Rec(body=RESP)
    out = await jev(rec).ask(REQ["state"], REQ["questions"])
    req = rec.requests[0]
    assert req.url.path == "/v1/systemone" and req.headers["authorization"] == "Bearer ts-test-key"
    body = json.loads(req.content)
    assert body == {"model": "jev-1.13.0", "state": REQ["state"], "questions": REQ["questions"]}
    assert out["answers"]["next_speaker"]["choice"] == "skeptic"


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (529, "transient", True),
        (429, "transient", True),
        (500, "provider_error", False),
        (422, "invalid_request", False),
        (401, "provider_not_ready", False),
    ],
)
async def test_adapter_classifies_errors(status, code, retryable):
    rec = Rec(status=status, body={"detail": "x"}, headers={"x-typesafe-request-id": "tr_1"})
    with pytest.raises(ProviderFailure) as err:
        await jev(rec).ask({}, {})
    assert (err.value.code, err.value.retryable) == (code, retryable)
    assert err.value.request_id == "tr_1"


async def test_adapter_timeout_is_unknown_usage():
    def timeout(request):
        return httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderFailure) as err:
        await jev(Rec(exc=timeout)).ask({}, {})
    assert err.value.code == "timeout" and err.value.usage_unknown


async def test_non_finite_numbers_in_the_jev_body_are_a_provider_failure():
    def nan_body(request):
        return httpx.Response(
            200,
            content=b'{"answers": {"q": {"confidence": NaN}}}',
            headers={"content-type": "application/json"},
        )

    with pytest.raises(ProviderFailure) as err:
        await jev(nan_body).ask({}, {})
    assert err.value.code == "provider_error"


async def test_snapshot_model_overrides_the_adapter_default():
    rec = Rec(body=RESP)
    await jev(rec).ask({}, {}, model="jev-1.12.0")
    assert json.loads(rec.requests[0].content)["model"] == "jev-1.12.0"


def test_state_bounding_also_trims_assessment_context():
    state = {
        "prior_public_messages": [{"headline": "h" * 3000} for _ in range(30)],
        "latest_user_message": "x" * 60000,
    }
    bounded = bound_state(state, max_tokens=8000)
    assert len(json.dumps(bounded)) / 4 <= 8000
