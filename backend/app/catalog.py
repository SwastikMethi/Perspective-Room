"""Versioned configuration from handoff/: personas, defaults, evaluation cases, fixture evidence.

Editable definitions stay in configuration files; the database never holds copies of them.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from app.domain.api import EvaluationCase, Persona
from app.domain.internal import PERSONA_IDS


class ConfigError(Exception):
    """Configuration is invalid; the app must not start."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Limits(_Strict):
    selected_personas: int
    auto_contributions: int
    panel_contributions: int
    standard_contributions: int
    research_jobs_per_turn: int
    web_tool_calls_per_research: int
    repairs_per_turn: int
    provider_retries: int
    provider_attempts_per_turn: int
    concurrent_generations: int
    concurrent_session_runs: int
    user_message_chars: int
    optional_recent_messages: int
    llm_input_tokens: int
    jev_state_tokens: int
    intake_output_tokens: int
    contribution_output_tokens: int
    summary_output_tokens: int
    memory_output_tokens: int
    research_output_tokens: int
    session_usd_cap: float | None


class Timeouts(_Strict):
    generation: float
    research: float
    jev: float
    turn_deadline: float
    sse_heartbeat: float


class JevThresholds(_Strict):
    routing_confidence: float
    audit_bad_score_below: float
    audit_failure_confidence: float


class Experiment(_Strict):
    default_repetitions: int
    max_repetitions: int
    max_cases_per_batch: int
    max_live_trials_per_batch: int
    evidence_policy: Literal["off", "fixture", "live"]
    base_output_budget_per_turn: int
    blind_rating: bool


class Prices(_Strict):
    enabled: bool
    rate_card_version: str | None
    note: str


class Defaults(_Strict):
    schema_version: str
    application_name: str
    default_mode: Literal["standard", "fixed_panel", "jev_guided"]
    provider_mode: Literal["live", "demo"]
    openai_model: str
    openai_research_model: str
    jev_model: str
    reasoning_effort: str | None
    temperature: float | None
    research_policy: Literal["auto", "off"]
    limits: Limits
    timeouts_seconds: Timeouts
    jev_thresholds: JevThresholds
    experiment: Experiment
    prices: Prices
    ui: dict[str, Any]


def canonical_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Catalog:
    personas: dict[str, Persona]
    order: list[str]
    default_selection: list[str]
    personas_version: str
    hashes: dict[str, str]
    cases: dict[str, EvaluationCase]
    cases_version: str
    cases_hash: str
    fixture_packs: dict[str, dict[str, Any]]
    defaults: Defaults

    def persona_hash(self, persona_id: str) -> str:
        return self.hashes[persona_id]


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"cannot read {path.name}: {e}") from e


def _load_personas(data: dict[str, Any]) -> tuple[dict[str, Persona], list[str]]:
    entries = data.get("personas", [])
    if len(entries) != 8:
        raise ConfigError(f"exactly 8 personas are required, found {len(entries)}")
    personas: dict[str, Persona] = {}
    for raw in entries:
        pid = raw.get("id")
        if pid in personas:
            raise ConfigError(f"duplicate persona id: {pid}")
        try:
            personas[pid] = Persona.model_validate(raw)
        except ValidationError as e:
            raise ConfigError(f"persona {pid}: {e}") from e
    if set(personas) != set(PERSONA_IDS):
        raise ConfigError(
            f"persona ids {sorted(personas)} do not match contract {sorted(PERSONA_IDS)}"
        )
    return personas, [p["id"] for p in entries]


def load_catalog(handoff_dir: Path) -> Catalog:
    cfg = handoff_dir / "config"
    pdata = _read(cfg / "personalities.json")
    personas, order = _load_personas(pdata)
    default_selection = list(pdata.get("default_selection", []))
    if (
        not default_selection
        or len(set(default_selection)) != len(default_selection)
        or not set(default_selection) <= set(personas)
    ):
        raise ConfigError(f"invalid default_selection: {default_selection}")

    try:
        defaults = Defaults.model_validate(_read(cfg / "app.defaults.json"))
    except ValidationError as e:
        raise ConfigError(f"app.defaults.json: {e}") from e

    cdata = _read(handoff_dir / "fixtures" / "benchmark_cases.json")
    cases: dict[str, EvaluationCase] = {}
    for raw in cdata.get("cases", []):
        try:
            case = EvaluationCase.model_validate(raw)
        except ValidationError as e:
            raise ConfigError(f"case {raw.get('id')}: {e}") from e
        if case.id in cases:
            raise ConfigError(f"duplicate case id: {case.id}")
        cases[case.id] = case

    pack = _read(handoff_dir / "fixtures" / "research_pack.json")
    if pack.get("is_fixture") is not True:
        raise ConfigError("research_pack.json must be labeled is_fixture")
    pack_ids = {s["research_pack_id"] for s in pack["sources"]}
    if len(pack_ids) != 1:
        raise ConfigError("research_pack.json sources must share one research_pack_id")

    return Catalog(
        personas=personas,
        order=order,
        default_selection=default_selection,
        personas_version=str(pdata.get("version")),
        hashes={pid: canonical_hash(p.model_dump(mode="json")) for pid, p in personas.items()},
        cases=cases,
        cases_version=str(cdata.get("version")),
        cases_hash=canonical_hash(cdata.get("cases", [])),
        fixture_packs={pack_ids.pop(): pack},
        defaults=defaults,
    )
