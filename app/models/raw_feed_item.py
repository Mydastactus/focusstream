import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.models.base import Base


class SourceType(str, enum.Enum):
    rss = "rss"
    newsletters = "newsletters"
    podcasts = "podcasts"


class RawFeedItem(Base):
    """A single ingested piece of content before it is matched to any sprint.
    `content_hash` de-duplicates identical items so each is embedded once."""

    __tablename__ = "raw_feed_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "item_5521"
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)  # article / transcript
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # Podcast audio enclosure URL; drives Whisper transcription.
    audio_url: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, index=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dim), nullable=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    cards: Mapped[list["SignalCard"]] = relationship(
        back_populates="raw_item", cascade="all, delete-orphan"
    )
