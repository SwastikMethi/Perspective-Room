"""Jev decisions (doc 05): one batch of independent typed questions per routing step, strict
validation of every returned option and number, and bounded text state."""

import json
import math
from dataclasses import dataclass
from typing import Any

MOVE_CRITERIA = {
    "explore": "Introduce a different possibility connected to the goal.",
    "challenge": "Examine one assumption with a concrete test.",
    "expand": "Develop a promising existing idea into something more concrete.",
    "combine": "Connect two existing ideas or messages into one direction.",
    "clarify": "Ask the user for material missing context.",
}
RESEARCH_CRITERIA = {
    "needed": "A specific external fact must be checked for this turn.",
    "not_needed": "No research question exists, or the contribution is conceptual.",
    "uncertain": "There is not enough information to decide.",
}
RETURN_USER = "return_user"
ASSESS_LEVELS = {
    "profile_fit": (
        "how clearly the candidate reflects the named profile's priorities",
        [
            "Contradicts the profile's priorities or invents credentials.",
            "Generic or unclear relative to the profile.",
            "Clearly reflects the profile's priorities and contribution habits.",
        ],
    ),
    "distinct_value": (
        "what the candidate adds beyond the public messages in the state",
        [
            "Restates a prior point without development.",
            "A modest elaboration of an existing point.",
            "A useful new question, implication, alternative, or concrete development.",
        ],
    ),
    "constraint_fidelity": (
        "how the candidate treats the user's explicit constraints",
        [
            "Contradicts an explicit user constraint.",
            "Ambiguous or incomplete with respect to the constraints.",
            "Respects the constraints or explicitly explains a trade-off.",
        ],
    ),
}


def _profile_line(p: dict[str, Any]) -> str:
    return f"{p['display_name']} — {p['tagline']} Priorities: {', '.join(p['priorities'])}."


def route_questions(
    eligible: list[dict[str, Any]], *, ask_speaker: bool, ask_research: bool, combinable: bool
) -> dict[str, Any]:
    """Questions never depend on each other; each move question is conditional on its persona."""
    questions: dict[str, Any] = {}
    if ask_speaker:
        criteria = {p["id"]: _profile_line(p) for p in eligible}
        criteria[RETURN_USER] = (
            "Another automatic contribution is unlikely to help, or "
            "essential user context is missing."
        )
        questions["next_speaker"] = {
            "type": "choice",
            "instructions": "Which available perspective would most usefully address the "
            "supplied focus now, considering the contributions already heard?",
            "criteria": criteria,
        }
    moves = {k: v for k, v in MOVE_CRITERIA.items() if combinable or k != "combine"}
    for p in eligible:
        questions[f"move_{p['id']}"] = {
            "type": "choice",
            "instructions": f"If {_profile_line(p)} speaks next, which contribution type would "
            "best address the supplied focus?",
            "criteria": dict(moves),
        }
    if ask_research:
        questions["research_needed"] = {
            "type": "choice",
            "instructions": "Does the supplied research question require current external "
            "evidence that would materially help this turn?",
            "criteria": dict(RESEARCH_CRITERIA),
        }
    return questions


def assessment_questions(persona_name: str) -> dict[str, Any]:
    return {
        dim: {
            "type": "score",
            "instructions": f"Rate the candidate contribution by {persona_name} in the state: "
            f"{focus}.",
            "criteria": list(levels),
        }
        for dim, (focus, levels) in ASSESS_LEVELS.items()
    }


@dataclass
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float


@dataclass
class ScoreAnswer:
    score: float
    probabilities: dict[str, float]
    confidence: float


@dataclass
class Invalid:
    reason: str


Answer = ChoiceAnswer | ScoreAnswer | Invalid


def _finite01(x: Any) -> bool:
    return (
        isinstance(x, int | float)
        and not isinstance(x, bool)
        and math.isfinite(x)
        and (0.0 <= x <= 1.0)
    )


def _probabilities(raw: Any, keys: set[str]) -> dict[str, float] | str:
    if not isinstance(raw, dict) or set(raw) != keys:
        return "probabilities do not match the options"
    if not all(_finite01(v) for v in raw.values()):
        return "probabilities must be finite numbers in [0, 1]"
    if abs(sum(raw.values()) - 1.0) > 1e-6:
        return "probabilities sum is not 1"
    return {k: float(v) for k, v in raw.items()}


def _one(q: dict[str, Any], a: Any) -> Answer:
    if not isinstance(a, dict):
        return Invalid("missing answer")
    if a.get("type") != q["type"]:
        return Invalid(f"type mismatch: expected {q['type']}")
    if not _finite01(a.get("confidence")):
        return Invalid("confidence must be a finite number in [0, 1]")
    if q["type"] == "choice":
        options = list(q["criteria"])
        if a.get("choice") not in options:
            return Invalid("choice is not one of the requested options")
        probs = _probabilities(a.get("probabilities"), set(options))
        if isinstance(probs, str):
            return Invalid(probs)
        return ChoiceAnswer(a["choice"], probs, float(a["confidence"]))
    levels = len(q["criteria"])
    score = a.get("score")
    if not (isinstance(score, int | float) and math.isfinite(score) and 0 <= score <= levels - 1):
        return Invalid("score is outside the level range")
    if not isinstance(a.get("legend"), dict):
        return Invalid("score legend missing")
    probs = _probabilities(a.get("probabilities"), {str(i) for i in range(levels)})
    if isinstance(probs, str):
        return Invalid(probs)
    return ScoreAnswer(float(score), probs, float(a["confidence"]))


def validate_answers(questions: dict[str, Any], envelope: Any) -> dict[str, Answer]:
    """Never trust a returned string as an action: everything is checked against the request."""
    answers = envelope.get("answers") if isinstance(envelope, dict) else None
    if not isinstance(answers, dict):
        return {qid: Invalid("missing answers") for qid in questions}
    return {qid: _one(q, answers.get(qid)) for qid, q in questions.items()}


TRIMMABLE_LISTS = ("recent_messages", "prior_public_messages", "idea_ledger", "open_questions")
MAX_FIELD_CHARS = 4000


def _clip(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
        return value[:MAX_FIELD_CHARS] + " …"
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip(v) for v in value]
    return value


def bound_state(state: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    """Fit the text state into the Jev budget: clip long fields, then drop the oldest list items
    (public messages first)."""
    out = _clip(dict(state))

    def size() -> float:
        return len(json.dumps(out)) / 4

    for key in TRIMMABLE_LISTS:
        items = list(out.get(key) or [])
        while items and size() > max_tokens:
            items.pop(0)
            out[key] = items
    return out
