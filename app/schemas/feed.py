from pydantic import BaseModel


class FeedSource(BaseModel):
    name: str
    type: str
    avatar_url: str | None = None  # null if the source has no avatar


class FeedContent(BaseModel):
    title: str
    thumbnail_url: str | None = None  # null if the item has no image
    ai_summary: str | None = None  # null on contextual-tier cards (not synthesized)
    estimated_read_time: str  # always populated (guaranteed by the serializer)


class FeedUserActions(BaseModel):
    is_saved: bool
    is_read: bool


class FeedItem(BaseModel):
    card_id: str
    intent_sprint_id: str
    signal_score: float
    signal_tier: str
    source: FeedSource
    content: FeedContent
    user_actions: FeedUserActions


class FeedResponse(BaseModel):
    sprint_id: str
    total_items: int
    items: list[FeedItem]
