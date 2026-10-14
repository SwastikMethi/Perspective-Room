"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-15 00:59:36.665803

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception as exc:  # surface a clear operator message instead of a broken search field
        raise RuntimeError(
            "PostgreSQL extension pg_trgm is required for chat search; the migration role "
            "needs permission to CREATE EXTENSION (see README / doc 12)."
        ) from exc
    op.create_table(
        "evaluation_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("provider_mode", sa.Text(), nullable=False),
        sa.Column("planned", sa.Integer(), nullable=False),
        sa.Column("finished", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'partial', 'cancelled', 'failed', 'interrupted')",
            name="batch_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "folders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_normalized", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_normalized"),
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route", "key"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_is_custom", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("folder_id", sa.Uuid(), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("organization_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("origin_session_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("selected_persona_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("brief", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("memory", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_sequence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("evaluation_batch_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('standard', 'fixed_panel', 'jev_guided')", name="session_mode"
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_batch_id"], ["evaluation_batches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["origin_session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sessions_folder",
        "sessions",
        [
            "folder_id",
            "is_archived",
            sa.literal_column("last_activity_at DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("evaluation_batch_id IS NULL"),
    )
    op.create_index(
        "ix_sessions_history",
        "sessions",
        ["is_archived", sa.literal_column("last_activity_at DESC"), sa.literal_column("id DESC")],
        unique=False,
        postgresql_where=sa.text("evaluation_batch_id IS NULL"),
    )
    op.create_index(
        "ix_sessions_pinned",
        "sessions",
        [sa.literal_column("last_activity_at DESC"), sa.literal_column("id DESC")],
        unique=False,
        postgresql_where=sa.text("evaluation_batch_id IS NULL AND is_pinned"),
    )
    op.create_index(
        "ix_sessions_title_trgm",
        "sessions",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_table(
        "evaluation_trials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("replicate", sa.Integer(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("blind_label", sa.Text(), nullable=False),
        sa.Column("evidence_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("degraded", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("revealed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column(
            "usage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("mode IN ('standard', 'fixed_panel', 'jev_guided')", name="trial_mode"),
        sa.ForeignKeyConstraint(["batch_id"], ["evaluation_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "case_id", "replicate", "mode"),
    )
    op.create_table(
        "idea_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("idea", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("constraints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("author_type", sa.Text(), nullable=False),
        sa.Column(
            "source_message_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "revision"),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("contribution_index", sa.Integer(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("persona_id", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("contribution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "warning_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.Column("origin_message_id", sa.Uuid(), nullable=True),
        sa.Column("turn_control", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("turn_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("round_status", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(role = 'user' AND persona_id IS NULL AND text IS NOT NULL AND contribution IS NULL AND summary IS NULL) OR (role = 'persona' AND persona_id IS NOT NULL AND contribution IS NOT NULL AND text IS NULL AND summary IS NULL) OR (role = 'moderator' AND persona_id IS NULL AND num_nonnulls(text, contribution, summary) = 1)",
            name="message_content_variant",
        ),
        sa.CheckConstraint("role IN ('user', 'persona', 'moderator')", name="message_role"),
        sa.ForeignKeyConstraint(["origin_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "contribution_index"),
        sa.UniqueConstraint("session_id", "sequence"),
    )
    op.create_index(
        "ix_messages_search_trgm",
        "messages",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_table(
        "evaluation_ratings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trial_id", sa.Uuid(), nullable=False),
        sa.Column("rater_alias", sa.Text(), nullable=False),
        sa.Column("useful_breadth", sa.Integer(), nullable=False),
        sa.Column("usefulness", sa.Integer(), nullable=False),
        sa.Column("consistency", sa.Integer(), nullable=True),
        sa.Column("redundancy", sa.Integer(), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("distinct_directions", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("unblinded", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trial_id"], ["evaluation_trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ratings_trial", "evaluation_ratings", ["trial_id", "created_at"], unique=False
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_table(
        "idea_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("origin_card_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('exploring', 'selected', 'parked')", name="card_status"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["origin_card_id"], ["idea_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_idea_cards_session", "idea_cards", ["session_id", "created_at", "id"], unique=False
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), server_default="queued", nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("control", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("slots", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "missing",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("published_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("degraded", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "warning_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "usage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("repairs_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("research_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("worker_id", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_of_run_id", sa.Uuid(), nullable=True),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'cancelling', 'completed', 'partial', 'cancelled', 'failed', 'interrupted')",
            name="run_status",
        ),
        sa.ForeignKeyConstraint(["retry_of_run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["messages.id"],
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_claim", "runs", ["status", "created_at"], unique=False)
    op.create_index("ix_runs_session", "runs", ["session_id", "created_at"], unique=False)
    op.create_index(
        "uq_runs_one_active_per_session",
        "runs",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running', 'cancelling')"),
    )
    op.create_foreign_key(
        "fk_messages_run_id", "messages", "runs", ["run_id"], ["id"], ondelete="SET NULL"
    )
    op.create_table(
        "provider_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("template_hash", sa.Text(), nullable=True),
        sa.Column("profile_hash", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("response_id", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_estimate_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("status", sa.Text(), server_default="started", nullable=False),
        sa.Column("usage_unknown", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "diagnostics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('started', 'ok', 'refused', 'incomplete', 'invalid', 'error', 'timeout', 'cancelled')",
            name="call_status",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provider_calls_run", "provider_calls", ["run_id"], unique=False)
    op.create_table(
        "research_packs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("raw_answer", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("normalized", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "unknowns",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("provider_response_id", sa.Text(), nullable=True),
        sa.Column("is_fixture", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("origin_pack_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('available', 'empty', 'failed')", name="pack_status"),
        sa.ForeignKeyConstraint(["origin_pack_id"], ["research_packs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "run_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('run.queued', 'run.started', 'run.stage', 'research.completed', 'message.completed', 'run.warning', 'run.completed', 'run.partial', 'run.cancelled', 'run.failed', 'run.interrupted')",
            name="event_type",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_events_run", "run_events", ["run_id", "id"], unique=False)
    op.create_table(
        "decision_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("persona_id", sa.Text(), nullable=True),
        sa.Column("provider_call_id", sa.Uuid(), nullable=True),
        sa.Column("eligible_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state_hash", sa.Text(), nullable=True),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("selected", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("repair_outcome", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["provider_call_id"], ["provider_calls.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_events_run", "decision_events", ["run_id", "step"], unique=False)
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("research_pack_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.Text(), nullable=True),
        sa.Column("provider_response_id", sa.Text(), nullable=False),
        sa.Column(
            "provider_citation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("research_excerpt", sa.Text(), nullable=False),
        sa.Column("is_fixture", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("origin_source_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["origin_source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["research_pack_id"], ["research_packs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sources_session", "sources", ["session_id", "retrieved_at", "id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_messages_run_id", "messages", type_="foreignkey")
    op.drop_index("ix_sources_session", table_name="sources")
    op.drop_table("sources")
    op.drop_index("ix_decision_events_run", table_name="decision_events")
    op.drop_table("decision_events")
    op.drop_index("ix_run_events_run", table_name="run_events")
    op.drop_table("run_events")
    op.drop_table("research_packs")
    op.drop_index("ix_provider_calls_run", table_name="provider_calls")
    op.drop_table("provider_calls")
    op.drop_index(
        "uq_runs_one_active_per_session",
        table_name="runs",
        postgresql_where=sa.text("status IN ('queued', 'running', 'cancelling')"),
    )
    op.drop_index("ix_runs_session", table_name="runs")
    op.drop_index("ix_runs_claim", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_idea_cards_session", table_name="idea_cards")
    op.drop_table("idea_cards")
    op.drop_table("feedback")
    op.drop_index("ix_ratings_trial", table_name="evaluation_ratings")
    op.drop_table("evaluation_ratings")
    op.drop_index(
        "ix_messages_search_trgm",
        table_name="messages",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_table("messages")
    op.drop_table("idea_revisions")
    op.drop_table("evaluation_trials")
    op.drop_index(
        "ix_sessions_title_trgm",
        table_name="sessions",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_sessions_pinned",
        table_name="sessions",
        postgresql_where=sa.text("evaluation_batch_id IS NULL AND is_pinned"),
    )
    op.drop_index(
        "ix_sessions_history",
        table_name="sessions",
        postgresql_where=sa.text("evaluation_batch_id IS NULL"),
    )
    op.drop_index(
        "ix_sessions_folder",
        table_name="sessions",
        postgresql_where=sa.text("evaluation_batch_id IS NULL"),
    )
    op.drop_table("sessions")
    op.drop_table("idempotency_records")
    op.drop_table("folders")
    op.drop_table("evaluation_batches")
