"""Session export (doc 08 §Fork and export semantics, doc 07 §Display and export).

Public provenance only: never keys, prompts, run snapshots, provider diagnostics or hidden
reasoning. Markdown numbers each source once, in order of first citation; the JSON document
keeps every block/item → source mapping by ID.
"""

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.catalog import Catalog
from app.domain.internal import WARNING_TEXT
from app.persistence.models import IdeaCard, IdeaRevision, Message, ResearchPack, Run, Source
from app.persistence.models import Session as SessionRow
from app.services.common import active_run_id, utcnow
from app.services.ideas import card_out, source_out
from app.services.runs import run_out
from app.services.sessions import session_out
from app.services.transcript import message_out

SCHEMA = "perspective-room/session-export"
SCHEMA_VERSION = 1
MODE_LABELS = {"jev_guided": "Jev-guided", "fixed_panel": "Fixed panel", "standard": "Standard"}
SECTION_LABELS = {
    "directions": "Directions",
    "disagreements": "Disagreements",
    "assumptions": "Assumptions",
    "questions": "Open questions",
    "experiments": "Experiments",
}


@dataclass(frozen=True)
class Exported:
    body: str
    media_type: str
    filename: str


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "chat"


async def build_document(db: AsyncSession, catalog: Catalog, session_id: UUID) -> dict[str, Any]:
    row = await db.get(SessionRow, session_id)
    if row is None:
        raise ApiError(404, "not_found", "Chat not found.")
    if row.evaluation_batch_id is not None:
        raise ApiError(409, "evaluation_managed", "Use the Lab export for Experiment Lab chats.")

    async def rows(model: Any, *order: Any) -> list[Any]:
        q = select(model).where(model.session_id == session_id).order_by(*order)
        return list((await db.scalars(q)).all())

    messages = await rows(Message, Message.sequence)
    runs = await rows(Run, Run.created_at, Run.id)
    packs = await rows(ResearchPack, ResearchPack.created_at, ResearchPack.id)
    names = {pid: p.display_name for pid, p in catalog.personas.items()}
    # Round status lives on each user message, so a fork (which copies no runs) keeps it.
    rounds = [
        {
            "user_message_id": str(m.id),
            "status": m.round_status,
            "provider_mode": (m.round_info or {}).get("provider_mode"),
            "warning_codes": list((m.round_info or {}).get("warning_codes", [])),
            "missing_persona_ids": list((m.round_info or {}).get("missing_persona_ids", [])),
            "degraded": bool((m.round_info or {}).get("degraded", False)),
        }
        for m in messages
        if m.role == "user" and m.round_info is not None
    ]
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "exported_at": utcnow().isoformat(),
        "session": session_out(row, await active_run_id(db, session_id)).model_dump(mode="json"),
        "labels": {
            "mode": MODE_LABELS[row.mode],
            "demo": any(r.get("provider_mode") == "demo" for r in rounds)
            or any(r.snapshot.get("provider_mode") == "demo" for r in runs),
            "degraded": any(r["degraded"] for r in rounds) or any(r.degraded for r in runs),
        },
        "rounds": rounds,
        "participants": {pid: names[pid] for pid in catalog.order},
        "brief_revisions": [
            {
                "revision": r.revision,
                "idea": r.idea,
                "goal": r.goal,
                "constraints": list(r.constraints),
                "author_type": r.author_type,
                "created_at": r.created_at.isoformat(),
            }
            for r in await rows(IdeaRevision, IdeaRevision.revision)
        ],
        "messages": [message_out(m).model_dump(mode="json") for m in messages],
        "runs": [
            {
                **run_out(r).model_dump(mode="json"),
                "user_message_id": str(r.user_message_id) if r.user_message_id else None,
                "mode": r.mode,
                "audience": r.audience,
                "missing_persona_ids": list(r.missing),
                "retry_of_run_id": str(r.retry_of_run_id) if r.retry_of_run_id else None,
            }
            for r in runs
        ],
        "research_packs": [
            {
                "id": str(p.id),
                "query": p.query,
                "status": p.status,
                "findings": (p.normalized or {}).get("findings", []),
                "unknowns": list(p.unknowns),
                "provider_response_id": p.provider_response_id,
                "is_fixture": p.is_fixture,
                "created_at": p.created_at.isoformat(),
            }
            for p in packs
        ],
        "sources": [
            source_out(s).model_dump(mode="json")
            for s in await rows(Source, Source.retrieved_at, Source.id)
        ],
        "idea_cards": [
            card_out(c).model_dump(mode="json")
            for c in await rows(IdeaCard, IdeaCard.created_at, IdeaCard.id)
        ],
    }


def to_markdown(doc: dict[str, Any]) -> str:
    session, labels, names = doc["session"], doc["labels"], doc["participants"]
    sources = {s["id"]: s for s in doc["sources"]}
    numbers: dict[str, int] = {}

    def cite(ids: list[str]) -> str:
        marks = []
        for sid in ids:
            if sid in sources:
                numbers.setdefault(sid, len(numbers) + 1)
                marks.append(f"[{numbers[sid]}]")
        return (" " + "".join(marks)) if marks else ""

    out = [f"# {session['title']}", ""]
    out.append(f"- Mode: {labels['mode']}")
    out.append(f"- Exported: {doc['exported_at']}")
    if labels["demo"]:
        out.append(f"- {WARNING_TEXT['demo_mode']}")
    if labels["degraded"]:
        out.append("- Some turns were degraded; see the notes under those turns.")
    brief = session["brief"]
    out += ["", f"## Brief (revision {brief['revision']})", "", f"**Idea:** {brief['idea']}"]
    if brief.get("goal"):
        out.append(f"**Goal:** {brief['goal']}")
    if brief["constraints"]:
        out += ["", "**Constraints:**", *[f"- {c}" for c in brief["constraints"]]]

    notes: dict[str, list[str]] = {}
    for r in doc["rounds"]:
        texts = [WARNING_TEXT.get(c, c) for c in r["warning_codes"] if c != "demo_mode"]
        if r["missing_persona_ids"]:
            missing = ", ".join(names.get(p, p) for p in r["missing_persona_ids"])
            texts.append(f"Missing replies: {missing}.")
        notes[r["user_message_id"]] = texts

    out += ["", "## Transcript"]
    for m in doc["messages"]:
        out.append("")
        if m["role"] == "user":
            out += [f"### You — {m['created_at'][:16].replace('T', ' ')}", "", m["text"] or ""]
            for note in dict.fromkeys(notes.get(m["id"], [])):
                out += ["", f"> Note: {note}"]
        elif m["contribution"]:
            c = m["contribution"]
            who = names.get(m["persona_id"], "Assistant") if m["persona_id"] else "Assistant"
            out += [f"### {who} — {c['headline']}", ""]
            out += [f"- *{b['kind']}:* {b['text']}{cite(b['source_ids'])}" for b in c["blocks"]]
            out += ["", f"*New angle:* {c['new_angle']}"]
            if c.get("next_question"):
                out.append(f"*Next question:* {c['next_question']}")
        elif m["summary"]:
            out.append("### Moderator — Summary")
            for sec in m["summary"]["sections"]:
                out += ["", f"#### {SECTION_LABELS[sec['kind']]}", ""]
                out += [f"- {i['text']}{cite(i['source_ids'])}" for i in sec["items"]]
        else:
            out += ["### Moderator", "", m["text"] or ""]

    speakers = {
        m["id"]: names.get(m["persona_id"], "Assistant") if m["persona_id"] else "Moderator"
        for m in doc["messages"]
    }
    out += ["", "## Saved ideas", ""]
    out += [
        f"- **{c['title']}** ({c['status']}, from {speakers.get(c['message_id'], 'a reply')})"
        + (f" — {c['note']}" if c["note"] else "")
        for c in doc["idea_cards"]
    ] or ["No saved ideas."]

    out += ["", "## Sources", ""]
    ordered = sorted(sources, key=lambda sid: numbers.get(sid, len(sources) + 1))
    for sid in ordered:
        numbers.setdefault(sid, len(numbers) + 1)
        s = sources[sid]
        tag = " (fixture)" if s["is_fixture"] else ""
        out.append(
            f"{numbers[sid]}. {s['title']} — {s['domain']}, retrieved {s['retrieved_at'][:10]}"
            f"{tag}  \n   <{s['url']}>"
        )
    if not sources:
        out.append("No sources were retrieved in this chat.")
    return "\n".join(out) + "\n"


async def export_session(
    db: AsyncSession, catalog: Catalog, session_id: UUID, fmt: str
) -> Exported:
    doc = await build_document(db, catalog, session_id)
    name = f"perspective-room-{_slug(doc['session']['title'])}-{doc['exported_at'][:10]}"
    if fmt == "json":
        body = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        return Exported(body, "application/json", f"{name}.json")
    return Exported(to_markdown(doc), "text/markdown; charset=utf-8", f"{name}.md")
