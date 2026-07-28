"""add sources table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # source_type enum already exists (created in 0001) — reference, don't create.
    source_type = sa.Enum(
        "rss", "newsletters", "podcasts", name="source_type", create_type=False
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", source_type, nullable=False),
        sa.Column("url", sa.String(), nullable=False, unique=True),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("sources")
