"""Deterministic validation of model output (docs 05, 07, 08). Provenance checks only: code
decides which messages and sources may be referenced; model text never widens that set."""

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.domain import api

SUMMARY_ORDER = ["directions", "disagreements", "assumptions", "questions", "experiments"]
NOTHING_ESTABLISHED = "No item was established."
LIMITS = {
    "headline": 160,
    "block": 2400,
    "new_angle": 400,
    "question": 400,
    "blocks": 12,
    "item": 1200,
    "title": 120,
    "focus": 400,
    "query": 300,
}


@dataclass
class Violation:
    code: str
    detail: str


def _text(v: list[Violation], value: str | None, field: str, limit: int) -> None:
    if value is None or not value.strip():
        v.append(Violation("empty_text", f"{field} is empty"))
    elif len(value) > limit:
        v.append(Violation("too_long", f"{field} exceeds {limit} characters"))


def _refs(v: list[Violation], ids: list[str], allowed: set[str], code: str, where: str) -> None:
    unknown = [i for i in ids if i not in allowed]
    if unknown:
        v.append(Violation(code, f"{where} references {len(unknown)} unknown id(s)"))


def validate_contribution(
    data: dict[str, Any], *, allowed_message_ids: set[str], allowed_source_ids: set[str]
) -> list[Violation]:
    try:
        c = api.Contribution.model_validate(data)
    except ValidationError as e:
        return [Violation("schema", f"{e.error_count()} schema error(s)")]
    v: list[Violation] = []
    _text(v, c.headline, "headline", LIMITS["headline"])
    _text(v, c.new_angle, "new_angle", LIMITS["new_angle"])
    if c.next_question is not None and len(c.next_question) > LIMITS["question"]:
        v.append(Violation("too_long", "next_question is too long"))
    if not c.blocks:
        v.append(Violation("no_blocks", "a contribution needs at least one block"))
    if len(c.blocks) > LIMITS["blocks"]:
        v.append(Violation("too_long", "too many blocks"))
    for i, b in enumerate(c.blocks):
        _text(v, b.text, f"block {i}", LIMITS["block"])
        _refs(v, b.source_ids, allowed_source_ids, "unknown_source", f"block {i}")
        if b.kind == "fact" and not b.source_ids:
            v.append(
                Violation("unsupported_fact", f"block {i} states an external fact without evidence")
            )
    _refs(
        v,
        c.referenced_message_ids,
        allowed_message_ids,
        "foreign_message_reference",
        "referenced_message_ids",
    )
    return v


def _items(
    v: list[Violation],
    items: list[dict[str, Any]],
    allowed_messages: set[str],
    allowed_sources: set[str],
    where: str,
    require_provenance: bool,
) -> None:
    for i, item in enumerate(items):
        _text(v, item.get("text"), f"{where} item {i}", LIMITS["item"])
        _refs(
            v,
            item.get("source_message_ids", []),
            allowed_messages,
            "foreign_message_reference",
            f"{where} item {i}",
        )
        _refs(v, item.get("source_ids", []), allowed_sources, "unknown_source", f"{where} item {i}")
        if require_provenance and not item.get("source_message_ids"):
            v.append(Violation("no_provenance", f"{where} item {i} cites no message"))


def validate_summary(
    data: dict[str, Any], *, allowed_message_ids: set[str], allowed_source_ids: set[str]
) -> list[Violation]:
    try:
        s = api.Summary.model_validate(data)
    except ValidationError as e:
        return [Violation("schema", f"{e.error_count()} schema error(s)")]
    v: list[Violation] = []
    if [sec.kind for sec in s.sections] != SUMMARY_ORDER:
        v.append(Violation("section_order", "a summary has exactly the five sections in order"))
    for sec in s.sections:
        _items(
            v,
            [i.model_dump() for i in sec.items],
            allowed_message_ids,
            allowed_source_ids,
            sec.kind,
            require_provenance=False,
        )
    return v


def normalize_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Empty sections say no item was established instead of inventing one."""
    out: dict[str, Any] = {"sections": []}
    for sec in data["sections"]:
        items = sec["items"] or [
            {"text": NOTHING_ESTABLISHED, "source_message_ids": [], "source_ids": []}
        ]
        out["sections"].append({"kind": sec["kind"], "items": items})
    return out


def validate_memory(
    data: dict[str, Any], *, allowed_message_ids: set[str], allowed_source_ids: set[str]
) -> list[Violation]:
    try:
        m = api.Memory.model_validate(data)
    except ValidationError as e:
        return [Violation("schema", f"{e.error_count()} schema error(s)")]
    v: list[Violation] = []
    _text(v, m.overview, "overview", LIMITS["item"])
    for name in ("ideas", "open_questions", "assumptions"):
        _items(
            v,
            [i.model_dump() for i in getattr(m, name)],
            allowed_message_ids,
            allowed_source_ids,
            name,
            require_provenance=True,
        )
    return v


def validate_intake(data: dict[str, Any]) -> list[Violation]:
    try:
        i = api.Intake.model_validate(data)
    except ValidationError as e:
        return [Violation("schema", f"{e.error_count()} schema error(s)")]
    v: list[Violation] = []
    _text(v, i.title_suggestion, "title_suggestion", LIMITS["title"])
    _text(v, i.focus, "focus", LIMITS["focus"])
    if i.research_query is not None and len(i.research_query) > LIMITS["query"]:
        v.append(Violation("too_long", "research_query is too long"))
    if i.clarifying_question is not None and len(i.clarifying_question) > LIMITS["question"]:
        v.append(Violation("too_long", "clarifying_question is too long"))
    return v


def validate_research(data: dict[str, Any], *, source_ids: set[str]) -> tuple[dict[str, Any], int]:
    """Keep only findings supported exclusively by server-assigned sources. Returns the cleaned
    pack and how many findings were dropped (the normalizer can never add a source)."""
    pack = api.Research.model_validate(data).model_dump(mode="json")
    kept = [
        f
        for f in pack["findings"]
        if f["statement"].strip() and f["source_ids"] and set(f["source_ids"]) <= source_ids
    ]
    return {**pack, "findings": kept}, len(pack["findings"]) - len(kept)


def normalize_intake(data: dict[str, Any]) -> dict[str, Any]:
    """Blank optional strings mean "none" (a whitespace clarification is never published)."""
    out = dict(data)
    for key in ("clarifying_question", "research_query", "research_reason"):
        if isinstance(out.get(key), str) and not out[key].strip():
            out[key] = None
    return out
