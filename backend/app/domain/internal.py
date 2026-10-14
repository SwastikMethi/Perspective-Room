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
