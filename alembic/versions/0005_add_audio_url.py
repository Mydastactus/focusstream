"""add audio_url to raw_feed_items

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_feed_items", sa.Column("audio_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_feed_items", "audio_url")
