"""Deterministic coordination policy (doc 05). Pure functions: no I/O, no model calls.

Order: Stop/limits (callers) → explicit user choices → eligibility → valid, confident Jev
answers → fixed fallback when an answer is uncertain, malformed or unavailable.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.services.jev_questions import Answer, ChoiceAnswer, ScoreAnswer

RETURN_USER = "return_user"
FIXED_MOVES = ("explore", "challenge", "expand")


def eligible(selected: list[str], heard: set[str]) -> list[str]:
    """Selected participants not yet heard in this automatic round, in selection order."""
    return [p for p in selected if p not in heard]


def fallback_speaker(
    candidates: list[str], last_heard: dict[str, int], selection_order: list[str]
) -> str:
    """Least recently heard (never heard first), ties broken by selection order."""
    return min(candidates, key=lambda p: (last_heard.get(p, -1), selection_order.index(p)))


def fallback_move(index: int) -> str:
    return "explore" if index == 0 else "expand"


def fixed_panel_plan(selected: list[str], round_index: int, k: int) -> list[tuple[str, str]]:
    """Condition B (G6): round-robin speakers continuing across rounds, with a move cycle that
    rotates per round so a persona is not locked to one move. Never repeats a speaker."""
    n = len(selected)
    k = min(k, n)
    return [
        (selected[(round_index * k + j) % n], FIXED_MOVES[(round_index + j) % len(FIXED_MOVES)])
        for j in range(k)
    ]


@dataclass
class Route:
    speaker: str | None  # None means return control to the user
    move: str
    fallback_reason: str | None  # why the speaker came from the fixed fallback, if it did
    confidence: float | None = None
    move_fallback: str | None = None  # why the move is the default, if it is


def _confident_choice(answer: Answer | None, threshold: float) -> tuple[str | None, str | None]:
    if answer is None:
        return None, "unavailable"
    if not isinstance(answer, ChoiceAnswer):
        return None, "invalid"
    if answer.confidence < threshold:
        return None, "low_confidence"
    return answer.choice, None


def decide_route(
    answers: dict[str, Answer],
    candidates: list[str],
    threshold: float,
    index: int,
    last_heard: dict[str, int],
    selection_order: list[str],
    *,
    target: str | None = None,
    move_override: str | None = None,
) -> Route:
    reason = None
    confidence = None
    if target is not None:
        speaker: str | None = target
    elif len(candidates) == 1:
        speaker = candidates[0]  # a single eligible option is chosen in code
    else:
        picked, reason = _confident_choice(answers.get("next_speaker"), threshold)
        a = answers.get("next_speaker")
        confidence = a.confidence if isinstance(a, ChoiceAnswer) else None
        if picked == RETURN_USER:
            return Route(None, fallback_move(index), None, confidence)
        if picked is None or picked not in candidates:
            reason = reason or "invalid"
            speaker = fallback_speaker(candidates, last_heard, selection_order)
        else:
            speaker = picked
    if move_override is not None:
        return Route(speaker, move_override, reason, confidence)
    move, move_reason = _confident_choice(answers.get(f"move_{speaker}"), threshold)
    return Route(speaker, move or fallback_move(index), reason, confidence, move_reason)


def decide_research(
    policy: str,
    override: str,
    intake_query: str | None,
    answer: Answer | None,
    capacity: int,
    threshold: float,
    mode: str,
) -> bool:
    """G7. `force` always researches; `off` (turn or session) never; auto needs a query and, in
    Jev-guided mode with a valid answer, `needed` above the routing threshold."""
    if capacity <= 0 or override == "off":
        return False
    if override == "force":
        return True
    if policy == "off" or not intake_query:
        return False
    if mode == "jev_guided" and isinstance(answer, ChoiceAnswer):
        return answer.choice == "needed" and answer.confidence >= threshold
    return True  # A/B, or C with an unavailable/invalid answer: the intake's judgment


def repair_dimension(
    scores: Mapping[str, Answer], bad_below: float, min_confidence: float
) -> str | None:
    """The first dimension confidently scored as bad. Low-confidence scores are observations."""
    for dim, a in scores.items():
        if isinstance(a, ScoreAnswer) and a.score < bad_below and a.confidence >= min_confidence:
            return dim
    return None
