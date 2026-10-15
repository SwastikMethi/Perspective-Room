"""Experiment Lab (doc 09; T20–T23): bounded matched batches through the normal orchestrator,
blinding and reveal tracking, ratings, honest results and exports. Demo providers only."""

import asyncio
import csv
import io

import pytest
from conftest import idem, make_test_env
from contract_support import contract_client
from sqlalchemy import func, select

from app.persistence.models import EvaluationTrial, Message, ProviderCall, Run
from app.persistence.models import Session as SessionRow

TWO = ["case_01", "case_02"]


class Slow:
    """Demo generation with a small delay per call, so a batch can be cancelled mid-way."""

    def __init__(self, inner):
        self.inner, self.name = inner, inner.name

    async def structured(self, **kw):
        await asyncio.sleep(0.05)
        return await self.inner.structured(**kw)

    async def web_research(self, **kw):
        return await self.inner.web_research(**kw)


def body(**over):
    base = {
        "case_ids": TWO,
        "modes": ["standard", "fixed_panel", "jev_guided"],
        "repetitions": 1,
        "evidence_policy": "off",
        "blind_rating": True,
        "max_trials": 90,
    }
    base.update(over)
    return base


async def create(client, **over):
    return await client.post("/api/v1/evaluations", json=body(**over), headers=idem())


async def wait_batch(client, batch_id, timeout=60):
    async with asyncio.timeout(timeout):
        while True:
            b = (await client.get(f"/api/v1/evaluations/{batch_id}")).json()
            if b["status"] not in ("queued", "running"):
                return b
            await asyncio.sleep(0.1)


async def trials(client, batch_id, reveal=False):
    r = await client.get(
        f"/api/v1/evaluations/{batch_id}/trials",
        params={"reveal": str(reveal).lower(), "limit": 100},
    )
    assert r.status_code == 200, r.text
    return r


async def test_cases_are_served_from_the_handoff_catalog(client):
    r = (await client.get("/api/v1/evaluation-cases")).json()
    assert len(r["items"]) == 30 and r["version"]
    assert r["items"][0]["id"] == "case_01" and len(r["items"][0]["user_turns"]) == 3


async def test_oversized_or_invalid_batches_are_refused_never_truncated(client):
    big = await create(client, case_ids=[f"case_{i:02d}" for i in range(1, 31)], repetitions=2)
    assert big.status_code == 422 and big.json()["code"] == "batch_too_large"
    capped = await create(client, max_trials=5)  # 2 × 3 = 6 > 5
    assert capped.status_code == 422 and capped.json()["code"] == "batch_too_large"
    assert (await create(client, case_ids=["case_99"])).status_code == 422
    assert (await create(client, modes=["standard", "standard"])).status_code == 422
    assert (await create(client, case_ids=["case_01", "case_01"])).status_code == 422
    assert (await client.get("/api/v1/evaluations")).json()["items"] == []


async def test_live_batch_with_jev_guided_needs_the_jev_key(db):
    from app.main import create_app

    app = create_app(env=make_test_env(APP_PROVIDER_MODE="live", OPENAI_API_KEY="sk-test-x"))
    try:
        async with contract_client(app) as c:
            r = await create(c, modes=["jev_guided"])
            assert r.status_code == 503 and r.json()["code"] == "provider_not_ready"
            ok = await create(c, modes=["standard", "fixed_panel"])
            assert ok.status_code == 202
    finally:
        await app.state.engine.dispose()


async def test_a_small_matched_batch_runs_through_the_normal_pipeline(running_app, client, db):
    key = idem()
    a = await client.post("/api/v1/evaluations", json=body(), headers=key)
    b = await client.post("/api/v1/evaluations", json=body(), headers=key)
    assert a.status_code == 202 and a.json() == b.json()
    batch = a.json()
    assert batch["planned_trials"] == 6 and batch["status"] in ("queued", "running")
    done = await wait_batch(client, batch["id"])
    assert done["status"] == "completed" and done["finished_trials"] == 6
    async with db() as s:
        rows = (await s.scalars(select(EvaluationTrial))).all()
        for t in rows:
            users = await s.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.session_id == t.session_id, Message.role == "user")
            )
            assert users == 3 and t.status == "completed"
            jev = await s.scalar(
                select(func.count())
                .select_from(ProviderCall)
                .join(Run, Run.id == ProviderCall.run_id)
                .where(
                    Run.session_id == t.session_id, ProviderCall.purpose.in_(("route", "assess"))
                )
            )
            assert (jev > 0) == (t.mode == "jev_guided")  # A and B never call Jev (T20)
        snaps = {}
        for t in rows:
            run = await s.scalar(select(Run).where(Run.session_id == t.session_id).limit(1))
            snaps[(t.case_id, t.mode)] = run.snapshot
    for case in TWO:
        b_, c_ = snaps[(case, "fixed_panel")], snaps[(case, "jev_guided")]
        for k in ("profiles", "selected", "models", "settings", "limits", "templates"):
            assert b_[k] == c_[k], k  # identical B/C conditions (T21)
    # Lab chats never appear in the workspace
    assert (await client.get("/api/v1/sessions", params={"archive": "all"})).json()["items"] == []


async def test_blinded_trials_hide_the_condition_until_revealed(running_app, client, db):
    batch = (await create(client, case_ids=["case_01"])).json()
    await wait_batch(client, batch["id"])
    blind = (await trials(client, batch["id"])).json()["items"]
    assert sorted(t["blind_label"] for t in blind) == ["Output 1", "Output 2", "Output 3"]
    assert all(t["mode"] is None and t["degraded"] is None for t in blind)
    revealing = {
        "coordination_fallback",
        "coordination_unavailable",
        "audit_unavailable",
        "quality_warning",
        "repair_used",
    }
    assert not any(set(m["warning_codes"]) & revealing for t in blind for m in t["messages"])
    rated = await client.post(
        f"/api/v1/evaluations/{batch['id']}/ratings",
        json={
            "trial_id": blind[0]["id"],
            "rater_alias": "r1",
            "useful_breadth": 4,
            "usefulness": 3,
            "consistency": None,
            "redundancy": 2,
            "note": "",
            "unblinded": False,
            "labels": [],
            "distinct_directions": 3,
        },
        headers=idem(),
    )
    assert rated.status_code == 201 and rated.json()["unblinded"] is False
    shown = await trials(client, batch["id"], reveal=True)
    assert shown.headers["cache-control"] == "no-store"
    items = shown.json()["items"]
    assert {t["mode"] for t in items} == {"standard", "fixed_panel", "jev_guided"}
    std = next(t for t in items if t["mode"] == "standard")
    after = await client.post(
        f"/api/v1/evaluations/{batch['id']}/ratings",
        json={
            "trial_id": std["id"],
            "rater_alias": "r1",
            "useful_breadth": 3,
            "usefulness": 3,
            "consistency": None,
            "redundancy": 2,
            "note": "",
            "unblinded": False,
            "labels": ["missed_constraint"],
            "distinct_directions": None,
        },
        headers=idem(),
    )
    assert after.json()["unblinded"] is True  # server-forced after reveal
    bad = await client.post(
        f"/api/v1/evaluations/{batch['id']}/ratings",
        json={
            "trial_id": std["id"],
            "rater_alias": "r2",
            "useful_breadth": 3,
            "usefulness": 3,
            "consistency": 4,  # Standard has no personalities to be consistent
            "redundancy": 2,
            "note": "",
            "unblinded": True,
            "labels": [],
            "distinct_directions": None,
        },
        headers=idem(),
    )
    assert bad.status_code == 422 and bad.json()["code"] == "consistency_not_applicable"


async def test_results_require_reveal_and_report_denominators_first(running_app, client, db):
    batch = (await create(client, case_ids=["case_01"])).json()
    await wait_batch(client, batch["id"])
    r = await client.get(f"/api/v1/evaluations/{batch['id']}/results")
    assert r.status_code == 409 and r.json()["code"] == "reveal_required"
    r = await client.get(f"/api/v1/evaluations/{batch['id']}/results", params={"reveal": "true"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    res = r.json()
    assert res["provider_mode"] == "demo" and res["evidence_policy"] == "off"
    assert [c["planned"] for c in res["conditions"]] == [1, 1, 1]
    assert all(c["estimated_cost_usd"] is None for c in res["conditions"])
    assert res["warnings"][0].startswith("Planned 3 trials")
    assert any("Demo provider" in w for w in res["warnings"])
    assert all(c["ci95_low"] is None for c in res["comparisons"])
    assert not any(
        c["metric"] == "consistency" and "standard" in (c["left"], c["right"])
        for c in res["comparisons"]
    )


async def test_cancel_keeps_finished_trials_and_starts_nothing_new(running_app, client, db):
    running_app.state.deps.generation = Slow(running_app.state.deps.generation)
    batch = (await create(client)).json()
    async with asyncio.timeout(30):
        while (await client.get(f"/api/v1/evaluations/{batch['id']}")).json()[
            "finished_trials"
        ] < 1:
            await asyncio.sleep(0.05)
    r = await client.post(f"/api/v1/evaluations/{batch['id']}/cancel")
    assert r.status_code == 200
    done = await wait_batch(client, batch["id"])
    assert done["status"] == "cancelled" and 1 <= done["finished_trials"] < 6
    async with db() as s:
        statuses = [t.status for t in (await s.scalars(select(EvaluationTrial))).all()]
        active = await s.scalar(
            select(func.count()).select_from(Run).where(Run.status.in_(("queued", "running")))
        )
    assert statuses.count("completed") == done["finished_trials"] and active == 0
    assert "queued" not in statuses


async def test_exports_escape_formulas_mark_missing_values_and_reveal(running_app, client, db):
    batch = (await create(client, case_ids=["case_01"])).json()
    await wait_batch(client, batch["id"])
    blind = (await trials(client, batch["id"])).json()["items"]
    await client.post(
        f"/api/v1/evaluations/{batch['id']}/ratings",
        json={
            "trial_id": blind[0]["id"],
            "rater_alias": "=cmd|'/c calc'!A1",
            "useful_breadth": 4,
            "usefulness": 4,
            "consistency": None,
            "redundancy": 1,
            "note": "+1 looks fine",
            "unblinded": False,
            "labels": [],
            "distinct_directions": None,
        },
        headers=idem(),
    )
    r = await client.get(f"/api/v1/evaluations/{batch['id']}/export", params={"format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"].startswith("attachment;")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 3  # one per trial × rating; unrated trials keep one NA row
    rated = next(x for x in rows if x["rater_alias"] != "NA")
    assert rated["rater_alias"].startswith("'=") and rated["note"].startswith("'+")
    unrated = [x for x in rows if x["rater_alias"] == "NA"]
    assert len(unrated) == 2 and unrated[0]["useful_breadth"] == "NA"
    assert {x["mode"] for x in rows} == {"standard", "fixed_panel", "jev_guided"}
    data = (
        await client.get(f"/api/v1/evaluations/{batch['id']}/export", params={"format": "json"})
    ).json()
    assert len(data["trials"]) == 3 and all(t["messages"] for t in data["trials"])
    async with db() as s:
        assert all(t.revealed for t in (await s.scalars(select(EvaluationTrial))).all())
    for t in data["trials"]:
        assert "snapshot" not in t or "api_key" not in str(t["snapshot"]).lower()


async def test_lab_sessions_cannot_be_driven_from_the_workspace(running_app, client, db):
    batch = (await create(client, case_ids=["case_01"], modes=["standard"])).json()
    await wait_batch(client, batch["id"])
    async with db() as s:
        sid = await s.scalar(
            select(SessionRow.id).where(SessionRow.evaluation_batch_id.is_not(None))
        )
    r = await client.delete(f"/api/v1/sessions/{sid}")
    assert r.status_code == 409 and r.json()["code"] == "evaluation_managed"


@pytest.mark.parametrize("cell", ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"])
def test_formula_leading_cells_are_prefixed(cell):
    from app.services.evaluation import csv_cell

    assert csv_cell(cell) == "'" + cell
    assert csv_cell("plain") == "plain" and csv_cell(None) == "NA"


# ---------- CLI ----------


def test_eval_run_dry_run_counts_locally_and_refuses_oversized(capsys):
    from app.cli import main as cli_main

    assert (
        cli_main(
            [
                "eval-run",
                "--cases",
                "case_01,case_02",
                "--modes",
                "standard,jev_guided",
                "--dry-run",
            ]
        )
        == 0
    )
    assert "4 trials planned" in capsys.readouterr().out
    all30 = ",".join(f"case_{i:02d}" for i in range(1, 31))
    assert (
        cli_main(
            [
                "eval-run",
                "--cases",
                all30,
                "--modes",
                "standard,fixed_panel,jev_guided",
                "--reps",
                "2",
                "--dry-run",
            ]
        )
        == 1
    )
    assert "limit is 90" in capsys.readouterr().err


def test_eval_run_posts_to_the_running_app_only_after_confirmation(monkeypatch, capsys):
    import json as _json

    from app import cli

    sent = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return _json.dumps({"id": "b-1", "planned_trials": 2, "status": "queued"}).encode()

    def fake_urlopen(req, timeout=0):
        sent.append((req.full_url, req.get_header("Idempotency-key"), _json.loads(req.data)))
        return Reply()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")
    assert cli.main(["eval-run", "--cases", "case_01", "--modes", "standard,fixed_panel"]) == 1
    assert sent == []  # declined: nothing was started
    monkeypatch.setattr("builtins.input", lambda prompt="": "run")
    assert (
        cli.main(
            [
                "eval-run",
                "--cases",
                "case_01",
                "--modes",
                "standard,fixed_panel",
                "--url",
                "http://127.0.0.1:8000",
            ]
        )
        == 0
    )
    [(url, key, payload)] = sent
    assert url == "http://127.0.0.1:8000/api/v1/evaluations" and key
    assert payload["case_ids"] == ["case_01"] and payload["evidence_policy"] == "off"
    assert "b-1" in capsys.readouterr().out


async def test_export_and_delete_eval_cli(running_app, client, db, tmp_path, monkeypatch):
    from conftest import TEST_DB_URL

    from app.cli import main as cli_main
    from app.settings import get_env

    batch = (await create(client, case_ids=["case_01"], modes=["standard"])).json()
    await wait_batch(client, batch["id"])
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    get_env.cache_clear()
    try:
        out = tmp_path / "eval.csv"
        code = await asyncio.to_thread(
            cli_main, ["export-eval", batch["id"], "--format", "csv", "--out", str(out)]
        )
        assert code == 0 and out.read_text().startswith("evaluation_id,")
        monkeypatch.setattr("builtins.input", lambda prompt="": "wrong-id")
        assert await asyncio.to_thread(cli_main, ["delete-eval", batch["id"]]) == 1
        monkeypatch.setattr("builtins.input", lambda prompt="": batch["id"])
        assert await asyncio.to_thread(cli_main, ["delete-eval", batch["id"]]) == 0
    finally:
        get_env.cache_clear()
    assert (await client.get(f"/api/v1/evaluations/{batch['id']}")).status_code == 404
    async with db() as s:
        assert await s.scalar(select(func.count()).select_from(SessionRow)) == 0


# ---------- Checkpoint 6 review regressions ----------


async def test_unknown_usage_is_exported_as_missing_not_zero(running_app, client, db):
    batch = (await create(client, case_ids=["case_01"], modes=["standard"])).json()
    await wait_batch(client, batch["id"])
    async with db() as s:
        [t] = (await s.scalars(select(EvaluationTrial))).all()
    if t.usage.get("usage_incomplete"):
        assert t.usage["input_tokens"] is None and t.usage["output_tokens"] is None
    r = await client.get(f"/api/v1/evaluations/{batch['id']}/export", params={"format": "csv"})
    [row] = list(csv.DictReader(io.StringIO(r.text)))
    assert "usage_incomplete" in row
    if row["usage_incomplete"] == "True":
        assert row["input_tokens"] == "NA" and row["output_tokens"] == "NA"


async def test_results_disclose_ratings_made_after_reveal(running_app, client, db):
    batch = (await create(client, case_ids=["case_01"], modes=["fixed_panel", "jev_guided"])).json()
    await wait_batch(client, batch["id"])
    blind = (await trials(client, batch["id"])).json()["items"]

    async def rate(trial_id, breadth):
        r = await client.post(
            f"/api/v1/evaluations/{batch['id']}/ratings",
            json={
                "trial_id": trial_id,
                "rater_alias": "r1",
                "useful_breadth": breadth,
                "usefulness": 3,
                "consistency": 3,
                "redundancy": 2,
                "note": "",
                "unblinded": False,
                "labels": [],
                "distinct_directions": None,
            },
            headers=idem(),
        )
        assert r.status_code == 201, r.text

    for t in blind:
        await rate(t["id"], 2)
    await trials(client, batch["id"], reveal=True)
    await rate(blind[0]["id"], 5)
    res = (await client.get(f"/api/v1/evaluations/{batch['id']}/results")).json()
    assert any("1 of 2 analysed ratings were made after reveal" in w for w in res["warnings"])


async def test_a_crash_inside_a_trial_fails_that_trial_and_the_batch_moves_on(
    running_app, client, db, monkeypatch
):
    from app.workers import lab

    real, calls = lab.submit_turn, {"n": 0}

    async def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 4:  # the first turn of the second trial
            raise RuntimeError("database blip")
        return await real(*a, **kw)

    monkeypatch.setattr(lab, "submit_turn", flaky)
    batch = (await create(client, case_ids=["case_01"], modes=["standard", "fixed_panel"])).json()
    done = await wait_batch(client, batch["id"])
    async with db() as s:
        statuses = sorted(t.status for t in (await s.scalars(select(EvaluationTrial))).all())
    assert statuses == ["completed", "failed"] and done["status"] == "partial"


async def test_results_report_fallbacks_and_repairs(running_app, client, db):
    batch = (await create(client, case_ids=["case_01"])).json()
    await wait_batch(client, batch["id"])
    res = (
        await client.get(f"/api/v1/evaluations/{batch['id']}/results", params={"reveal": "true"})
    ).json()
    assert any(w.startswith("Fallbacks:") for w in res["warnings"])
    assert any(w.startswith("Repairs used:") for w in res["warnings"])


async def test_ratings_need_a_finished_trial(client, db):
    batch = (await create(client, case_ids=["case_01"], modes=["standard"])).json()  # stays queued
    async with db() as s:
        [t] = (await s.scalars(select(EvaluationTrial))).all()
    r = await client.post(
        f"/api/v1/evaluations/{batch['id']}/ratings",
        json={
            "trial_id": str(t.id),
            "rater_alias": "r1",
            "useful_breadth": 3,
            "usefulness": 3,
            "consistency": None,
            "redundancy": 2,
            "note": "",
            "unblinded": False,
            "labels": [],
            "distinct_directions": None,
        },
        headers=idem(),
    )
    assert r.status_code == 409 and r.json()["code"] == "trial_not_finished"


async def test_cancelling_a_queued_batch_counts_its_trials_as_not_finished(client, db):
    batch = (await create(client, case_ids=["case_01"])).json()  # no worker: stays queued
    r = (await client.post(f"/api/v1/evaluations/{batch['id']}/cancel")).json()
    assert r["status"] == "cancelled" and r["finished_trials"] == 0 and r["failed_trials"] == 3


async def test_export_uses_the_case_inputs_captured_with_the_batch(running_app, client, db):
    batch = (await create(client, case_ids=["case_01"], modes=["standard"])).json()
    await wait_batch(client, batch["id"])
    cases = running_app.state.catalog.cases
    cases["case_01"] = cases["case_01"].model_copy(update={"idea": "EDITED AFTER THE RUN"})
    data = (
        await client.get(f"/api/v1/evaluations/{batch['id']}/export", params={"format": "json"})
    ).json()
    assert data["cases"][0]["idea"] != "EDITED AFTER THE RUN"


async def test_low_confidence_fallbacks_are_counted_and_hidden_while_blind(running_app, client, db):
    from test_orchestrator import UnsureJev, use

    use(running_app, UnsureJev())
    batch = (await create(client, case_ids=["case_01"], modes=["jev_guided"])).json()
    await wait_batch(client, batch["id"])
    blind = (await trials(client, batch["id"])).json()["items"]
    codes = {c for t in blind for m in t["messages"] for c in m["warning_codes"]}
    assert "coordination_low_confidence" not in codes
    res = (
        await client.get(f"/api/v1/evaluations/{batch['id']}/results", params={"reveal": "true"})
    ).json()
    assert any("low-confidence fixed order: 1 trial" in w for w in res["warnings"])
    r = await client.get(f"/api/v1/evaluations/{batch['id']}/export", params={"format": "csv"})
    [row] = list(csv.DictReader(io.StringIO(r.text)))
    assert row["low_confidence_fallback"] == "True"
