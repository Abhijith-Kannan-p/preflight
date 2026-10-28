"""webhook delivery retries and resend

Revision ID: 7f59c509aff5
Revises: e2d71c184196
Create Date: 2026-10-29 03:18:01.711308

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7f59c509aff5"
down_revision: str | None = "e2d71c184196"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_deliveries",
        sa.Column("status", sa.String(length=16), server_default="delivered", nullable=False),
    )
    op.add_column(
        "webhook_deliveries",
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "webhook_deliveries",
        sa.Column("attempt_log", sa.JSON(), server_default="[]", nullable=False),
    )
    op.add_column("webhook_deliveries", sa.Column("payload", sa.JSON(), nullable=True))
    op.add_column("webhook_deliveries", sa.Column("resent_from", sa.Integer(), nullable=True))
    # Earlier single-attempt deliveries that failed.
    op.execute("UPDATE webhook_deliveries SET status = 'failed' WHERE NOT ok")


def downgrade() -> None:
    op.drop_column("webhook_deliveries", "resent_from")
    op.drop_column("webhook_deliveries", "payload")
    op.drop_column("webhook_deliveries", "attempt_log")
    op.drop_column("webhook_deliveries", "attempts")
    op.drop_column("webhook_deliveries", "status")
