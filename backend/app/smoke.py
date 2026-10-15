"""`python -m app.cli smoke-live` (doc 10 §Live smoke): the small live set, driven through the
running app's HTTP API (G19) — connection check, one Jev-guided turn, one direct-person
follow-up, one forced-research turn, one summary — plus an optional personality probe (an
eight-person panel and one follow-up). Diagnostics (returned model IDs, usage, latency, request
IDs, refusals/incomplete) come from the local provider-call log. Failures are reported as
failures, never as live success. Writes a JSON report; prints a short summary."""

import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.persistence.db import make_engine, make_sessionmaker
from app.persistence.models import Message, ProviderCall, Run, Source
from app.settings import AppEnv

TERMINAL = {"completed", "partial", "cancelled", "failed", "interrupted"}
ALL_EIGHT = [
    "mentor",
    "skeptic",
    "explorer",
    "strategist",
    "engineer",
    "customer",
    "civic",
    "health",
]


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: Any = None) -> Any:
        req = urllib.request.Request(
            self.base + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            raise RuntimeError(f"{method} {path} → {e.code}: {detail}") from e


def control(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "audience": "auto",
        "target_persona_id": None,
        "move_override": None,
        "reply_to_message_id": None,
        "idea_card_ids": [],
        "research_override": "auto",
    }
    return {**base, **over}


def turn(
    api: Api, sid: str, message: str, over: dict[str, Any], timeout: float = 660
) -> dict[str, Any]:
    version = api.call("GET", f"/api/v1/sessions/{sid}")["version"]
    run = api.call(
        "POST",
        f"/api/v1/sessions/{sid}/turns",
        {"expected_version": version, "message": message, "control": control(**over)},
    )
    started = time.monotonic()
    while run["status"] not in TERMINAL:
        if time.monotonic() - started > timeout:
            break
        time.sleep(1)
        run = api.call("GET", f"/api/v1/runs/{run['id']}")
    run["elapsed_s"] = round(time.monotonic() - started, 1)
    return run


async def diagnostics(env: AppEnv, run_ids: list[str]) -> dict[str, Any]:
    engine = make_engine(env.DATABASE_URL)
    try:
        async with make_sessionmaker(engine)() as db:
            calls = (
                await db.scalars(
                    select(ProviderCall)
                    .where(ProviderCall.run_id.in_([uuid.UUID(r) for r in run_ids]))
                    .order_by(ProviderCall.started_at)
                )
            ).all()
            out: dict[str, Any] = {"calls": [], "messages": {}, "sources": {}}
            for c in calls:
                out["calls"].append(
                    {
                        "run_id": str(c.run_id),
                        "purpose": c.purpose,
                        "provider": c.provider,
                        "model": c.model,  # the model the provider says answered
                        "status": c.status,
                        "duration_ms": c.duration_ms,
                        "input_tokens": c.input_tokens,
                        "output_tokens": c.output_tokens,
                        "reasoning_tokens": c.reasoning_tokens,
                        "usage_unknown": c.usage_unknown,
                        "request_id": c.request_id,
                        "diagnostics": c.diagnostics,
                    }
                )
            for rid in run_ids:
                run = await db.get(Run, uuid.UUID(rid))
                if run is None:
                    continue
                msgs = (
                    await db.scalars(
                        select(Message).where(Message.run_id == run.id).order_by(Message.sequence)
                    )
                ).all()
                out["messages"][rid] = [
                    {
                        "persona_id": m.persona_id,
                        "headline": (m.contribution or {}).get("headline"),
                        "blocks": [
                            {"kind": b["kind"], "text": b["text"], "source_ids": b["source_ids"]}
                            for b in (m.contribution or {}).get("blocks", [])
                        ],
                        "summary_sections": [
                            s["kind"] for s in (m.summary or {}).get("sections", [])
                        ],
                        "text": m.text,
                    }
                    for m in msgs
                ]
                srcs = (
                    await db.scalars(select(Source).where(Source.session_id == run.session_id))
                ).all()
                out["sources"][rid] = [
                    {"title": s.title, "url": s.url, "domain": s.domain, "is_fixture": s.is_fixture}
                    for s in srcs
                ]
            return out
    finally:
        await engine.dispose()


def run_smoke(env: AppEnv, url: str, out_dir: Path, probe: bool) -> tuple[int, Path]:
    import asyncio

    api = Api(url)
    report: dict[str, Any] = {"started_at": datetime.now(UTC).isoformat(), "steps": []}
    check = api.call("POST", "/api/v1/provider-checks")
    report["provider_check"] = check
    settings = api.call("GET", "/api/v1/settings")
    report["provider_mode"] = settings["provider_mode"]
    report["configured_models"] = {
        k: settings[k] for k in ("openai_model", "research_model", "jev_model")
    }
    ok = settings["provider_mode"] == "live" and all(
        check[p]["status"] == "ok" for p in ("openai", "jev")
    )
    run_ids: list[str] = []
    if ok:
        s = api.call(
            "POST",
            "/api/v1/sessions",
            {"idea": "A weekly repair café run by volunteers at the neighborhood library."},
        )
        steps = [
            ("jev_guided_turn", s["id"], "Help me explore how to make this work.", {}),
            (
                "direct_person",
                s["id"],
                "What could go wrong first?",
                {"audience": "person", "target_persona_id": "skeptic"},
            ),
            (
                "forced_research",
                s["id"],
                "What does existing research or reporting say about repair cafés reducing waste?",
                {"research_override": "force"},
            ),
            (
                "summary",
                s["id"],
                "Summarize where we are.",
                {"audience": "summary", "research_override": "off"},
            ),
        ]
        if probe:
            p = api.call(
                "POST",
                "/api/v1/sessions",
                {
                    "idea": "A community seed library where neighbors swap seeds and growing tips.",
                    "selected_persona_ids": ALL_EIGHT,
                },
            )
            steps += [
                (
                    "probe_panel",
                    p["id"],
                    "Everyone: what would you want to get right first?",
                    {"audience": "panel"},
                ),
                (
                    "probe_followup",
                    p["id"],
                    "Good news on the main concern: the library will host it for free and "
                    "handle storage. How does that change your view?",
                    {"audience": "panel"},
                ),
            ]
        for name, sid, message, over in steps:
            try:
                run = turn(api, sid, message, over)
                report["steps"].append({"step": name, "run": run})
                run_ids.append(run["id"])
            except RuntimeError as e:
                report["steps"].append({"step": name, "error": str(e)})
        report["diagnostics"] = asyncio.run(diagnostics(env, run_ids))
    report["finished_at"] = datetime.now(UTC).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"smoke-live-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return (
        0
        if ok
        and all(
            st.get("run", {}).get("status") in ("completed", "partial") for st in report["steps"]
        )
        else 1
    ), out
