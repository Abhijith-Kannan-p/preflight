"""per-visitor sandboxes, per-workspace audit chains, review cache key, idempotency keys

Revision ID: a3c1d9e7f201
Revises: 597a73c4b3b3
Create Date: 2026-10-28 12:00:00

Facts, channel profiles and sample drafts get a surrogate primary key so each workspace can
hold its own `F-087`, `linkedin` and `sample_linkedin`. Existing rows keep their ids and stay
in the template workspace.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3c1d9e7f201"
down_revision: str | None = "597a73c4b3b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEMPLATE = "ws_paywise"
SCOPED = ("facts", "channel_profiles", "sample_drafts")


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("kind", sa.String(16), nullable=False, server_default="template"),
    )
    op.add_column("workspaces", sa.Column("last_active_at", sa.DateTime(timezone=True)))

    op.add_column("users", sa.Column("persona", sa.String(32)))
    op.execute("UPDATE users SET persona = id")
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_unique_constraint("users_workspace_id_email_key", "users", ["workspace_id", "email"])
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])

    for table in SCOPED:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {table}_pkey")
        op.execute(f"ALTER TABLE {table} ADD COLUMN pk SERIAL PRIMARY KEY")
        op.create_unique_constraint(f"{table}_workspace_id_id_key", table, ["workspace_id", "id"])
    op.create_index("ix_facts_id", "facts", ["id"])

    op.add_column("revisions", sa.Column("context_hash", sa.String(64)))
    op.create_index("ix_revisions_context_hash", "revisions", ["context_hash"])

    op.add_column(
        "audit_events",
        sa.Column("workspace_id", sa.String(32), nullable=False, server_default=TEMPLATE),
    )
    op.alter_column("audit_events", "workspace_id", server_default=None)
    op.create_index("ix_audit_events_workspace_id", "audit_events", ["workspace_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("body", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_index("ix_audit_events_workspace_id", "audit_events")
    op.drop_column("audit_events", "workspace_id")
    op.drop_index("ix_revisions_context_hash", "revisions")
    op.drop_column("revisions", "context_hash")
    op.drop_index("ix_facts_id", "facts")
    for table in SCOPED:
        op.execute(f"DELETE FROM {table} WHERE workspace_id <> '{TEMPLATE}'")
        op.drop_constraint(f"{table}_workspace_id_id_key", table, type_="unique")
        op.execute(f"ALTER TABLE {table} DROP COLUMN pk")
        op.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (id)")
    op.drop_index("ix_users_workspace_id", "users")
    op.drop_constraint("users_workspace_id_email_key", "users", type_="unique")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.drop_column("users", "persona")
    op.drop_column("workspaces", "last_active_at")
    op.drop_column("workspaces", "kind")
