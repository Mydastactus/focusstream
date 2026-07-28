import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class FeedbackAction(str, enum.Enum):
    upvote = "upvote"
    downvote = "downvote"
    save = "save"
    dismiss = "dismiss"


class Feedback(Base):
    """User signal on a Signal Card. Feeds future re-ranking / threshold tuning."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    card_id: Mapped[str] = mapped_column(
        ForeignKey("signal_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[FeedbackAction] = mapped_column(
        Enum(FeedbackAction, name="feedback_action"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    card: Mapped["SignalCard"] = relationship(back_populates="feedback")
