"""Shared response builders so the per-sprint feed and the aggregate ("All")
feed emit byte-identical FeedItem shapes."""

from app.models.raw_feed_item import RawFeedItem
from app.models.signal_card import SignalCard
from app.schemas.feed import FeedContent, FeedItem, FeedSource, FeedUserActions


def to_feed_item(card: SignalCard, raw: RawFeedItem) -> FeedItem:
    return FeedItem(
        card_id=card.id,
        intent_sprint_id=card.intent_sprint_id,
        signal_score=card.signal_score,
        signal_tier=card.signal_tier.value,
        source=FeedSource(
            name=raw.source_name,
            type=raw.source_type.value,
            avatar_url=raw.source_avatar_url,
        ),
        content=FeedContent(
            title=raw.title,
            thumbnail_url=raw.thumbnail_url,
            ai_summary=card.ai_summary,
            estimated_read_time=card.estimated_read_time,
        ),
        user_actions=FeedUserActions(is_saved=card.is_saved, is_read=card.is_read),
    )
