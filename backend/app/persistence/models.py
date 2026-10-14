"""Relational schema (doc 08 §Persistence). JSONB holds immutable snapshots and typed content."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

RUN_STATUSES = (
    "queued",
    "running",
    "cancelling",
    "completed",
    "partial",
    "cancelled",
    "failed",
    "interrupted",
)
ACTIVE_RUN_STATUSES = ("queued", "running", "cancelling")
TERMINAL_RUN_STATUSES = ("completed", "partial", "cancelled", "failed", "interrupted")
EVENT_TYPES = (
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
)
BATCH_STATUSES = ("queued", "running", "completed", "partial", "cancelled", "failed", "interrupted")
MODES = ("standard", "fixed_panel", "jev_guided")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(primary_key=True, default=uuid4)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Base(DeclarativeBase):
    # none_as_null: Python None is SQL NULL (not JSON null), so content CHECKs see real NULLs.
    type_annotation_map = {
        dict[str, Any]: JSONB(none_as_null=True),
        list[Any]: JSONB(none_as_null=True),
        datetime: DateTime(timezone=True),
    }


class Folder(Base):
    __tablename__ = "folders"
    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    name_normalized: Mapped[str] = mapped_column(Text, unique=True)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class EvaluationBatch(Base):
    __tablename__ = "evaluation_batches"
    __table_args__ = (CheckConstraint(_in("status", BATCH_STATUSES), name="batch_status"),)
    id: Mapped[UUID] = _uuid_pk()
    status: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]]
    snapshot: Mapped[dict[str, Any]]
    seed: Mapped[int] = mapped_column(BigInteger)
    provider_mode: Mapped[str] = mapped_column(Text)
    planned: Mapped[int] = mapped_column(Integer)
    finished: Mapped[int] = mapped_column(Integer, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, server_default="0")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None]


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(_in("mode", MODES), name="session_mode"),
        Index(
            "ix_sessions_history",
            "is_archived",
            sql_text("last_activity_at DESC"),
            sql_text("id DESC"),
            postgresql_where=sql_text("evaluation_batch_id IS NULL"),
        ),
        Index(
            "ix_sessions_folder",
            "folder_id",
            "is_archived",
            sql_text("last_activity_at DESC"),
            sql_text("id DESC"),
            postgresql_where=sql_text("evaluation_batch_id IS NULL"),
        ),
        Index(
            "ix_sessions_pinned",
            sql_text("last_activity_at DESC"),
            sql_text("id DESC"),
            postgresql_where=sql_text("evaluation_batch_id IS NULL AND is_pinned"),
        ),
        Index(
            "ix_sessions_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )
    id: Mapped[UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(Text)
    title_is_custom: Mapped[bool] = mapped_column(Boolean, server_default="false")
    folder_id: Mapped[UUID | None] = mapped_column(ForeignKey("folders.id", ondelete="SET NULL"))
    is_pinned: Mapped[bool] = mapped_column(Boolean, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, server_default="false")
    organization_version: Mapped[int] = mapped_column(Integer, server_default="1")
    last_activity_at: Mapped[datetime] = _now()
    origin_session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL")
    )
    mode: Mapped[str] = mapped_column(Text)
    selected_persona_ids: Mapped[list[Any]]
    settings: Mapped[dict[str, Any]]
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    brief: Mapped[dict[str, Any]]
    memory: Mapped[dict[str, Any] | None]
    last_sequence: Mapped[int] = mapped_column(Integer, server_default="0")
    evaluation_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("evaluation_batches.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class IdeaRevision(Base):
    __tablename__ = "idea_revisions"
    __table_args__ = (UniqueConstraint("session_id", "revision"),)
    id: Mapped[UUID] = _uuid_pk()
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    idea: Mapped[str] = mapped_column(Text)
    goal: Mapped[str | None] = mapped_column(Text)
    constraints: Mapped[list[Any]]
    author_type: Mapped[str] = mapped_column(Text)
    source_message_ids: Mapped[list[Any]] = mapped_column(server_default=sql_text("'[]'::jsonb"))
    created_at: Mapped[datetime] = _now()


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="run_status"),
        Index(
            "uq_runs_one_active_per_session",
            "session_id",
            unique=True,
            postgresql_where=sql_text(_in("status", ACTIVE_RUN_STATUSES)),
        ),
        Index("ix_runs_claim", "status", "created_at"),
        Index("ix_runs_session", "session_id", "created_at"),
    )
    id: Mapped[UUID] = _uuid_pk()
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    user_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL", deferrable=True, initially="DEFERRED")
    )
    status: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text, server_default="queued")
    mode: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(Text)
    control: Mapped[dict[str, Any]]
    snapshot: Mapped[dict[str, Any]]
    slots: Mapped[list[Any]]
    missing: Mapped[list[Any]] = mapped_column(server_default=sql_text("'[]'::jsonb"))
    requested_count: Mapped[int] = mapped_column(Integer)
    published_count: Mapped[int] = mapped_column(Integer, server_default="0")
    degraded: Mapped[bool] = mapped_column(Boolean, server_default="false")
    warning_codes: Mapped[list[Any]] = mapped_column(server_default=sql_text("'[]'::jsonb"))
    error: Mapped[dict[str, Any] | None]
    usage: Mapped[dict[str, Any]] = mapped_column(server_default=sql_text("'{}'::jsonb"))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    repairs_used: Mapped[int] = mapped_column(Integer, server_default="0")
    research_used: Mapped[int] = mapped_column(Integer, server_default="0")
    intake: Mapped[dict[str, Any] | None]  # the normalized intake, reused by retries
    cancel_requested: Mapped[bool] = mapped_column(Boolean, server_default="false")
    worker_id: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None]
    deadline_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    retry_of_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    session_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


MESSAGE_VARIANTS = (
    "(role = 'user' AND persona_id IS NULL AND text IS NOT NULL"
    " AND contribution IS NULL AND summary IS NULL)"
    " OR (role = 'persona' AND persona_id IS NOT NULL AND contribution IS NOT NULL"
    " AND text IS NULL AND summary IS NULL)"
    " OR (role = 'moderator' AND persona_id IS NULL"
    " AND num_nonnulls(text, contribution, summary) = 1)"
)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence"),
        UniqueConstraint("run_id", "contribution_index"),
        CheckConstraint(_in("role", ("user", "persona", "moderator")), name="message_role"),
        CheckConstraint(MESSAGE_VARIANTS, name="message_content_variant"),
        Index(
            "ix_messages_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )
    id: Mapped[UUID] = _uuid_pk()
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL", use_alter=True, name="fk_messages_run_id")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    contribution_index: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(Text)
    persona_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    contribution: Mapped[dict[str, Any] | None]
    summary: Mapped[dict[str, Any] | None]
    warning_codes: Mapped[list[Any]] = mapped_column(server_default=sql_text("'[]'::jsonb"))
    search_text: Mapped[str] = mapped_column(Text, server_default="")
    origin_message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    turn_control: Mapped[dict[str, Any] | None]
    turn_snapshot: Mapped[dict[str, Any] | None]
    round_status: Mapped[str | None] = mapped_column(Text)
    # Public status of the round this user message opened (copied by forks; read by exports).
    round_info: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = _now()


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (
        CheckConstraint(_in("type", EVENT_TYPES), name="event_type"),
        Index("ix_run_events_run", "run_id", "id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _now()


class ResearchPack(Base):
    __tablename__ = "research_packs"
    __table_args__ = (
        CheckConstraint(_in("status", ("available", "empty", "failed")), name="pack_status"),
    )
    id: Mapped[UUID] = _uuid_pk()
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    raw_answer: Mapped[dict[str, Any] | None]
    normalized: Mapped[dict[str, Any] | None]
    unknowns: Mapped[list[Any]] = mapped_column(server_default=sql_text("'[]'::jsonb"))
    provider_response_id: Mapped[str | None] = mapped_column(Text)
    is_fixture: Mapped[bool] = mapped_column(Boolean, server_default="false")
    origin_pack_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_packs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now()


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_session", "session_id", "retrieved_at", "id"),)
    id: Mapped[UUID] = _uuid_pk()
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    research_pack_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_packs.id", ondelete="CASCADE")
    )
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime]
    published_at: Mapped[str | None] = mapped_column(Text)
    provider_response_id: Mapped[str] = mapped_column(Text)
    provider_citation: Mapped[list[Any]] = mapped_column(server_default=sql_text("'[]'::jsonb"))
    research_excerpt: Mapped[str] = mapped_column(Text)
    is_fixture: Mapped[bool] = mapped_column(Boolean, server_default="false")
    origin_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now()


class IdeaCard(Base):
    __tablename__ = "idea_cards"
    __table_args__ = (
        CheckConstraint(_in("status", ("exploring", "selected", "parked")), name="card_status"),
        Index("ix_idea_cards_session", "session_id", "created_at", "id"),
    )
    id: Mapped[UUID] = _uuid_pk()
    session_id: Mapped[UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    origin_card_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("idea_cards.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[UUID] = _uuid_pk()
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), unique=True
    )
    labels: Mapped[list[Any]]
    note: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = _now()


class ProviderCall(Base):
    __tablename__ = "provider_calls"
    __table_args__ = (
        CheckConstraint(
            _in(
                "status",
                (
                    "started",
                    "ok",
                    "refused",
                    "incomplete",
                    "invalid",
                    "error",
                    "timeout",
                    "cancelled",
                ),
            ),
            name="call_status",
        ),
        Index("ix_provider_calls_run", "run_id"),
    )
    id: Mapped[UUID] = _uuid_pk()
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    template_hash: Mapped[str | None] = mapped_column(Text)
    profile_hash: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    response_id: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None]
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_estimate_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    status: Mapped[str] = mapped_column(Text, server_default="started")
    usage_unknown: Mapped[bool] = mapped_column(Boolean, server_default="false")
    diagnostics: Mapped[dict[str, Any]] = mapped_column(server_default=sql_text("'{}'::jsonb"))


class DecisionEvent(Base):
    __tablename__ = "decision_events"
    __table_args__ = (Index("ix_decision_events_run", "run_id", "step"),)
    id: Mapped[UUID] = _uuid_pk()
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    step: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    persona_id: Mapped[str | None] = mapped_column(Text)
    provider_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("provider_calls.id", ondelete="SET NULL")
    )
    eligible_options: Mapped[list[Any]]
    state_hash: Mapped[str | None] = mapped_column(Text)
    state: Mapped[dict[str, Any] | None]
    answers: Mapped[dict[str, Any] | None]
    selected: Mapped[dict[str, Any]]
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    repair_outcome: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("route", "key"),)
    id: Mapped[UUID] = _uuid_pk()
    route: Mapped[str] = mapped_column(Text)
    key: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int] = mapped_column(Integer)
    response: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _now()


class EvaluationTrial(Base):
    __tablename__ = "evaluation_trials"
    __table_args__ = (
        UniqueConstraint("batch_id", "case_id", "replicate", "mode"),
        CheckConstraint(_in("mode", MODES), name="trial_mode"),
    )
    id: Mapped[UUID] = _uuid_pk()
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("evaluation_batches.id", ondelete="CASCADE"))
    case_id: Mapped[str] = mapped_column(Text)
    replicate: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(Text)
    session_id: Mapped[UUID | None] = mapped_column(ForeignKey("sessions.id"))
    blind_label: Mapped[str] = mapped_column(Text)
    evidence_hash: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    degraded: Mapped[bool] = mapped_column(Boolean, server_default="false")
    revealed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    revealed_at: Mapped[datetime | None]
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    usage: Mapped[dict[str, Any]] = mapped_column(server_default=sql_text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class EvaluationRating(Base):
    __tablename__ = "evaluation_ratings"
    __table_args__ = (Index("ix_ratings_trial", "trial_id", "created_at"),)
    id: Mapped[UUID] = _uuid_pk()
    trial_id: Mapped[UUID] = mapped_column(ForeignKey("evaluation_trials.id", ondelete="CASCADE"))
    rater_alias: Mapped[str] = mapped_column(Text)
    useful_breadth: Mapped[int] = mapped_column(Integer)
    usefulness: Mapped[int] = mapped_column(Integer)
    consistency: Mapped[int | None] = mapped_column(Integer)
    redundancy: Mapped[int] = mapped_column(Integer)
    labels: Mapped[list[Any]]
    distinct_directions: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text)
    unblinded: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = _now()
