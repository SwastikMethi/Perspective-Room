# GENERATED from handoff/contracts/openapi.yaml by scripts/gen_contracts.sh - do not edit.

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Error(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    code: str
    message: str
    retryable: bool
    request_id: str
    details: dict[str, Any]


class Brief(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    idea: str
    goal: str | None
    constraints: list[str]
    revision: Annotated[int, Field(ge=1)]


class SessionSettings(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    research_policy: Literal["auto", "off"]
    auto_contributions: Annotated[int, Field(ge=1, le=3)]


class SessionCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    title: Annotated[str | None, Field(max_length=120, min_length=1)] = None
    idea: Annotated[str, Field(max_length=16000, min_length=1)]
    mode: Literal["standard", "fixed_panel", "jev_guided"] | None = None
    selected_persona_ids: Annotated[
        list[
            Literal[
                "mentor",
                "skeptic",
                "explorer",
                "strategist",
                "engineer",
                "customer",
                "civic",
                "health",
            ]
        ]
        | None,
        Field(max_length=8, min_length=1),
    ] = None
    settings: SessionSettings | None = None
    folder_id: UUID | None = None


class Session(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    title: str
    mode: Literal["standard", "fixed_panel", "jev_guided"]
    selected_persona_ids: list[
        Literal[
            "mentor", "skeptic", "explorer", "strategist", "engineer", "customer", "civic", "health"
        ]
    ]
    version: int
    brief: Brief
    settings: SessionSettings
    active_run_id: UUID | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    organization_version: Annotated[int, Field(ge=1)]
    folder_id: UUID | None
    is_pinned: bool
    is_archived: bool
    last_activity_at: AwareDatetime
    origin_session_id: UUID | None


class Brief1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    idea: str
    goal: str | None
    constraints: list[str]


class SessionPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: Annotated[int, Field(ge=1)]
    selected_persona_ids: Annotated[
        list[
            Literal[
                "mentor",
                "skeptic",
                "explorer",
                "strategist",
                "engineer",
                "customer",
                "civic",
                "health",
            ]
        ]
        | None,
        Field(max_length=8, min_length=1),
    ] = None
    settings: SessionSettings | None = None
    brief: Brief1 | None = None


class TurnControl(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    audience: Literal["auto", "person", "panel", "summary"]
    target_persona_id: (
        Literal[
            "mentor", "skeptic", "explorer", "strategist", "engineer", "customer", "civic", "health"
        ]
        | None
    )
    move_override: Literal["explore", "challenge", "expand", "combine"] | None
    reply_to_message_id: UUID | None
    idea_card_ids: list[UUID]
    research_override: Literal["auto", "off", "force"]


class TurnCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: Annotated[int, Field(ge=1)]
    message: Annotated[str, Field(max_length=16000, min_length=1)]
    control: TurnControl


class Usage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    usage_incomplete: bool


class Run(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    session_id: UUID
    status: Literal[
        "queued",
        "running",
        "cancelling",
        "completed",
        "partial",
        "cancelled",
        "failed",
        "interrupted",
    ]
    stage: str
    published_count: Annotated[int, Field(ge=0)]
    requested_count: Annotated[int, Field(ge=1, le=8)]
    degraded: bool
    warning_codes: list[str]
    error: Error | None
    usage: Usage
    session_version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Intake(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    title_suggestion: str
    focus: str
    intent: Literal["brainstorm", "follow_up", "clarify", "summarize"]
    clarifying_question: str | None
    research_query: str | None
    research_reason: str | None
    open_questions: list[str]


class Block(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["observation", "suggestion", "question", "assumption", "fact", "limitation"]
    text: str
    source_ids: list[str]


class Contribution(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    headline: str
    blocks: list[Block]
    referenced_message_ids: list[str]
    new_angle: str
    next_question: str | None


class Item(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    text: str
    source_message_ids: list[str]
    source_ids: list[str]


class Section(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["directions", "disagreements", "assumptions", "questions", "experiments"]
    items: list[Item]


class Summary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sections: list[Section]


class Idea(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    text: str
    source_message_ids: list[str]
    source_ids: list[str]


class OpenQuestion(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    text: str
    source_message_ids: list[str]
    source_ids: list[str]


class Assumption(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    text: str
    source_message_ids: list[str]
    source_ids: list[str]


class Memory(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    overview: str
    ideas: list[Idea]
    open_questions: list[OpenQuestion]
    assumptions: list[Assumption]


class Finding(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    statement: str
    source_ids: list[str]
    qualification: str | None


class Research(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query: str
    findings: list[Finding]
    unknowns: list[str]


class Message(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    session_id: UUID
    run_id: UUID | None
    sequence: int
    role: Literal["user", "persona", "moderator"]
    persona_id: (
        Literal[
            "mentor", "skeptic", "explorer", "strategist", "engineer", "customer", "civic", "health"
        ]
        | None
    )
    text: str | None
    contribution: Contribution | None
    summary: Summary | None
    created_at: AwareDatetime
    warning_codes: list[str]


class MessageList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    items: list[Message]
    next_cursor: str | None
    previous_cursor: str | None


class RunEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    run_id: UUID
    type: Literal[
        "run.queued",
        "run.started",
        "run.stage",
        "research.completed",
        "message.completed",
        "run.warning",
        "run.completed",
        "run.partial",
        "run.cancelled",
        "run.failed",
        "run.interrupted",
    ]
    created_at: AwareDatetime
    data: dict[str, Any]


class Source(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    session_id: UUID
    research_pack_id: UUID
    url: str
    title: str
    domain: str
    retrieved_at: AwareDatetime
    published_at: str | None
    research_excerpt: str
    provider_response_id: str
    is_fixture: bool


class SourceList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    items: list[Source]
    next_cursor: str | None


class IdeaCardCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    message_id: UUID
    title: Annotated[str, Field(max_length=120, min_length=1)]
    note: str
    status: Literal["exploring", "selected", "parked"]


class IdeaCard(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    session_id: UUID
    message_id: UUID
    title: Annotated[str, Field(max_length=120, min_length=1)]
    note: str
    status: Literal["exploring", "selected", "parked"]
    version: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class IdeaCardPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: int
    title: str | None = None
    note: str | None = None
    status: Literal["exploring", "selected", "parked"] | None = None


class IdeaCardList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    items: list[IdeaCard]
    next_cursor: str | None


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    labels: list[Literal["useful", "new_perspective", "repetitive", "off_character"]]
    note: str


class Feedback(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    message_id: UUID
    labels: list[Literal["useful", "new_perspective", "repetitive", "off_character"]]
    note: str
    updated_at: AwareDatetime


class ForkCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: int
    through_message_id: UUID | None
    title: str | None
    mode: Literal["standard", "fixed_panel", "jev_guided"] | None = None
    before_message_id: UUID | None = None
    purpose: Literal["fork", "edit", "regenerate"] = "fork"
    folder_id: UUID | None = None


class RetryCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: int


class Settings(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    provider_mode: Literal["live", "demo"]
    openai_configured: bool
    jev_configured: bool
    openai_model: str
    research_model: str
    jev_model: str
    limits: dict[str, Any]
    local_only: bool


class Openai(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["ok", "missing", "failed", "demo"]
    message: str


class Jev(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["ok", "missing", "failed", "demo"]
    message: str


class ProviderCheck(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    openai: Openai
    jev: Jev


class Persona(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    display_name: str
    tagline: str
    initials: str
    accent: str
    priorities: list[str]
    contribution_habits: list[str]
    voice: str
    productive_tension: str
    update_rule: str
    boundaries: list[str]
    example: str
    evaluation_probes: list[str]
    version: str
    simulated: bool


class PersonaList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    items: list[Persona]
    default_selection: list[
        Literal[
            "mentor", "skeptic", "explorer", "strategist", "engineer", "customer", "civic", "health"
        ]
    ]


class EvaluationCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    case_ids: Annotated[list[str], Field(max_length=30, min_length=1)]
    modes: Annotated[
        list[Literal["standard", "fixed_panel", "jev_guided"]], Field(max_length=3, min_length=1)
    ]
    repetitions: Annotated[int, Field(ge=1, le=5)]
    evidence_policy: Literal["off", "fixture", "live"]
    blind_rating: bool
    max_trials: Annotated[int, Field(ge=1, le=90)]


class Evaluation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    status: Literal[
        "queued", "running", "completed", "partial", "cancelled", "failed", "interrupted"
    ]
    planned_trials: int
    finished_trials: int
    failed_trials: int
    config: EvaluationCreate
    created_at: AwareDatetime
    updated_at: AwareDatetime


class EvaluationList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    items: list[Evaluation]
    next_cursor: str | None


class Trial(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    evaluation_id: UUID
    case_id: str
    replicate: int
    blind_label: str
    mode: Literal["standard", "fixed_panel", "jev_guided"] | None
    session_id: UUID
    status: str
    degraded: bool | None
    messages: list[Message]


class TrialList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    items: list[Trial]
    next_cursor: str | None


class RatingCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    trial_id: UUID
    rater_alias: str
    useful_breadth: Annotated[int, Field(ge=1, le=5)]
    usefulness: Annotated[int, Field(ge=1, le=5)]
    consistency: Annotated[int | None, Field(ge=1, le=5)]
    redundancy: Annotated[int, Field(ge=1, le=5)]
    note: str
    unblinded: bool
    labels: list[
        Literal[
            "unsupported_claim", "missed_constraint", "false_credential", "mishandled_disagreement"
        ]
    ]
    distinct_directions: Annotated[int | None, Field(ge=0)]


class Rating(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    trial_id: UUID
    rater_alias: str
    useful_breadth: Annotated[int, Field(ge=1, le=5)]
    usefulness: Annotated[int, Field(ge=1, le=5)]
    consistency: Annotated[int | None, Field(ge=1, le=5)]
    redundancy: Annotated[int, Field(ge=1, le=5)]
    note: str
    unblinded: bool
    labels: list[
        Literal[
            "unsupported_claim", "missed_constraint", "false_credential", "mishandled_disagreement"
        ]
    ]
    distinct_directions: Annotated[int | None, Field(ge=0)]
    created_at: AwareDatetime


class EvaluationCase(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    domain: str
    idea: str
    constraints: list[str]
    persona_ids: list[
        Literal[
            "mentor", "skeptic", "explorer", "strategist", "engineer", "customer", "civic", "health"
        ]
    ]
    user_turns: list[str]
    evidence_pack_id: str | None
    evaluation_focus: list[str]


class EvaluationCaseList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    version: str
    items: list[EvaluationCase]


class ConditionResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mode: Literal["standard", "fixed_panel", "jev_guided"]
    planned: int
    completed: int
    incomplete: int
    degraded: int
    rated_trials: int
    mean_useful_breadth: float | None
    mean_usefulness: float | None
    mean_consistency: float | None
    mean_redundancy: float | None
    median_elapsed_ms: float | None
    estimated_cost_usd: float | None


class CaseDifference(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    case_id: str
    difference: float


class PairedComparison(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    left: Literal["standard", "fixed_panel", "jev_guided"]
    right: Literal["standard", "fixed_panel", "jev_guided"]
    metric: Literal["useful_breadth", "usefulness", "consistency", "redundancy"]
    matched_cases: int
    mean_difference: float | None
    ci95_low: float | None
    ci95_high: float | None
    case_differences: list[CaseDifference]
    interpretation: str


class EvaluationResults(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    evaluation_id: UUID
    provider_mode: Literal["live", "demo"]
    evidence_policy: Literal["off", "fixture", "live"]
    conditions: list[ConditionResult]
    comparisons: list[PairedComparison]
    ratings: list[Rating]
    warnings: list[str]


class Health(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["ok", "degraded"]
    database: Literal["ok", "failed"]
    worker: Literal["ok", "failed"]
    version: str


class SessionOrganizationPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_organization_version: Annotated[int, Field(ge=1)]
    title: Annotated[str | None, Field(max_length=120, min_length=1)] = None
    folder_id: UUID | None = None
    is_pinned: bool | None = None
    is_archived: bool | None = None


class Folder(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    name: Annotated[str, Field(max_length=80, min_length=1)]
    version: Annotated[int, Field(ge=1)]
    chat_count: Annotated[int, Field(ge=0)]
    archived_chat_count: Annotated[int, Field(ge=0)]
    created_at: AwareDatetime
    updated_at: AwareDatetime


class FolderList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    items: list[Folder]
    next_cursor: str | None


class FolderCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(max_length=80, min_length=1)]


class FolderPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: Annotated[int, Field(ge=1)]
    name: Annotated[str, Field(max_length=80, min_length=1)]


class SearchMatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["title", "message"]
    snippet: Annotated[str, Field(max_length=240, min_length=1)]
    message_id: UUID | None
    message_sequence: Annotated[int | None, Field(ge=1)]


class SessionSummary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: UUID
    title: str
    mode: Literal["standard", "fixed_panel", "jev_guided"]
    selected_persona_ids: list[
        Literal[
            "mentor", "skeptic", "explorer", "strategist", "engineer", "customer", "civic", "health"
        ]
    ]
    organization_version: Annotated[int, Field(ge=1)]
    folder_id: UUID | None
    is_pinned: bool
    is_archived: bool
    last_activity_at: AwareDatetime
    active_run_id: UUID | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    match: SearchMatch | None


class ForkResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    session: Session
    turn_template: TurnCreate | None


class SessionList(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    items: list[SessionSummary]
    next_cursor: str | None
