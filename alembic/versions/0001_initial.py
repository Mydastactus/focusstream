"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-27
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.core.config import settings

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBED_DIM = settings.embedding_dim


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    sprint_status = sa.Enum("active", "completed", "archived", name="sprint_status")
    source_type = sa.Enum("rss", "newsletters", "podcasts", name="source_type")
    signal_tier = sa.Enum("high_signal", "contextual", "low_signal", name="signal_tier")
    feedback_action = sa.Enum(
        "upvote", "downvote", "save", "dismiss", name="feedback_action"
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "sprints",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("sources_allowed", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("status", sprint_status, nullable=False, server_default="active"),
        sa.Column("intent_embedding", Vector(EMBED_DIM), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("duration_days > 0", name="ck_sprint_duration_positive"),
    )
    op.create_index(
        "idx_sprints_user_active",
        "sprints",
        ["user_id"],
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "raw_feed_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_avatar_url", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("thumbnail_url", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False, unique=True),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # HNSW approximate-nearest-neighbour index. Requires EMBED_DIM <= 2000.
    op.execute(
        "CREATE INDEX idx_raw_items_embedding ON raw_feed_items "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "signal_cards",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "intent_sprint_id",
            sa.String(),
            sa.ForeignKey("sprints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_item_id",
            sa.String(),
            sa.ForeignKey("raw_feed_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_score", sa.Float(), nullable=False),
        sa.Column("signal_tier", signal_tier, nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("estimated_read_time", sa.String(), nullable=True),
        sa.Column("is_saved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("intent_sprint_id", "raw_item_id", name="uq_card_sprint_item"),
    )
    op.create_index(
        "idx_cards_sprint_feed", "signal_cards", ["intent_sprint_id", "signal_score"]
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "card_id",
            sa.String(),
            sa.ForeignKey("signal_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", feedback_action, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_feedback_card", "feedback", ["card_id"])


def downgrade() -> None:
    op.drop_index("idx_feedback_card", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("idx_cards_sprint_feed", table_name="signal_cards")
    op.drop_table("signal_cards")
    op.execute("DROP INDEX IF EXISTS idx_raw_items_embedding")
    op.drop_table("raw_feed_items")
    op.drop_index("idx_sprints_user_active", table_name="sprints")
    op.drop_table("sprints")
    op.drop_table("users")
    for enum_name in ("feedback_action", "signal_tier", "source_type", "sprint_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
