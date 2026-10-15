"""round info on user messages, intake on runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15 05:30:00

A round's public status (provider mode, warnings, missing replies) lives on its user message so
forks and exports keep it; a run's intake result lets a retry reuse it instead of paying again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "round_info", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "runs",
        sa.Column(
            "intake", postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "intake")
    op.drop_column("messages", "round_info")
