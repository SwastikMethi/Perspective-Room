"""The demo provider is deterministic, schema-valid, labeled, and honors test directives."""

import json

import pytest
from contract_support import component

from app.providers.base import Incomplete, ProviderFailure, Refused, Structured
from app.providers.demo import DemoCoordinator, DemoGeneration, directives


def payload(**kw):
    base = {
        "task": "contribution",
        "profile": {
            "id": "skeptic",
            "display_name": "Skeptical realist",
            "priorities": ["testable assumptions", "failure conditions", "evidence"],
        },
        "move": "challenge",
        "focus": "Make interview practice feel less intimidating.",
        "latest_user_message": "I want to build an interview-practice app for students.",
        "recent_messages": [],
        "evidence": [],
    }
    base.update(kw)
    return [{"role": "user", "content": [{"type": "input_text", "text": json.dumps(base)}]}]


async def ask(gen, schema_name, **kw):
    return await gen.structured(
        purpose="draft",
        instructions="x",
        input_items=payload(**kw),
        schema_name=schema_name,
        schema={},
        max_output_tokens=4096,
        model="demo",
        reasoning_effort=None,
    )


def test_directives_are_parsed_from_user_text():
    d = directives("[[demo:delay=1500]] [[demo:fail=skeptic]] please [[demo:long]]")
    assert d == {"delay": "1500", "fail": "skeptic", "long": ""}
    assert directives("no directives here") == {}


async def test_contribution_is_deterministic_and_contract_valid():
    gen = DemoGeneration()
    a, b = await ask(gen, "contribution"), await ask(gen, "contribution")
    assert isinstance(a, Structured) and a.data == b.data
    assert not list(component("Contribution").iter_errors(a.data))
    assert a.model == "demo" and a.usage.input_tokens is None


async def test_personas_produce_different_contributions():
    gen = DemoGeneration()
    s = await ask(gen, "contribution")
    m = await ask(
        gen,
        "contribution",
        profile={
            "id": "mentor",
            "display_name": "Empathetic mentor",
            "priorities": ["emotional safety"],
        },
        move="explore",
    )
    assert s.data["headline"] != m.data["headline"]


async def test_cites_only_supplied_evidence():
    gen = DemoGeneration()
    ev = [{"source_id": "src-1", "statement": "A pilot found practice helped.", "title": "Pilot"}]
    r = await ask(gen, "contribution", evidence=ev)
    cited = {sid for b in r.data["blocks"] for sid in b["source_ids"]}
    assert cited <= {"src-1"}


@pytest.mark.parametrize("name", ["intake", "summary", "memory", "research"])
async def test_other_schemas_are_contract_valid(name):
    gen = DemoGeneration()
    extra = {
        "recent_messages": [
            {
                "id": "m1",
                "role": "persona",
                "persona_id": "mentor",
                "headline": "Start small",
                "text": "Try one answer.",
            }
        ],
        "source_map": {"src-1": {"title": "Pilot", "url": "https://example.org/a"}},
        "research_text": "A pilot found practice helped.",
        "query": "interview practice evidence",
    }
    r = await ask(gen, name, **extra)
    title = {"intake": "Intake", "summary": "Summary", "memory": "Memory", "research": "Research"}
    assert not list(component(title[name]).iter_errors(r.data)), r.data


async def test_failure_refusal_and_incomplete_directives():
    gen = DemoGeneration()
    msg = "[[demo:fail=skeptic]] go"
    with pytest.raises(ProviderFailure):
        await ask(gen, "contribution", latest_user_message=msg)
    other = {"id": "mentor", "display_name": "Empathetic mentor", "priorities": ["safety"]}
    assert isinstance(
        await ask(gen, "contribution", latest_user_message=msg, profile=other), Structured
    )
    assert isinstance(
        await ask(gen, "contribution", latest_user_message="[[demo:refuse]]"), Refused
    )
    assert isinstance(
        await ask(gen, "contribution", latest_user_message="[[demo:incomplete]]"), Incomplete
    )


async def test_demo_coordinator_answers_every_question_validly():
    jev = DemoCoordinator()
    questions = {
        "next_speaker": {
            "type": "choice",
            "instructions": "x",
            "criteria": {"mentor": "a", "skeptic": "b", "return_user": "c"},
        },
        "fit": {"type": "score", "instructions": "x", "criteria": ["bad", "ok", "good"]},
    }
    out = await jev.ask({"latest_user_message": "hi", "already_heard": []}, questions)
    ans = out["answers"]
    assert ans["next_speaker"]["choice"] in questions["next_speaker"]["criteria"]
    assert abs(sum(ans["next_speaker"]["probabilities"].values()) - 1) < 1e-9
    assert 0 <= ans["fit"]["score"] <= 2 and set(ans["fit"]["probabilities"]) == {"0", "1", "2"}


async def test_fail_once_fails_the_first_attempt_per_message_then_succeeds():
    gen = DemoGeneration()
    msg = "[[demo:fail_once=skeptic]] go"
    with pytest.raises(ProviderFailure):
        await ask(gen, "contribution", latest_user_message=msg, latest_user_message_id="m1")
    ok = await ask(gen, "contribution", latest_user_message=msg, latest_user_message_id="m1")
    assert isinstance(ok, Structured)
    with pytest.raises(ProviderFailure):  # a different turn fails once too
        await ask(gen, "contribution", latest_user_message=msg, latest_user_message_id="m2")
