from typing import Literal

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    # The API spec labels this `item_id`; we resolve it against Signal Cards
    # (the objects the feed surfaces carry `card_id`).
    item_id: str = Field(..., examples=["card_0091"])
    action: Literal["upvote", "downvote", "save", "dismiss"]
    reason: str | None = None


class FeedbackResponse(BaseModel):
    status: str
    item_id: str
    action: str
