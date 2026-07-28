"""add is_dismissed to signal_cards

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signal_cards",
        sa.Column("is_dismissed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("signal_cards", "is_dismissed")
