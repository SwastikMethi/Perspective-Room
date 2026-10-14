"""Run pipeline. Checkpoint 2 slice: sequential slots → validate → publish (Task 16 adds routing,
intake, research, assessment, repair, panel concurrency and memory)."""

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from app.catalog import Catalog
from app.domain import api
from app.persistence.models import Run
from app.prompts.loader import template
from app.providers.base import Coordinator, GenerationProvider, ProviderFailure, Structured
from app.services.publish import publish_contribution
from app.services.runs import set_stage, update_run
from app.settings import AppEnv
from app.workers.context import RunContext, RunResult


@dataclass
class Deps:
    env: AppEnv
    catalog: Catalog
    generation: GenerationProvider
    coordinator: Coordinator


def schema_for(name: str, catalog_dir: Any) -> dict[str, Any]:
    raw = json.loads((catalog_dir / "contracts" / "llm" / f"{name}.schema.json").read_text())
    return {k: v for k, v in raw.items() if k not in ("$schema", "title")}


def _input(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload)}]}]


PROVIDER_MODE_CHANGED = {
    "code": "provider_mode_changed",
    "message": "This turn was queued in a different provider mode (live/demo) than the app now "
    "runs in. Nothing was generated; send it again.",
    "retryable": False,
    "request_id": "",
    "details": {},
}


async def execute(ctx: RunContext, deps: Deps) -> RunResult:
    snap = ctx.snapshot
    if snap["provider_mode"] != deps.env.APP_PROVIDER_MODE:  # never demo for live, or vice versa
        return RunResult(status="failed", error=PROVIDER_MODE_CHANGED)
    if snap["provider_mode"] == "demo":
        ctx.warn("demo_mode")
    async with ctx.sessionmaker() as s:
        run = await s.scalar(select(Run).where(Run.id == ctx.run_id))
        assert run is not None
        slots = list(run.slots) or list(snap["selected"][: run.requested_count])
    schema = schema_for("contribution", deps.env.HANDOFF_DIR)
    models = snap["models"]
    published, missing = 0, []
    for index, slot in enumerate(slots):
        await ctx.check_db()
        profile = snap["profiles"].get(slot)
        await set_stage(ctx, "drafting", persona_id=slot if profile else None)
        payload = {
            "task": "contribution",
            "profile": profile,
            "move": "explore",
            "focus": snap["message_text"],
            "latest_user_message": snap["message_text"],
            "brief": snap["brief"],
            "recent_messages": [],
            "evidence": [],
            "length_target_words": [100, 180],
        }
        name = "persona" if profile else "standard"
        try:
            result = await ctx.call(
                deps.generation.structured(
                    purpose="draft",
                    instructions=template(name).text,
                    input_items=_input(payload),
                    schema_name="contribution",
                    schema=schema,
                    max_output_tokens=snap["limits"]["contribution_output_tokens"],
                    model=models["openai_model"],
                    reasoning_effort=models["reasoning_effort"],
                )
            )
        except ProviderFailure:
            result = None
        content = None
        if isinstance(result, Structured):
            try:
                content = api.Contribution.model_validate(result.data).model_dump(mode="json")
            except ValidationError:
                content = None
        if content is None:
            missing.append(slot)
            ctx.warn("contribution_failed")
            continue
        await publish_contribution(
            ctx,
            role="persona" if profile else "moderator",
            persona_id=slot if profile else None,
            contribution=content,
            contribution_index=index,
        )
        published += 1
    await update_run(ctx, missing=missing)
    if not missing:
        return RunResult(status="completed")
    return RunResult(status="partial" if published else "failed")
