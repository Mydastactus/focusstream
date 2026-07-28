import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.serializers import to_feed_item
from app.models.raw_feed_item import RawFeedItem
from app.models.signal_card import SignalCard
from app.models.sprint import EmbeddingStatus, Sprint, SprintStatus
from app.models.user import User
from app.schemas.feed import FeedResponse
from app.schemas.sprint import (
    CreateSprintRequest,
    CreateSprintResponse,
    RetryEmbeddingResponse,
)
from app.workers.tasks import embed_sprint_intent

router = APIRouter(prefix="/sprints", tags=["sprints"])


def _sprint_id() -> str:
    return f"spr_{secrets.token_hex(4)}"


@router.post("", response_model=CreateSprintResponse, status_code=status.HTTP_201_CREATED)
async def create_sprint(
    payload: CreateSprintRequest, db: AsyncSession = Depends(get_db)
) -> CreateSprintResponse:
    user = await db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")

    now = datetime.now(timezone.utc)
    sprint = Sprint(
        id=_sprint_id(),
        user_id=payload.user_id,
        title=payload.title,
        description=payload.description,
        duration_days=payload.duration_days,
        sources_allowed=payload.sources_allowed,
        status=SprintStatus.active,
        expires_at=now + timedelta(days=payload.duration_days),
    )
    db.add(sprint)
    await db.commit()

    # Dispatch async embedding so the request path never blocks on the model.
    # The sprint is usable immediately; it becomes *matchable* once the vector lands.
    embed_sprint_intent.delay(sprint.id)

    return CreateSprintResponse(
        sprint_id=sprint.id, status="active", embedding_status="queued"
    )


@router.post("/{sprint_id}/embedding/retry", response_model=RetryEmbeddingResponse)
async def retry_embedding(
    sprint_id: str, db: AsyncSession = Depends(get_db)
) -> RetryEmbeddingResponse:
    """Re-queue embedding for a sprint whose intent vector failed to compute.
    Backs the "retry" affordance on a `failed` sprint pill."""
    sprint = await db.get(Sprint, sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail="sprint_not_found")
    if sprint.embedding_status == EmbeddingStatus.ready:
        raise HTTPException(status_code=409, detail="embedding_already_ready")

    sprint.embedding_status = EmbeddingStatus.pending
    await db.commit()
    embed_sprint_intent.delay(sprint.id)

    return RetryEmbeddingResponse(sprint_id=sprint.id, embedding_status="queued")


@router.get("/{sprint_id}/feed", response_model=FeedResponse)
async def get_feed(
    sprint_id: str, db: AsyncSession = Depends(get_db)
) -> FeedResponse:
    sprint = await db.get(Sprint, sprint_id)
    if sprint is None:
        raise HTTPException(status_code=404, detail="sprint_not_found")

    # Pure read of pre-computed cards — no embedding, no LLM in the request path.
    stmt = (
        select(SignalCard, RawFeedItem)
        .join(RawFeedItem, SignalCard.raw_item_id == RawFeedItem.id)
        .where(SignalCard.intent_sprint_id == sprint_id)
        .where(SignalCard.is_dismissed.is_(False))
        .order_by(SignalCard.signal_score.desc(), SignalCard.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    items = [to_feed_item(card, raw) for card, raw in rows]
    return FeedResponse(sprint_id=sprint_id, total_items=len(items), items=items)
