"""Internal (non-contract) vocabulary: identifiers derived from the generated contract models."""

from types import UnionType
from typing import Literal, Union, get_args, get_origin

from app.domain import api


def _literal_values(annotation: object) -> tuple[str, ...]:
    """Values of the Literal inside `annotation` (unwrapping `X | None` and `list[X]`)."""
    origin = get_origin(annotation)
    if origin is Literal:
        return tuple(get_args(annotation))
    if origin in (Union, UnionType, list):
        for arg in get_args(annotation):
            values = _literal_values(arg)
            if values:
                return values
    return ()


PERSONA_IDS: tuple[str, ...] = _literal_values(api.Message.model_fields["persona_id"].annotation)
MODES: tuple[str, ...] = _literal_values(api.Session.model_fields["mode"].annotation)

# G2 warning vocabulary with the plain text shown in the UI and exports.
WARNING_TEXT: dict[str, str] = {
    "coordination_fallback": "Fixed order used for this turn.",
    "coordination_unavailable": "Jev was unavailable; fixed order used for this turn.",
    "audit_unavailable": "Quality checks were unavailable for some replies.",
    "quality_warning": "A reply was published with a quality warning.",
    "repair_used": "One reply was revised once after a quality check.",
    "research_unavailable": "Current facts were not checked; replies use labeled assumptions.",
    "research_empty": "The search found no usable sources; nothing was verified.",
    "research_findings_dropped": "Research findings without valid sources were dropped.",
    "memory_unavailable": "The conversation memory was not updated after this turn.",
    "contribution_failed": "Some replies could not be produced.",
    "deadline_exceeded": "The turn reached its time limit.",
    "usage_unknown": "Some provider usage is unknown.",
    "demo_mode": "Demo mode — deterministic fixtures, no external calls.",
    "budget_cap_unenforced": "The session cost cap cannot be enforced (no rate card).",
    "intake_unavailable": "The turn was read without the usual intake step.",
    "attempts_exhausted": "The turn reached its limit of provider calls.",
}
