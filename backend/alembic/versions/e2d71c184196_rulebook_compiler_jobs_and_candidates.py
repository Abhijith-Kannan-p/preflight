"""rulebook compiler jobs and candidates

Revision ID: e2d71c184196
Revises: 2a92a2b7d433
Create Date: 2026-10-29 01:10:10.706590

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2d71c184196"
down_revision: str | None = "2a92a2b7d433"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compile_jobs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_compile_jobs_workspace_id"), "compile_jobs", ["workspace_id"], unique=False
    )
    op.create_table(
        "rule_candidates",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("extracted", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("match_status", sa.String(length=16), nullable=False),
        sa.Column("match_ref", sa.String(length=80), nullable=True),
        sa.Column("match_note", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided_by", sa.String(length=32), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_ref", sa.String(length=80), nullable=True),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["compile_jobs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rule_candidates_job_id"), "rule_candidates", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_rule_candidates_job_id"), table_name="rule_candidates")
    op.drop_table("rule_candidates")
    op.drop_index(op.f("ix_compile_jobs_workspace_id"), table_name="compile_jobs")
    op.drop_table("compile_jobs")
