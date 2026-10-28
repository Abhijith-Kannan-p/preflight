"""visual review: page images of a revision, and image regions on findings

Revision ID: 2a92a2b7d433
Revises: a3c1d9e7f201
Create Date: 2026-10-28 17:59:20.444884

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2a92a2b7d433"
down_revision: str | None = "a3c1d9e7f201"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revision_assets",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("revision_id", sa.String(length=32), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(length=32), nullable=False),
        sa.Column("scale", sa.Float(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["revisions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_revision_assets_revision_id"), "revision_assets", ["revision_id"], unique=False
    )
    op.add_column("findings", sa.Column("region", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("findings", "region")
    op.drop_index(op.f("ix_revision_assets_revision_id"), table_name="revision_assets")
    op.drop_table("revision_assets")
