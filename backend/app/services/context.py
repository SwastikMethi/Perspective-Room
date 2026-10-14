"""Immutable run snapshots and token budgeting (docs 02, 06)."""

import json
import math
from typing import Any

from app.catalog import Catalog
from app.persistence.models import IdeaCard
from app.persistence.models import Session as SessionRow
from app.prompts.loader import TEMPLATE_DIR, template
from app.settings import AppEnv


def estimate_tokens(text: str) -> int:
    # ponytail: chars/4 heuristic; swap in a tokenizer if limits start to bite.
    return math.ceil(len(text) / 4)


def template_hashes() -> dict[str, str]:
    return {p.stem: template(p.stem).sha256 for p in sorted(TEMPLATE_DIR.glob("*.md"))}


def build_snapshot(
    *,
    env: AppEnv,
    catalog: Catalog,
    session: SessionRow,
    control: dict[str, Any],
    message_id: str,
    message_text: str,
    cards: list[IdeaCard],
) -> dict[str, Any]:
    """Everything a run needs, frozen at submission: later edits never change it."""
    selected = list(session.selected_persona_ids)
    d = catalog.defaults
    return {
        "session_version": session.version,
        "mode": session.mode,
        "selected": selected,
        "profiles": {p: catalog.personas[p].model_dump(mode="json") for p in selected},
        "profile_hashes": {p: catalog.persona_hash(p) for p in selected},
        "settings": dict(session.settings),
        "brief": dict(session.brief),
        "memory": session.memory,
        "control": control,
        "message_id": message_id,
        "message_text": message_text,
        "idea_cards": [
            {
                "id": str(c.id),
                "message_id": str(c.message_id),
                "title": c.title,
                "note": c.note,
                "status": c.status,
            }
            for c in cards
        ],
        "models": {
            "openai_model": env.OPENAI_MODEL,
            "research_model": env.OPENAI_RESEARCH_MODEL,
            "jev_model": env.JEV_MODEL,
            "reasoning_effort": env.OPENAI_REASONING_EFFORT,
        },
        "limits": d.limits.model_dump(),
        "timeouts": d.timeouts_seconds.model_dump(),
        "thresholds": d.jev_thresholds.model_dump(),
        "templates": template_hashes(),
        "turn_output_budget": d.experiment.base_output_budget_per_turn,
        "provider_mode": env.APP_PROVIDER_MODE,
        "roster": list(catalog.order),
    }


def required_context_tokens(
    snapshot: dict[str, Any], reply_text: str, cards: list[IdeaCard], max_output: int
) -> int:
    """Material that can never be dropped (TRD §Context) plus the reserved output."""
    brief = snapshot["brief"]
    parts = [
        snapshot["message_text"],
        brief["idea"],
        brief.get("goal") or "",
        "\n".join(brief.get("constraints", [])),
        reply_text,
        json.dumps(snapshot["profiles"]),
        "\n".join(f"{c.title}\n{c.note}" for c in cards),
    ]
    return sum(estimate_tokens(p) for p in parts) + max_output
