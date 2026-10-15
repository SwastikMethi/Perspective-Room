"""Experiment Lab (doc 09, G19, G20): bounded matched batches, blinded presentation with reveal
tracking, append-only ratings, measured results and exports. Trials run through the normal
orchestrator in Lab-managed sessions; nothing here generates text or fabricates a number."""

import csv
import io
import json
import random
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.catalog import Catalog, canonical_hash
from app.domain import api
from app.persistence.models import (
    EvaluationBatch,
    EvaluationRating,
    EvaluationTrial,
    IdeaRevision,
    Message,
    ProviderCall,
    ResearchPack,
    Run,
    Source,
)
from app.persistence.models import Session as SessionRow
from app.prompts.loader import TEMPLATE_DIR, template
from app.services.common import decode_cursor, encode_cursor, invalid, keyset_page, utcnow
from app.services.results_math import METRICS, TrialPoint, paired_comparison, trial_scores
from app.services.transcript import message_out
from app.settings import AppEnv

MODE_ORDER = ("standard", "fixed_panel", "jev_guided")
REVEALING_WARNINGS = {
    "coordination_fallback",
    "coordination_low_confidence",
    "coordination_unavailable",
    "audit_unavailable",
    "quality_warning",
    "repair_used",
}
ACTIVE_BATCH = ("queued", "running")
HARD_TRIAL_CAP = 90
FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")


def batch_out(b: EvaluationBatch) -> api.Evaluation:
    return api.Evaluation(
        id=b.id,
        status=b.status,  # type: ignore[arg-type]
        planned_trials=b.planned,
        finished_trials=b.finished,
        failed_trials=b.failed,
        config=api.EvaluationCreate(**b.config),
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


async def get_batch(db: AsyncSession, batch_id: UUID) -> EvaluationBatch:
    b = await db.get(EvaluationBatch, batch_id)
    if b is None:
        raise ApiError(404, "not_found", "Evaluation not found.")
    return b


def list_cases(catalog: Catalog) -> api.EvaluationCaseList:
    return api.EvaluationCaseList(version=catalog.cases_version, items=list(catalog.cases.values()))


# ---------- create ----------


def _validate(body: api.EvaluationCreate, catalog: Catalog) -> int:
    if len(set(body.case_ids)) != len(body.case_ids):
        raise invalid("case_ids contains duplicates", field="case_ids")
    if len(set(body.modes)) != len(body.modes):
        raise invalid("modes contains duplicates", field="modes")
    unknown = [c for c in body.case_ids if c not in catalog.cases]
    if unknown:
        raise invalid(f"Unknown case IDs: {', '.join(unknown)}", field="case_ids")
    planned = len(body.case_ids) * len(body.modes) * body.repetitions
    cap = min(
        body.max_trials, HARD_TRIAL_CAP, catalog.defaults.experiment.max_live_trials_per_batch
    )
    if planned > cap:
        raise ApiError(
            422,
            "batch_too_large",
            f"{planned} trials planned; the limit is {cap}. "
            "Choose fewer cases, modes or repetitions.",
            details={"planned_trials": planned, "max_trials": cap},
        )
    return planned


def _require_providers(env: AppEnv, modes: list[str]) -> None:
    if env.APP_PROVIDER_MODE == "demo":
        return
    if not env.openai_configured:
        raise ApiError(503, "provider_not_ready", "OpenAI is not configured; set OPENAI_API_KEY.")
    if "jev_guided" in modes and not env.jev_configured:
        raise ApiError(
            503,
            "provider_not_ready",
            "A live Jev-guided condition needs TYPESAFE_API_KEY; remove it or configure Jev.",
        )


def _labels(seed: int, case_id: str, replicate: int, modes: list[Any]) -> dict[str, str]:
    """G20: neutral 'Output N' labels, shuffled per (case, replicate), reproducible by seed."""
    order = list(modes)
    random.Random(f"{seed}:{case_id}:{replicate}").shuffle(order)
    return {mode: f"Output {i + 1}" for i, mode in enumerate(order)}


async def create_batch(
    db: AsyncSession, env: AppEnv, catalog: Catalog, body: api.EvaluationCreate
) -> api.Evaluation:
    planned = _validate(body, catalog)
    _require_providers(env, list(body.modes))
    modes = [m for m in MODE_ORDER if m in body.modes]
    seed = random.SystemRandom().randrange(1, 2**31)
    names = sorted(p.stem for p in TEMPLATE_DIR.glob("*.md"))
    snapshot = {
        "provider_mode": env.APP_PROVIDER_MODE,
        "models": {
            "openai_model": env.OPENAI_MODEL,
            "research_model": env.OPENAI_RESEARCH_MODEL,
            "jev_model": env.JEV_MODEL,
            "reasoning_effort": env.OPENAI_REASONING_EFFORT,
        },
        "profile_hashes": {pid: catalog.persona_hash(pid) for pid in catalog.order},
        "templates": {n: template(n).version for n in names},
        "cases_version": catalog.cases_version,
        "cases_hash": catalog.cases_hash,
        "limits": catalog.defaults.limits.model_dump(),
        "turn_output_budget": catalog.defaults.experiment.base_output_budget_per_turn,
        "evidence_policy": body.evidence_policy,
        "seed": seed,
        # The exact inputs of this batch, so an export never reflects a later edit (M9).
        "cases": {c: catalog.cases[c].model_dump(mode="json") for c in body.case_ids},
    }
    now = utcnow()
    batch = EvaluationBatch(
        status="queued",
        config=body.model_dump(mode="json"),
        snapshot=snapshot,
        seed=seed,
        provider_mode=env.APP_PROVIDER_MODE,
        planned=planned,
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    await db.flush()
    for case_id in body.case_ids:
        case = catalog.cases[case_id]
        pack = catalog.fixture_packs.get(case.evidence_pack_id or "")
        use_pack = body.evidence_policy == "fixture" and pack is not None
        for rep in range(1, body.repetitions + 1):
            labels = _labels(seed, case_id, rep, modes)
            for mode in modes:
                session = SessionRow(
                    title=f"Lab {case_id} · {rep} · {labels[mode]}",
                    title_is_custom=True,  # never retitled; the title carries no condition
                    mode=mode,
                    selected_persona_ids=list(case.persona_ids),
                    settings={
                        "research_policy": "auto" if body.evidence_policy == "live" else "off",
                        "auto_contributions": catalog.defaults.limits.auto_contributions,
                    },
                    brief={
                        "idea": case.idea,
                        "goal": None,
                        "constraints": list(case.constraints),
                        "revision": 1,
                    },
                    evaluation_batch_id=batch.id,
                    last_activity_at=now,
                    created_at=now,
                    updated_at=now,
                )
                db.add(session)
                await db.flush()
                db.add(
                    IdeaRevision(
                        session_id=session.id,
                        revision=1,
                        idea=case.idea,
                        goal=None,
                        constraints=list(case.constraints),
                        author_type="evaluation_case",
                    )
                )
                if use_pack:
                    await _copy_fixture_pack(db, session.id, pack)  # type: ignore[arg-type]
                db.add(
                    EvaluationTrial(
                        batch_id=batch.id,
                        case_id=case_id,
                        replicate=rep,
                        mode=mode,
                        session_id=session.id,
                        blind_label=labels[mode],
                        evidence_hash=canonical_hash(pack) if use_pack else None,
                        created_at=now,
                        updated_at=now,
                    )
                )
    await db.flush()
    return batch_out(batch)


async def _copy_fixture_pack(db: AsyncSession, session_id: UUID, pack: dict[str, Any]) -> None:
    """The same immutable, labeled fixture evidence for every condition of a case (doc 07/09)."""
    row = ResearchPack(
        session_id=session_id,
        run_id=None,
        query=pack["normalized"]["query"],
        status="available",
        raw_answer=None,
        normalized=None,
        unknowns=list(pack["normalized"].get("unknowns", [])),
        is_fixture=True,
    )
    db.add(row)
    await db.flush()
    ids: dict[str, str] = {}
    for s in pack["sources"]:
        src = Source(
            session_id=session_id,
            research_pack_id=row.id,
            url=s["url"],
            title=s["title"],
            domain=s["domain"],
            retrieved_at=s["retrieved_at"],
            published_at=s.get("published_at"),
            provider_response_id=s.get("provider_response_id"),
            provider_citation=[],
            research_excerpt=s["research_excerpt"],
            is_fixture=True,
        )
        db.add(src)
        await db.flush()
        ids[s["id"]] = str(src.id)
    normalized = json.loads(json.dumps(pack["normalized"]))
    for f in normalized.get("findings", []):
        f["source_ids"] = [ids[i] for i in f.get("source_ids", []) if i in ids]
    row.normalized = normalized


async def list_batches(db: AsyncSession, limit: int, cursor: str | None) -> api.EvaluationList:
    rows, nxt = await keyset_page(
        db,
        select(EvaluationBatch),
        EvaluationBatch.created_at,
        EvaluationBatch.id,
        limit=limit,
        cursor=cursor,
        scope="evaluations",
        descending=True,
    )
    return api.EvaluationList(items=[batch_out(b) for b in rows], next_cursor=nxt)


async def cancel_batch(db: AsyncSession, batch_id: UUID) -> tuple[api.Evaluation, list[UUID]]:
    """Stop issuing turns; returns the active child runs the caller must cancel."""
    b = await db.scalar(
        select(EvaluationBatch).where(EvaluationBatch.id == batch_id).with_for_update()
    )
    if b is None:
        raise ApiError(404, "not_found", "Evaluation not found.")
    active: list[UUID] = []
    if b.status in ACTIVE_BATCH:
        b.cancel_requested = True
        b.updated_at = utcnow()
        if b.status == "queued":
            b.status, b.finished_at = "cancelled", b.updated_at
            b.finished, b.failed = 0, b.planned  # nothing ran; every trial is not finished
            await db.execute(
                update(EvaluationTrial)
                .where(EvaluationTrial.batch_id == b.id, EvaluationTrial.status == "queued")
                .values(status="cancelled", updated_at=b.updated_at)
            )
        active = list(
            (
                await db.scalars(
                    select(Run.id)
                    .join(SessionRow, SessionRow.id == Run.session_id)
                    .where(
                        SessionRow.evaluation_batch_id == b.id,
                        Run.status.in_(("queued", "running")),
                    )
                )
            ).all()
        )
    await db.flush()
    return batch_out(b), active


# ---------- trials, blinding and reveal ----------


async def _reveal_all(db: AsyncSession, batch_id: UUID) -> None:
    now = utcnow()
    await db.execute(
        update(EvaluationTrial)
        .where(EvaluationTrial.batch_id == batch_id, EvaluationTrial.revealed.is_(False))
        .values(revealed=True, revealed_at=now, updated_at=now)
    )


def _blinded_message(m: Message) -> api.Message:
    out = message_out(m)
    out.warning_codes = [w for w in out.warning_codes if w not in REVEALING_WARNINGS]
    return out


async def list_trials(
    db: AsyncSession, batch_id: UUID, *, reveal: bool, limit: int, cursor: str | None
) -> api.TrialList:
    await get_batch(db, batch_id)
    if reveal:
        await _reveal_all(db, batch_id)
    q = select(EvaluationTrial).where(EvaluationTrial.batch_id == batch_id)
    key = tuple_(EvaluationTrial.case_id, EvaluationTrial.replicate, EvaluationTrial.blind_label)
    scope = f"trials:{batch_id}"
    if cursor:
        c = decode_cursor(cursor, scope)
        try:
            q = q.where(key > tuple_(str(c["c"]), int(c["r"]), str(c["l"])))
        except (KeyError, TypeError, ValueError) as e:
            raise ApiError(400, "bad_request", "That cursor is not valid.") from e
    rows = list(
        (
            await db.scalars(
                q.order_by(
                    EvaluationTrial.case_id, EvaluationTrial.replicate, EvaluationTrial.blind_label
                ).limit(limit + 1)
            )
        ).all()
    )
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        nxt = encode_cursor({"c": last.case_id, "r": last.replicate, "l": last.blind_label}, scope)
    items = []
    for t in rows:
        msgs = (
            await db.scalars(
                select(Message).where(Message.session_id == t.session_id).order_by(Message.sequence)
            )
        ).all()
        shown = reveal or t.revealed
        items.append(
            api.Trial(
                id=t.id,
                evaluation_id=t.batch_id,
                case_id=t.case_id,
                replicate=t.replicate,
                blind_label=t.blind_label,
                mode=t.mode if shown else None,  # type: ignore[arg-type]
                session_id=t.session_id,  # type: ignore[arg-type]
                status=t.status,
                degraded=t.degraded if shown else None,
                messages=[message_out(m) if shown else _blinded_message(m) for m in msgs],
            )
        )
    return api.TrialList(items=items, next_cursor=nxt)


# ---------- ratings ----------


def _rating_out(r: EvaluationRating) -> api.Rating:
    return api.Rating(
        id=r.id,
        trial_id=r.trial_id,
        rater_alias=r.rater_alias,
        useful_breadth=r.useful_breadth,
        usefulness=r.usefulness,
        consistency=r.consistency,
        redundancy=r.redundancy,
        note=r.note,
        unblinded=r.unblinded,
        labels=list(r.labels),
        distinct_directions=r.distinct_directions,
        created_at=r.created_at,
    )


async def create_rating(db: AsyncSession, batch_id: UUID, body: api.RatingCreate) -> api.Rating:
    await get_batch(db, batch_id)
    trial = await db.scalar(
        select(EvaluationTrial)
        .where(EvaluationTrial.id == body.trial_id, EvaluationTrial.batch_id == batch_id)
        .with_for_update()
    )
    if trial is None:
        raise invalid("That trial is not part of this evaluation.", field="trial_id")
    if trial.status not in ("completed", "partial"):
        raise ApiError(
            409, "trial_not_finished", "Only finished outputs can be rated (this one has none)."
        )
    if trial.mode == "standard" and body.consistency is not None:
        raise ApiError(
            422,
            "consistency_not_applicable",
            "Personality consistency does not apply to the single-assistant condition; "
            "leave it empty.",
        )
    if len(set(body.labels)) != len(body.labels):
        raise invalid("labels contains duplicates", field="labels")
    alias = body.rater_alias.strip()[:80]
    if not alias:
        raise invalid(
            "Enter a rater alias (any short name, not your full name).", field="rater_alias"
        )
    rating = EvaluationRating(
        trial_id=trial.id,
        rater_alias=alias,
        useful_breadth=body.useful_breadth,
        usefulness=body.usefulness,
        consistency=body.consistency,
        redundancy=body.redundancy,
        labels=list(body.labels),
        distinct_directions=body.distinct_directions,
        note=body.note[:4000],
        unblinded=body.unblinded or trial.revealed,  # the server decides after a reveal
        created_at=utcnow(),
    )
    db.add(rating)
    await db.flush()
    return _rating_out(rating)


# ---------- results ----------


async def _ratings(db: AsyncSession, batch_id: UUID) -> list[EvaluationRating]:
    return list(
        (
            await db.scalars(
                select(EvaluationRating)
                .join(EvaluationTrial, EvaluationTrial.id == EvaluationRating.trial_id)
                .where(EvaluationTrial.batch_id == batch_id)
                .order_by(EvaluationRating.created_at, EvaluationRating.id)
            )
        ).all()
    )


async def _trials(db: AsyncSession, batch_id: UUID) -> list[EvaluationTrial]:
    return list(
        (
            await db.scalars(
                select(EvaluationTrial)
                .where(EvaluationTrial.batch_id == batch_id)
                .order_by(EvaluationTrial.case_id, EvaluationTrial.replicate, EvaluationTrial.mode)
            )
        ).all()
    )


async def _trial_flags(db: AsyncSession, trials: list[EvaluationTrial]) -> dict[UUID, set[str]]:
    """Run warning codes per trial (fallbacks, repairs, quality warnings) from its Lab chat."""
    by_session = {t.session_id: t.id for t in trials}
    out: dict[UUID, set[str]] = {t.id: set() for t in trials}
    rows = await db.execute(
        select(Run.session_id, Run.warning_codes).where(Run.session_id.in_(list(by_session)))
    )
    for sid, codes in rows.all():
        out[by_session[sid]] |= set(codes or [])
    return out


FALLBACK_CODES = {"coordination_fallback", "coordination_unavailable", "audit_unavailable"}


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return float(s[mid]) if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


async def results(db: AsyncSession, batch_id: UUID, *, reveal: bool) -> api.EvaluationResults:
    b = await get_batch(db, batch_id)
    trials = await _trials(db, batch_id)
    if not reveal and not all(t.revealed for t in trials):
        raise ApiError(
            409,
            "reveal_required",
            "Results reveal which output came from which condition. Reveal first, then view them.",
        )
    if reveal:
        await _reveal_all(db, batch_id)
    ratings = await _ratings(db, batch_id)
    scores = trial_scores(
        [
            {
                "trial_id": str(r.trial_id),
                "rater_alias": r.rater_alias,
                "created_at": r.created_at,
                **{m: getattr(r, m) for m in METRICS},
            }
            for r in ratings
        ]
    )
    modes = [m for m in MODE_ORDER if m in b.config["modes"]]
    conditions = []
    for mode in modes:
        mine = [t for t in trials if t.mode == mode]
        rated = [t for t in mine if str(t.id) in scores]

        def mean(metric: str, rows: list[EvaluationTrial] = rated) -> float | None:
            vals = [v for t in rows if (v := scores[str(t.id)].get(metric)) is not None]
            return sum(vals) / len(vals) if vals else None

        conditions.append(
            api.ConditionResult(
                mode=mode,  # type: ignore[arg-type]
                planned=len(mine),
                completed=sum(t.status == "completed" for t in mine),
                incomplete=sum(t.status != "completed" for t in mine),
                degraded=sum(t.degraded for t in mine),
                rated_trials=len(rated),
                mean_useful_breadth=mean("useful_breadth"),
                mean_usefulness=mean("usefulness"),
                mean_consistency=None if mode == "standard" else mean("consistency"),
                mean_redundancy=mean("redundancy"),
                median_elapsed_ms=_median([t.elapsed_ms for t in mine if t.elapsed_ms is not None]),
                estimated_cost_usd=None,  # G21: no rate card
            )
        )
    points = [TrialPoint(t.case_id, t.replicate, t.mode, str(t.id), t.degraded) for t in trials]
    comparisons = []
    for left, right in (("jev_guided", "fixed_panel"), ("jev_guided", "standard")):
        if left not in modes or right not in modes:
            continue
        for metric in METRICS:
            if metric == "consistency" and "standard" in (left, right):
                continue  # not applicable to the single assistant
            for exclude in (False, True):
                comparisons.append(
                    api.PairedComparison(
                        **paired_comparison(
                            points,
                            scores,
                            left,
                            right,
                            metric,
                            seed=b.seed,
                            exclude_degraded=exclude,
                        )
                    )
                )
    done = sum(t.status == "completed" for t in trials)
    flags = await _trial_flags(db, trials)
    by_mode = {m: [t for t in trials if t.mode == m] for m in modes}

    def per_mode(test: Any) -> str:
        return ", ".join(f"{m}: {sum(test(flags[t.id]) for t in by_mode[m])}" for m in modes)

    low = sum("coordination_low_confidence" in flags[t.id] for t in trials)
    latest: dict[tuple[UUID, str], EvaluationRating] = {}
    for r in ratings:
        latest[(r.trial_id, r.rater_alias)] = r
    unblinded = sum(r.unblinded for r in latest.values())
    warnings = [
        f"Planned {len(trials)} trials; {done} completed, {len(trials) - done} incomplete. "
        "Means and comparisons use rated trials only; unrated or incomplete trials are left "
        "out (never scored as zero) and a case counts only where both conditions are rated.",
        f"Fallbacks: {sum(bool(flags[t.id] & FALLBACK_CODES) for t in trials)} trials "
        f"({per_mode(lambda f: bool(f & FALLBACK_CODES))}); low-confidence fixed order: "
        f"{low} trial{'' if low == 1 else 's'}; degraded trials: "
        f"{sum(t.degraded for t in trials)}.",
        f"Repairs used: {sum('repair_used' in flags[t.id] for t in trials)} trials "
        f"({per_mode(lambda f: 'repair_used' in f)}); quality warnings: "
        f"{sum('quality_warning' in flags[t.id] for t in trials)} trials.",
        f"{len({r.trial_id for r in ratings})} of {len(trials)} trials have at least one rating; "
        f"{unblinded} of {len(latest)} analysed ratings were made after reveal (unblinded). "
        "Each rater's latest rating counts.",
        f"Evidence policy: {b.config['evidence_policy']}"
        + (
            " (synthetic fixture packs, plumbing only)"
            if b.config["evidence_policy"] == "fixture"
            else ""
        ),
        "Cost is unknown: no rate card is configured.",
    ]
    if b.provider_mode == "demo":
        warnings.append(
            "Demo provider: deterministic fixtures — never a live-model effectiveness result."
        )
    if b.status not in ("completed",):
        warnings.append(f"Batch status: {b.status}.")
    return api.EvaluationResults(
        evaluation_id=b.id,
        provider_mode=b.provider_mode,  # type: ignore[arg-type]
        evidence_policy=b.config["evidence_policy"],
        conditions=conditions,
        comparisons=comparisons,
        ratings=[_rating_out(r) for r in ratings],
        warnings=warnings,
    )


# ---------- export ----------


def csv_cell(value: Any) -> str:
    """Spreadsheet-safe cell: missing → NA; formula-leading text prefixed with an apostrophe."""
    if value is None:
        return "NA"
    text = ";".join(map(str, value)) if isinstance(value, list) else str(value)
    return "'" + text if text.startswith(FORMULA_LEADS) else text


CSV_COLUMNS = [
    "evaluation_id", "provider_mode", "evidence_policy", "cases_version", "case_id", "replicate",
    "mode", "blind_label", "trial_status", "degraded", "fallback", "low_confidence_fallback",
    "repair_used",
    "quality_warning", "evidence_hash", "elapsed_ms", "input_tokens", "output_tokens",
    "usage_incomplete", "provider_calls", "output_words", "rating_id", "rater_alias",
    "useful_breadth", "usefulness", "consistency", "redundancy", "distinct_directions", "labels",
    "unblinded", "note", "rated_at",
]  # fmt: skip


async def _trial_extras(db: AsyncSession, t: EvaluationTrial) -> dict[str, Any]:
    msgs = (
        await db.scalars(
            select(Message).where(Message.session_id == t.session_id).order_by(Message.sequence)
        )
    ).all()
    words = 0
    for m in msgs:
        if m.role != "user" and m.contribution:
            words += sum(len(b["text"].split()) for b in m.contribution["blocks"])
    calls = await db.scalar(
        select(func.count())
        .select_from(ProviderCall)
        .join(Run, Run.id == ProviderCall.run_id)
        .where(Run.session_id == t.session_id)
    )
    return {"messages": msgs, "words": words, "calls": int(calls or 0)}


async def export_batch(
    db: AsyncSession, catalog: Catalog, batch_id: UUID, fmt: str
) -> tuple[str, str]:
    b = await get_batch(db, batch_id)
    await _reveal_all(db, batch_id)  # an export shows the conditions (G20)
    trials = await _trials(db, batch_id)
    ratings = await _ratings(db, batch_id)
    by_trial: dict[UUID, list[EvaluationRating]] = {}
    for r in ratings:
        by_trial.setdefault(r.trial_id, []).append(r)
    flags = await _trial_flags(db, trials)
    if fmt == "csv":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(CSV_COLUMNS)
        for t in trials:
            extra = await _trial_extras(db, t)
            usage = t.usage or {}
            base: list[Any] = [
                b.id, b.provider_mode, b.config["evidence_policy"], b.snapshot.get("cases_version"),
                t.case_id, t.replicate, t.mode, t.blind_label, t.status, t.degraded,
                bool(flags[t.id] & FALLBACK_CODES), "coordination_low_confidence" in flags[t.id],
                "repair_used" in flags[t.id],
                "quality_warning" in flags[t.id], t.evidence_hash, t.elapsed_ms,
                usage.get("input_tokens"), usage.get("output_tokens"),
                bool(usage.get("usage_incomplete")), extra["calls"], extra["words"],
            ]  # fmt: skip
            rows: list[EvaluationRating | None] = list(by_trial.get(t.id, [])) or [None]
            for row in rows:
                rating: list[Any] = (
                    [
                        row.id,
                        row.rater_alias,
                        row.useful_breadth,
                        row.usefulness,
                        row.consistency,
                        row.redundancy,
                        row.distinct_directions,
                        list(row.labels) or None,
                        row.unblinded,
                        row.note or None,
                        row.created_at.isoformat(),
                    ]  # fmt: skip
                    if row
                    else [None] * 11
                )
                w.writerow([csv_cell(v) for v in base + rating])
        return out.getvalue(), "text/csv; charset=utf-8"
    trial_docs = []
    for t in trials:
        extra = await _trial_extras(db, t)
        request_ids = (
            await db.scalars(
                select(ProviderCall.request_id)
                .join(Run, Run.id == ProviderCall.run_id)
                .where(Run.session_id == t.session_id, ProviderCall.request_id.is_not(None))
            )
        ).all()
        trial_docs.append(
            {
                "id": str(t.id),
                "case_id": t.case_id,
                "replicate": t.replicate,
                "mode": t.mode,
                "blind_label": t.blind_label,
                "status": t.status,
                "degraded": t.degraded,
                "evidence_hash": t.evidence_hash,
                "elapsed_ms": t.elapsed_ms,
                "usage": t.usage,
                "provider_calls": extra["calls"],
                "provider_request_ids": list(request_ids),  # local diagnosis; never credentials
                "output_words": extra["words"],
                "messages": [message_out(m).model_dump(mode="json") for m in extra["messages"]],
                "ratings": [_rating_out(r).model_dump(mode="json") for r in by_trial.get(t.id, [])],
            }
        )
    doc = {
        "schema": "perspective-room/evaluation-export",
        "schema_version": 1,
        "exported_at": utcnow().isoformat(),
        "evaluation": batch_out(b).model_dump(mode="json"),
        "snapshot": b.snapshot,
        "cases": [
            (b.snapshot.get("cases") or {}).get(c)
            or (catalog.cases[c].model_dump(mode="json") if c in catalog.cases else {"id": c})
            for c in b.config["case_ids"]
        ],
        "trials": trial_docs,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2, default=str) + "\n", "application/json"


# ---------- delete (CLI) ----------


async def delete_batch(db: AsyncSession, batch_id: UUID) -> dict[str, int]:
    """Removes a finished batch, its trials, ratings and Lab sessions. Refuses active batches."""
    b = await db.scalar(
        select(EvaluationBatch).where(EvaluationBatch.id == batch_id).with_for_update()
    )
    if b is None:
        raise ApiError(404, "not_found", "Evaluation not found.")
    if b.status in ACTIVE_BATCH:
        raise ApiError(409, "run_active", "Cancel the batch and wait for it to stop first.")
    sessions = (
        await db.scalars(select(SessionRow).where(SessionRow.evaluation_batch_id == b.id))
    ).all()
    counts = {
        "trials": int(
            await db.scalar(
                select(func.count())
                .select_from(EvaluationTrial)
                .where(EvaluationTrial.batch_id == b.id)
            )
            or 0
        ),
        "ratings": len(await _ratings(db, b.id)),
        "sessions": len(sessions),
    }
    await db.delete(b)  # trials, ratings and Lab sessions cascade
    await db.flush()
    return counts
