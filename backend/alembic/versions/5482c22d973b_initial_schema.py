"""initial schema

Revision ID: 5482c22d973b
Revises:
Create Date: 2026-10-22 21:06:29.189752

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5482c22d973b"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("actor_id", sa.String(length=32), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hash"),
    )
    op.create_index(op.f("ix_audit_events_entity_id"), "audit_events", ["entity_id"], unique=False)
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("n_items", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("confusion", sa.JSON(), nullable=False),
        sa.Column("failures", sa.JSON(), nullable=False),
        sa.Column("latency_ms_p50", sa.Float(), nullable=False),
        sa.Column("latency_ms_p95", sa.Float(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("voice_profile", sa.JSON(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("rulebook_version", sa.Integer(), nullable=False),
        sa.Column("factbook_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "channel_profiles",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("max_chars", sa.Integer(), nullable=True),
        sa.Column("max_hashtags", sa.Integer(), nullable=True),
        sa.Column("subject_max_chars", sa.Integer(), nullable=True),
        sa.Column("consumer", sa.Boolean(), nullable=False),
        sa.Column("rule_code", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "confidential_terms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("term", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sample_drafts",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=120), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "terms",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("term", sa.String(length=120), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "product_name",
                "banned",
                "discouraged",
                name="termkind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("variants", sa.JSON(), nullable=False),
        sa.Column("replacement", sa.String(length=120), nullable=True),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False),
        sa.Column("rule_code", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "creator",
                "reviewer",
                "brand_manager",
                "approver",
                "admin",
                name="role",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "webhooks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("secret", sa.String(length=64), nullable=False),
        sa.Column("slack_format", sa.Boolean(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_table(
        "facts",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("source_doc", sa.String(length=200), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("superseded_by", sa.String(length=16), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "retired", name="rulestatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("approved_by", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
        ),
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
    op.create_table(
        "rules",
        sa.Column("pk", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("critical", "major", "minor", name="severity", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("source_doc", sa.String(length=200), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "retired", name="rulestatus", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("approved_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("pk"),
        sa.UniqueConstraint("workspace_id", "code", "version"),
    )
    op.create_index(op.f("ix_rules_code"), "rules", ["code"], unique=False)
    op.create_table(
        "submissions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=32), nullable=False),
        sa.Column("author_id", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "draft",
                "in_review",
                "changes_requested",
                "approved",
                "published",
                name="submissionstate",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("approved_by", sa.String(length=32), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("webhook_id", sa.String(length=32), nullable=False),
        sa.Column("event", sa.String(length=48), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["webhook_id"],
            ["webhooks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_webhook_deliveries_webhook_id"), "webhook_deliveries", ["webhook_id"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("submission_id", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_table(
        "revisions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("submission_id", sa.String(length=32), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_uri", sa.String(length=300), nullable=True),
        sa.Column("source_format", sa.String(length=16), nullable=False),
        sa.Column("normalised_doc", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("brand_score", sa.Integer(), nullable=True),
        sa.Column("degraded", sa.Boolean(), nullable=False),
        sa.Column("rulebook_version", sa.Integer(), nullable=True),
        sa.Column("factbook_version", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "number"),
    )
    op.create_index(
        op.f("ix_revisions_submission_id"), "revisions", ["submission_id"], unique=False
    )
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("revision_id", sa.String(length=32), nullable=True),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("masked", sa.Boolean(), nullable=False),
        sa.Column("masked_count", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["revisions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_calls_revision_id"), "ai_calls", ["revision_id"], unique=False)
    op.create_table(
        "claims",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("revision_id", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("span", sa.JSON(), nullable=False),
        sa.Column("claim_type", sa.String(length=32), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("fact_id", sa.String(length=16), nullable=True),
        sa.Column("current_fact_id", sa.String(length=16), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["revisions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_claims_revision_id"), "claims", ["revision_id"], unique=False)
    op.create_table(
        "findings",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("revision_id", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("span", sa.JSON(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("rule_code", sa.String(length=16), nullable=False),
        sa.Column("rule_source", sa.String(length=200), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("critical", "major", "minor", name="severity", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.JSON(), nullable=True),
        sa.Column("detector", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("related", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["revisions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_findings_revision_id"), "findings", ["revision_id"], unique=False)
    op.create_table(
        "comments",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("submission_id", sa.String(length=32), nullable=False),
        sa.Column("finding_id", sa.String(length=32), nullable=True),
        sa.Column("author_id", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_comments_submission_id"), "comments", ["submission_id"], unique=False)
    op.create_table(
        "decisions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("submission_id", sa.String(length=32), nullable=False),
        sa.Column("revision_id", sa.String(length=32), nullable=True),
        sa.Column("finding_id", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["revisions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_decisions_submission_id"), "decisions", ["submission_id"], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_decisions_submission_id"), table_name="decisions")
    op.drop_table("decisions")
    op.drop_index(op.f("ix_comments_submission_id"), table_name="comments")
    op.drop_table("comments")
    op.drop_index(op.f("ix_findings_revision_id"), table_name="findings")
    op.drop_table("findings")
    op.drop_index(op.f("ix_claims_revision_id"), table_name="claims")
    op.drop_table("claims")
    op.drop_index(op.f("ix_ai_calls_revision_id"), table_name="ai_calls")
    op.drop_table("ai_calls")
    op.drop_index(op.f("ix_revisions_submission_id"), table_name="revisions")
    op.drop_table("revisions")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_webhook_deliveries_webhook_id"), table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_table("submissions")
    op.drop_index(op.f("ix_rules_code"), table_name="rules")
    op.drop_table("rules")
    op.drop_table("facts")
    op.drop_table("api_keys")
    op.drop_table("webhooks")
    op.drop_table("users")
    op.drop_table("terms")
    op.drop_table("sample_drafts")
    op.drop_table("confidential_terms")
    op.drop_table("channel_profiles")
    op.drop_table("workspaces")
    op.drop_table("eval_runs")
    op.drop_index(op.f("ix_audit_events_entity_id"), table_name="audit_events")
    op.drop_table("audit_events")
    # ### end Alembic commands ###
