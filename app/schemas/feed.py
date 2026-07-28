from pydantic import BaseModel


class FeedSource(BaseModel):
    name: str
    type: str
    avatar_url: str | None = None


class FeedContent(BaseModel):
    title: str
    thumbnail_url: str | None = None
    ai_summary: str | None = None
    estimated_read_time: str | None = None


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
