import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SignalTier(str, enum.Enum):
    high_signal = "high_signal"
    contextual = "contextual"
    low_signal = "low_signal"


class SignalCard(Base):
    """A processed (item x sprint) match. Denormalized-for-read: the feed
    endpoint joins card + raw_item and returns rows directly, no computation."""

    __tablename__ = "signal_cards"
    __table_args__ = (
        UniqueConstraint("intent_sprint_id", "raw_item_id", name="uq_card_sprint_item"),
        Index("idx_cards_sprint_feed", "intent_sprint_id", "signal_score"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "card_0091"
    intent_sprint_id: Mapped[str] = mapped_column(
        ForeignKey("sprints.id", ondelete="CASCADE"), nullable=False
    )
    raw_item_id: Mapped[str] = mapped_column(
        ForeignKey("raw_feed_items.id", ondelete="CASCADE"), nullable=False
    )
    signal_score: Mapped[float] = mapped_column(Float, nullable=False)  # cosine sim
    signal_tier: Mapped[SignalTier] = mapped_column(
        Enum(SignalTier, name="signal_tier"), nullable=False
    )
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_read_time: Mapped[str | None] = mapped_column(String, nullable=True)
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Downvote / dismiss hides the card from the feed (distinct from is_read).
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sprint: Mapped["Sprint"] = relationship(back_populates="cards")
    raw_item: Mapped["RawFeedItem"] = relationship(back_populates="cards")
    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="card", cascade="all, delete-orphan"
    )
