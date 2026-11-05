"""Add the background_jobs table.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "run_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("result", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_background_jobs_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'dead')",
            name="ck_background_jobs_status_valid",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_background_jobs_attempts_non_negative"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_background_jobs_max_attempts_positive"),
        sa.CheckConstraint("timeout_seconds >= 1", name="ck_background_jobs_timeout_positive"),
    )
    op.create_index(
        "ix_background_jobs_claimable",
        "background_jobs",
        ["run_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_background_jobs_reclaimable",
        "background_jobs",
        ["locked_until"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_reclaimable", table_name="background_jobs")
    op.drop_index("ix_background_jobs_claimable", table_name="background_jobs")
    op.drop_table("background_jobs")
