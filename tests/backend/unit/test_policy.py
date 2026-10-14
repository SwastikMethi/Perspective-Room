"""Deterministic policy (doc 05 §Deterministic policy, G6, G7)."""

import pytest

from app.services.jev_questions import ChoiceAnswer, Invalid, ScoreAnswer
from app.services.policy import (
    RETURN_USER,
    decide_research,
    decide_route,
    eligible,
    fallback_move,
    fallback_speaker,
    fixed_panel_plan,
    repair_dimension,
)

SEL = ["mentor", "skeptic", "explorer"]


def choice(c, conf=0.8, options=None):
    opts = options or [c]
    return ChoiceAnswer(c, {o: 1 / len(opts) for o in opts}, conf)


def test_eligible_excludes_heard_and_keeps_selection_order():
    assert eligible(SEL, {"skeptic"}) == ["mentor", "explorer"]


def test_fallback_speaker_is_least_recently_heard_then_selection_order():
    assert fallback_speaker(SEL, {}, SEL) == "mentor"
    assert fallback_speaker(SEL, {"mentor": 3, "skeptic": 1}, SEL) == "explorer"
    assert fallback_speaker(["mentor", "skeptic"], {"mentor": 2, "skeptic": 2}, SEL) == "mentor"


def test_fallback_move_is_explore_then_expand():
    assert [fallback_move(i) for i in range(3)] == ["explore", "expand", "expand"]


def test_fixed_panel_plan_rotates_moves_and_never_repeats_a_speaker():
    assert fixed_panel_plan(SEL, 0, 3) == [
        ("mentor", "explore"),
        ("skeptic", "challenge"),
        ("explorer", "expand"),
    ]
    assert fixed_panel_plan(SEL, 1, 3) == [
        ("mentor", "challenge"),
        ("skeptic", "expand"),
        ("explorer", "explore"),
    ]
    two = fixed_panel_plan(["mentor", "skeptic"], 0, 3)
    assert [s for s, _ in two] == ["mentor", "skeptic"]  # min(k, n): one voice per round
    five = ["mentor", "skeptic", "explorer", "strategist", "engineer"]
    assert [s for s, _ in fixed_panel_plan(five, 1, 3)] == ["strategist", "engineer", "mentor"]


def test_valid_confident_jev_choice_wins():
    answers = {"next_speaker": choice("skeptic"), "move_skeptic": choice("challenge")}
    r = decide_route(answers, SEL, 0.35, 0, {}, SEL)
    assert (r.speaker, r.move, r.fallback_reason) == ("skeptic", "challenge", None)


def test_explicit_target_and_move_override_jev():
    answers = {"next_speaker": choice("mentor"), "move_skeptic": choice("expand")}
    r = decide_route(answers, SEL, 0.35, 0, {}, SEL, target="skeptic", move_override="combine")
    assert (r.speaker, r.move) == ("skeptic", "combine")


@pytest.mark.parametrize(
    "answer,reason",
    [
        (choice("skeptic", conf=0.2), "low_confidence"),
        (Invalid("choice is not one of the requested options"), "invalid"),
        (None, "unavailable"),
    ],
)
def test_uncertain_or_bad_speaker_falls_back_deterministically(answer, reason):
    answers = {} if answer is None else {"next_speaker": answer}
    r = decide_route(answers, SEL, 0.35, 0, {"mentor": 0}, SEL)
    assert r.speaker == "skeptic" and r.fallback_reason == reason and r.move == "explore"


def test_single_eligible_option_is_chosen_in_code():
    r = decide_route({"next_speaker": Invalid("x")}, ["explorer"], 0.35, 1, {}, SEL)
    assert r.speaker == "explorer" and r.fallback_reason is None and r.move == "expand"


def test_return_user_is_honored():
    r = decide_route({"next_speaker": choice(RETURN_USER)}, SEL, 0.35, 1, {}, SEL)
    assert r.speaker is None


@pytest.mark.parametrize(
    "policy,override,query,answer,mode,expected",
    [
        ("auto", "auto", "q", choice("needed", 0.9), "jev_guided", True),
        ("auto", "auto", "q", choice("needed", 0.2), "jev_guided", False),
        ("auto", "auto", "q", choice("not_needed", 0.9), "jev_guided", False),
        ("auto", "auto", None, choice("needed", 0.9), "jev_guided", False),
        ("auto", "auto", "q", Invalid("x"), "jev_guided", True),  # G7 fallback: intake query
        ("auto", "auto", "q", None, "fixed_panel", True),
        ("auto", "auto", None, None, "standard", False),
        ("off", "auto", "q", choice("needed", 0.9), "jev_guided", False),
        ("off", "force", None, None, "fixed_panel", True),
        ("auto", "off", "q", choice("needed", 0.9), "jev_guided", False),
    ],
)
def test_research_decision(policy, override, query, answer, mode, expected):
    assert decide_research(policy, override, query, answer, 1, 0.35, mode) is expected


def test_research_is_never_decided_without_capacity():
    assert decide_research("auto", "force", "q", None, 0, 0.35, "jev_guided") is False


def score(s, conf):
    return ScoreAnswer(s, {"0": 0.2, "1": 0.3, "2": 0.5}, conf)


def test_repair_needs_a_low_score_with_high_confidence():
    assert (
        repair_dimension(
            {"profile_fit": score(0.4, 0.8), "distinct_value": score(2, 0.9)}, 0.5, 0.7
        )
        == "profile_fit"
    )
    assert repair_dimension({"profile_fit": score(0.4, 0.5)}, 0.5, 0.7) is None  # observation
    assert repair_dimension({"profile_fit": Invalid("x")}, 0.5, 0.7) is None
