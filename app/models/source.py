from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.raw_feed_item import SourceType


class Source(Base):
    """A content source to poll (RSS / newsletter / podcast feed URL)."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "src_1a2b"
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[SourceType] = mapped_column(
        # Enum type already created by migration 0001 -> don't re-create it.
        Enum(SourceType, name="source_type", create_type=False), nullable=False
    )
    url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
