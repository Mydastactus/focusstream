from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.serializers import to_feed_item
from app.models.raw_feed_item import RawFeedItem
from app.models.signal_card import SignalCard
from app.models.sprint import EmbeddingStatus, Sprint, SprintStatus
from app.models.user import User
from app.schemas.feed import FeedResponse
from app.schemas.sprint import SprintSummary

router = APIRouter(prefix="/users", tags=["users"])


def _display_status(status: SprintStatus, embedding_status: EmbeddingStatus) -> str:
    # completed and archived both surface as "completed" (frontend has no
    # 'archived' state).
    if status != SprintStatus.active:
        return "completed"
    if embedding_status == EmbeddingStatus.ready:
        return "active"
    if embedding_status == EmbeddingStatus.failed:
        return "failed"
    return "indexing"  # pending


@router.get("/{user_id}/sprints", response_model=list[SprintSummary])
async def list_user_sprints(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> list[SprintSummary]:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    # Card counts per sprint, joined in one query (no N+1).
    card_counts = (
        select(
            SignalCard.intent_sprint_id.label("sprint_id"),
            func.count().label("cnt"),
        )
        .group_by(SignalCard.intent_sprint_id)
        .subquery()
    )
    # Select a computed is_indexed flag instead of the vector column so we don't
    # pull a 1536-float embedding per sprint just to null-check it.
    stmt = (
        select(
            Sprint.id,
            Sprint.title,
            Sprint.status,
            Sprint.embedding_status,
            func.coalesce(card_counts.c.cnt, 0).label("item_count"),
        )
        .outerjoin(card_counts, card_counts.c.sprint_id == Sprint.id)
        .where(Sprint.user_id == user_id)
        .order_by(Sprint.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    return [
        SprintSummary(
            id=row.id,
            title=row.title,
            status=_display_status(row.status, row.embedding_status),
            item_count=int(row.item_count),
        )
        for row in rows
    ]


@router.get("/{user_id}/feed", response_model=FeedResponse)
async def get_aggregate_feed(
    user_id: str, db: AsyncSession = Depends(get_db)
) -> FeedResponse:
    """The "All Signal Stream" view: cards across all of the user's *active*
    sprints, deduped so an item that matched several sprints appears once (its
    highest-scoring card), ordered by score then recency."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    # DISTINCT ON (raw_item_id) keeps the best-scoring card per underlying item
    # across the user's active, non-dismissed cards.
    best_card_ids = (
        select(SignalCard.id)
        .join(Sprint, SignalCard.intent_sprint_id == Sprint.id)
        .where(Sprint.user_id == user_id)
        .where(Sprint.status == SprintStatus.active)
        .where(SignalCard.is_dismissed.is_(False))
        .order_by(SignalCard.raw_item_id, SignalCard.signal_score.desc())
        .distinct(SignalCard.raw_item_id)
        .subquery()
    )

    stmt = (
        select(SignalCard, RawFeedItem)
        .join(RawFeedItem, SignalCard.raw_item_id == RawFeedItem.id)
        .where(SignalCard.id.in_(select(best_card_ids.c.id)))
        .order_by(SignalCard.signal_score.desc(), SignalCard.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    items = [to_feed_item(card, raw) for card, raw in rows]
    # sprint_id is a sentinel here — each item carries its own intent_sprint_id.
    return FeedResponse(sprint_id="all", total_items=len(items), items=items)
