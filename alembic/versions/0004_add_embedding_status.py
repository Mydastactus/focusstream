"""add embedding_status to sprints

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    embedding_status = sa.Enum("pending", "ready", "failed", name="embedding_status")
    embedding_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "sprints",
        sa.Column(
            "embedding_status",
            sa.Enum("pending", "ready", "failed", name="embedding_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
    )
    # Backfill: sprints that already have a vector are ready, not pending.
    op.execute(
        "UPDATE sprints SET embedding_status = 'ready' WHERE intent_embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("sprints", "embedding_status")
    op.execute("DROP TYPE IF EXISTS embedding_status")
