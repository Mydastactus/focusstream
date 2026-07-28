import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.models.base import Base


class SprintStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    archived = "archived"


class EmbeddingStatus(str, enum.Enum):
    """Lifecycle of the intent vector. `failed` means the worker exhausted its
    retries — the sprint would otherwise show "Indexing…" forever."""

    pending = "pending"
    ready = "ready"
    failed = "failed"


class Sprint(Base):
    """A user-defined learning goal ("Intent Sprint"). Its `intent_embedding`
    is the query vector every incoming content item is scored against."""

    __tablename__ = "sprints"
    __table_args__ = (
        CheckConstraint("duration_days > 0", name="ck_sprint_duration_positive"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "spr_104"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    sources_allowed: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    status: Mapped[SprintStatus] = mapped_column(
        Enum(SprintStatus, name="sprint_status"),
        default=SprintStatus.active,
        nullable=False,
    )
    # Filled asynchronously by the worker after creation.
    intent_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dim), nullable=True
    )
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        Enum(EmbeddingStatus, name="embedding_status"),
        default=EmbeddingStatus.pending,
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="sprints")
    cards: Mapped[list["SignalCard"]] = relationship(
        back_populates="sprint", cascade="all, delete-orphan"
    )
